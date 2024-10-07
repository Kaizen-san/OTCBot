import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from models.ticker_data import TickerData
from utils.google_sheets import add_to_sheet, get_watchlist_from_sheet
from datetime import datetime
from utils.formatting import convert_timestamp


logger = logging.getLogger(__name__)

WAITING_FOR_NOTE = 1

async def view_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    watchlist = await get_watchlist_from_sheet(user_id)
    
    if watchlist:
        watchlist_text = "Your current watchlist:\n" + "\n".join([f"${ticker} - {note}" for ticker, note in watchlist])
    else:
        watchlist_text = "Your watchlist is empty."
    
    await update.message.reply_text(watchlist_text)

async def add_to_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    ticker = query.data.split('_')[-1]
    context.user_data['current_ticker'] = ticker
    
    await query.message.reply_text(f"Adding {ticker} to your watchlist. Please enter a note about why you're adding this stock:")
    
    return WAITING_FOR_NOTE

async def save_note_and_add_to_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_note = update.message.text
    ticker = context.user_data.get('current_ticker')
    user_id = update.effective_user.id
    username = update.effective_user.username or "Unknown"
    logger.info(f"Received note for ticker {ticker}: {user_note}")

    if not ticker:
        logger.error("No ticker found in user_data")
        await update.message.reply_text("Sorry, there was an error. Please try adding the stock again.")
        return ConversationHandler.END
    
    try:
        ticker_data = TickerData.get(ticker)
        if not ticker_data:
            await update.message.reply_text(f"Error: Data not found for {ticker}. Please fetch the info again using /info {ticker}")
            return ConversationHandler.END

        # Extract required information from ticker_data
        profile = ticker_data.profile_data
        trade = ticker_data.trade_data
        security = profile.get("securities", [{}])[0]
        
        row_data = [
            ticker,
            str(user_id),
            username,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            security.get("tierDisplayName", "N/A"),
            security.get("outstandingShares", "N/A"),
            convert_timestamp(security.get("outstandingSharesAsOfDate", "N/A")),
            security.get("dtcShares", "N/A"),
            convert_timestamp(security.get("dtcSharesAsOfDate", "N/A")),
            security.get("publicFloat", "N/A"),
            convert_timestamp(security.get("publicFloatAsOfDate", "N/A")),
            trade.get("previousClose", "N/A") if trade else "N/A",
            profile.get("isProfileVerified", False),
            convert_timestamp(profile.get("profileVerifiedAsOfDate", "N/A")),
            profile.get("latestFilingType", "N/A"),
            convert_timestamp(profile.get("latestFilingDate", "N/A")),
            profile.get("latestFilingUrl", "N/A"),
            profile.get("isCaveatEmptor", False),
            "; ".join([f"{news['releaseDate']}: {news['title']}" for news in ticker_data.news_data[:3]]),
            user_note
        ]

        await add_to_sheet(row_data)
        await update.message.reply_text(f"{ticker} has been added to your watchlist with your note!")
        logger.info(f"Successfully added {ticker} to watchlist for user {user_id} with note: {user_note}")
    except Exception as e:
        logger.error(f"Error adding {ticker} to watchlist: {str(e)}", exc_info=True)
        await update.message.reply_text(f"An error occurred while adding {ticker} to the watchlist. Please try again later.")
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END