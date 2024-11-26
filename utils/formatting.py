from datetime import datetime

"""
Text and data formatting utilities module.
Contains helper functions for formatting numbers, dates, timestamps, and HTML content
for Telegram messages.

"""

def format_number(value):
    try:
        return "{:,}".format(int(value))
    except (ValueError, TypeError):
        return value

from datetime import datetime

def convert_timestamp(date_str):
    """Convert timestamp to datetime object for database storage"""
    if date_str == "N/A":
        return None
    try:
        if isinstance(date_str, (int, float)):
            return datetime.utcfromtimestamp(date_str / 1000)
        elif isinstance(date_str, str):
            try:
                return datetime.strptime(date_str, "%m/%d/%Y")
            except ValueError:
                return None
        else:
            return None
    except Exception:
        return None

def format_timestamp(date_str):
    """Format timestamp for display purposes"""
    if date_str == "N/A":
        return "N/A"
    try:
        if isinstance(date_str, (int, float)):
            return datetime.utcfromtimestamp(date_str / 1000).strftime('%Y-%m-%d')
        elif isinstance(date_str, str):
            try:
                return datetime.strptime(date_str, "%m/%d/%Y").strftime('%Y-%m-%d')
            except ValueError:
                return "Invalid Date"
        else:
            return "Invalid Date"
    except Exception:
        return "Invalid Date"

def custom_escape_html(text):
    if not isinstance(text, str):
        text = str(text)
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def get_full_filing_url(relative_url):
    base_url = "https://www.otcmarkets.com/"
    return f"{base_url}{relative_url}"