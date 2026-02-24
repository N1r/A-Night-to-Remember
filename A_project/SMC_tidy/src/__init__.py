"""
SMC Technical Analysis Package
Smart Money Concepts analysis tool for stock market data
"""

__version__ = "2.1.0"

# Core Engine (New)
from .core import (
    VectorizedSMCEngine,
    EngineConfig,
    InstitutionalSignal,
    SignalGenerator,
    RiskManager,
    PremiumChartBuilder,
    ColorScheme,
    OrderBlock, OBType,
    FairValueGap, FVGType,
    StructureBreak, BreakType,
    LiquidityLevel, LiquidityType,
    SwingPoint,
    MarketState, ZoneType, TrendDirection,
    AnalysisOutput, SignalType,
    create_summary_panel,
)

# Orchestrator (New)
from .orchestrator import (
    SMCOrchestrator,
    OrchestratorConfig,
    AnalysisResult,
    analyze_from_file,
)

# Config
from .config import get_config, AppConfig, SMCConfig, DataConfig, ChartConfig, WebConfig

# Data fetching
from .data_fetch import (
    AStockFetcher,
    HKStockFetcher,
    USStockFetcher,
    get_fetcher,
    convert_to_smc_format,
    batch_convert_to_smc,
)

# Legacy SMC Analysis
from .smc_analysis import (
    SMCAnalyzer, 
    AnalysisResult as LegacyAnalysisResult,
    analyze_ob_overlap,
    AdvancedSMCStrategy,
    TradingSignal,
    StrategyAnalysis,
    batch_analyze_strategies,
    EnhancedSMCStrategy,
    EnhancedTradingSignal,
    EnhancedStrategyAnalysis,
)

# Legacy Chart Plot
from .chart_plot import SMCChartPlotter, create_summary_card as legacy_create_summary_card

# Web
from .web import run_app

# Report
from .report import generate_report_from_analyses, generate_market_report

__all__ = [
    # New Core Engine
    "VectorizedSMCEngine",
    "EngineConfig",
    "InstitutionalSignal",
    "SignalGenerator",
    "RiskManager",
    "PremiumChartBuilder",
    "ColorScheme",
    # New Types
    "OrderBlock",
    "OBType",
    "FairValueGap",
    "FVGType",
    "StructureBreak",
    "BreakType",
    "LiquidityLevel",
    "LiquidityType",
    "SwingPoint",
    "MarketState",
    "ZoneType",
    "TrendDirection",
    "AnalysisOutput",
    "SignalType",
    # New Orchestrator
    "SMCOrchestrator",
    "OrchestratorConfig",
    "AnalysisResult",
    "analyze_from_file",
    "create_summary_panel",
    # Config
    "get_config",
    "AppConfig",
    "SMCConfig",
    "DataConfig",
    "ChartConfig",
    "WebConfig",
    # Data fetching
    "AStockFetcher",
    "HKStockFetcher",
    "USStockFetcher",
    "get_fetcher",
    "convert_to_smc_format",
    "batch_convert_to_smc",
    # Legacy Analysis
    "SMCAnalyzer",
    "LegacyAnalysisResult",
    "analyze_ob_overlap",
    # Legacy Strategy
    "AdvancedSMCStrategy",
    "TradingSignal",
    "StrategyAnalysis",
    "batch_analyze_strategies",
    # Enhanced Strategy
    "EnhancedSMCStrategy",
    "EnhancedTradingSignal",
    "EnhancedStrategyAnalysis",
    # Legacy Visualization
    "SMCChartPlotter",
    "legacy_create_summary_card",
    # Web
    "run_app",
    # Report
    "generate_report_from_analyses",
    "generate_market_report",
]
