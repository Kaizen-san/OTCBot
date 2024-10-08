import asyncio
import aiohttp
import logging
from telegram import Update
from telegram.ext import ContextTypes
from models.ticker_data import TickerData
from utils.pdf_utils import extract_text_from_pdf
from api.claude import analyze_with_claude
from utils.parsing import parse_claude_response

logger = logging.getLogger(__name__)

async def analyze_report_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    ticker = query.data.split('_')[-1]
    ticker_data = TickerData.get(ticker)
    
    if not ticker_data:
        await query.message.reply_text(f"Sorry, some information is missing for {ticker}. Please fetch the ticker info again.")
        return

    await query.message.reply_text(f"Fetching and analyzing the latest report for {ticker}. This may take a few moments...")
    
    try:
        await perform_analysis(query.message, context, ticker, ticker_data)
    except Exception as e:
        logger.error(f"Error during analysis for {ticker}: {str(e)}", exc_info=True)
        await query.message.reply_text(f"An error occurred during the analysis for {ticker}. Please try again later.")

async def perform_analysis(message, context: ContextTypes.DEFAULT_TYPE, ticker: str, ticker_data: TickerData):
    filing_url = ticker_data.get_latest_filing_url()
    if not filing_url or filing_url == "N/A":
        await message.reply_text(f"No latest filing URL found for {ticker}.")
        return

    base_url = "https://www.otcmarkets.com/otcapi"
    full_url = f"{base_url}{filing_url}"
    
    logger.info(f"Attempting to fetch filing for {ticker} from URL: {full_url}")

    content = await fetch_filing_content(full_url)
    logger.info(f"Successfully fetched content for {ticker}. Content size: {len(content)} bytes")
    
    text = extract_text_from_pdf(content)
    
    if not text:
        await message.reply_text(f"Unable to extract text from the filing for {ticker}. The document might be in an unsupported format.")
        return
    
    logger.info(f"Successfully extracted text for {ticker}. Text length: {len(text)} characters")
    
    analysis = await analyze_with_claude(ticker, text, ticker_data.get_previous_close_price())
    
    if not analysis:
        await message.reply_text(f"Failed to get a valid response from the analysis API for {ticker}. Please try again later.")
        return
    
    formatted_analysis = parse_claude_response(analysis)
    
    await send_analysis(message, context, formatted_analysis)

async def fetch_filing_content(filing_url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(filing_url, headers=headers) as response:
            response.raise_for_status()
            return await response.read()

async def send_analysis(message, context, formatted_analysis):
    MAX_MESSAGE_LENGTH = 4000
    if len(formatted_analysis) > MAX_MESSAGE_LENGTH:
        chunks = [formatted_analysis[i:i+MAX_MESSAGE_LENGTH] for i in range(0, len(formatted_analysis), MAX_MESSAGE_LENGTH)]
        for chunk in chunks:
            await message.reply_text(chunk, parse_mode='HTML')
    else:
        await message.reply_text(formatted_analysis, parse_mode='HTML')