"""
SMC Analysis Test Suite
=======================

Unit tests and integration tests.
"""
import pytest
import asyncio
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.validation import DataValidator, validate_stock_data, validate_dataframe
from src.utils.exceptions import DataValidationError, DataFetchError
from src.utils.monitoring import PerformanceMonitor, HealthChecker
from src.smc_analysis import SMCAnalyzer, EnhancedSMCStrategy


class TestDataValidator:
    """Test data validation functionality."""
    
    @pytest.fixture
    def validator(self):
        return DataValidator()
    
    @pytest.fixture
    def sample_df(self):
        """Create sample stock data."""
        dates = pd.date_range(start='2024-01-01', periods=200, freq='D')
        data = {
            'date': dates,
            'open': np.random.uniform(10, 20, 200),
            'high': np.random.uniform(20, 25, 200),
            'low': np.random.uniform(8, 10, 200),
            'close': np.random.uniform(12, 18, 200),
            'volume': np.random.randint(100000, 1000000, 200),
        }
        df = pd.DataFrame(data)
        # Ensure OHLC consistency
        df['high'] = df[['high', 'open', 'close']].max(axis=1)
        df['low'] = df[['low', 'open', 'close']].min(axis=1)
        return df
    
    def test_validate_valid_dataframe(self, validator, sample_df):
        """Test validation of valid DataFrame."""
        result = validator.validate_dataframe(sample_df, symbol="TEST")
        assert result.is_valid
        assert len(result.errors) == 0
    
    def test_validate_empty_dataframe(self, validator):
        """Test validation of empty DataFrame."""
        result = validator.validate_dataframe(pd.DataFrame(), symbol="TEST")
        assert not result.is_valid
        assert "empty" in result.errors[0].lower()
    
    def test_validate_missing_columns(self, validator):
        """Test validation with missing columns."""
        df = pd.DataFrame({'date': [], 'open': []})
        result = validator.validate_dataframe(df, symbol="TEST")
        assert not result.is_valid
    
    def test_validate_negative_prices(self, validator, sample_df):
        """Test detection of negative prices."""
        sample_df.loc[0, 'close'] = -10
        result = validator.validate_dataframe(sample_df, symbol="TEST")
        assert not result.is_valid or len(result.errors) > 0
    
    def test_validate_insufficient_data(self, validator):
        """Test detection of insufficient data."""
        dates = pd.date_range(start='2024-01-01', periods=50, freq='D')
        df = pd.DataFrame({
            'date': dates,
            'open': np.random.uniform(10, 20, 50),
            'high': np.random.uniform(20, 25, 50),
            'low': np.random.uniform(8, 10, 50),
            'close': np.random.uniform(12, 18, 50),
            'volume': np.random.randint(100000, 1000000, 50),
        })
        result = validator.validate_dataframe(df, symbol="TEST")
        # Should have warning about insufficient data
        assert len(result.warnings) > 0


class TestValidateStockData:
    """Test the validate_stock_data convenience function."""
    
    def test_valid_data(self):
        """Test with valid data."""
        df = pd.DataFrame({
            'date': pd.date_range(start='2024-01-01', periods=200, freq='D'),
            'open': np.random.uniform(10, 20, 200),
            'high': np.random.uniform(20, 25, 200),
            'low': np.random.uniform(8, 10, 200),
            'close': np.random.uniform(12, 18, 200),
            'volume': np.random.randint(100000, 1000000, 200),
        })
        # Ensure consistency
        df['high'] = df[['high', 'open', 'close']].max(axis=1)
        df['low'] = df[['low', 'open', 'close']].min(axis=1)
        
        is_valid, cleaned_df, issues = validate_stock_data(df, "TEST")
        assert is_valid
    
    def test_chinese_columns(self):
        """Test with Chinese column names."""
        df = pd.DataFrame({
            '日期': pd.date_range(start='2024-01-01', periods=200, freq='D'),
            '开盘': np.random.uniform(10, 20, 200),
            '最高': np.random.uniform(20, 25, 200),
            '最低': np.random.uniform(8, 10, 200),
            '收盘': np.random.uniform(12, 18, 200),
            '成交量': np.random.randint(100000, 1000000, 200),
        })
        # Ensure consistency
        df['最高'] = df[['最高', '开盘', '收盘']].max(axis=1)
        df['最低'] = df[['最低', '开盘', '收盘']].min(axis=1)
        
        is_valid, cleaned_df, issues = validate_stock_data(df, "TEST")
        assert is_valid


class TestSMCAnalyzer:
    """Test SMC analysis functionality."""
    
    @pytest.fixture
    def analyzer(self):
        return SMCAnalyzer()
    
    @pytest.fixture
    def sample_data(self):
        """Create sample OHLCV data."""
        np.random.seed(42)
        dates = pd.date_range(start='2024-01-01', periods=300, freq='D')
        
        # Create a more realistic price pattern
        base_price = 100
        prices = [base_price]
        for i in range(299):
            change = np.random.uniform(-2, 2)
            prices.append(prices[-1] + change)
        
        df = pd.DataFrame({
            'date': dates,
            'open': prices,
            'high': [p + np.random.uniform(0, 3) for p in prices],
            'low': [p - np.random.uniform(0, 3) for p in prices],
            'close': [p + np.random.uniform(-1, 1) for p in prices],
            'volume': np.random.randint(1000000, 5000000, 300),
        })
        
        # Ensure consistency
        df['high'] = df[['high', 'open', 'close']].max(axis=1)
        df['low'] = df[['low', 'open', 'close']].min(axis=1)
        
        return df
    
    def test_analyze_returns_result(self, analyzer, sample_data):
        """Test that analyze returns a valid result."""
        result = analyzer.analyze(sample_data, symbol="TEST")
        assert result is not None
        assert result.current_price > 0
    
    def test_analyze_detects_trend(self, analyzer, sample_data):
        """Test that trend detection works."""
        result = analyzer.analyze(sample_data, symbol="TEST")
        assert result.trend in ["bullish", "bearish", "neutral"]
    
    def test_analyze_detects_zone(self, analyzer, sample_data):
        """Test that premium/discount zone detection works."""
        result = analyzer.analyze(sample_data, symbol="TEST")
        assert result.premium_discount in ["premium", "discount", "equilibrium"]


class TestPerformanceMonitor:
    """Test performance monitoring."""
    
    @pytest.fixture
    def monitor(self):
        return PerformanceMonitor()
    
    def test_track_sync_operation(self, monitor):
        """Test tracking synchronous operations."""
        with monitor.track("test_op"):
            # Simulate work
            sum(range(1000))
        
        stats = monitor.get_stats("test_op")
        assert stats["count"] == 1
        assert stats["success_count"] == 1
        assert stats["duration_avg_ms"] > 0
    
    def test_track_multiple_operations(self, monitor):
        """Test tracking multiple operations."""
        for i in range(5):
            with monitor.track("multi_op"):
                pass
        
        stats = monitor.get_stats("multi_op")
        assert stats["count"] == 5
    
    def test_track_failed_operation(self, monitor):
        """Test tracking failed operations."""
        try:
            with monitor.track("fail_op"):
                raise ValueError("Test error")
        except ValueError:
            pass
        
        stats = monitor.get_stats("fail_op")
        assert stats["success_rate"] == 0
        assert stats["error_count"] == 1


class TestHealthChecker:
    """Test health checking functionality."""
    
    @pytest.fixture
    def health_checker(self):
        return HealthChecker()
    
    @pytest.fixture
    def temp_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)
    
    def test_check_disk_space(self, health_checker):
        """Test disk space check."""
        is_ok, message, free_gb = health_checker.check_disk_space()
        assert isinstance(is_ok, bool)
        assert isinstance(free_gb, float)
    
    def test_check_memory(self, health_checker):
        """Test memory check."""
        is_ok, message, free_pct = health_checker.check_memory()
        assert isinstance(is_ok, bool)
        assert isinstance(free_pct, float)
    
    def test_full_check(self, health_checker, temp_dir):
        """Test full health check."""
        status = health_checker.full_check(temp_dir)
        assert status is not None
        assert isinstance(status.is_healthy, bool)


class TestExceptions:
    """Test custom exceptions."""
    
    def test_data_fetch_error(self):
        """Test DataFetchError creation."""
        error = DataFetchError(
            "Test fetch error",
            symbol="000001",
            retry_count=2,
        )
        assert error.symbol == "000001"
        assert error.retry_count == 2
        assert error.recoverable is True
    
    def test_data_validation_error(self):
        """Test DataValidationError creation."""
        error = DataValidationError(
            "Test validation error",
            validation_errors=["issue1", "issue2"],
        )
        assert len(error.validation_errors) == 2
        assert error.recoverable is False
    
    def test_error_to_dict(self):
        """Test error serialization."""
        error = DataFetchError("Test", symbol="TEST")
        d = error.to_dict()
        assert "error_code" in d
        assert "message" in d
        assert "timestamp" in d


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
