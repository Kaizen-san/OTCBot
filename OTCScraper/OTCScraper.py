import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Replace with your actual Telegram bot token
TELEGRAM_TOKEN = "1746938345:AAENVpvuuGDgeHMNVVJ0q-qzFAmI2gr4SV0"

def convert_timestamp(date_str):
    if date_str == "N/A":
        return "N/A"
    try:
        # Check if the date_str is a timestamp (in milliseconds)
        if isinstance(date_str, (int, float)):
            return datetime.utcfromtimestamp(date_str / 1000).strftime('%Y-%m-%d')
        # Check if the date_str is a date string in format "M/D/YYYY"
        elif isinstance(date_str, str):
            try:
                # Try to parse the date string "M/D/YYYY"
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hello! Send me a ticker symbol to get the stock information.\nUse /info <TICKER> to get the stock info."
    )

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Get ticker symbol from the command arguments
    if context.args:
        ticker = context.args[0].upper()
    else:
        await update.message.reply_text("Please provide a ticker symbol. Usage: /info <TICKER>")
        return

    await update.message.reply_text(f"Fetching information for ticker: {ticker}")

    # Step 1: Make the first HTTP request to get the company profile
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
        logger.info("Company Profile Response: %s", parsed_profile)  # Debug log
    except requests.RequestException as e:
        await update.message.reply_text(f"Error fetching company profile: {e}")
        return

    # Step 2: Make the second HTTP request to get the previous close price
    trade_url = f"https://backend.otcmarkets.com/otcapi/stock/trade/inside/{ticker}?symbol={ticker}"
    try:
        trade_response = requests.get(trade_url, headers=headers)
        trade_response.raise_for_status()
        parsed_trade = trade_response.json()
        logger.info("Trade Response: %s", parsed_trade)  # Debug log
    except requests.RequestException as e:
        await update.message.reply_text(f"Error fetching trade information: {e}")
        return

    # Step 3: Check if both requests were successful
    if profile_response.status_code == 200 and trade_response.status_code == 200:
        # Parse the JSON responses
        parsed_profile = profile_response.json()
        parsed_trade = trade_response.json()

        # Extract relevant information from the company profile JSON
        security = parsed_profile.get("securities", [{}])[0]
        outstanding_shares = format_number(security.get("outstandingShares", "N/A"))
        outstanding_shares_date = convert_timestamp(security.get("outstandingSharesAsOfDate", "N/A"))

        held_at_dtc = format_number(security.get("dtcShares", "N/A"))
        dtc_shares_date = convert_timestamp(security.get("dtcSharesAsOfDate", "N/A"))

        public_float = format_number(security.get("publicFloat", "N/A"))
        public_float_date = convert_timestamp(security.get("publicFloatAsOfDate", "N/A"))

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
        profile_verified_date_raw = parsed_profile.get("profileVerifiedAsOfDate", "N/A")
        profile_verified_date = convert_timestamp(profile_verified_date_raw)

        latest_filing_type = parsed_profile.get("latestFilingType", "N/A")
        latest_filing_date = convert_timestamp(parsed_profile.get("latestFilingDate", "N/A"))

        # Extract the previous close price from the trade JSON
        previous_close_price = parsed_trade.get("previousClose", "N/A")

        # Format the response message
        response_message = (
            f"*Company Profile:*\n"
            f"*Phone:* {company_profile['phone']}\n"
            f"*Email:* {company_profile['email']}\n"
            f"*Address:* {company_profile['address']['address1']}, {company_profile['address']['address2']}, {company_profile['address']['city']}, {company_profile['address']['state']}, {company_profile['address']['zip']}, {company_profile['address']['country']}\n"
            f"*Website:* {company_profile['website']}\n"
            f"*Twitter:* {company_profile['twitter']}\n"
            f"*LinkedIn:* {company_profile['linkedin']}\n"
            f"*Instagram:* {company_profile['instagram']}\n\n"
            f"*Outstanding Shares:* {outstanding_shares} (As Of Date: {outstanding_shares_date})\n"
            f"*Held at DTC:* {held_at_dtc} (As Of Date: {dtc_shares_date})\n"
            f"*Public Float:* {public_float} (As Of Date: {public_float_date})\n"
            f"*Previous Close Price:* ${previous_close_price}\n\n"
            f"*Officers:*\n"
            + "\n".join([f"{officer['name']} - {officer['title']}" for officer in officers]) + "\n\n"
            f"*Profile Verified:* {'Yes' if profile_verified else 'No'}\n"
            f"*Verification Date:* {profile_verified_date}\n\n"
            f"*Latest Filing Type:* {latest_filing_type}\n"
            f"*Latest Filing Date:* {latest_filing_date}\n\n"
        )

        await update.message.reply_text(response_message, parse_mode='Markdown')
    else:
        await update.message.reply_text("Failed to retrieve data.")

def main() -> None:
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("info", info))  # Add the /info command handler

    application.run_polling()

if __name__ == "__main__":
    main()
