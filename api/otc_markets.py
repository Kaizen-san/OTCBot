import aiohttp
import logging
from utils.rate_limiter import rate_limited_request

"""
OTC Markets API client module.
Handles all interactions with the OTC Markets API, including fetching company profiles,
trade data, and news. Implements rate limiting and error handling for API requests.

"""

logger = logging.getLogger(__name__)

BASE_URL = "https://backend.otcmarkets.com/otcapi"

async def get_profile_data(ticker):
    url = f"{BASE_URL}/company/profile/full/{ticker}"
    headers = {
        "Host": "backend.otcmarkets.com",
        "Origin": "https://www.otcmarkets.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Referer": "https://www.otcmarkets.com/",
    }
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            response.raise_for_status()
            return await response.json()

async def get_trade_data(ticker):
    url = f"{BASE_URL}/stock/trade/inside/{ticker}"
    return await fetch_data(url)

async def get_news_data(ticker):
    url = f"{BASE_URL}/company/{ticker}/dns/news"
    params = {
        "page": 1,
        "pageSize": 5,
        "sortOn": "releaseDate",
        "sortDir": "DESC"
    }
    try:
        return await fetch_data(url, params=params)
    except aiohttp.ContentTypeError:
        logger.warning(f"No news data available for {ticker}")
        return []  # Return an empty list instead of raising an exception

async def fetch_data(url, params=None):
    headers = {
        "Host": "backend.otcmarkets.com",
        "Origin": "https://www.otcmarkets.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.107 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
        "Referer": "https://www.otcmarkets.com/",
    }

    try:
        async with aiohttp.ClientSession() as session:
            response = await rate_limited_request(session.get, url, headers=headers, params=params)
            response.raise_for_status()
            return await response.json()
    except aiohttp.ClientError as e:
        logger.error(f"Error fetching data from {url}: {str(e)}")
        raise