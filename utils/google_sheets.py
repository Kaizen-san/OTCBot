import gspread
from google.oauth2.service_account import Credentials
from config import Config

"""
Google Sheets integration module.
Handles all interactions with Google Sheets API for storing and retrieving
watchlist data and other persistent storage needs.

"""

scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
creds = Credentials.from_service_account_file(Config.GOOGLE_APPLICATION_CREDENTIALS, scopes=scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(Config.WATCHLIST_SHEET_ID).sheet1

async def get_watchlist_from_sheet(user_id):
    try:
        cell_list = sheet.findall(str(user_id), in_column=2)
        watchlist = [(sheet.cell(cell.row, 1).value, sheet.cell(cell.row, 20).value) for cell in cell_list]
        return watchlist
    except Exception as e:
        logger.error(f"Error fetching watchlist: {str(e)}")
        return []

async def add_to_sheet(row_data):
    sheet.append_row(row_data)