"""
Hong Kong stock market data fetcher with enhanced features.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import akshare as ak
import pandas as pd

from .base import BaseDataFetcher, DataFetchError

logger = logging.getLogger(__name__)


class HKStockFetcher(BaseDataFetcher):
    """
    Hong Kong stock market data fetcher using akshare.
    
    Features:
    - Async support with rate limiting
    - Anti-scraping delays
    - Caching for repeated requests
    - Rich CLI output
    """
    
    MARKET_NAME = "港股"
    
    def __init__(self, output_dir=None, config=None, use_cache: bool = True):
        super().__init__(output_dir, config, use_cache)
        self._show_welcome(self.MARKET_NAME)
    
    async def get_spot_data(self, top_n: int = 100) -> pd.DataFrame:
        """Get HK stock spot data sorted by trading volume."""
        cache_key = f"hk_stock_spot_{top_n}_{datetime.now().strftime('%Y%m%d')}"
        
        def _fetch():
            try:
                df = ak.stock_hk_spot_em()
                stocks = df.nlargest(top_n, '成交额')
                
                result = stocks[['代码', '名称', '最新价', '涨跌幅', '成交额', '成交量']].copy()
                result['成交额(万港元)'] = result['成交额'] / 10000
                result['成交额(亿港元)'] = result['成交额'] / 100000000
                result['市场'] = self.MARKET_NAME
                
                return result
            except Exception as e:
                logger.error(f"Error fetching HK spot data: {e}")
                return pd.DataFrame()
        
        return await self.fetch_with_retry(
            _fetch,
            use_cache=True,
            cache_key=cache_key,
        )
    
    async def get_stock_history(
        self,
        code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: str = "daily",
        adjust: str = "qfq",
    ) -> Optional[pd.DataFrame]:
        """Get historical data for a single HK stock."""
        code = code.zfill(5)
        
        if end_date is None:
            end_date = datetime.now().strftime('%Y%m%d')
        if start_date is None:
            start_date = (datetime.now() - timedelta(days=self.config.start_date_days)).strftime('%Y%m%d')
        
        cache_key = f"hk_stock_hist_{code}_{start_date}_{end_date}_{period}"
        
        def _fetch():
            try:
                data = ak.stock_hk_hist(
                    symbol=code,
                    start_date=start_date,
                    end_date=end_date,
                    period=period,
                    adjust=adjust,
                )
                
                if data.empty:
                    return None
                
                return data
                
            except Exception as e:
                logger.error(f"Error fetching HK stock {code}: {e}")
                return None
        
        return await self.fetch_with_retry(
            _fetch,
            use_cache=True,
            cache_key=cache_key,
        )
    
    async def get_hk_main_stocks(self) -> pd.DataFrame:
        """Get main board stocks list."""
        cache_key = f"hk_main_stocks_{datetime.now().strftime('%Y%m%d')}"
        
        def _fetch():
            try:
                df = ak.stock_hk_main_board_spot_em()
                return df
            except Exception as e:
                logger.error(f"Error fetching HK main board stocks: {e}")
                return pd.DataFrame()
        
        return await self.fetch_with_retry(_fetch, cache_key=cache_key)
    
    async def get_hs_holdings(self) -> pd.DataFrame:
        """Get Hang Seng Index constituents."""
        cache_key = f"hk_hs_holdings_{datetime.now().strftime('%Y%m%d')}"
        
        def _fetch():
            try:
                df = ak.stock_hk_component_em(symbol="恒生指数")
                return df
            except Exception as e:
                logger.error(f"Error fetching HS holdings: {e}")
                return pd.DataFrame()
        
        return await self.fetch_with_retry(_fetch, cache_key=cache_key)
    
    async def _fetch_single_async(
        self,
        code: str,
        name: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        skip_existing: bool = True,
    ) -> Optional[Dict]:
        """Fetch single HK stock data with existence check."""
        code = code.zfill(5)
        
        if name is None:
            name = f"港股{code}"
        
        clean_name = self.clean_filename(name)
        
        # Check if data already exists
        if skip_existing:
            possible_patterns = [
                f"{code}_{clean_name}_daily.csv",
                f"{code}_{clean_name}_daily_smc.csv",
            ]
            
            for pattern in possible_patterns:
                existing_file = self.output_dir / pattern
                if existing_file.exists():
                    try:
                        df = pd.read_csv(existing_file)
                        if not df.empty and len(df) > 100:
                            logger.debug(f"Data exists for {code}, skipping fetch")
                            return {
                                'code': code,
                                'name': name,
                                'filename': str(existing_file),
                                'data_count': len(df),
                                'market': self.MARKET_NAME,
                                'skipped': True,
                            }
                    except Exception:
                        pass
        
        data = await self.get_stock_history(code, start_date, end_date)
        
        if data is None or data.empty:
            return None
        
        filename = f"{code}_{clean_name}_daily.csv"
        
        filepath = self.save_to_csv(data, filename)
        
        return {
            'code': code,
            'name': name,
            'filename': str(filepath),
            'data_count': len(data),
            'market': self.MARKET_NAME,
            'skipped': False,
        }
