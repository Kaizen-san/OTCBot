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
from telegram.request import HTTPXRequest
import asyncio
from telegram.error import TimedOut, NetworkError
import json
import time
from anthropic import Anthropic, HUMAN_PROMPT, AI_PROMPT, AsyncAnthropic
import base64
import aiohttp


logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = Config.TELEGRAM_TOKEN
if not TELEGRAM_TOKEN:
    raise ValueError("No TELEGRAM_TOKEN set for Bot")

request = HTTPXRequest(connection_pool_size=8, read_timeout=30, write_timeout=30)
application = Application.builder().token(TELEGRAM_TOKEN).request(request).build()

# Google Sheets setup
GOOGLE_APPLICATION_CREDENTIALS = Config.GOOGLE_APPLICATION_CREDENTIALS
WATCHLIST_SHEET_ID = Config.WATCHLIST_SHEET_ID

#Claude API
anthropic = Anthropic(api_key=Config.ANTHROPIC_API_KEY)

scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_file(GOOGLE_APPLICATION_CREDENTIALS, scopes=scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(WATCHLIST_SHEET_ID).sheet1

ticker_data = {}

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
    keyboard = [
        [InlineKeyboardButton("View Watchlist", callback_data="view_watchlist")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Hello! Send me a ticker symbol to get the stock information.\n"
        "Use /info <TICKER> to get the stock info.\n"
        "Or click the button below to view your watchlist.",
        reply_markup=reply_markup
    )
async def get_watchlist(user_id):
    try:
        # Find all rows where the user_id matches
        cell_list = sheet.findall(str(user_id), in_column=2)
        watchlist = [sheet.cell(cell.row, 1).value for cell in cell_list]
        return watchlist
    except Exception as e:
        logger.error(f"Error fetching watchlist: {str(e)}")
        return []

async def view_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    watchlist = await get_watchlist(user_id)

    if watchlist:
        watchlist_text = "Your current watchlist:\n" + "\n".join([f"${ticker}" for ticker in watchlist])
    else:
        watchlist_text = "Your watchlist is empty."

    await query.edit_message_text(watchlist_text)


async def add_to_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global ticker_data
    query = update.callback_query
    await query.answer()

    ticker = query.data.split('_')[-1]  # Use the last part of the split string
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"

    logger.debug(f"Adding {ticker} to watchlist for user {user_id}")
    logger.debug(f"Current ticker_data keys: {list(ticker_data.keys())}")

    try:
        # Check if the ticker is already in the watchlist
        cell = sheet.find(ticker, in_column=1)
        if cell:
            await query.edit_message_text(f"{ticker} is already in your watchlist!")
            return

        # Fetch the parsed profile, trade, and news data from the global dictionary
        ticker_info = ticker_data.get(ticker)
        if not ticker_info:
            logger.error(f"Ticker data not found for {ticker}")
            await query.edit_message_text(f"Error: Profile data not found for {ticker}. Please fetch the info again using /info {ticker}")
            return

        parsed_profile = ticker_info['profile']
        parsed_trade = ticker_info['trade']
        latest_news = ticker_info['news']

        # Extract the required information
        security = parsed_profile.get("securities", [{}])[0]
        outstanding_shares = format_number(security.get("outstandingShares", "N/A"))
        outstanding_shares_date = convert_timestamp(security.get("outstandingSharesAsOfDate", "N/A"))
        held_at_dtc = format_number(security.get("dtcShares", "N/A"))
        dtc_shares_date = convert_timestamp(security.get("dtcSharesAsOfDate", "N/A"))
        public_float = format_number(security.get("publicFloat", "N/A"))
        public_float_date = convert_timestamp(security.get("publicFloatAsOfDate", "N/A"))
        tier_display_name = security.get("tierDisplayName", "N/A")
        profile_verified = parsed_profile.get("isProfileVerified", False)
        profile_verified_date = convert_timestamp(parsed_profile.get("profileVerifiedAsOfDate", "N/A"))
        latest_filing_type = parsed_profile.get("latestFilingType", "N/A")
        latest_filing_date = convert_timestamp(parsed_profile.get("latestFilingDate", "N/A"))
        latest_filing_url = parsed_profile.get("latestFilingUrl", "N/A")
        if latest_filing_url and latest_filing_url != "N/A":
            latest_filing_url = get_full_filing_url(latest_filing_url)
        previous_close_price = parsed_trade.get("previousClose", "N/A") if parsed_trade else "N/A"
        is_caveat_emptor = parsed_profile.get("isCaveatEmptor", False)

        # Format the latest news
        news_str = "; ".join([f"{news['releaseDate']}: {news['title']}" for news in latest_news])

        # Prepare the row data
        row_data = [
            ticker, str(user_id), username, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            tier_display_name, outstanding_shares, outstanding_shares_date, held_at_dtc, dtc_shares_date,
            public_float, public_float_date, previous_close_price, profile_verified, profile_verified_date,
            latest_filing_type, latest_filing_date, latest_filing_url, is_caveat_emptor, news_str
        ]

        # Add the data to the watchlist
        sheet.append_row(row_data)
        await query.edit_message_text(f"{ticker} has been added to your watchlist with all available information!")

        # Clear the data from the global dictionary to free up memory
        del ticker_data[ticker]
    except Exception as e:
        logger.error(f"Error adding {ticker} to watchlist: {str(e)}")
        await query.edit_message_text(f"An error occurred while adding {ticker} to the watchlist. Please try again later.")

async def analyze_report_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    ticker = query.data.split('_')[-1]
    logger.debug(f"Analyzing report for ticker: {ticker}")
    
    latest_filing_url = context.user_data.get(f'latest_filing_url_{ticker}', "N/A")
    logger.debug(f"Retrieved latest filing URL for {ticker}: {latest_filing_url}")
    
    if latest_filing_url != "N/A":
        await query.edit_message_text(f"Fetching and analyzing the latest report for {ticker}. This may take a few moments...")
        
        # Start the analysis in a separate task
        asyncio.create_task(perform_analysis(update, context, ticker, latest_filing_url))

        await query.edit_message_text(f"Analysis for {ticker} has started. You will be notified when it's complete.")
    else:
        error_message = f"Sorry, no latest filing URL available for {ticker}. Please fetch the ticker info again using /info {ticker}"
        logger.error(error_message)
        await query.edit_message_text(error_message)

async def perform_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE, ticker: str, latest_filing_url: str):
    logger.info(f"Starting analysis for {ticker}")
    try:
        # Fetch the PDF content
        logger.debug(f"Attempting to fetch PDF from URL: {latest_filing_url}")
        async with aiohttp.ClientSession() as session:
            async with session.get(latest_filing_url) as response:
                response.raise_for_status()
                pdf_content = await response.read()
        logger.debug(f"Fetched PDF content for {ticker}, size: {len(pdf_content)} bytes")
        
        # Analyze the report using Claude
        logger.debug("Calling analyze_with_claude function")
        analysis = await analyze_with_claude(ticker, pdf_content)
        logger.debug("Received analysis from Claude")
        
        # Send the analysis to the user
        await context.bot.send_message(chat_id=update.effective_chat.id, text=analysis, parse_mode=ParseMode.HTML)
        logger.info(f"Sent analysis for {ticker} to user")
    except aiohttp.ClientError as e:
        logger.error(f"Error fetching PDF for {ticker}: {str(e)}")
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"An error occurred while fetching the report for {ticker}. Please try again later."
        )
    except Exception as e:
        logger.error(f"Error analyzing report for {ticker}: {str(e)}", exc_info=True)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"An error occurred while analyzing the report for {ticker}. Please try again later."
        )

async def analyze_with_claude(ticker, pdf_content):
    logger.debug(f"Starting analysis with Claude for ticker: {ticker}")
    questions = [
        f"What is the total revenue reported for {ticker} in this quarter?",
        f"Has there been an increase or decrease in net income for {ticker} compared to the previous quarter?",
        f"What are the main factors contributing to {ticker}'s performance this quarter?",
        f"Are there any significant changes in {ticker}'s financial position?",
        f"What is {ticker}'s outlook for the next quarter?"
    ]
    
    analysis = f"Analysis of {ticker}'s Quarterly Report:\n\n"
    
    initial_prompt = f"Human: I'm sending you a PDF of the latest quarterly report for {ticker}. Please analyze this report thoroughly. I will ask you specific questions about it afterwards."
    
    try:
        logger.debug("Sending initial prompt to Claude")
        async with AsyncAnthropic() as client:
            # Initial analysis
            response = await client.messages.create(
                model="claude-3-opus-20240229",
                max_tokens=1000,
                messages=[
                    {"role": "human", "content": initial_prompt},
                    {"role": "human", "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": base64.b64encode(pdf_content).decode('utf-8')
                            }
                        }
                    ]}
                ]
            )
        logger.debug("Received initial response from Claude")
        
        # Ask each question separately
        for question in questions:
            logger.debug(f"Sending question to Claude: {question}")
            async with AsyncAnthropic() as client:
                response = await client.messages.create(
                    model="claude-3-opus-20240229",
                    max_tokens=1000,
                    messages=[
                        {"role": "human", "content": question}
                    ]
                )
            logger.debug("Received response from Claude for question")
            analysis += f"Q: {question}\nA: {response.content}\n\n"
        
        logger.debug("Completed analysis with Claude")
        return analysis
    except Exception as e:
        logger.error(f"Error calling Claude API: {str(e)}", exc_info=True)
        return f"An error occurred while analyzing the report with Claude: {str(e)}"

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global ticker_data
    ticker = context.args[0].upper() if context.args else None
    logger.debug("Received /info command with args: %s", context.args)
    
    if not ticker:
        await update.message.reply_text("Please provide a ticker symbol. Usage: /info <TICKER>")
        return

    max_retries = 3
    for attempt in range(max_retries):
        try:
            await update.message.reply_text(f"Fetching information for ticker: {ticker}")
            # Rest of your existing code...
            break  # If successful, break out of the retry loop
        except (TimedOut, NetworkError) as e:
            if attempt < max_retries - 1:  # i.e. not on the last attempt
                logger.warning(f"Attempt {attempt + 1} failed: {str(e)}. Retrying...")
                await asyncio.sleep(1)  # Wait a bit before retrying
            else:
                logger.error(f"Failed to fetch info after {max_retries} attempts: {str(e)}")
                await update.message.reply_text("Sorry, I'm having trouble fetching the information. Please try again later.")
                return

    profile_url = f"https://backend.otcmarkets.com/otcapi/company/profile/full/{ticker}?symbol={ticker}"
    trade_url = f"https://backend.otcmarkets.com/otcapi/stock/trade/inside/{ticker}?symbol={ticker}"
    news_url = f"https://backend.otcmarkets.com/otcapi/company/{ticker}/dns/news?symbol={ticker}&page=1&pageSize=5&sortOn=releaseDate&sortDir=DESC"

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
        # Fetch Profile Data
        profile_response = requests.get(profile_url, headers=headers)
        profile_response.raise_for_status()
        parsed_profile = profile_response.json()
        logger.info("Company Profile Response: %s", parsed_profile)
    except requests.RequestException as e:
        logger.error(f"Error fetching company profile: {e}")
        await update.message.reply_text(f"Error fetching company profile: {e}")
        return

    try:
        # Fetch Trade Data
        trade_response = requests.get(trade_url, headers=headers)
        trade_response.raise_for_status()
        parsed_trade = trade_response.json()
        logger.info("Trade Response: %s", parsed_trade)
    except requests.RequestException as e:
        logger.warning(f"No trade information available: {e}")
        parsed_trade = None

    try:
        # Fetch News Data
        news_response = requests.get(news_url, headers=headers)
        news_response.raise_for_status()
        news_data = news_response.json()
        latest_news = [{'title': item.get('title', 'N/A'),
                        'releaseDate': datetime.fromtimestamp(item.get('releaseDate', 0) / 1000).strftime('%Y-%m-%d')}
                       for item in news_data.get('records', [])[:3]]
    except requests.RequestException as e:
        logger.error(f"Error fetching news: {e}")
        latest_news = []

    try:
        # Store the parsed data in the global dictionary
        ticker_data[ticker] = {
            'profile': parsed_profile,
            'trade': parsed_trade,
            'news': latest_news
        }
        logger.info(f"Data stored for ticker {ticker}: {json.dumps(ticker_data[ticker], default=str)}")
    except Exception as e:
        logger.error(f"Error storing data for ticker {ticker}: {str(e)}")
        await update.message.reply_text(f"An error occurred while processing data for {ticker}. Please try again.")
        return
   
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
        logger.debug(f"Raw latest filing URL for {ticker}: {latest_filing_url}")
        if latest_filing_url and latest_filing_url != "N/A":
            latest_filing_url = get_full_filing_url(latest_filing_url)
            logger.debug(f"Full latest filing URL for {ticker}: {latest_filing_url}")

         # Store the latest filing URL in user_data
        context.user_data[f'latest_filing_url_{ticker}'] = latest_filing_url
        logger.debug(f"Stored latest filing URL for {ticker} in user_data: {latest_filing_url}")

        previous_close_price = parsed_trade.get("previousClose", "N/A") if parsed_trade else "N/A"

        business_desc = parsed_profile.get("businessDesc", "N/A")
        is_caveat_emptor = parsed_profile.get("isCaveatEmptor", False)

        keyboard = [
            [
                InlineKeyboardButton("📈 Chart", url=f"https://www.tradingview.com/symbols/{ticker}/?offer_id=10&aff_id=29379"),
                InlineKeyboardButton("📄 OTC Profile", url=f"https://www.otcmarkets.com/stock/{ticker}/security"),
                InlineKeyboardButton("🐦 Twitter", url=f"https://x.com/search?q=${ticker}&src=typed_query&f=live"),
            ],
            [
                InlineKeyboardButton("➕ Add to Watchlist", callback_data=f"add_watchlist_{ticker}")
            ],
            [
                InlineKeyboardButton("📊 Analyze Latest Report", callback_data=f"analyze_report_{ticker}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        logger.debug(f"Sending response for ticker {ticker} with callback data: add_watchlist_{ticker}")
        

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

class RateLimiter:
    def __init__(self, max_calls, time_frame):
        self.max_calls = max_calls
        self.time_frame = time_frame
        self.calls = []

    def try_acquire(self):
        now = time.time()
        self.calls = [call for call in self.calls if now - call < self.time_frame]
        if len(self.calls) < self.max_calls:
            self.calls.append(now)
            return True
        return False

rate_limiter = RateLimiter(max_calls=30, time_frame=1)  # 30 calls per second

async def rate_limited_request(method, *args, **kwargs):
    while not rate_limiter.try_acquire():
        await asyncio.sleep(0.1)
    return await method(*args, **kwargs)

def main() -> None:

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("info", info))
    application.add_handler(CallbackQueryHandler(add_to_watchlist, pattern="^add_watchlist_"))
    application.add_handler(CallbackQueryHandler(view_watchlist, pattern="^view_watchlist$"))
    application.add_handler(CallbackQueryHandler(analyze_report_button, pattern="^analyze_report_"))


    application.run_polling(poll_interval=1.0)  # Increase polling interval

if __name__ == "__main__":
    main()
