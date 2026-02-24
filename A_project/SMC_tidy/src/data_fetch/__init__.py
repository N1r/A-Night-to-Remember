"""
Data fetch module for SMC analysis tool.
Provides async-enabled data fetching for multiple markets with:
- Rich CLI output
- Anti-scraping measures
- Rate limiting
- Caching
"""
from .base import (
    BaseDataFetcher,
    DataFetchError,
    DataCache,
    RateLimiter,
    AntiScraping,
    detect_and_map_columns,
    convert_to_smc_format,
    batch_convert_to_smc,
)
from .a_stock import AStockFetcher
from .hk_stock import HKStockFetcher
from .us_stock import USStockFetcher

__all__ = [
    "BaseDataFetcher",
    "DataFetchError",
    "DataCache",
    "RateLimiter",
    "AntiScraping",
    "AStockFetcher",
    "HKStockFetcher",
    "USStockFetcher",
    "detect_and_map_columns",
    "convert_to_smc_format",
    "batch_convert_to_smc",
    "get_fetcher",
]


def get_fetcher(market: str, output_dir=None, config=None, use_cache: bool = True):
    """Factory function to get appropriate fetcher for market."""
    fetchers = {
        "a_stock": AStockFetcher,
        "a股": AStockFetcher,
        "hk_stock": HKStockFetcher,
        "港股": HKStockFetcher,
        "hk": HKStockFetcher,
        "us_stock": USStockFetcher,
        "美股": USStockFetcher,
        "us": USStockFetcher,
    }
    
    fetcher_class = fetchers.get(market.lower())
    if fetcher_class is None:
        raise ValueError(f"Unknown market: {market}. Available: {list(fetchers.keys())}")
    
    return fetcher_class(output_dir=output_dir, config=config, use_cache=use_cache)
