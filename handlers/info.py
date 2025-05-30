import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from api.otc_markets import get_profile_data, get_trade_data, get_news_data
from utils.formatting import format_number, format_timestamp, custom_escape_html
from models.ticker_data import TickerData
import urllib.parse
import asyncio
from telegram.error import TimedOut, NetworkError
from datetime import datetime


"""
Stock information retrieval and formatting module.
Handles fetching and formatting comprehensive stock information from various sources,
creating formatted messages with stock data, and managing interactive buttons.

"""


logger = logging.getLogger(__name__)

ticker_data = {}

async def is_valid_ticker(text: str) -> bool:
    return 3 <= len(text) <= 5 and text.isalpha()

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global ticker_data
    
    if update.message.text.startswith('/'):
        ticker = context.args[0].upper() if context.args else None
    else:
        potential_ticker = update.message.text.strip().upper()
        ticker = potential_ticker if await is_valid_ticker(potential_ticker) else None
    
    logger.debug("Received info request for ticker: %s", ticker)
    
    if not ticker:
        return

    max_retries = 3
    for attempt in range(max_retries):
        try:
            await update.message.reply_text(f"Fetching information for ticker: {ticker}")
            
            profile_data = await get_profile_data(ticker)
            trade_data = await get_trade_data(ticker)
            news_data = await get_news_data(ticker)

            logger.debug(f"Profile data: {profile_data}")
            logger.debug(f"Trade data: {trade_data}")
            logger.debug(f"News data: {news_data}")

            try:
                ticker_data = TickerData(profile_data, trade_data, news_data)
                TickerData.set(ticker, ticker_data)
                
                response_message = format_response(ticker_data, ticker)
                reply_markup = create_reply_markup(ticker)
                await update.message.reply_text(response_message, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
            except Exception as e:
                logger.error(f"Error formatting or sending response for {ticker}: {str(e)}")
                await update.message.reply_text(f"An error occurred while processing data for {ticker}. Please try again later.")

            
            break  # If successful, break out of the retry loop
        except (TimedOut, NetworkError) as e:
            if attempt < max_retries - 1:  # i.e. not on the last attempt
                logger.warning(f"Attempt {attempt + 1} failed: {str(e)}. Retrying...")
                await asyncio.sleep(1)  # Wait a bit before retrying
            else:
                logger.error(f"Failed to fetch info after {max_retries} attempts: {str(e)}")
                await update.message.reply_text("Sorry, I'm having trouble fetching the information. Please try again later.")
                return
        except Exception as e:
            logger.error(f"Error fetching data for {ticker}: {str(e)}")
            await update.message.reply_text(f"An error occurred while fetching data for {ticker}. Please try again later.")
            return

def format_response(ticker_data, ticker):
    logger.debug(f"Formatting response for {ticker}")
    logger.debug(f"Ticker data: {ticker_data.__dict__}")

    profile = ticker_data.profile_data
    trade = ticker_data.trade_data
    news = ticker_data.news_data

    security = profile.get("securities", [{}])[0]
    outstanding_shares = format_number(security.get("outstandingShares", "N/A"))
    outstanding_shares_date = format_timestamp(security.get("outstandingSharesAsOfDate", "N/A"))
    held_at_dtc = format_number(security.get("dtcShares", "N/A"))
    dtc_shares_date = format_timestamp(security.get("dtcSharesAsOfDate", "N/A"))
    public_float = format_number(security.get("publicFloat", "N/A"))
    public_float_date = format_timestamp(security.get("publicFloatAsOfDate", "N/A"))
    tier_display_name = security.get("tierDisplayName", "N/A")

    profile_verified = profile.get("isProfileVerified", False)
    profile_verified_date = format_timestamp(profile.get("profileVerifiedAsOfDate", "N/A"))

    latest_filing_type = profile.get("latestFilingType", "N/A")
    latest_filing_date = format_timestamp(profile.get("latestFilingDate", "N/A"))
    latest_filing_url = profile.get("latestFilingUrl", "N/A")
    if latest_filing_url and latest_filing_url != "N/A":
        latest_filing_url = f"https://www.otcmarkets.com/otcapi{latest_filing_url}"

    previous_close_price = trade.get("previousClose", "N/A") if trade else "N/A"

    business_desc = profile.get("businessDesc", "N/A")
    is_caveat_emptor = profile.get("isCaveatEmptor", False)

    tier_display_emoji = "🎀" if tier_display_name == "Pink Current Information" else \
                         "🔺" if tier_display_name == "Pink Limited Information" else ""

    caveat_emptor_message = "<b>☠️ Warning - Caveat Emptor: True</b>\n\n" if is_caveat_emptor else ""

    news_content = "<b>📰 Latest News:</b>\n"
    if isinstance(news, dict) and 'records' in news and news['records']:
        for news_item in news['records'][:3]:
            news_url = f"https://www.otcmarkets.com/stock/{ticker}/news/{urllib.parse.quote(news_item['title'])}?id={news_item['id']}"
            news_date = datetime.fromtimestamp(news_item['releaseDate'] / 1000).strftime('%Y-%m-%d')
            news_content += f"• {news_date}: <a href='{news_url}'>{custom_escape_html(news_item['title'])}</a>\n"
    else:
        news_content += "No recent news available.\n"


    company_profile = {
        "phone": profile.get("phone", "N/A"),
        "email": profile.get("email", "N/A"),
        "address": {
            "address1": profile.get("execAddr", {}).get("addr1", "N/A"),
            "address2": profile.get("execAddr", {}).get("addr2", "N/A"),
            "city": profile.get("execAddr", {}).get("city", "N/A"),
            "state": profile.get("execAddr", {}).get("state", "N/A"),
            "zip": profile.get("execAddr", {}).get("zip", "N/A"),
            "country": profile.get("execAddr", {}).get("country", "N/A")
        },
        "website": profile.get("website", "N/A"),
        "twitter": profile.get("twitter", "N/A"),
        "linkedin": profile.get("linkedin", "N/A"),
        "instagram": profile.get("instagram", "N/A")
    }

    officers = profile.get("officers", [])

    response_message = (
        f"<b>Company Profile for {custom_escape_html(ticker)}:</b>\n\n"
        f"{tier_display_emoji} <b>{custom_escape_html(tier_display_name)}</b>\n"
        f"{caveat_emptor_message}"
        f"<b>💼 Outstanding Shares:</b> {custom_escape_html(outstanding_shares)} (As of: {custom_escape_html(outstanding_shares_date)})\n"
        f"<b>🏦 Held at DTC:</b> {custom_escape_html(held_at_dtc)} (As of: {custom_escape_html(dtc_shares_date)})\n"
        f"<b>🌍 Public Float:</b> {custom_escape_html(public_float)} (As of: {custom_escape_html(public_float_date)})\n"
        f"<b>💵 Previous Close Price:</b> ${custom_escape_html(previous_close_price)}\n\n"
        f"<b>✅ Profile Verified:</b> {'Yes' if profile_verified else 'No'}\n"
        f"<b>🗓️ Verification Date:</b> {custom_escape_html(profile_verified_date)}\n\n"
        f"<b>📄 Latest Filing Type:</b> {custom_escape_html(latest_filing_type)}\n"
        f"<b>🗓️ Latest Filing Date:</b> {custom_escape_html(latest_filing_date)}\n"
        f"<b>📄 Latest Filing:</b> <a href='{latest_filing_url}'>View Filing</a>\n\n"
        f"{news_content}\n\n"
        f"<b>📞 Phone:</b> {custom_escape_html(profile.get('phone', 'N/A'))}\n"
        f"<b>📧 Email:</b> {custom_escape_html(profile.get('email', 'N/A'))}\n"
        f"<b>🏢 Address:</b> {custom_escape_html(profile.get('address1', 'N/A'))}, {custom_escape_html(profile.get('address2', 'N/A'))}, "
        f"{custom_escape_html(profile.get('city', 'N/A'))}, {custom_escape_html(profile.get('state', 'N/A'))}, "
        f"{custom_escape_html(profile.get('zip', 'N/A'))}, {custom_escape_html(profile.get('country', 'N/A'))}\n"
        f"<b>🌐 Website:</b> {custom_escape_html(profile.get('website', 'N/A'))}\n"
        f"<b>🐦 Twitter:</b> {custom_escape_html(profile.get('twitter', 'N/A'))}\n"
        f"<b>🔗 LinkedIn:</b> {custom_escape_html(profile.get('linkedin', 'N/A'))}\n"
        f"<b>📸 Instagram:</b> {custom_escape_html(profile.get('instagram', 'N/A'))}\n\n"
        f"<b>👥 Officers:</b>\n"
        + "\n".join([f"{custom_escape_html(officer['name'])} - {custom_escape_html(officer['title'])}" for officer in profile.get('officers', [])]) + "\n\n"
        f"<b>📝 Business Description:</b> {custom_escape_html(business_desc)}\n"
    )

    return response_message

def create_reply_markup(ticker):
    keyboard = [
        [
            InlineKeyboardButton("📈 Chart", url=f"https://www.tradingview.com/chart/?symbol=OTC:{ticker}"),
            InlineKeyboardButton("📄 OTC Profile", url=f"https://www.otcmarkets.com/stock/{ticker}/profile"),
            InlineKeyboardButton("🐦 Twitter", url=f"https://x.com/search?q=${ticker}&src=typed_query&f=live"),
        ],
        [
            InlineKeyboardButton("➕ Add to Watchlist", callback_data=f"add_watchlist_{ticker}")
        ],
        [
            InlineKeyboardButton("📊 Analyze Latest Report", callback_data=f"analyze_report_{ticker}")
        ],
        [
            InlineKeyboardButton("🐦 Get X.com Profile", callback_data=f"scrape_x_profile_{ticker}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)
