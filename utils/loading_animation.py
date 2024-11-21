import asyncio
from telegram import Message
from telegram.ext import ContextTypes

"""
UI feedback module.
Provides animated loading indicators for long-running operations in
Telegram messages.

"""

async def loading_animation(message: Message, text: str, context: ContextTypes.DEFAULT_TYPE):
    animation = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    i = 0
    while context.user_data.get('loading', True):
        try:
            await message.edit_text(f"{animation[i]} {text}")
            await asyncio.sleep(0.1)
            i = (i + 1) % len(animation)
        except Exception:
            await asyncio.sleep(0.1)
