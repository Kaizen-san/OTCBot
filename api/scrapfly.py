import logging
from scrapfly import ScrapeConfig, ScrapflyClient
from config import Config
from datetime import datetime
import json

logger = logging.getLogger(__name__)

SCRAPFLY = ScrapflyClient(key=Config.SCRAPFLY_API_KEY)

async def scrape_tweets(url: str) -> list:
    """
    Scrape the latest tweets from an X.com profile, ensuring multiple tweets per date are captured
    """
    result = await SCRAPFLY.async_scrape(ScrapeConfig(
        url, 
        render_js=True,
        wait_for_selector="[data-testid='tweet']"
    ))
    
    print(f"Scrapfly response status: {result.status_code}")
    
    _xhr_calls = result.scrape_result["browser_data"]["xhr_call"]
    tweet_calls = [f for f in _xhr_calls if "UserTweets" in f["url"]]
    
    print(f"Found {len(tweet_calls)} UserTweets XHR calls")
    
    all_tweets = []
    for xhr in tweet_calls:
        if not xhr["response"]:
            continue
        try:
            data = json.loads(xhr["response"]["body"])
            if 'data' in data and 'user' in data['data']:
                user_data = data['data']['user']['result']
                if 'timeline_v2' in user_data:
                    timeline = user_data['timeline_v2']['timeline']
                    if 'instructions' in timeline:
                        for instruction in timeline['instructions']:
                            if instruction['type'] == 'TimelineAddEntries':
                                entries = instruction.get('entries', [])
                                for entry in entries:
                                    if 'content' in entry and 'itemContent' in entry['content']:
                                        item_content = entry['content']['itemContent']
                                        if 'tweet_results' in item_content:
                                            tweet = item_content['tweet_results']['result']
                                            if 'legacy' in tweet:
                                                legacy = tweet['legacy']
                                                created_at = datetime.strptime(legacy.get('created_at', ''), '%a %b %d %H:%M:%S +0000 %Y')
                                                all_tweets.append({
                                                    'id': tweet.get('rest_id', ''),
                                                    'text': legacy.get('full_text', ''),
                                                    'created_at': created_at,
                                                    'retweet_count': legacy.get('retweet_count', 0),
                                                    'favorite_count': legacy.get('favorite_count', 0)
                                                })
                                                print(f"Extracted tweet from {created_at}")
        except Exception as e:
            print(f"Error processing tweet data: {str(e)}")
    
    # Sort tweets by created_at in descending order (most recent first)
    all_tweets.sort(key=lambda x: x['created_at'], reverse=True)
    
    # Convert datetime back to string for JSON serialization
    for tweet in all_tweets:
        tweet['created_at'] = tweet['created_at'].strftime('%Y-%m-%d %H:%M:%S')
    
    print(f"Extracted and sorted {len(all_tweets)} tweets")
    return all_tweets  # Return all tweets without limiting