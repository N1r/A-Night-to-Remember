"""
SMC Analysis - Monitoring and Performance
=========================================

Performance monitoring, health checking, and alerting.
"""
import asyncio
import json
import logging
import os
import platform
import psutil
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Tuple
from collections import defaultdict
import traceback

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetric:
    """Single performance metric."""
    name: str
    value: float
    unit: str
    timestamp: datetime = field(default_factory=datetime.now)
    tags: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "timestamp": self.timestamp.isoformat(),
            "tags": self.tags,
        }


@dataclass
class HealthStatus:
    """System health status."""
    is_healthy: bool
    issues: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_healthy": self.is_healthy,
            "issues": self.issues,
            "metrics": self.metrics,
            "timestamp": self.timestamp.isoformat(),
        }


class PerformanceMonitor:
    """
    Performance monitoring for operations.
    
    Features:
    - Execution time tracking
    - Memory usage monitoring
    - Operation success/failure rates
    - Performance percentiles
    """
    
    def __init__(self, max_history: int = 1000):
        """
        Initialize performance monitor.
        
        Args:
            max_history: Maximum number of operations to keep in history
        """
        self.max_history = max_history
        self._operations: Dict[str, List[Dict]] = defaultdict(list)
        self._metrics: List[PerformanceMetric] = []
        self._lock = threading.Lock()
        self._start_time = time.monotonic()
    
    @contextmanager
    def track(self, operation: str, **tags):
        """
        Context manager to track operation duration.
        
        Usage:
            with monitor.track("fetch_data", symbol="000001"):
                # ... operation code ...
        """
        start_time = time.monotonic()
        start_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
        error = None
        
        try:
            yield self
        except Exception as e:
            error = str(e)
            raise
        finally:
            duration = time.monotonic() - start_time
            end_memory = psutil.Process().memory_info().rss / 1024 / 1024
            memory_delta = end_memory - start_memory
            
            self._record_operation(
                operation=operation,
                duration=duration,
                memory_delta=memory_delta,
                success=error is None,
                error=error,
                tags=tags,
            )
    
    def track_async(self, operation: str, **tags):
        """
        Async context manager to track operation duration.
        
        Usage:
            async with monitor.track_async("fetch_data", symbol="000001"):
                # ... async operation code ...
        """
        @contextmanager
        def _track():
            start_time = time.monotonic()
            start_memory = psutil.Process().memory_info().rss / 1024 / 1024
            error = None
            
            try:
                yield self
            except Exception as e:
                error = str(e)
                raise
            finally:
                duration = time.monotonic() - start_time
                end_memory = psutil.Process().memory_info().rss / 1024 / 1024
                memory_delta = end_memory - start_memory
                
                self._record_operation(
                    operation=operation,
                    duration=duration,
                    memory_delta=memory_delta,
                    success=error is None,
                    error=error,
                    tags=tags,
                )
        
        return _track()
    
    def _record_operation(
        self,
        operation: str,
        duration: float,
        memory_delta: float,
        success: bool,
        error: Optional[str],
        tags: Dict[str, str],
    ) -> None:
        """Record an operation execution."""
        record = {
            "timestamp": datetime.now().isoformat(),
            "duration_ms": duration * 1000,
            "memory_delta_mb": memory_delta,
            "success": success,
            "error": error,
            "tags": tags,
        }
        
        with self._lock:
            self._operations[operation].append(record)
            
            # Limit history
            if len(self._operations[operation]) > self.max_history:
                self._operations[operation] = self._operations[operation][-self.max_history:]
    
    def record_metric(
        self,
        name: str,
        value: float,
        unit: str,
        tags: Optional[Dict[str, str]] = None,
    ) -> None:
        """Record a custom metric."""
        metric = PerformanceMetric(
            name=name,
            value=value,
            unit=unit,
            tags=tags or {},
        )
        
        with self._lock:
            self._metrics.append(metric)
            if len(self._metrics) > self.max_history:
                self._metrics = self._metrics[-self.max_history:]
    
    def get_stats(self, operation: str) -> Dict[str, Any]:
        """
        Get statistics for an operation.
        
        Returns:
            Dictionary with min, max, avg, p50, p95, p99 durations
        """
        with self._lock:
            records = self._operations.get(operation, [])
        
        if not records:
            return {}
        
        durations = [r["duration_ms"] for r in records if r["success"]]
        errors = [r for r in records if not r["success"]]
        
        if not durations:
            return {
                "count": len(records),
                "success_rate": 0,
                "error_count": len(errors),
            }
        
        sorted_durations = sorted(durations)
        n = len(sorted_durations)
        
        return {
            "count": len(records),
            "success_count": len(durations),
            "error_count": len(errors),
            "success_rate": len(durations) / len(records) * 100,
            "duration_min_ms": min(durations),
            "duration_max_ms": max(durations),
            "duration_avg_ms": sum(durations) / len(durations),
            "duration_p50_ms": sorted_durations[int(n * 0.5)],
            "duration_p95_ms": sorted_durations[int(n * 0.95)] if n > 20 else sorted_durations[-1],
            "duration_p99_ms": sorted_durations[int(n * 0.99)] if n > 100 else sorted_durations[-1],
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """Get overall performance summary."""
        summary = {}
        
        for operation in self._operations:
            summary[operation] = self.get_stats(operation)
        
        # Add system metrics
        process = psutil.Process()
        summary["_system"] = {
            "uptime_seconds": time.monotonic() - self._start_time,
            "memory_mb": process.memory_info().rss / 1024 / 1024,
            "cpu_percent": process.cpu_percent(),
            "thread_count": process.num_threads(),
        }
        
        return summary
    
    def export_metrics(self, output_path: Path) -> None:
        """Export metrics to a JSON file."""
        data = {
            "operations": dict(self._operations),
            "metrics": [m.to_dict() for m in self._metrics],
            "summary": self.get_summary(),
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)


class HealthChecker:
    """
    System health checker.
    
    Checks:
    - Disk space
    - Memory availability
    - Data freshness
    - API connectivity
    """
    
    def __init__(
        self,
        min_disk_space_gb: float = 1.0,
        min_memory_percent: float = 10.0,
        max_data_age_hours: int = 24,
    ):
        """
        Initialize health checker.
        
        Args:
            min_disk_space_gb: Minimum required disk space
            min_memory_percent: Minimum required free memory percentage
            max_data_age_hours: Maximum data age before warning
        """
        self.min_disk_space_gb = min_disk_space_gb
        self.min_memory_percent = min_memory_percent
        self.max_data_age_hours = max_data_age_hours
    
    def check_disk_space(self, path: Path = None) -> Tuple[bool, str, float]:
        """
        Check available disk space.
        
        Returns:
            Tuple of (is_ok, message, free_space_gb)
        """
        if path is None:
            path = Path.cwd()
        
        try:
            usage = psutil.disk_usage(str(path))
            free_gb = usage.free / (1024 ** 3)
            
            if free_gb < self.min_disk_space_gb:
                return False, f"Low disk space: {free_gb:.2f} GB (min: {self.min_disk_space_gb} GB)", free_gb
            
            return True, f"Disk space OK: {free_gb:.2f} GB free", free_gb
        except Exception as e:
            return False, f"Error checking disk space: {e}", 0
    
    def check_memory(self) -> Tuple[bool, str, float]:
        """
        Check available memory.
        
        Returns:
            Tuple of (is_ok, message, free_percent)
        """
        try:
            memory = psutil.virtual_memory()
            free_percent = memory.available / memory.total * 100
            
            if free_percent < self.min_memory_percent:
                return False, f"Low memory: {free_percent:.1f}% free (min: {self.min_memory_percent}%)", free_percent
            
            return True, f"Memory OK: {free_percent:.1f}% free", free_percent
        except Exception as e:
            return False, f"Error checking memory: {e}", 0
    
    def check_data_directory(self, data_dir: Path) -> Tuple[bool, str, int]:
        """
        Check data directory health.
        
        Returns:
            Tuple of (is_ok, message, file_count)
        """
        if not data_dir.exists():
            return False, f"Data directory does not exist: {data_dir}", 0
        
        try:
            files = list(data_dir.glob("*.csv"))
            file_count = len(files)
            
            if file_count == 0:
                return False, "No data files found", 0
            
            # Check for recent files
            now = datetime.now()
            recent_files = [
                f for f in files
                if datetime.fromtimestamp(f.stat().st_mtime) > now - timedelta(hours=self.max_data_age_hours)
            ]
            
            if len(recent_files) == 0:
                return True, f"Data directory OK but no recent files (total: {file_count})", file_count
            
            return True, f"Data directory OK: {file_count} files ({len(recent_files)} recent)", file_count
        except Exception as e:
            return False, f"Error checking data directory: {e}", 0
    
    def full_check(self, data_dir: Path = None) -> HealthStatus:
        """
        Perform full health check.
        
        Returns:
            HealthStatus with all check results
        """
        issues = []
        metrics = {}
        
        # Check disk
        disk_ok, disk_msg, disk_gb = self.check_disk_space()
        metrics["disk_free_gb"] = disk_gb
        if not disk_ok:
            issues.append(disk_msg)
        
        # Check memory
        mem_ok, mem_msg, mem_pct = self.check_memory()
        metrics["memory_free_percent"] = mem_pct
        if not mem_ok:
            issues.append(mem_msg)
        
        # Check data directory
        if data_dir:
            data_ok, data_msg, file_count = self.check_data_directory(data_dir)
            metrics["data_file_count"] = file_count
            if not data_ok:
                issues.append(data_msg)
        
        # Add system info
        metrics["platform"] = platform.system()
        metrics["python_version"] = platform.python_version()
        metrics["cpu_count"] = os.cpu_count()
        
        return HealthStatus(
            is_healthy=len(issues) == 0,
            issues=issues,
            metrics=metrics,
        )


class AlertManager:
    """
    Simple alert manager for notifications.
    """
    
    def __init__(self, log_file: Optional[Path] = None):
        """
        Initialize alert manager.
        
        Args:
            log_file: Optional path to log alerts to file
        """
        self.log_file = log_file
        self._alerts: List[Dict[str, Any]] = []
        self._handlers: List[Callable] = []
    
    def add_handler(self, handler: Callable[[Dict], None]) -> None:
        """Add an alert handler function."""
        self._handlers.append(handler)
    
    def alert(
        self,
        level: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Issue an alert.
        
        Args:
            level: Alert level (info, warning, error, critical)
            message: Alert message
            context: Optional context information
        """
        alert_data = {
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message,
            "context": context or {},
        }
        
        # Store alert
        self._alerts.append(alert_data)
        
        # Log to file
        if self.log_file:
            try:
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(alert_data, default=str) + "\n")
            except Exception as e:
                logger.error(f"Failed to write alert to file: {e}")
        
        # Call handlers
        for handler in self._handlers:
            try:
                handler(alert_data)
            except Exception as e:
                logger.error(f"Alert handler error: {e}")
        
        # Log
        log_level = {
            "info": logging.INFO,
            "warning": logging.WARNING,
            "error": logging.ERROR,
            "critical": logging.CRITICAL,
        }.get(level, logging.INFO)
        
        logger.log(log_level, f"[ALERT] {level.upper()}: {message}")
    
    def info(self, message: str, context: Optional[Dict] = None) -> None:
        """Issue info alert."""
        self.alert("info", message, context)
    
    def warning(self, message: str, context: Optional[Dict] = None) -> None:
        """Issue warning alert."""
        self.alert("warning", message, context)
    
    def error(self, message: str, context: Optional[Dict] = None) -> None:
        """Issue error alert."""
        self.alert("error", message, context)
    
    def critical(self, message: str, context: Optional[Dict] = None) -> None:
        """Issue critical alert."""
        self.alert("critical", message, context)
    
    def get_recent_alerts(self, count: int = 10) -> List[Dict]:
        """Get recent alerts."""
        return self._alerts[-count:]


# Global monitor instance
_monitor: Optional[PerformanceMonitor] = None


def get_monitor() -> PerformanceMonitor:
    """Get or create global performance monitor."""
    global _monitor
    if _monitor is None:
        _monitor = PerformanceMonitor()
    return _monitor


def track_performance(operation: str, **tags):
    """
    Decorator to track function performance.
    
    Usage:
        @track_performance("fetch_data")
        def fetch_data(symbol):
            ...
    """
    def decorator(func):
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            monitor = get_monitor()
            with monitor.track(operation, **tags):
                return func(*args, **kwargs)
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            monitor = get_monitor()
            with monitor.track(operation, **tags):
                return await func(*args, **kwargs)
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator
