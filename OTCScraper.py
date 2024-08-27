import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes
import logging
from datetime import datetime
import os

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "DEFAULT_TOKEN_NOT_SET")
logger.debug(f"Direct TELEGRAM_TOKEN: {TELEGRAM_TOKEN}")

if TELEGRAM_TOKEN == "DEFAULT_TOKEN_NOT_SET":
    logger.error("TELEGRAM_TOKEN not found in environment variables")
    raise ValueError("No TELEGRAM_TOKEN set for Bot")

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hello! Send me a ticker symbol to get the stock information.\nUse /info <TICKER> to get the stock info."
    )

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        latest_filing_url = parsed_profile.get("latestFilingUrl", "N/A")
        if latest_filing_url and latest_filing_url != "N/A":
           latest_filing_url = get_full_filing_url(latest_filing_url)

        # Extract previous close price only if trade information is available
        previous_close_price = parsed_trade.get("previousClose", "N/A") if parsed_trade else "N/A"

        # Parse additional fields
        business_desc = parsed_profile.get("businessDesc", "N/A")
        is_caveat_emptor = parsed_profile.get("isCaveatEmptor", False)  # Default to False if not present

        keyboard = [
            [
                InlineKeyboardButton("📈 Chart", url=f"https://www.tradingview.com/symbols/{ticker}/?offer_id=10&aff_id=29379"),
                InlineKeyboardButton("📄 OTC Profile", url=f"https://www.otcmarkets.com/stock/{ticker}/security"),
                InlineKeyboardButton("🐦 Twitter", url=f"https://twitter.com/search?q=${ticker}&src=typed_query&f=live"),
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

         # Determine emoji based on Tier Display Name
        tier_display_emoji = "🎀" if tier_display_name == "Pink Current Information" else \
                             "🔺" if tier_display_name == "Pink Limited Information" else ""

        # Determine Caveat Emptor message
        caveat_emptor_message = ""
        if is_caveat_emptor:
                caveat_emptor_message = "*☠️ Warning - Caveat Emptor: True*\n\n"
                
        response_message = (
            f"*Company Profile for {ticker}:*\n\n"
            f"{tier_display_emoji} *{tier_display_name}*\n"
            f"{caveat_emptor_message}"
            f"*💼 Outstanding Shares:* {outstanding_shares} (As of: {outstanding_shares_date})\n"
            f"*🏦 Held at DTC:* {held_at_dtc} (As of: {dtc_shares_date})\n"
            f"*🌍 Public Float:* {public_float} (As of: {public_float_date})\n"
            f"*💵 Previous Close Price:* ${previous_close_price}\n\n"
            f"*✅ Profile Verified:* {'Yes' if profile_verified else 'No'}\n"
            f"*🗓️ Verification Date:* {profile_verified_date}\n\n"
            f"*📄 Latest Filing Type:* {latest_filing_type}\n"
            f"*🗓️ Latest Filing Date:* {latest_filing_date}\n"
            f"*📄 Latest Filing:* [View Filing]({latest_filing_url})\n\n"
            f"*📝 Business Description:* {business_desc}\n"
            f"*📞 Phone:* {company_profile['phone']}\n"
            f"*📧 Email:* {company_profile['email']}\n"
            f"*🏢 Address:* {company_profile['address']['address1']}, {company_profile['address']['address2']}, "
            f"{company_profile['address']['city']}, {company_profile['address']['state']}, "
            f"{company_profile['address']['zip']}, {company_profile['address']['country']}\n"
            f"*🌐 Website:* {company_profile['website']}\n"
            f"*🐦 Twitter:* {company_profile['twitter']}\n"
            f"*🔗 LinkedIn:* {company_profile['linkedin']}\n"
            f"*📸 Instagram:* {company_profile['instagram']}\n\n"
            f"*👥 Officers:*\n"
            + "\n".join([f"{officer['name']} - {officer['title']}" for officer in officers]) + "\n\n"
        )

        await update.message.reply_text(response_message, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text("Failed to retrieve data.")

def main() -> None:
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("info", info))  # Add the /info command handler

    application.run_polling()

if __name__ == "__main__":
    main()
