"""
SMC Report Module - HTML Report Generation
"""

from .market_report import MarketSituationReport, generate_market_report
from .html_report import HTMLReportGenerator, generate_report_from_analyses

__all__ = [
    "MarketSituationReport",
    "generate_market_report",
    "HTMLReportGenerator",
    "generate_report_from_analyses",
]
