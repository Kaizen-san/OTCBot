import os

"""
Configuration management module that handles environment variables and global settings.
Contains the Config class which provides centralized access to API tokens, credentials,
and other configuration values used throughout the application.

"""

class Config:
    TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "DEFAULT_TOKEN_NOT_SET")
    print(f"Config: TELEGRAM_TOKEN = {TELEGRAM_TOKEN}")
    GOOGLE_APPLICATION_CREDENTIALS = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "DEFAULT_TOKEN_NOT_SET")
    WATCHLIST_SHEET_ID = "1EWVVCYC5EbYzx3jIFhwthdTJxyNvWdz57kzX-DRwwn0"
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "DEFAULT_TOKEN_NOT_SET")
    DATABASE_URL = os.environ.get("DATABASE_URL")
    WEBHOOK_URL = os.environ.get("MAKE_WEBHOOK", "DEFAULT_TOKEN_NOT_SET")
    SCRAPFLY_API_KEY =  os.environ.get("SCRAPFLY", "DEFAULT_TOKEN_NOT_SET")
    OTC_MARKETS_BASE_URL = "https://www.otcmarkets.com/otcapi"

