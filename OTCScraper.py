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
from aiohttp import ClientTimeout, ClientResponseError, ClientConnectorError
import io
from io import BytesIO
import PyPDF2
import re
import urllib.parse



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
    global ticker_data
    query = update.callback_query
    await query.answer()
    
    ticker = query.data.split('_')[-1]
    logger.debug(f"Analyzing report for ticker: {ticker}")
    
    ticker_info = ticker_data.get(ticker, {})
    latest_filing_url = ticker_info.get('profile', {}).get('latestFilingUrl', "N/A")
    previous_close_price = ticker_info.get('previous_close_price', "N/A")
    
    if latest_filing_url != "N/A" and previous_close_price != "N/A":
        if latest_filing_url and latest_filing_url != "N/A":
            latest_filing_url = get_full_filing_url(latest_filing_url)
        await query.edit_message_text(f"Fetching and analyzing the latest report for {ticker}. This may take a few moments...")
        
        try:
            await perform_analysis(update, context, ticker, latest_filing_url, previous_close_price)
        except Exception as e:
            logger.error(f"Error during analysis for {ticker}: {str(e)}", exc_info=True)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"An error occurred during the analysis for {ticker}. Please try again later."
            )
    else:
        error_message = f"Sorry, some information is missing for {ticker}. Please fetch the ticker info again using /info {ticker}"
        logger.error(error_message)
        await query.edit_message_text(error_message)

async def perform_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE, ticker: str, latest_filing_url: str, previous_close_price: str):
    logger.info(f"Starting analysis for {ticker}")
    max_retries = 5
    retry_delay = 4
    MAX_MESSAGE_LENGTH = 4000  # Leaving some room for formatting
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    for attempt in range(max_retries):
        try:
            timeout = ClientTimeout(total=120, connect=30, sock_read=60)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                logger.debug(f"Attempt {attempt + 1} to fetch content from URL: {latest_filing_url}")
                async with session.get(latest_filing_url, headers=headers) as response:
                    response.raise_for_status()
                    content = await response.read()
                    
            logger.debug(f"Fetched content for {ticker}, size: {len(content)} bytes")
            
            text = extract_text_from_pdf(io.BytesIO(content))
            
            if not text:
                raise Exception("Failed to extract text from document")
            
            logger.debug("Calling analyze_with_claude function")
            raw_analysis = await analyze_with_claude(ticker, text, previous_close_price)
            logger.debug("Received analysis from Claude")
            
            formatted_analysis = parse_claude_response(raw_analysis)
            
            if len(formatted_analysis) > MAX_MESSAGE_LENGTH:
                chunks = [formatted_analysis[i:i+MAX_MESSAGE_LENGTH] for i in range(0, len(formatted_analysis), MAX_MESSAGE_LENGTH)]
                for chunk in chunks:
                    await context.bot.send_message(chat_id=update.effective_chat.id, text=chunk, parse_mode=ParseMode.HTML)
            else:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=formatted_analysis, parse_mode=ParseMode.HTML)
            
            logger.info(f"Sent analysis for {ticker} to user")
            return
        except asyncio.TimeoutError:
            logger.warning(f"Timeout error on attempt {attempt + 1} for {ticker}")
        except ClientResponseError as e:
            logger.warning(f"HTTP error on attempt {attempt + 1} for {ticker}: {e.status} {e.message}")
        except ClientConnectorError as e:
            logger.warning(f"Connection error on attempt {attempt + 1} for {ticker}: {str(e)}")
        except Exception as e:
            logger.error(f"Error in analysis for {ticker} on attempt {attempt + 1}: {str(e)}", exc_info=True)
        
        if attempt < max_retries - 1:
            await asyncio.sleep(retry_delay * (attempt + 1))
        else:
            error_message = f"Failed to analyze the report for {ticker} after {max_retries} attempts."
            await context.bot.send_message(chat_id=update.effective_chat.id, text=error_message)

def extract_text_from_pdf(pdf_content):
    try:
        reader = PyPDF2.PdfReader(pdf_content)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        if not text.strip():
            logger.warning("Extracted text is empty")
            return None
        return text
    except Exception as e:
        logger.error(f"Error extracting text from PDF: {e}")
        return None

async def analyze_with_claude(ticker, text_content, previous_close_price):
    logger.debug(f"Starting analysis with Claude for ticker: {ticker}")
    questions = [
        "In what industry is it? (Block chain, real estate, mining, etc..)",
        "Is it a shell company? If yes, what are the plans for this shell?",
        "What is the amount of the convertible notes the company has? (in $)",
        "When are the convertible notes due? Please elaborate on each convertible note mentioned in the document, including its due date",
        "Have there been any changes to the share structure between the quarters, such as share dilution or a decrease in the number of shares?",
        "Did they settle them (the convertible notes) or do they have plans to settle or do something with it?",
        "Are there any future plans for the business?",
        "Are there any upcoming material events disclosed or hinted at in the document, such as potential acquisitions, mergers, or significant changes in the share structure?",
        "Are there any plans for reverse split in the future?",
        f"What is the ratio of total assets to market capitalization (total market cap) for the company, based on the information provided in the document? Use the previous close price of ${previous_close_price} to calculate the market cap.",
    ]
    
    prompt = f"""Analyze the following document thoroughly for {ticker}, including any tables or structured data. Then answer these questions:

{chr(10).join(f"{i+1}. {q}" for i, q in enumerate(questions))}

Document content:
{text_content[:100000]}  # Limit to first 100,000 characters to avoid token limits

Start your reply with "Here is the analysis for {ticker}:" Provide your answers in a clear, concise manner but not as you are answering a question but as if you are stating a fact. Do not include question numbers or prefixes in your responses.
"""
    
    try:
        async with AsyncAnthropic() as client:
            response = await client.messages.create(
                model="claude-3-opus-20240229",
                max_tokens=4000,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
        
        return response.content[0]['text'] if isinstance(response.content, list) and response.content and 'text' in response.content[0] else str(response.content)
    except Exception as e:
        logger.error(f"Error calling Claude API: {str(e)}", exc_info=True)
        return f"An error occurred while analyzing the report with Claude: {str(e)}"
    

def parse_claude_response(response):
    # Extract the text between [TextBlock(text=' and ', type='text')]
    match = re.search(r"\[TextBlock\(text='(.*?)', type='text'\)\]", response, re.DOTALL)
    if not match:
        return "Error: Could not parse the response"
    
    text = match.group(1)
    
    # Replace "\n\n" with a custom paragraph separator
    text = text.replace("\\n\\n", "\n\n<PARAGRAPH>\n\n")
    
    # Replace "\n" with an actual newline
    text = text.replace("\\n", "\n")
    
    # Split into paragraphs and join with double newlines
    paragraphs = text.split("<PARAGRAPH>")
    formatted_text = "\n\n".join(paragraph.strip() for paragraph in paragraphs)
    
    return formatted_text
    

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
        previous_close_price = parsed_trade.get("previousClose", "N/A")
    except requests.RequestException as e:
        logger.warning(f"No trade information available: {e}")
        parsed_trade = None
        previous_close_price = "N/A"

    try:
        # Fetch News Data
        news_response = requests.get(news_url, headers=headers)
        news_response.raise_for_status()
        news_data = news_response.json()
        latest_news = [
            {
                'title': item.get('title', 'N/A'),
                'releaseDate': datetime.fromtimestamp(item.get('releaseDate', 0) / 1000).strftime('%Y-%m-%d'),
                'id': item.get('id', 'N/A')
            }
            for item in news_data.get('records', [])[:3]
        ]
    except requests.RequestException as e:
        logger.error(f"Error fetching news: {e}")
        latest_news = []

    try:
        # Store the parsed data in the global dictionary
        ticker_data[ticker] = {
        'profile': parsed_profile,
        'trade': parsed_trade,
        'news': latest_news,
        'previous_close_price': previous_close_price  # Add this line
        }
        logger.info(f"Data stored for ticker {ticker}: {json.dumps(ticker_data[ticker], default=str)}")

    except Exception as e:
        logger.error(f"Error storing data for ticker {ticker}: {str(e)}")
        await update.message.reply_text(f"An error occurred while processing data for {ticker}. Please try again.")
        return
      # Store the previous close price in user_data
        context.user_data[f'previous_close_price_{ticker}'] = previous_close_price
        logger.debug(f"Stored previous close price for {ticker} in user_data: {previous_close_price}")
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
                InlineKeyboardButton("📄 OTC Profile", url=f"https://www.tradingview.com/chart/?symbol=OTC%3{ticker}"),
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
                news_url = f"https://www.otcmarkets.com/stock/{ticker}/news/{urllib.parse.quote(news['title'])}?id={news['id']}"
                news_content += f"• {custom_escape_html(news['releaseDate'])}: <a href='{news_url}'>{custom_escape_html(news['title'])}</a>\n"
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