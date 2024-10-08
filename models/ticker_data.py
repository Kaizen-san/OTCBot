from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class TickerData:
    _instances = {}

    def __init__(self, profile_data, trade_data, news_data):
        self.profile_data = profile_data
        self.trade_data = trade_data
        self.news_data = news_data
        self.timestamp = datetime.now()
        logger.debug(f"TickerData initialized with: {self.__dict__}")

    @classmethod
    def get(cls, ticker):
        return cls._instances.get(ticker.upper())

    @classmethod
    def set(cls, ticker, instance):
        cls._instances[ticker.upper()] = instance

    def get_latest_filing_url(self):
        url = self.profile_data.get("latestFilingUrl", "N/A")
        logger.debug(f"Latest filing URL: {url}")
        return url

    def get_previous_close_price(self):
        return self.trade_data.get("previousClose", "N/A")

    def get_twitter_url(self):
        return self.profile_data.get("twitter", "N/A")

    def is_outdated(self, max_age_minutes=30):
        age = datetime.now() - self.timestamp
        return age.total_seconds() / 60 > max_age_minutes