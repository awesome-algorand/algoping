import json
from datetime import datetime, time, timedelta
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


def get_nfds_for_address(address: str) -> dict:
    url = "https://api.nf.domains"
    url += "/nfd"

    params = {"owner": address}
    try:
        response = requests.get(url, params=params)
        data = response.json()
        if len(data) > 0:
            return data[0]
        else:
            return ellipse_address(address)
    except requests.RequestException:
        # handle error
        return ellipse_address(address)


def generate_date_strings():
    # Get today's date
    today = datetime.utcnow().date()

    yesterday = today - timedelta(days=1)

    # Start of day is midnight
    start_of_day = time(0, 0, 1)

    # Combine date and time to get datetime objects
    start_datetime = datetime.combine(yesterday, start_of_day)

    # Format datetime objects as strings in the desired format
    start_date_string = start_datetime.strftime("%Y-%m-%d")
    end_date_string = start_date_string + "T23:59:59"

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
    transactions(options: {asc: "date.date"}, date: {since: $from, till: $from}) {
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

    account_info = indexer_client.account_info(cur_address)
    all_proposer_balances.append(
        account_info["account"]["amount-without-pending-rewards"]
    )
    all_blocks[cur_address] += block["count"]

total_blocks = sum(all_blocks.values())

results = {
    "biggest_proposer": get_nfds_for_address(biggest_block_proposer),
    "total_blocks": total_blocks,
    "total_txns": total_transactions,
    "average": to_pretty_value(sum(all_proposer_balances) / len(all_proposer_balances))
    + " ALGO",
    "max": to_pretty_value(max(all_proposer_balances)) + " ALGO",
    "min": to_pretty_value(min(all_proposer_balances)) + " ALGO",
}

tweet = f"🕰 On {to_pretty_date(start_date)} #Algorand has had {results['total_blocks']} blocks proposed and {results['total_txns']} transactions. The following address {results['biggest_proposer']} proposed the most blocks. Average of balances of all proposers is {results['average']}, the smallest proposer had {results['min']} and the biggest proposer had {results['max']}"

if len(tweet) > 280:
    tweet = tweet[:280] + "..."

print(tweet)
tweepy_client.create_tweet(text=str(tweet))
