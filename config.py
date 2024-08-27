import os

class Config:
    TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "DEFAULT_TOKEN_NOT_SET")
    print(f"Config: TELEGRAM_TOKEN = {TELEGRAM_TOKEN}")
