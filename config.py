import os

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
print("Direct TELEGRAM_TOKEN:", TELEGRAM_TOKEN)

if not TELEGRAM_TOKEN:
    raise ValueError("No TELEGRAM_TOKEN set for Bot")
