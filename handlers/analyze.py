import logging
from telegram import Update
from telegram.ext import ContextTypes
from api.claude import analyze_with_claude
from utils.pdf_utils import extract_text_from_pdf
from models.ticker_data import TickerData
import aiohttp
from utils.parsing import parse_claude_response
from telegram.constants import ParseMode
from utils.formatting import get_full_filing_url


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
    logger.info(f"Starting analysis for {ticker}")
    
    try:
        # Step 1: Fetch the latest report
        filing_url = ticker_data.get_latest_filing_url()
        logger.info(f"Fetching latest report for {ticker} from URL: {filing_url}")
        if not filing_url or filing_url == "N/A":
            raise ValueError(f"No valid filing URL found for {ticker}")
        
        full_url = get_full_filing_url(filing_url)
        logger.info(f"Full URL for {ticker}: {full_url}")
        
        pdf_content = await fetch_filing_content(full_url)
        logger.info(f"PDF content fetched for {ticker}, size: {len(pdf_content)} bytes")
        
        pdf_content = await fetch_filing_content(filing_url)
        logger.info(f"PDF content fetched for {ticker}, size: {len(pdf_content)} bytes")

        # Step 2: Extract text from the PDF
        logger.info(f"Extracting text from PDF for {ticker}")
        text = extract_text_from_pdf(pdf_content)
        if not text:
            raise ValueError(f"Failed to extract text from PDF for {ticker}")
        logger.info(f"Text extracted for {ticker}, length: {len(text)}")

        # Step 3: Send text + relevant questions to Claude
        logger.info(f"Sending text and questions to Claude for {ticker}")
        previous_close_price = ticker_data.get_previous_close_price()
        analysis = await analyze_with_claude(ticker, text, previous_close_price)
        
        # Step 4: Retrieve response from Claude
        if not analysis:
            raise ValueError(f"Failed to get analysis from Claude for {ticker}")
        logger.info(f"Received analysis from Claude for {ticker}")

        # Step 5: Post message to the channel
        logger.info(f"Formatting and sending analysis for {ticker}")
        formatted_analysis = parse_claude_response(analysis)
        await send_analysis(update, context, formatted_analysis)
        logger.info(f"Analysis sent for {ticker}")

    except ValueError as e:
        logger.error(f"Value error during analysis for {ticker}: {str(e)}")
        await update.message.reply_text(str(e))
    except aiohttp.ClientError as e:
        logger.error(f"Network error fetching content for {ticker}: {str(e)}")
        await update.message.reply_text(f"Error fetching the latest report for {ticker}. Please try again later.")
    except PyPDF2.errors.PdfReadError as e:
        logger.error(f"Error reading PDF for {ticker}: {str(e)}")
        await update.message.reply_text(f"Error reading the PDF document for {ticker}. Please try again later.")
    except Exception as e:
        logger.error(f"Unexpected error during analysis for {ticker}: {str(e)}", exc_info=True)
        await update.message.reply_text(f"An unexpected error occurred during the analysis for {ticker}. Please try again later.")

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