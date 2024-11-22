import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from models.ticker_data import TickerData
from utils.google_sheets import add_to_sheet, get_watchlist_from_sheet
from datetime import datetime
from utils.formatting import convert_timestamp, format_number
from main import db


"""
Watchlist management module.
Handles all watchlist-related functionality including adding stocks, managing notes,
and retrieving watchlist data from Google Sheets.

"""

WAITING_FOR_NOTE = 1

async def view_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler for viewing user's watchlist"""
    try:
        user_id = update.effective_user.id
        watchlist = await db.get_user_watchlist(user_id)
        
        if watchlist:
            watchlist_text = "Your current watchlist:\n\n" + "\n".join([
                f"${ticker} - {note}" for ticker, note in watchlist
            ])
        else:
            watchlist_text = "Your watchlist is empty."
        
        await update.message.reply_text(watchlist_text)
        
    except Exception as e:
        logger.error(f"Error viewing watchlist: {e}")
        await update.message.reply_text("An error occurred while fetching your watchlist. Please try again later.")

async def add_to_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for initiating watchlist addition"""
    query = update.callback_query
    await query.answer()
    
    ticker = query.data.split('_')[-1]
    context.user_data['current_ticker'] = ticker
    
    await query.message.reply_text(f"Adding {ticker} to your watchlist. Please enter a note about why you're adding this stock:")
    
    return WAITING_FOR_NOTE

async def save_note_and_add_to_watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for saving note and completing watchlist addition"""
    try:
        user_note = update.message.text
        ticker = context.user_data.get('current_ticker')
        user_id = update.effective_user.id
        username = update.effective_user.username or "Unknown"

        if not ticker:
            logger.error("No ticker found in user_data")
            await update.message.reply_text("Sorry, there was an error. Please try adding the stock again.")
            return ConversationHandler.END

        ticker_data = TickerData.get(ticker)
        if not ticker_data:
            await update.message.reply_text(f"Error: Data not found for {ticker}. Please fetch the info again using /info {ticker}")
            return ConversationHandler.END

        profile = ticker_data.profile_data
        trade = ticker_data.trade_data
        security = profile.get("securities", [{}])[0]

        # Handle news data
        news_data = ticker_data.news_data
        if isinstance(news_data, dict) and 'records' in news_data:
            news_records = news_data['records'][:3]
            news_summary = "; ".join([
                f"{news.get('displayDateTime', 'N/A')}: {news.get('title', 'N/A')}" 
                for news in news_records
            ])
        else:
            news_summary = "No recent news available"

        # Prepare values for database insertion
        values = {
            'ticker': ticker,
            'user_id': user_id,
            'username': username,
            'ticker_info': profile.get('businessDesc', 'N/A'),
            'outstanding_shares': security.get('outstandingShares', 0),
            'os_as_of': security.get('outstandingSharesAsOfDate'),
            'held_at_dtc': security.get('dtcShares', 0),
            'held_at_dtc_as_of': security.get('dtcSharesAsOfDate'),
            'float_shares': security.get('publicFloat', 0),
            'float_as_of': security.get('publicFloatAsOfDate'),
            'last_close_price': trade.get('previousClose', 0) if trade else 0,
            'profile_verified': profile.get('isProfileVerified', False),
            'verification_date': profile.get('profileVerifiedAsOfDate'),
            'latest_filing_type': profile.get('latestFilingType', 'N/A'),
            'filing_date': profile.get('latestFilingDate'),
            'filing_link': f"https://www.otcmarkets.com/otcapi{profile.get('latestFilingUrl', '')}",
            'is_caveat_emptor': profile.get('isCaveatEmptor', False),
            'latest_news': news_summary,
            'notes': user_note
        }

        success = await db.add_stock_to_watchlist(values)
        
        if success:
            await update.message.reply_text(f"{ticker} has been added to your watchlist with your note!")
            logger.info(f"Successfully added {ticker} to watchlist for user {user_id}")
        else:
            raise Exception("Failed to add to watchlist")

    except Exception as e:
        logger.error(f"Error adding {ticker} to watchlist: {e}", exc_info=True)
        await update.message.reply_text(f"An error occurred while adding {ticker} to the watchlist. Please try again later.")

    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handler for canceling the operation"""
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END