import tweepy


def get_tweepy(
    bearer_token: str,
    consumer_key: str,
    consumer_secret: str,
    access_token: str,
    access_token_secret: str,
):
    # Create API object
    return tweepy.Client(
        bearer_token=bearer_token,
        consumer_key=consumer_key,
        consumer_secret=consumer_secret,
        access_token=access_token,
        access_token_secret=access_token_secret,
    )
