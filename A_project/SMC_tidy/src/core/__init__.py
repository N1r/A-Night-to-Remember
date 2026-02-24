"""
SMC Core Engine Module
======================

High-performance vectorized SMC (Smart Money Concepts) analysis engine.

Key Components:
- VectorizedSMCEngine: Pure NumPy/Pandas implementation
- Premium visualizer with dark theme
- Institutional-grade signal output
"""

from .engine import VectorizedSMCEngine, EngineConfig
from .signals import InstitutionalSignal, SignalGenerator, RiskManager
from .types import (
    OrderBlock, OBType,
    FairValueGap, FVGType,
    StructureBreak, BreakType,
    LiquidityLevel, LiquidityType,
    SwingPoint,
    MarketState, ZoneType, TrendDirection,
    AnalysisOutput, SignalType,
)
from .visualizer import PremiumChartBuilder, ColorScheme, create_summary_panel

__all__ = [
    # Engine
    "VectorizedSMCEngine",
    "EngineConfig",
    # Signals
    "InstitutionalSignal",
    "SignalGenerator",
    "RiskManager",
    # Types
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
    # Visualizer
    "PremiumChartBuilder",
    "ColorScheme",
    "create_summary_panel",
]
