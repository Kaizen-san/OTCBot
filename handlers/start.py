from telegram import Update, BotCommand
from telegram.ext import ContextTypes

"""
Bot initialization and command setup module.
Handles the initial bot setup, welcome messages, and configuration of available
commands in the Telegram bot interface.

"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hello! Use the menu button to access available commands or simply type any ticker symbol to get information."
    )

async def setup_commands(bot):
    commands = [
        BotCommand("info", "Get stock information (usage: /info <TICKER>)"),
        BotCommand("wl", "View your watchlist"),
        BotCommand("premium", "Manage premium status and subscription"),
    ]
    await bot.set_my_commands(commands)