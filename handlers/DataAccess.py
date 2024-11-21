from typing import List, Tuple
import asyncpg
import logging

logger = logging.getLogger(__name__)

class DataAccess:
    """
    Database access layer - solely responsible for database communication.
    Handles raw database queries and returns raw data.
    """
    
    def __init__(self, connection_params: dict):
        """Initialize with database connection parameters"""
        self.pool = None
        self.connection_params = connection_params

    async def connect(self):
        """Establish database connection pool"""
        if not self.pool:
            self.pool = await asyncpg.create_pool(**self.connection_params)

    async def disconnect(self):
        """Close database connection pool"""
        if self.pool:
            await self.pool.close()

    async def add_stock_to_watchlist(self, values: dict) -> bool:
        """
        Raw database operation to insert/update a stock in watchlist
        Returns True if successful, False otherwise
        """
        try:
            async with self.pool.acquire() as conn:
                await conn.execute('''
                    INSERT INTO stock_info (
                        ticker, user_id, username, date_added, ticker_info,
                        outstanding_shares, os_as_of, held_at_dtc, held_at_dtc_as_of,
                        float_shares, float_as_of, last_close_price, profile_verified,
                        verification_date, latest_filing_type, filing_date,
                        filing_link, is_caveat_emptor, latest_news, notes
                    ) VALUES (
                        $1, $2, $3, NOW(), $4, $5, $6, $7, $8, $9, $10, $11, 
                        $12, $13, $14, $15, $16, $17, $18, $19
                    )
                ''', 
                values['ticker'], values['user_id'], values['username'], 
                values['ticker_info'], values['outstanding_shares'], 
                values['os_as_of'], values['held_at_dtc'], 
                values['held_at_dtc_as_of'], values['float_shares'], 
                values['float_as_of'], values['last_close_price'], 
                values['profile_verified'], values['verification_date'], 
                values['latest_filing_type'], values['filing_date'], 
                values['filing_link'], values['is_caveat_emptor'], 
                values['latest_news'], values['notes'])
                return True

        except Exception as e:
            logger.error(f"Database error in add_stock_to_watchlist: {e}")
            return False

    async def get_user_watchlist(self, user_id: int) -> List[Tuple[str, str]]:
        """
        Raw database operation to get user's watchlist
        Returns list of (ticker, notes) tuples
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch('''
                    SELECT ticker, notes 
                    FROM stock_info 
                    WHERE user_id = $1 
                    ORDER BY date_added DESC
                ''', user_id)
                return [(row['ticker'], row['notes']) for row in rows]

        except Exception as e:
            logger.error(f"Database error in get_user_watchlist: {e}")
            return []
