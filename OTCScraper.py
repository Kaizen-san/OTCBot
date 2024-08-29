import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
import logging
from datetime import datetime
from config import Config
from telegram.error import BadRequest
from telegram.constants import ParseMode
import gspread
from google.oauth2.service_account import Credentials

# Set up loggingsss
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = Config.TELEGRAM_TOKEN
if not TELEGRAM_TOKEN:
    raise ValueError("No TELEGRAM_TOKEN set for Bot")

# Google Sheets setup
GOOGLE_APPLICATION_CREDENTIALS = Config.GOOGLE_APPLICATION_CREDENTIALS
WATCHLIST_SHEET_ID = Config.WATCHLIST_SHEET_ID

scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_file(GOOGLE_APPLICATION_CREDENTIALS, scopes=scope)
client = gspread.authorize(creds)

# Open the Google Sheet
sheet = client.open_by_key(WATCHLIST_SHEET_ID).sheet1

def get_full_filing_url(relative_url):
    base_url = "https://www.otcmarkets.com/otcapi"
    return f"{base_url}{relative_url}"

def convert_timestamp(date_str):
    if date_str == "N/A":
        return "N/A"
    try:
        if isinstance(date_str, (int, float)):
            return datetime.utcfromtimestamp(date_str / 1000).strftime('%Y-%m-%d')
        elif isinstance(date_str, str):
            try:
                return datetime.strptime(date_str, "%m/%d/%Y").strftime('%Y-%m-%d')
            except ValueError:
                logger.error("Error parsing date string: %s", date_str)
                return "Invalid Date"
        else:
            logger.error("Timestamp is not a number or a recognizable date string: %s", date_str)
            return "Invalid Date"
    except Exception as e:
        logger.error("Error converting timestamp: %s", e)
        return "Invalid Date"

def format_number(value):
    try:
        return "{:,}".format(int(value))
    except (ValueError, TypeError):
        return value

def custom_escape_html(text):
    if not isinstance(text, str):
        text = str(text)
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.debug("Received /start command")
    await update.message.reply_text(
        "Hello! Send me a ticker symbol to get the stock information.\nUse /info <TICKER> to get the stock info."
    )

async def add_to_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    ticker = query.data.split('_')[1]
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"

    try:
        # Check if the ticker is already in the watchlist
        cell = sheet.find(ticker, in_column=1)
        if cell:
            await query.edit_message_text(f"{ticker} is already in your watchlist!")
            return

        # Add the ticker to the watchlist
        sheet.append_row([ticker, str(user_id), username, datetime.now().strftime("%Y-%m-%d %H:%M:%S")])
        await query.edit_message_text(f"{ticker} has been added to your watchlist!")
    except Exception as e:
        logger.error(f"Error adding to watchlist: {e}")
        await query.edit_message_text("An error occurred while adding to the watchlist. Please try again later.")

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.debug("Received /info command with args: %s", context.args)
    
    if context.args:
        ticker = context.args[0].upper()
    else:
        await update.message.reply_text("Please provide a ticker symbol. Usage: /info <TICKER>")
        return

    await update.message.reply_text(f"Fetching information for ticker: {ticker}")

    profile_url = f"https://backend.otcmarkets.com/otcapi/company/profile/full/{ticker}?symbol={ticker}"
    headers = {
        "Host": "backend.otcmarkets.com",
        "Origin": "https://www.otcmarkets.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Referer": "https://www.otcmarkets.com/",
    }

    try:
        profile_response = requests.get(profile_url, headers=headers)
        profile_response.raise_for_status()
        parsed_profile = profile_response.json()
        logger.info("Company Profile Response: %s", parsed_profile)
    except requests.RequestException as e:
        logger.error(f"Error fetching company profile: {e}")
        await update.message.reply_text(f"Error fetching company profile: {e}")
        return

    trade_url = f"https://backend.otcmarkets.com/otcapi/stock/trade/inside/{ticker}?symbol={ticker}"
    try:
        trade_response = requests.get(trade_url, headers=headers)
        trade_response.raise_for_status()
        parsed_trade = trade_response.json()
        logger.info("Trade Response: %s", parsed_trade)
    except requests.RequestException as e:
        logger.warning(f"No trade information available: {e}")
        parsed_trade = None  # Set trade data to None if unavailable

    news_url = f"https://backend.otcmarkets.com/otcapi/company/{ticker}/dns/news?symbol={ticker}&page=1&pageSize=5&sortOn=releaseDate&sortDir=DESC"
    try:
        news_response = requests.get(news_url, headers=headers)
        news_response.raise_for_status()
        news_data = news_response.json()
        
        latest_news = []
        for item in news_data.get('records', [])[:3]:
            title = item.get('title', 'N/A')
            release_date = item.get('releaseDate', 'N/A')
            if release_date != 'N/A':
                release_date = datetime.fromtimestamp(release_date / 1000).strftime('%Y-%m-%d')
            latest_news.append({'title': title, 'releaseDate': release_date})
    except requests.RequestException as e:
        logger.error(f"Error fetching news: {e}")
        latest_news = []

    if profile_response.status_code == 200:
        parsed_profile = profile_response.json()

        security = parsed_profile.get("securities", [{}])[0]
        outstanding_shares = format_number(security.get("outstandingShares", "N/A"))
        outstanding_shares_date = convert_timestamp(security.get("outstandingSharesAsOfDate", "N/A"))

        held_at_dtc = format_number(security.get("dtcShares", "N/A"))
        dtc_shares_date = convert_timestamp(security.get("dtcSharesAsOfDate", "N/A"))

        public_float = format_number(security.get("publicFloat", "N/A"))
        public_float_date = convert_timestamp(security.get("publicFloatAsOfDate", "N/A"))
        tier_display_name = security.get("tierDisplayName", "N/A")

        company_profile = {
            "phone": parsed_profile.get("phone", "N/A"),
            "email": parsed_profile.get("email", "N/A"),
            "address": {
                "address1": parsed_profile.get("execAddr", {}).get("addr1", "N/A"),
                "address2": parsed_profile.get("execAddr", {}).get("addr2", "N/A"),
                "city": parsed_profile.get("execAddr", {}).get("city", "N/A"),
                "state": parsed_profile.get("execAddr", {}).get("state", "N/A"),
                "zip": parsed_profile.get("execAddr", {}).get("zip", "N/A"),
                "country": parsed_profile.get("execAddr", {}).get("country", "N/A")
            },
            "website": parsed_profile.get("website", "N/A"),
            "twitter": parsed_profile.get("twitter", "N/A"),
            "linkedin": parsed_profile.get("linkedin", "N/A"),
            "instagram": parsed_profile.get("instagram", "N/A")
        }

        officers = parsed_profile.get("officers", [])

        profile_verified = parsed_profile.get("isProfileVerified", False)
        profile_verified_date = convert_timestamp(parsed_profile.get("profileVerifiedAsOfDate", "N/A"))

        latest_filing_type = parsed_profile.get("latestFilingType", "N/A")
        latest_filing_date = convert_timestamp(parsed_profile.get("latestFilingDate", "N/A"))
        latest_filing_url = parsed_profile.get("latestFilingUrl", "N/A")
        if latest_filing_url and latest_filing_url != "N/A":
            latest_filing_url = get_full_filing_url(latest_filing_url)

        previous_close_price = parsed_trade.get("previousClose", "N/A") if parsed_trade else "N/A"

        business_desc = parsed_profile.get("businessDesc", "N/A")
        is_caveat_emptor = parsed_profile.get("isCaveatEmptor", False)

        keyboard = [
            [
                InlineKeyboardButton("📈 Chart", url=f"https://www.tradingview.com/symbols/{ticker}/?offer_id=10&aff_id=29379"),
                InlineKeyboardButton("📄 OTC Profile", url=f"https://www.otcmarkets.com/stock/{ticker}/security"),
                InlineKeyboardButton("🐦 Twitter", url=f"https://twitter.com/search?q=${ticker}&src=typed_query&f=live"),
            ],
            [
                InlineKeyboardButton("➕ Add to Watchlist", callback_data=f"add_watchlist_{ticker}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        tier_display_emoji = "🎀" if tier_display_name == "Pink Current Information" else \
                             "🔺" if tier_display_name == "Pink Limited Information" else ""

        caveat_emptor_message = "<b>☠️ Warning - Caveat Emptor: True</b>\n\n" if is_caveat_emptor else ""

        # Prepare news content
        news_content = "<b>📰 Latest News:</b>\n"
        if latest_news:
          for news in latest_news:
            news_content += f"• {custom_escape_html(news['releaseDate'])}: {custom_escape_html(news['title'])}\n"
        else:
         news_content += "No recent news available.\n"

        try:
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
                f"<b>📞 Phone:</b> {custom_escape_html(company_profile['phone'])}\n"
                f"<b>📧 Email:</b> {custom_escape_html(company_profile['email'])}\n"
                f"<b>🏢 Address:</b> {custom_escape_html(company_profile['address']['address1'])}, {custom_escape_html(company_profile['address']['address2'])}, "
                f"{custom_escape_html(company_profile['address']['city'])}, {custom_escape_html(company_profile['address']['state'])}, "
                f"{custom_escape_html(company_profile['address']['zip'])}, {custom_escape_html(company_profile['address']['country'])}\n"
                f"<b>🌐 Website:</b> {custom_escape_html(company_profile['website'])}\n"
                f"<b>🐦 Twitter:</b> {custom_escape_html(company_profile['twitter'])}\n"
                f"<b>🔗 LinkedIn:</b> {custom_escape_html(company_profile['linkedin'])}\n"
                f"<b>📸 Instagram:</b> {custom_escape_html(company_profile['instagram'])}\n\n"
                f"<b>👥 Officers:</b>\n"
                + "\n".join([f"{custom_escape_html(officer['name'])} - {custom_escape_html(officer['title'])}" for officer in officers]) + "\n\n"

                f"<b>📝 Business Description:</b> {custom_escape_html(business_desc)}\n"
            )

            await update.message.reply_text(response_message, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
        except BadRequest as e:
            logger.error(f"Error sending formatted message: {e}")
            # Fall back to sending without parsing
            await update.message.reply_text("Error in formatting. Here's the raw data:", parse_mode=None)
            await update.message.reply_text(str(response_message), reply_markup=reply_markup, parse_mode=None)
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            await update.message.reply_text("An unexpected error occurred. Please try again later.")
    else:
        await update.message.reply_text("Failed to retrieve data.")

def main() -> None:
    logger.debug("Starting bot")
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("info", info))
    application.add_handler(CallbackQueryHandler(add_to_watchlist, pattern="^add_watchlist_"))

    application.run_polling()

if __name__ == "__main__":
    main()
