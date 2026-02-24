"""
US stock market data fetcher using yfinance with enhanced features.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

from .base import BaseDataFetcher, DataFetchError

logger = logging.getLogger(__name__)


class USStockFetcher(BaseDataFetcher):
    """
    US stock market data fetcher using yfinance.
    
    Features:
    - Async support with rate limiting
    - Anti-scraping delays
    - Caching for repeated requests
    - Rich CLI output
    """
    
    MARKET_NAME = "美股"
    
    def __init__(self, output_dir=None, config=None, use_cache: bool = True):
        super().__init__(output_dir, config, use_cache)
        self._show_welcome(self.MARKET_NAME)
    
    async def get_spot_data(self, top_n: int = 100) -> pd.DataFrame:
        """Get US market movers data."""
        # Use major ETFs/stocks as proxy
        symbols = ['SPY', 'QQQ', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'TSLA', 'META', 'BRK-B']
        
        def _fetch():
            try:
                data = yf.download(symbols, period='1d', progress=False)
                return data
            except Exception as e:
                logger.error(f"Error fetching US spot data: {e}")
                return pd.DataFrame()
        
        return await self.fetch_with_retry(_fetch)
    
    async def get_stock_history(
        self,
        code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: str = "1y",
        interval: str = "1d",
    ) -> Optional[pd.DataFrame]:
        """Get historical data for a single US stock."""
        cache_key = f"us_stock_hist_{code}_{period}_{interval}"
        
        def _fetch():
            try:
                ticker = yf.Ticker(code)
                
                if start_date:
                    data = ticker.history(start=start_date, end=end_date, interval=interval)
                else:
                    data = ticker.history(period=period, interval=interval)
                
                if data.empty:
                    return None
                
                # Rename columns to match our format
                data = data.reset_index()
                data.columns = [col.lower().replace(' ', '_') for col in data.columns]
                
                return data
                
            except Exception as e:
                logger.error(f"Error fetching US stock {code}: {e}")
                return None
        
        return await self.fetch_with_retry(_fetch, cache_key=cache_key)
    
    async def get_stock_info(self, code: str) -> Dict:
        """Get stock information and metadata."""
        cache_key = f"us_stock_info_{code}"
        
        def _fetch():
            try:
                ticker = yf.Ticker(code)
                info = ticker.info
                return {
                    'code': code,
                    'name': info.get('longName', code),
                    'sector': info.get('sector', 'N/A'),
                    'industry': info.get('industry', 'N/A'),
                    'market_cap': info.get('marketCap', 0),
                    'pe_ratio': info.get('trailingPE', 0),
                    'dividend_yield': info.get('dividendYield', 0),
                }
            except Exception as e:
                logger.error(f"Error getting info for {code}: {e}")
                return {'code': code, 'name': code}
        
        return await self.fetch_with_retry(_fetch, max_retries=2)
    
    async def _fetch_single_async(
        self,
        code: str,
        name: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Optional[Dict]:
        """Fetch single US stock data."""
        if name is None:
            info = await self.get_stock_info(code)
            name = info.get('name', code)
        
        data = await self.get_stock_history(code, start_date, end_date)
        
        if data is None or data.empty:
            return None
        
        clean_name = self.clean_filename(name)
        filename = f"{code}_{clean_name}_daily.csv"
        
        filepath = self.save_to_csv(data, filename)
        
        return {
            'code': code,
            'name': name,
            'filename': str(filepath),
            'data_count': len(data),
            'market': self.MARKET_NAME,
        }
