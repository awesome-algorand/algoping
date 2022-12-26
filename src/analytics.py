import json
from datetime import datetime, time, timezone
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


def ellipse_address(address: str, width: int = 4) -> str:
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

    # Start of day is midnight
    start_of_day = time(0, 0, 0)

    # End of day is 23:59:59
    end_of_day = time(23, 59, 59)

    # Combine date and time to get datetime objects
    start_datetime = datetime.combine(today, start_of_day)
    end_datetime = datetime.combine(today, end_of_day)

    # Format datetime objects as strings in the desired format
    start_date_string = start_datetime.astimezone(timezone.utc).strftime("%Y-%m-%d")
    end_date_string = (
        end_datetime.astimezone(timezone.utc).strftime("%Y-%m-%d") + "T23:59:59"
    )

    return start_date_string, end_date_string


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
  algorand {
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

if not response or not response["data"]["algorand"]["blocks"]:
    print("No blocks found for this date range")
    exit()

all_proposer_balances = []
biggest_block_proposer = response["data"]["algorand"]["blocks"][0]["address"]["address"]
total_blocks = 0

for block in response["data"]["algorand"]["blocks"]:
    account_info = indexer_client.account_info(block["address"]["address"])
    all_proposer_balances.append(
        account_info["account"]["amount-without-pending-rewards"]
    )
    total_blocks += block["count"]


def to_pretty_value(value):
    return format(value // 1e6, ",")


results = {
    "biggest_proposer": get_nfds_for_address(biggest_block_proposer),
    "total_blocks": total_blocks,
    "average": to_pretty_value(sum(all_proposer_balances) / len(all_proposer_balances))
    + " ALGO",
    "max": to_pretty_value(max(all_proposer_balances)) + " ALGO",
    "min": to_pretty_value(min(all_proposer_balances)) + " ALGO",
}

message = f"🕰 In the past 24 hours #Algorand has had {results['total_blocks']} blocks. The following address {results['biggest_proposer']} proposed the most blocks. The average proposer had {results['average']}, the smallest proposer had {results['min']} and the biggest proposer had {results['max']}"

if len(message) > 280:
    message = message[:280] + "..."

tweepy_client.create_tweet(message)
print(message)
