from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from api.scrapfly import scrape_tweets
from models.ticker_data import TickerData
import logging

logger = logging.getLogger(__name__)

async def scrape_x_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    ticker = query.data.split('_')[-1]
    ticker_data = TickerData.get(ticker)
    
    if not ticker_data:
        await query.edit_message_text(f"No data found for {ticker}.")
        return

    twitter_url = ticker_data.profile_data.get("twitter", "N/A")
    
    if twitter_url == "N/A":
        await query.edit_message_text(f"No Twitter URL found for {ticker}.")
        return
    
    try:
        tweets = await scrape_tweets(twitter_url)
        
        if tweets:
            username = twitter_url.split('/')[-1]
            tweet_info = f"Latest tweets from <a href='{twitter_url}'>@{username}</a> for {ticker}:\n\n"
            
            current_date = None
            tweet_count = 0
            for tweet in tweets:
                tweet_date = tweet['created_at'].split()[0]
                if tweet_date != current_date:
                    current_date = tweet_date
                    tweet_count = 0
                
                if tweet_count < 3:  # Display up to 3 tweets per day
                    tweet_url = f"{twitter_url}/status/{tweet['id']}"
                    tweet_text = tweet['text'][:150] + "..." if len(tweet['text']) > 150 else tweet['text']
                    tweet_info += (f"<b>{tweet['created_at']}</b>\n"
                                   f"<a href='{tweet_url}'>{tweet_text}</a>\n"
                                   f"🔁 {tweet['retweet_count']} | ❤️ {tweet['favorite_count']}\n\n")
                    tweet_count += 1
                
                if len(tweet_info) > 3800:  # Leave some room for potential truncation message
                    tweet_info += "More tweets available..."
                    break
            
            await query.edit_message_text(
                text=tweet_info,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True
            )
        else:
            await query.edit_message_text(f"No tweets found for {ticker} ({twitter_url}).")
    except Exception as e:
        logger.error(f"Error scraping X.com tweets: {str(e)}")
        await query.edit_message_text(f"An error occurred while fetching tweets for {ticker} ({twitter_url}).")

def format_tweets(tweets, twitter_url, ticker):
    username = twitter_url.split('/')[-1]
    tweet_info = f"Latest tweets from <a href='{twitter_url}'>@{username}</a> for {ticker}:\n\n"
    
    current_date = None
    tweet_count = 0
    for tweet in tweets:
        tweet_date = tweet['created_at'].split()[0]
        if tweet_date != current_date:
            current_date = tweet_date
            tweet_count = 0
        
        if tweet_count < 3:  # Display up to 3 tweets per day
            tweet_url = f"{twitter_url}/status/{tweet['id']}"
            tweet_text = tweet['text'][:150] + "..." if len(tweet['text']) > 150 else tweet['text']
            tweet_info += (f"<b>{tweet['created_at']}</b>\n"
                           f"<a href='{tweet_url}'>{tweet_text}</a>\n"
                           f"🔁 {tweet['retweet_count']} | ❤️ {tweet['favorite_count']}\n\n")
            tweet_count += 1
        
        if len(tweet_info) > 3800:
            tweet_info += "More tweets available..."
            break
    
    return tweet_info