"""
A-share market data fetcher with enhanced features.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import akshare as ak
import pandas as pd

from .base import BaseDataFetcher, DataFetchError

logger = logging.getLogger(__name__)


class AStockFetcher(BaseDataFetcher):
    """
    A-share market data fetcher using akshare.
    
    Features:
    - Async support with rate limiting
    - Anti-scraping delays
    - Caching for repeated requests
    - Rich CLI output
    """
    
    MARKET_NAME = "A股"
    
    def __init__(self, output_dir=None, config=None, use_cache: bool = True):
        super().__init__(output_dir, config, use_cache)
        self._show_welcome(self.MARKET_NAME)
    
    async def get_spot_data(self, top_n: int = 100) -> pd.DataFrame:
        """Get A-share spot data sorted by trading volume."""
        cache_key = f"a_stock_spot_{top_n}_{datetime.now().strftime('%Y%m%d')}"
        
        def _fetch():
            try:
                df = ak.stock_zh_a_spot_em()
                stocks = df.nlargest(top_n, '成交额')
                
                result = stocks[['代码', '名称', '最新价', '涨跌幅', '成交额', '成交量', '振幅', '换手率']].copy()
                result['成交额(万)'] = result['成交额'] / 10000
                result['成交额(亿)'] = result['成交额'] / 100000000
                result['市场'] = self.MARKET_NAME
                
                return result
            except Exception as e:
                logger.error(f"Error fetching A-share spot data: {e}")
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
        """Get historical data for a single A-share stock.
        
        Args:
            code: Stock code (6 digits)
            start_date: Start date (YYYYMMDD) - not used for intraday
            end_date: End date (YYYYMMDD) - not used for intraday  
            period: "daily", "weekly", "monthly", or "60" for 60-minute bars
            adjust: Price adjustment type ("qfq", "hfq", "")
        """
        code = code.zfill(6)
        
        cache_key = f"a_stock_hist_{code}_{period}_{adjust}"
        
        # 预先计算日期，避免闭包问题
        _end_date = end_date or datetime.now().strftime('%Y%m%d')
        _start_date = start_date or (datetime.now() - timedelta(days=self.config.start_date_days)).strftime('%Y%m%d')
        
        def _fetch():
            try:
                if period == "60":
                    # Use intraday API for 60-minute data
                    data = ak.stock_zh_a_hist_min_em(
                        symbol=code,
                        period="60",
                        adjust=adjust,
                    )
                    # Rename columns to match daily format
                    if not data.empty:
                        data = data.rename(columns={
                            '时间': '日期',
                            '开盘': 'open',
                            '收盘': 'close',
                            '最高': 'high',
                            '最低': 'low',
                            '成交量': 'volume',
                            '成交额': 'amount',
                        })
                else:
                    # Use daily/weekly/monthly API
                    data = ak.stock_zh_a_hist(
                        symbol=code,
                        start_date=_start_date,
                        end_date=_end_date,
                        period=period,
                        adjust=adjust,
                    )
                
                if data.empty:
                    return None
                
                return data
                
            except Exception as e:
                logger.error(f"Error fetching stock {code} ({period}): {e}")
                return None
        
        return await self.fetch_with_retry(
            _fetch,
            use_cache=True,
            cache_key=cache_key,
        )
    
    async def get_stock_name(self, code: str) -> str:
        """Get stock name by code."""
        code = code.zfill(6)
        cache_key = f"a_stock_name_{code}"
        
        def _fetch():
            try:
                info = ak.stock_individual_info_em(symbol=code)
                if not info.empty:
                    return info[info['item'] == '股票简称']['value'].iloc[0]
            except Exception as e:
                logger.debug(f"Could not get name for {code}: {e}")
            return f"股票{code}"
        
        try:
            return await self.fetch_with_retry(
                _fetch,
                max_retries=1,
                use_cache=True,
                cache_key=cache_key,
            )
        except:
            return f"股票{code}"
    
    async def get_realtime_quotes(self, codes: List[str]) -> pd.DataFrame:
        """Get real-time quotes for multiple stocks."""
        codes_normalized = [c.zfill(6) for c in codes]
        
        def _fetch():
            try:
                df = ak.stock_zh_a_spot_em()
                df = df[df['代码'].isin(codes_normalized)]
                return df[['代码', '名称', '最新价', '涨跌幅', '成交额', '成交量']]
            except Exception as e:
                logger.error(f"Error fetching real-time quotes: {e}")
                return pd.DataFrame()
        
        return await self.fetch_with_retry(_fetch)
    
    async def get_industry_data(self) -> pd.DataFrame:
        """Get industry classification data."""
        cache_key = f"a_stock_industry_{datetime.now().strftime('%Y%m%d')}"
        
        def _fetch():
            try:
                df = ak.stock_board_industry_name_em()
                return df
            except Exception as e:
                logger.error(f"Error fetching industry data: {e}")
                return pd.DataFrame()
        
        return await self.fetch_with_retry(_fetch, cache_key=cache_key)
    
    async def get_concept_list(self) -> pd.DataFrame:
        """Get concept theme list."""
        cache_key = f"a_stock_concepts_{datetime.now().strftime('%Y%m%d')}"
        
        def _fetch():
            try:
                df = ak.stock_board_concept_name_em()
                return df
            except Exception as e:
                logger.error(f"Error fetching concept list: {e}")
                return pd.DataFrame()
        
        return await self.fetch_with_retry(_fetch, cache_key=cache_key)
    
    async def _fetch_single_async(
        self,
        code: str,
        name: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: str = "daily",
        skip_existing: bool = True,
    ) -> Optional[Dict]:
        """Fetch single A-share stock data with existence check."""
        code = code.zfill(6)
        
        if name is None:
            name = await self.get_stock_name(code)
        
        # Clean name for filename
        clean_name = self.clean_filename(name)
        
        # Determine file suffix based on period
        period_suffix = "daily" if period == "daily" else "60min"
        
        # Check if data already exists
        if skip_existing:
            # Try multiple possible filenames
            possible_patterns = [
                f"{code}_{clean_name}_{period_suffix}.csv",
                f"{code}_{clean_name}_{period_suffix}_smc.csv",
            ]
            
            for pattern in possible_patterns[:2]:  # Check exact matches first
                existing_file = self.output_dir / pattern
                if existing_file.exists():
                    # Verify the file has data
                    try:
                        df = pd.read_csv(existing_file)
                        min_threshold = 100 if period == "daily" else 500  # 60min needs more data
                        if not df.empty and len(df) > min_threshold:
                            logger.debug(f"Data exists for {code} ({period}), skipping fetch")
                            return {
                                'code': code,
                                'name': name,
                                'filename': str(existing_file),
                                'data_count': len(df),
                                'market': self.MARKET_NAME,
                                'period': period,
                                'skipped': True,
                            }
                    except Exception:
                        pass
        
        # For 60min, use shorter date range (akshare limitation)
        if period == "60" and start_date is None:
            # 60min data typically available for last 30-60 days
            start_date = (datetime.now() - timedelta(days=60)).strftime('%Y%m%d')
        
        data = await self.get_stock_history(code, start_date, end_date, period=period)
        
        if data is None or data.empty:
            return None
        
        filename = f"{code}_{clean_name}_{period_suffix}.csv"
        
        filepath = self.save_to_csv(data, filename)
        
        return {
            'code': code,
            'name': name,
            'filename': str(filepath),
            'data_count': len(data),
            'market': self.MARKET_NAME,
            'period': period,
            'skipped': False,
        }
    
    def get_stocks_by_sector(self, sector: str) -> pd.DataFrame:
        """Get stocks by sector/industry."""
        try:
            df = ak.stock_board_industry_cons_em(symbol=sector)
            return df
        except Exception as e:
            logger.error(f"Error getting stocks for sector {sector}: {e}")
            return pd.DataFrame()
    
    def get_concept_stocks(self, concept: str) -> pd.DataFrame:
        """Get stocks by concept theme."""
        try:
            df = ak.stock_board_concept_cons_em(symbol=concept)
            return df
        except Exception as e:
            logger.error(f"Error getting stocks for concept {concept}: {e}")
            return pd.DataFrame()
    
    async def get_north_money_flow(self) -> pd.DataFrame:
        """Get north-bound capital flow data."""
        cache_key = f"a_stock_north_{datetime.now().strftime('%Y%m%d')}"
        
        def _fetch():
            try:
                df = ak.stock_em_hsgt_north_net_flow_in_indicator()
                return df
            except Exception as e:
                logger.error(f"Error fetching north money flow: {e}")
                return pd.DataFrame()
        
        return await self.fetch_with_retry(_fetch, cache_key=cache_key)
