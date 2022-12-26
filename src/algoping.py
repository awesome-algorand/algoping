from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from os import environ
from time import sleep

import requests

from src.utils.tweet import get_tweepy


@dataclass
class Endpoint:
    url: str
    title: str


def fetch(endpoint: Endpoint):
    try:
        page = requests.get(endpoint.url)
        return page.status_code == 200, endpoint
    except:
        # Catch HTTP errors/exceptions here
        print(f"WARNING: {endpoint.title} is down")
        return False, endpoint


def calculate_downtime(history: list, delay: int):
    # Calculate the total number of down time periods
    down_periods = history.count(False)
    # Calculate the total duration of down time in seconds
    down_duration = down_periods * delay
    # Convert down time to minutes and round to the nearest minute
    down_duration_minutes = round(down_duration / 60)
    return down_duration_minutes


tweepy_client = get_tweepy(
    bearer_token=environ.get("BEARER_TOKEN"),
    consumer_key=environ.get("CONSUMER_KEY"),
    consumer_secret=environ.get("CONSUMER_SECRET"),
    access_token=environ.get("ACCESS_TOKEN"),
    access_token_secret=environ.get("ACCESS_TOKEN_SECRET"),
)

endpoints = [
    Endpoint(
        "https://algoindexer.algoexplorerapi.io/health",
        "AlgoExplorer.io Indexer (MainNet)",
    ),
    Endpoint(
        "https://algoindexer.algoexplorerapi.io/health",
        "AlgoExplorer.io Node (MainNet)",
    ),
    Endpoint(
        "https://node.testnet.algoexplorerapi.io/health",
        "AlgoExplorer.io Node (TestNet)",
    ),
    Endpoint(
        "https://algoindexer.testnet.algoexplorerapi.io/health",
        "AlgoExplorer.io Indexer (TestNet)",
    ),
    Endpoint(
        "https://testnet-idx.algonode.cloud/health", "AlgoNode.io Indexer (TestNet)"
    ),
    Endpoint(
        "https://mainnet-idx.algonode.cloud/health", "AlgoNode.io Indexer (MainNet)"
    ),
    Endpoint("https://testnet-api.algonode.cloud/health", "AlgoNode.io Node (TestNet)"),
    Endpoint("https://mainnet-api.algonode.cloud/health", "AlgoNode.io Node (MainNet)"),
]

results = {}

pool = ThreadPoolExecutor(max_workers=len(endpoints))
duration = environ.get("DURATION_SECONDS", 30)  # seconds
delay = environ.get("LIVENESS_DELAY_SECONDS", 5)  # seconds

while duration > 0:
    for status, endpoint in pool.map(fetch, endpoints):
        if endpoint.title in results:
            results[endpoint.title].append(status)
        else:
            results[endpoint.title] = [status]

    duration -= delay
    print(f"Sleeping for {delay} seconds, total seconds left {duration}")
    sleep(delay)

for endpoint, history in results.items():
    downtime = calculate_downtime(history, delay)
    if downtime > 0:
        message = f"🚧 WARNING: {endpoint} has been down for {downtime} minutes in the past {duration / 60} minutes! 🕰"
        tweepy_client.create_tweet(message)
        print(message)
