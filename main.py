import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, filters
from config import Config
from handlers import start, info, watchlist, analyze, scrape
from utils.rate_limiter import RateLimiter
from telegram.error import TimedOut, NetworkError
from telegram.request import HTTPXRequest
import asyncio

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)

rate_limiter = RateLimiter(max_calls=30, time_frame=1)

async def post_init(application: Application) -> None:
    await start.setup_commands(application.bot)

def main() -> None:
    application = Application.builder().token(Config.TELEGRAM_TOKEN).build()

    # Create ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(watchlist.add_to_watchlist, pattern="^add_watchlist_")],
        states={
            watchlist.WAITING_FOR_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, watchlist.save_note_and_add_to_watchlist)],
        },
        fallbacks=[CommandHandler("cancel", watchlist.cancel)],
        per_message=False,
        per_chat=True
    )

    # Add handlers
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", start.start))
    application.add_handler(CommandHandler("info", info.info))
    application.add_handler(CommandHandler("wl", watchlist.view_watchlist))
    application.add_handler(CallbackQueryHandler(analyze.analyze_report_button, pattern="^analyze_report_"))
    application.add_handler(CallbackQueryHandler(scrape.scrape_x_profile, pattern="^scrape_x_profile_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, info.info))

    # Set up post-init hook
    application.post_init = post_init

    # Start the bot
    application.run_polling(poll_interval=1.0)

if __name__ == "__main__":
    main()