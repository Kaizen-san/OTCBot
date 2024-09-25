import logging
import aiohttp
from telegram import Update
from telegram.ext import ContextTypes
from config import Config

logger = logging.getLogger(__name__)

async def send_to_webhook(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    ticker = query.data.split('_')[-1]
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(Config.WEBHOOK_URL, json={"ticker": ticker}) as response:
                if response.status == 200:
                    await query.edit_message_text(f"Successfully sent {ticker} to webhook.")
                else:
                    await query.edit_message_text(f"Failed to send {ticker} to webhook. Status code: {response.status}")
        except Exception as e:
            logger.error(f"Error sending to webhook: {str(e)}")
            await query.edit_message_text(f"An error occurred while sending {ticker} to webhook.")