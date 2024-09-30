import logging
from telegram import Update
from telegram.ext import ContextTypes
from api.claude import analyze_with_claude
from utils.pdf_utils import extract_text_from_pdf
from models.ticker_data import TickerData
import aiohttp
from utils.parsing import parse_claude_response
from telegram.constants import ParseMode


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
        await perform_analysis(update, context, ticker, ticker_data)
    except Exception as e:
        logger.error(f"Error during analysis for {ticker}: {str(e)}", exc_info=True)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"An error occurred during the analysis for {ticker}. Please try again later."
        )

async def perform_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE, ticker: str, ticker_data: TickerData):
    filing_url = ticker_data.get_latest_filing_url()
    content = await fetch_filing_content(filing_url)
    text = extract_text_from_pdf(content)
    
    if not text:
        raise Exception("Failed to extract text from document")
    
    analysis = await analyze_with_claude(ticker, text, ticker_data.get_previous_close_price())
    
    if not analysis:
        raise Exception("Failed to get a valid response from Claude API")
    
    formatted_analysis = parse_claude_response(analysis)
    
    await send_analysis(update, context, formatted_analysis)

async def fetch_filing_content(filing_url):
    async with aiohttp.ClientSession() as session:
        async with session.get(filing_url) as response:
            response.raise_for_status()
            return await response.read()

async def send_analysis(update, context, formatted_analysis):
    MAX_MESSAGE_LENGTH = 4000
    if len(formatted_analysis) > MAX_MESSAGE_LENGTH:
        chunks = [formatted_analysis[i:i+MAX_MESSAGE_LENGTH] for i in range(0, len(formatted_analysis), MAX_MESSAGE_LENGTH)]
        for chunk in chunks:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=chunk, parse_mode='HTML')
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=formatted_analysis, parse_mode='HTML')