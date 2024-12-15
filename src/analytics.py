import json
from datetime import datetime, time, timedelta, timezone
from os import environ

import requests
from algosdk.v2client.indexer import IndexerClient

from src.utils.tweet import get_tweepy

tweepy_client = get_tweepy(
    bearer_token=environ.get("BEARER_TOKEN"),
    consumer_key=environ.get("CONSUMER_KEY"),
    consumer_secret=environ.get("CONSUMER_SECRET"),
    access_token=environ.get("ACCESS_TOKEN"),
    access_token_secret=environ.get("ACCESS_TOKEN_SECRET"),
)


def to_pretty_value(value, from_algo=True):
    resp = (
        format(float(value) // 1e6 if from_algo else float(value), ",")
        .rstrip("0")
        .rstrip(".")
    )

    if resp == "0":
        return "~0.1"

    return resp


def ellipse_address(address: str, width: int = 3) -> str:
    return f"{address[:width]}...{address[-width:]}"


def get_nfd_for_address(address: str) -> str:
    url = "https://api.nf.domains/nfd/lookup"
    params = {"address": address, "view": "tiny", "allowUnverified": "true"}
    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        if address in data and data[address] and "name" in data[address]:
            return data[address]["name"]
    return ellipse_address(address)


def generate_date_strings():
    # Get today's date
    today = datetime.now(timezone.utc).date()

    # Yesterday's date
    yesterday = today - timedelta(days=1)

    # Start of yesterday (midnight)
    start_datetime = datetime.combine(yesterday, time.min, tzinfo=timezone.utc)

    # End of yesterday (today's midnight - 1 second)
    end_datetime = datetime.combine(today, time.min, tzinfo=timezone.utc) - timedelta(
        seconds=1
    )

    # Format datetime objects as strings in the desired format
    start_date_string = start_datetime.strftime("%Y-%m-%d")
    end_date_string = end_datetime.strftime("%Y-%m-%dT%H:%M:%S")

    return start_date_string, end_date_string


def to_pretty_date(date_string: str) -> str:
    # Parse the input date string as a datetime object
    date = datetime.strptime(date_string, "%Y-%m-%d").date()

    # Get the name of the month and the day of the month
    month_name = date.strftime("%b")
    day_of_month = date.strftime("%d")

    # Add a suffix to the day of the month (e.g. "st" for 1, "nd" for 2, etc.)
    if day_of_month.endswith("1"):
        suffix = "st"
    elif day_of_month.endswith("2"):
        suffix = "nd"
    elif day_of_month.endswith("3"):
        suffix = "rd"
    else:
        suffix = "th"

    # Return the formatted string
    return f"{month_name} {day_of_month}{suffix}"


# Test the function
start_date, end_date = generate_date_strings()

indexer_client = IndexerClient(
    "",
    "https://mainnet-idx.algonode.cloud",
    headers={"User-Agent": "algosdk"},
)

url = "https://graphql.bitquery.io"
query = """
query ($limit: Int!, $offset: Int!, $from: ISO8601DateTime, $till: ISO8601DateTime) {
  algorand(network: algorand) {
    blocks(
      options: {desc: "count", asc: "address.address", limit: $limit, offset: $offset}
      date: {since: $from, till: $till}
    ) {
      address: proposer {
        address
        annotation
      }
      count
      min_date: minimum(of: date)
      max_date: maximum(of: date)
    }
    transactions(options: {asc: "date.date"}, date: {since: $from, till: $till}) {
      date: date {
        date
      }
      count: countBigInt
      fee
    }
  }
}
"""

variables = {
    "limit": 1000,
    "offset": 0,
    "from": start_date,
    "till": end_date,
    "dateFormat": "%Y-%m-%d",
}


payload = json.dumps(
    {
        "query": query,
        "variables": variables,
    }
)

headers = {
    "Content-Type": "application/json",
    "X-API-KEY": environ.get("BITQUERY_API_KEY"),
}

response = requests.request("POST", url, headers=headers, data=payload).json()

if (
    not response
    or not response["data"]["algorand"]["blocks"]
    or not response["data"]["algorand"]["transactions"]
):
    print("No blocks found for this date range")
    exit()

all_proposer_balances = []
biggest_block_proposer = response["data"]["algorand"]["blocks"][0]["address"]["address"]
all_blocks = {}
total_transactions = to_pretty_value(
    response["data"]["algorand"]["transactions"][0]["count"], False
)

for block in response["data"]["algorand"]["blocks"]:
    cur_address = block["address"]["address"]

    if cur_address not in all_blocks:
        all_blocks[cur_address] = 0

    try:
        account_info = indexer_client.account_info(cur_address)
        all_proposer_balances.append(
            account_info["account"]["amount-without-pending-rewards"]
        )
    except Exception as e:
        print(f"Error fetching account info for {cur_address}: {e}")
        continue

    all_blocks[cur_address] += block["count"]

total_blocks = sum(all_blocks.values())

results = {
    "biggest_proposer": get_nfd_for_address(biggest_block_proposer),
    "total_blocks": total_blocks,
    "total_txns": total_transactions,
    "average": to_pretty_value(sum(all_proposer_balances) / len(all_proposer_balances))
    + " ALGO",
    "max": to_pretty_value(max(all_proposer_balances)) + " #ALGO",
    "min": to_pretty_value(min(all_proposer_balances)) + " ALGO",
}

tweet = f"🕰 {to_pretty_date(start_date)}: #Algorand had {results['total_blocks']} blocks, {results['total_txns']} txns. Top proposer: {results['biggest_proposer']}. Avg proposer balance: {results['average']}. Smallest: {results['min']}, largest: {results['max']}"  # noqa: E501"

if len(tweet) > 280:
    tweet = tweet[:280] + "..."

print(tweet)
try:
    tweepy_client.create_tweet(text=str(tweet))
except Exception as e:
    print("Error tweeting: ", e)

## Send notiboy notification to algoping channel

algoping_app_id = environ.get("NOTIBOY_APP_ID")

url = f"https://app.notiboy.com/api/v1/chains/algorand/channels/{algoping_app_id}/notifications/private"

payload = {
    "receivers": [],
    "message": tweet,
    "link": "https://twitter.com/AlgoPing",
    "type": "public",
}

headers = {
    "X-USER-ADDRESS": environ.get("NOTIBOY_USER_ADDRESS"),
    "Authorization": f"Bearer {environ.get('NOTIBOY_API_KEY')}",
}

try:
    requests.request(
        "POST", url, headers=headers, data=json.dumps(payload, indent=4), verify=False
    )
except Exception as e:
    print("Error sending notiboy notification: ", e)
