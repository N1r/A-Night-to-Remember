"""
Enhanced base data fetcher with Rich CLI, anti-scraping, and caching.
"""
import asyncio
import hashlib
import json
import logging
import random
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Callable
import functools

import pandas as pd
from rich.console import Console
from rich.progress import (
    Progress, SpinnerColumn, TextColumn, BarColumn, 
    TaskProgressColumn, TimeElapsedColumn, MofNCompleteColumn
)
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint
from rich.live import Live

from ..config import get_config, DataConfig

logger = logging.getLogger(__name__)
console = Console()

# Try to import diskcache for caching
try:
    from diskcache import Cache
    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False


class DataFetchError(Exception):
    """Custom exception for data fetching errors."""
    def __init__(self, message: str, code: str = None, retry_count: int = 0):
        super().__init__(message)
        self.code = code
        self.retry_count = retry_count


class RateLimiter:
    """Token bucket rate limiter for API requests."""
    
    def __init__(self, rate: float = 2.0, capacity: int = 10):
        """
        Args:
            rate: Tokens added per second (requests/second)
            capacity: Maximum tokens in bucket
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.monotonic()
        self._lock = asyncio.Lock()
    
    async def acquire(self, tokens: int = 1) -> bool:
        """Acquire tokens, waiting if necessary."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.tokens = min(
                self.capacity,
                self.tokens + elapsed * self.rate
            )
            self.last_update = now
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            
            # Calculate wait time
            wait_time = (tokens - self.tokens) / self.rate
            await asyncio.sleep(wait_time)
            self.tokens = 0
            self.last_update = time.monotonic()
            return True


class AntiScraping:
    """Anti-scraping utilities for avoiding detection."""
    
    # Common user agents
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    ]
    
    @classmethod
    def get_random_user_agent(cls) -> str:
        """Get a random user agent."""
        return random.choice(cls.USER_AGENTS)
    
    @classmethod
    def get_random_delay(cls, min_delay: float = 0.5, max_delay: float = 2.0) -> float:
        """Get a random delay with jitter."""
        base = random.uniform(min_delay, max_delay)
        # Add exponential jitter
        jitter = random.uniform(0, base * 0.3)
        return base + jitter
    
    @classmethod
    async def human_like_delay(cls, base: float = 1.0):
        """Sleep with human-like random delay."""
        delay = cls.get_random_delay(base * 0.5, base * 1.5)
        await asyncio.sleep(delay)


class DataCache:
    """Simple file-based cache for API responses."""
    
    def __init__(self, cache_dir: Optional[Path] = None, ttl: int = 3600):
        """
        Args:
            cache_dir: Directory for cache files
            ttl: Time to live in seconds (default 1 hour)
        """
        self.cache_dir = cache_dir or Path.home() / ".smc_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl
        
        # Try to use diskcache if available
        self._cache = None
        if CACHE_AVAILABLE:
            try:
                self._cache = Cache(str(self.cache_dir))
            except Exception:
                pass
    
    def _get_cache_key(self, key: str) -> str:
        """Generate cache key hash."""
        return hashlib.md5(key.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached data."""
        cache_key = self._get_cache_key(key)
        
        if self._cache:
            try:
                val = self._cache.get(cache_key)
                if val is None:
                    return None
                # 恢复 DataFrame
                if isinstance(val, dict) and val.get("__type__") == "dataframe":
                    return pd.DataFrame(val["data"])
                # 损坏的缓存（str 格式的 DataFrame）直接丢弃
                if isinstance(val, str) and ("DataFrame" in val or "  " in val[:50]):
                    self._cache.delete(cache_key)
                    return None
                return val
            except Exception:
                pass
        
        # Fallback to file cache
        cache_file = self.cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            try:
                mtime = cache_file.stat().st_mtime
                if time.time() - mtime < self.ttl:
                    with open(cache_file, 'r') as f:
                        val = json.load(f)
                    if isinstance(val, dict) and val.get("__type__") == "dataframe":
                        return pd.DataFrame(val["data"])
                    return val
            except Exception:
                pass
        return None
    
    def set(self, key: str, value: Any) -> None:
        """Set cached data."""
        cache_key = self._get_cache_key(key)
        
        # DataFrame 需要特殊处理，转为 dict 存储
        if isinstance(value, pd.DataFrame):
            value = {"__type__": "dataframe", "data": value.to_dict(orient="list")}
        
        if self._cache:
            try:
                self._cache.set(cache_key, value, expire=self.ttl)
                return
            except Exception:
                pass
        
        # Fallback to file cache
        cache_file = self.cache_dir / f"{cache_key}.json"
        try:
            with open(cache_file, 'w') as f:
                json.dump(value, f, default=str)
        except Exception:
            pass
    
    def clear(self) -> None:
        """Clear all cached data."""
        if self._cache:
            try:
                self._cache.clear()
            except Exception:
                pass


class BaseDataFetcher(ABC):
    """Enhanced abstract base class with Rich CLI, anti-scraping, and caching."""
    
    def __init__(
        self,
        output_dir: Optional[Path] = None,
        config: Optional[DataConfig] = None,
        use_cache: bool = True,
    ):
        self.config = config or get_config().data
        # Ensure output_dir is a Path object
        if output_dir is None:
            output_dir = get_config().raw_data_dir
        self.output_dir = Path(output_dir) if not isinstance(output_dir, Path) else output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize components
        self._session = None
        self._rate_limiter = RateLimiter(
            rate=1.0 / self.config.batch_delay if self.config.batch_delay > 0 else 2.0,
            capacity=self.config.concurrent_requests,
        )
        self._cache = DataCache() if use_cache else None
        self._anti_scraping = AntiScraping()
        
        # Statistics
        self._stats = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'cache_hits': 0,
            'cache_misses': 0,
        }
    
    def _show_welcome(self, market: str = "Stock"):
        """Display welcome message with Rich (简洁版)."""
        console.print(f"[bold cyan]SMC Data Fetcher[/bold cyan] - {market}")
    
    def _show_results_table(self, results: List[Dict], title: str = "Fetch Results"):
        """Display results in a Rich table (简化版，不打印详细列表)."""
        if not results:
            return
        
        # 只打印汇总，不打印详细表格
        total = len(results)
        success = sum(1 for r in results if r.get('data_count', 0) > 0)
        console.print(f"[green]✓[/green] 成功: {success}/{total}")
    
    @abstractmethod
    async def get_spot_data(self, top_n: int = 100) -> pd.DataFrame:
        """Get spot market data asynchronously."""
        pass
    
    @abstractmethod
    async def get_stock_history(
        self,
        code: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: str = "daily",
        adjust: str = "qfq",
    ) -> Optional[pd.DataFrame]:
        """Get historical data for a single stock asynchronously."""
        pass
    
    def clean_filename(self, name: str) -> str:
        """Clean filename by removing invalid characters."""
        invalid_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
        for char in invalid_chars:
            name = name.replace(char, '_')
        return name.strip()
    
    def get_default_date_range(self) -> Tuple[str, str]:
        """Get default date range based on config."""
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=self.config.start_date_days)).strftime('%Y%m%d')
        return start_date, end_date
    
    def save_to_csv(
        self,
        df: pd.DataFrame,
        filename: str,
        encoding: str = "utf-8-sig"
    ) -> Path:
        """Save DataFrame to CSV file."""
        filepath = self.output_dir / filename
        df.to_csv(filepath, index=False, encoding=encoding)
        logger.debug(f"Data saved to {filepath}")
        return filepath
    
    async def fetch_with_retry(
        self,
        fetch_func: Callable,
        *args,
        max_retries: Optional[int] = None,
        retry_delay: Optional[float] = None,
        use_cache: bool = True,
        cache_key: Optional[str] = None,
        **kwargs
    ) -> Any:
        """Execute fetch function with retry, rate limiting, and caching.
        
        Supports both sync and async functions.
        """
        import asyncio
        import inspect
        
        max_retries = max_retries or self.config.max_retries
        retry_delay = retry_delay or self.config.retry_delay
        
        # Check cache first
        if use_cache and self._cache and cache_key:
            cached = self._cache.get(cache_key)
            if cached is not None:
                self._stats['cache_hits'] += 1
                logger.debug(f"Cache hit: {cache_key}")
                return cached
            self._stats['cache_misses'] += 1
        
        # Apply rate limiting
        await self._rate_limiter.acquire()
        
        # Check if fetch_func is async
        is_async = inspect.iscoroutinefunction(fetch_func)
        
        last_error = None
        self._stats['total_requests'] += 1
        
        for attempt in range(max_retries):
            try:
                # Add anti-scraping delay
                if attempt > 0:
                    await self._anti_scraping.human_like_delay(retry_delay * (attempt + 1))
                
                # Call function appropriately based on type
                if is_async:
                    result = await fetch_func(*args, **kwargs)
                else:
                    # Run sync function in thread pool
                    result = await asyncio.to_thread(fetch_func, *args, **kwargs)
                
                self._stats['successful_requests'] += 1
                
                # Cache successful result
                if use_cache and self._cache and cache_key:
                    self._cache.set(cache_key, result)
                
                return result
                
            except Exception as e:
                last_error = e
                self._stats['failed_requests'] += 1
                error_msg = str(e)[:50]
                logger.warning(f"Attempt {attempt + 1}/{max_retries} failed: {error_msg}")
                
                if attempt < max_retries - 1:
                    # Exponential backoff with jitter
                    wait_time = retry_delay * (2 ** attempt) + random.uniform(0, 1)
                    await asyncio.sleep(wait_time)
        
        raise DataFetchError(
            f"All retries failed: {last_error}",
            retry_count=max_retries
        )
    
    async def batch_fetch_async(
        self,
        codes: List[str],
        names: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        period: str = "daily",
        show_progress: bool = True,
    ) -> List[Dict]:
        """
        Batch fetch data with Rich progress display.
        
        Features:
        - Concurrent requests with semaphore
        - Rate limiting
        - Anti-scraping delays
        - Rich progress bar (clean output)
        - Support for different periods (daily, 60min, etc.)
        """
        semaphore = asyncio.Semaphore(self.config.concurrent_requests)
        results = []
        errors = []
        
        async def fetch_one(code: str, name: Optional[str], task_id):
            async with semaphore:
                try:
                    # Apply rate limiting
                    await self._rate_limiter.acquire()
                    
                    # Add anti-scraping delay
                    await self._anti_scraping.human_like_delay(self.config.batch_delay)
                    
                    result = await self._fetch_single_async(
                        code, name, start_date, end_date, period=period
                    )
                    return result, None
                except Exception as e:
                    return None, (code, str(e)[:100])
        
        period_label = "60分钟" if period == "60" else "日线"
        
        if show_progress:
            # Rich progress bar - 简洁版本，不打印每行
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                MofNCompleteColumn(),
                TaskProgressColumn(),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                task = progress.add_task(
                    f"[cyan]获取{period_label}数据...",
                    total=len(codes)
                )
                
                # Create all tasks
                tasks = []
                for i, code in enumerate(codes):
                    name = names[i] if names else None
                    tasks.append(fetch_one(code, name, task))
                
                # Execute with progress updates
                for coro in asyncio.as_completed(tasks):
                    result, error = await coro
                    progress.advance(task)
                    
                    if result:
                        results.append(result)
                        # 只在进度条描述中更新，不打印额外行
                        if result.get('skipped'):
                            progress.update(task, description=f"[cyan]获取{period_label}数据... (跳过已有)")
                    elif error:
                        code, err_msg = error
                        errors.append(error)
                        # 只在进度条描述中显示错误计数
                        progress.update(task, description=f"[cyan]获取{period_label}数据... (失败: {len(errors)})")
        else:
            # Without progress bar
            tasks = [
                fetch_one(code, names[i] if names else None, i)
                for i, code in enumerate(codes)
            ]
            for coro in asyncio.as_completed(tasks):
                result, error = await coro
                if result:
                    results.append(result)
                elif error:
                    errors.append(error)
        
        # Display summary
        self._show_fetch_summary(len(codes), len(results), len(errors), errors)
        
        return results
    
    def _show_fetch_summary(self, total: int, success: int, failed: int, errors: List = None):
        """Display fetch summary with error details."""
        if failed > 0:
            console.print(f"[yellow]⚠ 失败: {failed}[/yellow]")
            if errors:
                # 按错误信息去重，显示前5种不同的错误
                unique_errors = {}
                for code, msg in errors:
                    key = msg[:80]
                    if key not in unique_errors:
                        unique_errors[key] = []
                    unique_errors[key].append(code)
                for msg, codes in list(unique_errors.items())[:5]:
                    codes_str = ", ".join(codes[:5])
                    if len(codes) > 5:
                        codes_str += f" ...等{len(codes)}只"
                    console.print(f"  [red]{codes_str}[/red]: {msg}")
        console.print(f"[green]✓ 成功: {success}/{total}[/green]")
    
    @abstractmethod
    async def _fetch_single_async(
        self,
        code: str,
        name: Optional[str],
        start_date: Optional[str],
        end_date: Optional[str],
    ) -> Optional[Dict]:
        """Fetch single stock data asynchronously."""
        pass
    
    def _fetch_single(self, code: str, *args, **kwargs) -> Optional[Dict]:
        """Synchronous wrapper for single stock fetch."""
        return asyncio.run(self._fetch_single_async(code, *args, **kwargs))
    
    def get_stats(self) -> Dict[str, int]:
        """Get fetcher statistics."""
        return self._stats.copy()


def detect_and_map_columns(columns: List[str]) -> Optional[Dict[str, str]]:
    """Detect and map data columns to SMC standard format."""
    column_mapping = {}
    
    # Time column detection
    time_patterns = ['时间', 'datetime', 'time', '日期', 'date', 'timestamp']
    for pattern in time_patterns:
        matching_cols = [col for col in columns if pattern.lower() in col.lower()]
        if matching_cols:
            column_mapping['time'] = matching_cols[0]
            break
    
    # Price column detection
    price_mappings = {
        'open': ['开盘', 'open', '开盘价', '开'],
        'high': ['最高', 'high', '最高价', '高'],
        'low': ['最低', 'low', '最低价', '低'],
        'close': ['收盘', 'close', '收盘价', '收'],
    }
    
    for smc_col, patterns in price_mappings.items():
        for pattern in patterns:
            matching_cols = [col for col in columns if pattern.lower() in col.lower()]
            if matching_cols:
                column_mapping[smc_col] = matching_cols[0]
                break
    
    # Volume column detection
    volume_patterns = ['成交额', 'volume', '量', 'amount']
    for pattern in volume_patterns:
        matching_cols = [col for col in columns if pattern.lower() in col.lower()]
        if matching_cols:
            column_mapping['volume'] = matching_cols[0]
            break
    
    # Check all required columns are found
    required_keys = ['time', 'open', 'high', 'low', 'close', 'volume']
    if all(key in column_mapping for key in required_keys):
        logger.debug(f"Column mapping: {column_mapping}")
        return column_mapping
    
    missing = [key for key in required_keys if key not in column_mapping]
    logger.warning(f"Missing required columns: {missing}")
    return None


def convert_to_smc_format(
    input_file: Path,
    output_file: Optional[Path] = None,
) -> Tuple[bool, Optional[pd.DataFrame]]:
    """Convert CSV file to SMC standard format."""
    try:
        df = pd.read_csv(input_file, encoding='utf-8-sig')
        
        if df.empty:
            logger.warning(f"Empty file: {input_file}")
            return False, None
        
        column_mapping = detect_and_map_columns(df.columns.tolist())
        if not column_mapping:
            logger.error(f"Cannot recognize format: {input_file}")
            return False, None
        
        smc_df = pd.DataFrame()
        
        # Time column
        time_col = column_mapping['time']
        smc_df['timestamp'] = pd.to_datetime(df[time_col])
        
        # Price columns
        for col in ['open', 'high', 'low', 'close']:
            smc_df[col] = pd.to_numeric(df[column_mapping[col]], errors='coerce')
        
        # Volume column
        volume_col = column_mapping['volume']
        smc_df['volume'] = pd.to_numeric(df[volume_col], errors='coerce')
        
        # Clean data
        smc_df = smc_df.dropna()
        smc_df = smc_df.sort_values('timestamp').reset_index(drop=True)
        
        # Generate output path
        if output_file is None:
            output_file = input_file.parent / f"{input_file.stem}_smc.csv"
        
        smc_df.to_csv(output_file, index=False, date_format='%Y-%m-%d %H:%M:%S')
        logger.debug(f"Converted: {input_file.name} -> {output_file.name}")
        
        return True, smc_df
        
    except Exception as e:
        logger.error(f"Error converting {input_file}: {e}")
        return False, None


def batch_convert_to_smc(
    input_dir: Path,
    output_dir: Optional[Path] = None,
    pattern: str = "*.csv",
) -> Dict[str, Any]:
    """Batch convert CSV files to SMC format with Rich progress."""
    if output_dir is None:
        output_dir = get_config().processed_data_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    
    csv_files = [f for f in input_dir.glob(pattern) if "_smc" not in f.stem]
    
    if not csv_files:
        console.print(f"[yellow]No CSV files found in {input_dir}[/yellow]")
        return {"success": 0, "failed": 0, "files": []}
    
    results = {"success": 0, "failed": 0, "files": []}
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]转换文件...", total=len(csv_files))
        
        for csv_file in csv_files:
            output_file = output_dir / f"{csv_file.stem}_smc.csv"
            success, df = convert_to_smc_format(csv_file, output_file)
            
            if success:
                results["success"] += 1
                results["files"].append({
                    "input": str(csv_file),
                    "output": str(output_file),
                    "rows": len(df) if df is not None else 0,
                })
            else:
                results["failed"] += 1
                progress.update(task, description=f"[cyan]转换文件... (失败: {results['failed']})")
            
            progress.advance(task)
    
    # Summary (简洁)
    console.print(f"[green]✓ 转换完成: {results['success']}/{len(csv_files)}[/green]")
    
    return results
