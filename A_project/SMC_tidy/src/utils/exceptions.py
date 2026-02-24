"""
SMC Analysis - Exception Classes
=================================

Custom exceptions for the SMC analysis system.
"""
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime


class ErrorSeverity(Enum):
    """Error severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories for classification."""
    NETWORK = "network"
    DATA = "data"
    CONFIG = "config"
    ANALYSIS = "analysis"
    SYSTEM = "system"
    USER = "user"


class SMCApiError(Exception):
    """Base exception for all SMC API errors."""
    
    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        category: ErrorCategory = ErrorCategory.SYSTEM,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        context: Optional[Dict[str, Any]] = None,
        recoverable: bool = True,
        retry_after: Optional[int] = None,
    ):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or "UNKNOWN_ERROR"
        self.category = category
        self.severity = severity
        self.context = context or {}
        self.recoverable = recoverable
        self.retry_after = retry_after
        self.timestamp = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for logging/serialization."""
        return {
            "error_code": self.error_code,
            "message": self.message,
            "category": self.category.value,
            "severity": self.severity.value,
            "context": self.context,
            "recoverable": self.recoverable,
            "retry_after": self.retry_after,
            "timestamp": self.timestamp.isoformat(),
        }
    
    def __str__(self) -> str:
        return f"[{self.error_code}] {self.message}"


class DataFetchError(SMCApiError):
    """Error during data fetching operations."""
    
    def __init__(
        self,
        message: str,
        symbol: Optional[str] = None,
        source: Optional[str] = None,
        retry_count: int = 0,
        **kwargs,
    ):
        context = kwargs.pop("context", {})
        if symbol:
            context["symbol"] = symbol
        if source:
            context["source"] = source
        context["retry_count"] = retry_count
        
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", f"FETCH_{symbol or 'UNKNOWN'}"),
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.MEDIUM if retry_count < 3 else ErrorSeverity.HIGH,
            context=context,
            recoverable=True,
            **kwargs,
        )
        self.symbol = symbol
        self.source = source
        self.retry_count = retry_count


class DataValidationError(SMCApiError):
    """Error during data validation."""
    
    def __init__(
        self,
        message: str,
        data_type: Optional[str] = None,
        validation_errors: Optional[list] = None,
        **kwargs,
    ):
        context = kwargs.pop("context", {})
        if data_type:
            context["data_type"] = data_type
        if validation_errors:
            context["validation_errors"] = validation_errors
        
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "DATA_VALIDATION_ERROR"),
            category=ErrorCategory.DATA,
            severity=ErrorSeverity.HIGH,
            context=context,
            recoverable=False,
            **kwargs,
        )
        self.validation_errors = validation_errors or []


class ConfigurationError(SMCApiError):
    """Error in configuration."""
    
    def __init__(
        self,
        message: str,
        config_key: Optional[str] = None,
        config_value: Optional[Any] = None,
        **kwargs,
    ):
        context = kwargs.pop("context", {})
        if config_key:
            context["config_key"] = config_key
        if config_value is not None:
            context["config_value"] = str(config_value)
        
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "CONFIG_ERROR"),
            category=ErrorCategory.CONFIG,
            severity=ErrorSeverity.HIGH,
            context=context,
            recoverable=False,
            **kwargs,
        )


class AnalysisError(SMCApiError):
    """Error during SMC analysis."""
    
    def __init__(
        self,
        message: str,
        symbol: Optional[str] = None,
        analysis_stage: Optional[str] = None,
        **kwargs,
    ):
        context = kwargs.pop("context", {})
        if symbol:
            context["symbol"] = symbol
        if analysis_stage:
            context["analysis_stage"] = analysis_stage
        
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", f"ANALYSIS_{symbol or 'UNKNOWN'}"),
            category=ErrorCategory.ANALYSIS,
            severity=ErrorSeverity.MEDIUM,
            context=context,
            recoverable=True,
            **kwargs,
        )


class ReportGenerationError(SMCApiError):
    """Error during report generation."""
    
    def __init__(
        self,
        message: str,
        report_type: Optional[str] = None,
        output_path: Optional[str] = None,
        **kwargs,
    ):
        context = kwargs.pop("context", {})
        if report_type:
            context["report_type"] = report_type
        if output_path:
            context["output_path"] = output_path
        
        super().__init__(
            message,
            error_code=kwargs.pop("error_code", "REPORT_ERROR"),
            category=ErrorCategory.SYSTEM,
            severity=ErrorSeverity.MEDIUM,
            context=context,
            recoverable=True,
            **kwargs,
        )


# Convenience functions for creating common errors
def create_network_timeout_error(symbol: str, timeout: int) -> DataFetchError:
    """Create a timeout error for data fetching."""
    return DataFetchError(
        f"Timeout after {timeout}s while fetching data for {symbol}",
        symbol=symbol,
        error_code="FETCH_TIMEOUT",
        retry_after=min(timeout * 2, 60),
    )


def create_rate_limit_error(source: str, retry_after: int) -> DataFetchError:
    """Create a rate limit error."""
    return DataFetchError(
        f"Rate limited by {source}, retry after {retry_after}s",
        source=source,
        error_code="RATE_LIMITED",
        retry_after=retry_after,
        severity=ErrorSeverity.MEDIUM,
    )


def create_invalid_data_error(symbol: str, issues: list) -> DataValidationError:
    """Create an invalid data error."""
    return DataValidationError(
        f"Invalid data for {symbol}: {', '.join(issues)}",
        data_type="stock_data",
        validation_errors=issues,
    )
