"""
SMC Analysis - Data Validation
===============================

Comprehensive data validation for stock data and configuration.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Union
import re

import numpy as np
import pandas as pd

from .exceptions import DataValidationError, ConfigurationError

logger = logging.getLogger(__name__)


# Required columns for different data types
REQUIRED_COLUMNS = {
    "stock_ohlcv": ["open", "high", "low", "close", "volume"],
    "stock_extended": ["open", "high", "low", "close", "volume", "amount"],
    "smc_format": ["open", "high", "low", "close", "volume", "date"],
}

# Minimum data points for different analysis types
MIN_DATA_POINTS = {
    "daily": 100,        # At least 100 trading days
    "60min": 500,        # At least 500 60-minute bars (~3 months)
    "weekly": 50,        # At least 50 weeks
}

# Maximum data staleness
MAX_DATA_AGE_DAYS = {
    "daily": 7,          # Daily data should not be older than 7 days
    "60min": 1,          # 60min data should not be older than 1 day
}


@dataclass
class ValidationResult:
    """Result of data validation."""
    is_valid: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_error(self, error: str) -> None:
        """Add an error message."""
        self.errors.append(error)
        self.is_valid = False
    
    def add_warning(self, warning: str) -> None:
        """Add a warning message."""
        self.warnings.append(warning)
    
    def merge(self, other: "ValidationResult") -> None:
        """Merge another validation result into this one."""
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        self.metadata.update(other.metadata)
        if other.errors:
            self.is_valid = False
    
    def __str__(self) -> str:
        status = "✓ VALID" if self.is_valid else "✗ INVALID"
        parts = [status]
        if self.errors:
            parts.append(f"Errors: {len(self.errors)}")
        if self.warnings:
            parts.append(f"Warnings: {len(self.warnings)}")
        return " | ".join(parts)


class DataValidator:
    """Comprehensive data validator for stock data."""
    
    def __init__(
        self,
        strict_mode: bool = False,
        auto_fix: bool = True,
        log_level: int = logging.INFO,
    ):
        """
        Initialize data validator.
        
        Args:
            strict_mode: If True, warnings become errors
            auto_fix: If True, attempt to fix common issues
            log_level: Logging level
        """
        self.strict_mode = strict_mode
        self.auto_fix = auto_fix
        self.log_level = log_level
    
    def validate_dataframe(
        self,
        df: pd.DataFrame,
        data_type: str = "stock_ohlcv",
        timeframe: str = "daily",
        symbol: str = "UNKNOWN",
    ) -> ValidationResult:
        """
        Validate a stock DataFrame.
        
        Args:
            df: DataFrame to validate
            data_type: Type of data (stock_ohlcv, stock_extended, smc_format)
            timeframe: Timeframe (daily, 60min, weekly)
            symbol: Stock symbol for error messages
            
        Returns:
            ValidationResult with validation status and details
        """
        result = ValidationResult(is_valid=True)
        
        # Check if DataFrame is empty
        if df is None or (hasattr(df, 'empty') and df.empty):
            result.add_error(f"DataFrame is empty for {symbol}")
            return result
        
        # Check required columns
        required_cols = REQUIRED_COLUMNS.get(data_type, REQUIRED_COLUMNS["stock_ohlcv"])
        missing_cols = [col for col in required_cols if col.lower() not in [c.lower() for c in df.columns]]
        
        if missing_cols:
            # Try to find similar column names
            for missing in missing_cols:
                found = False
                for col in df.columns:
                    if missing.lower() in col.lower() or col.lower() in missing.lower():
                        if self.auto_fix:
                            df.rename(columns={col: missing}, inplace=True)
                            logger.log(self.log_level, f"Renamed column '{col}' to '{missing}' for {symbol}")
                            found = True
                            break
                if not found:
                    result.add_error(f"Missing required column '{missing}' for {symbol}")
        
        # Check minimum data points
        min_points = MIN_DATA_POINTS.get(timeframe, 100)
        if len(df) < min_points:
            result.add_warning(
                f"Insufficient data for {symbol}: {len(df)} rows (need {min_points})"
            )
            if self.strict_mode:
                result.add_error(f"Insufficient data for reliable analysis")
        
        # Validate OHLCV data quality
        if all(col.lower() in [c.lower() for c in df.columns] for col in ["open", "high", "low", "close"]):
            self._validate_ohlcv_quality(df, result, symbol)
        
        # Check for data freshness
        self._check_data_freshness(df, result, timeframe, symbol)
        
        # Check for gaps in data
        self._check_data_gaps(df, result, timeframe, symbol)
        
        return result
    
    def _validate_ohlcv_quality(
        self,
        df: pd.DataFrame,
        result: ValidationResult,
        symbol: str,
    ) -> None:
        """Validate OHLCV data quality."""
        # Normalize column names
        df_cols = {col.lower(): col for col in df.columns}
        
        for col in ["open", "high", "low", "close"]:
            if col not in df_cols:
                continue
            series = df[df_cols[col]]
            
            # Check for NaN values
            nan_count = series.isna().sum()
            if nan_count > 0:
                nan_pct = nan_count / len(series) * 100
                if nan_pct > 5:
                    result.add_error(f"Too many NaN values in {col} for {symbol}: {nan_pct:.1f}%")
                else:
                    result.add_warning(f"NaN values in {col} for {symbol}: {nan_count}")
            
            # Check for negative values (except volume can be 0)
            if col != "volume":
                neg_count = (series < 0).sum()
                if neg_count > 0:
                    result.add_error(f"Negative values in {col} for {symbol}: {neg_count}")
            
            # Check for extreme values (potential data errors)
            if col in ["open", "high", "low", "close"]:
                mean_val = series.mean()
                std_val = series.std()
                if std_val > 0:
                    z_scores = np.abs((series - mean_val) / std_val)
                    extreme_count = (z_scores > 5).sum()
                    if extreme_count > 0:
                        result.add_warning(f"Extreme values in {col} for {symbol}: {extreme_count}")
        
        # Check OHLC consistency: high >= max(open, close), low <= min(open, close)
        if all(c in df_cols for c in ["open", "high", "low", "close"]):
            high_violations = (df[df_cols["high"]] < df[[df_cols["open"], df_cols["close"]]].max(axis=1)).sum()
            low_violations = (df[df_cols["low"]] > df[[df_cols["open"], df_cols["close"]]].min(axis=1)).sum()
            
            if high_violations > 0:
                result.add_warning(f"High < max(open,close) in {high_violations} rows for {symbol}")
            if low_violations > 0:
                result.add_warning(f"Low > min(open,close) in {low_violations} rows for {symbol}")
    
    def _check_data_freshness(
        self,
        df: pd.DataFrame,
        result: ValidationResult,
        timeframe: str,
        symbol: str,
    ) -> None:
        """Check if data is fresh enough."""
        # Find date column
        date_col = None
        for col in df.columns:
            if col.lower() in ["date", "日期", "datetime", "时间", "time"]:
                date_col = col
                break
        
        if date_col is None:
            result.add_warning(f"No date column found for {symbol}, cannot check freshness")
            return
        
        try:
            dates = pd.to_datetime(df[date_col], errors='coerce')
            latest_date = dates.max()
            
            if pd.isna(latest_date):
                result.add_warning(f"Could not parse dates for {symbol}")
                return
            
            max_age = MAX_DATA_AGE_DAYS.get(timeframe, 7)
            age = (datetime.now() - latest_date.to_pydatetime()).days
            
            if age > max_age:
                result.add_warning(f"Data is {age} days old for {symbol} (max: {max_age})")
        except Exception as e:
            result.add_warning(f"Error checking data freshness for {symbol}: {e}")
    
    def _check_data_gaps(
        self,
        df: pd.DataFrame,
        result: ValidationResult,
        timeframe: str,
        symbol: str,
    ) -> None:
        """Check for gaps in data."""
        date_col = None
        for col in df.columns:
            if col.lower() in ["date", "日期", "datetime", "时间", "time"]:
                date_col = col
                break
        
        if date_col is None:
            return
        
        try:
            dates = pd.to_datetime(df[date_col], errors='coerce')
            dates = dates.dropna().sort_values()
            
            if len(dates) < 2:
                return
            
            # Calculate expected frequency
            if timeframe == "daily":
                expected_gap = timedelta(days=1)
                max_gap = timedelta(days=7)  # Allow up to 1 week gap
            elif timeframe == "60min":
                expected_gap = timedelta(hours=1)
                max_gap = timedelta(days=3)  # Allow up to 3 days gap
            else:
                expected_gap = timedelta(days=7)
                max_gap = timedelta(days=14)
            
            # Count significant gaps
            gaps = dates.diff()
            large_gaps = (gaps > max_gap).sum()
            
            if large_gaps > 0:
                result.add_warning(f"Found {large_gaps} significant data gaps for {symbol}")
                
        except Exception as e:
            logger.debug(f"Error checking data gaps for {symbol}: {e}")


def validate_dataframe(
    df: pd.DataFrame,
    data_type: str = "stock_ohlcv",
    timeframe: str = "daily",
    symbol: str = "UNKNOWN",
    raise_on_error: bool = False,
) -> ValidationResult:
    """
    Convenience function to validate a DataFrame.
    
    Args:
        df: DataFrame to validate
        data_type: Type of data
        timeframe: Timeframe
        symbol: Stock symbol
        raise_on_error: If True, raise exception on validation failure
        
    Returns:
        ValidationResult
    """
    validator = DataValidator()
    result = validator.validate_dataframe(df, data_type, timeframe, symbol)
    
    if raise_on_error and not result.is_valid:
        raise DataValidationError(
            f"Data validation failed for {symbol}",
            validation_errors=result.errors,
        )
    
    return result


def validate_stock_data(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str = "daily",
    min_rows: Optional[int] = None,
) -> Tuple[bool, pd.DataFrame, List[str]]:
    """
    Validate and clean stock data.
    
    Args:
        df: DataFrame to validate
        symbol: Stock symbol
        timeframe: Timeframe
        min_rows: Minimum required rows (default: auto based on timeframe)
        
    Returns:
        Tuple of (is_valid, cleaned_df, issues)
    """
    issues = []
    
    if df is None or df.empty:
        return False, df, ["DataFrame is empty"]
    
    # Make a copy to avoid modifying original
    df = df.copy()
    
    # Set minimum rows
    if min_rows is None:
        min_rows = MIN_DATA_POINTS.get(timeframe, 100)
    
    # Clean column names
    df.columns = [c.lower().strip() for c in df.columns]
    
    # Handle common column name variations
    column_mapping = {
        "日期": "date",
        "时间": "date",
        "开盘": "open",
        "收盘": "close",
        "最高": "high",
        "最低": "low",
        "成交量": "volume",
        "成交额": "amount",
        "振幅": "amplitude",
        "换手率": "turnover",
    }
    
    for old_name, new_name in column_mapping.items():
        if old_name in df.columns and new_name not in df.columns:
            df.rename(columns={old_name: new_name}, inplace=True)
    
    # Check required columns
    required = ["open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    
    if missing:
        issues.append(f"Missing columns: {missing}")
        return False, df, issues
    
    # Remove rows with NaN in critical columns
    initial_len = len(df)
    df = df.dropna(subset=required)
    if len(df) < initial_len:
        issues.append(f"Removed {initial_len - len(df)} rows with NaN values")
    
    # Remove rows with negative prices
    price_cols = ["open", "high", "low", "close"]
    initial_len = len(df)
    for col in price_cols:
        df = df[df[col] > 0]
    if len(df) < initial_len:
        issues.append(f"Removed {initial_len - len(df)} rows with invalid prices")
    
    # Fix OHLC consistency if needed
    df["high"] = df[["high", "open", "close"]].max(axis=1)
    df["low"] = df[["low", "open", "close"]].min(axis=1)
    
    # Check minimum rows
    if len(df) < min_rows:
        issues.append(f"Insufficient data: {len(df)} rows (need {min_rows})")
        return False, df, issues
    
    return True, df, issues


def validate_config(config_dict: Dict[str, Any], schema: Optional[Dict] = None) -> ValidationResult:
    """
    Validate configuration dictionary.
    
    Args:
        config_dict: Configuration dictionary to validate
        schema: Optional validation schema
        
    Returns:
        ValidationResult
    """
    result = ValidationResult(is_valid=True)
    
    # Basic validation
    if not isinstance(config_dict, dict):
        result.add_error("Configuration must be a dictionary")
        return result
    
    # Validate SMC analysis config
    if "smc_analysis" in config_dict:
        smc = config_dict["smc_analysis"]
        if not isinstance(smc, dict):
            result.add_error("smc_analysis must be a dictionary")
        else:
            if "swing_length" in smc:
                if not isinstance(smc["swing_length"], int) or smc["swing_length"] < 1:
                    result.add_error("smc_analysis.swing_length must be a positive integer")
    
    # Validate data fetch config
    if "data_fetch" in config_dict:
        data = config_dict["data_fetch"]
        if not isinstance(data, dict):
            result.add_error("data_fetch must be a dictionary")
        else:
            if "concurrent_requests" in data:
                if not isinstance(data["concurrent_requests"], int) or data["concurrent_requests"] < 1:
                    result.add_error("data_fetch.concurrent_requests must be a positive integer")
            if "batch_delay" in data:
                if not isinstance(data["batch_delay"], (int, float)) or data["batch_delay"] < 0:
                    result.add_error("data_fetch.batch_delay must be a non-negative number")
    
    return result


def validate_stock_code(code: str, market: str = "a_stock") -> Tuple[bool, str, str]:
    """
    Validate and normalize stock code.
    
    Args:
        code: Stock code to validate
        market: Market type (a_stock, hk_stock, us_stock)
        
    Returns:
        Tuple of (is_valid, normalized_code, error_message)
    """
    if not code:
        return False, "", "Stock code is empty"
    
    # Remove whitespace
    code = str(code).strip()
    
    if market == "a_stock":
        # A股: 6位数字
        if not re.match(r"^\d{6}$", code):
            # Try to normalize
            if re.match(r"^\d{1,5}$", code):
                code = code.zfill(6)
            else:
                return False, code, f"Invalid A-share code format: {code}"
    
    elif market == "hk_stock":
        # 港股: 5位数字，通常以0开头
        if not re.match(r"^\d{5}$", code):
            if re.match(r"^\d{1,4}$", code):
                code = code.zfill(5)
            else:
                return False, code, f"Invalid HK stock code format: {code}"
    
    elif market == "us_stock":
        # 美股: 字母组合
        if not re.match(r"^[A-Z]{1,5}$", code, re.IGNORECASE):
            return False, code, f"Invalid US stock code format: {code}"
        code = code.upper()
    
    return True, code, ""
