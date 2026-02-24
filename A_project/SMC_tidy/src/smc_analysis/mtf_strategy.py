"""
Multi-Timeframe (MTF) SMC Strategy
=================================

Performs Confluence analysis using a High Timeframe (HTF) context 
and a Low Timeframe (LTF) execution entry.

Core Idea:
1. Identify high value POIs (Point of Interest) on HTF (e.g. Daily).
2. Wait for price to mitigate these HTF POIs.
3. Switch to LTF (e.g. 60min or 15min).
4. Look for alignment in LTF: CHOCH, BOS, or Liquidity Sweep.
5. Enter on LTF Order Block / FVG with tighter stops and higher RR.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any

import pandas as pd

from .analyzer import SMCAnalyzer, AnalysisResult
from .enhanced_strategy import EnhancedTradingSignal, EnhancedSMCStrategy

logger = logging.getLogger(__name__)


@dataclass
class MTFTradingSignal:
    """Multi-timeframe trading signal combining HTF context and LTF entry."""
    symbol: str
    name: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    
    # State flags
    is_valid: bool = False
    signal_type: str = "neutral"  # 'long', 'short', 'neutral'
    
    # HTF Context
    htf_trend: str = "neutral"
    htf_poi_type: str = ""  # 'ob', 'fvg', 'liquidity'
    htf_distance_to_poi: float = 0.0  # Percentage distance to the HTF POI
    htf_mitigated: bool = False # Has HTF POI been tapped?
    
    # LTF Execution
    ltf_trend: str = "neutral"
    ltf_choch_present: bool = False
    ltf_sweep_present: bool = False
    ltf_fvg_alignment: bool = False
    
    # Entry parameters (based on LTF)
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit_1: float = 0.0
    take_profit_2: float = 0.0
    take_profit_3: float = 0.0
    risk_reward_ratio: float = 0.0
    
    # Analysis
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'symbol': self.symbol,
            'name': self.name,
            'timestamp': self.timestamp.isoformat(),
            'is_valid': self.is_valid,
            'signal_type': self.signal_type,
            'htf_trend': self.htf_trend,
            'htf_poi_type': self.htf_poi_type,
            'htf_mitigated': self.htf_mitigated,
            'ltf_trend': self.ltf_trend,
            'ltf_choch_present': self.ltf_choch_present,
            'ltf_sweep_present': self.ltf_sweep_present,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'take_profit_1': self.take_profit_1,
            'take_profit_2': self.take_profit_2,
            'take_profit_3': self.take_profit_3,
            'risk_reward_ratio': self.risk_reward_ratio,
            'reasons': self.reasons,
            'warnings': self.warnings,
        }

@dataclass
class MTFAnalysisResult:
    """Result of MTF analysis containing both HTF and LTF results."""
    symbol: str
    name: str = ""
    htf_result: Optional[AnalysisResult] = None
    ltf_result: Optional[AnalysisResult] = None
    signal: Optional[MTFTradingSignal] = None


class MTFSMCStrategy:
    """Multi-timeframe implementation of SMC."""
    
    def __init__(self):
        self.htf_analyzer = SMCAnalyzer(timeframe="daily")
        self.ltf_analyzer = SMCAnalyzer(timeframe="intraday")
        # We can leverage the logic in EnhancedSMCStrategy for the LTF entry sizing & RR
        self.ltf_strategy = EnhancedSMCStrategy(timeframe="intraday")

    def analyze(
        self,
        htf_df: pd.DataFrame,
        ltf_df: pd.DataFrame,
        symbol: str = "UNKNOWN",
        name: str = ""
    ) -> MTFAnalysisResult:
        """
        Perform MTF analysis.
        
        Args:
            htf_df: Daily/HTF DataFrame
            ltf_df: Intraday/LTF DataFrame (60min, 15min, etc.)
            symbol: Stock symbol
            name: Stock name
        """
        # Run independent analysis on both dataframes
        htf_result = self.htf_analyzer.analyze(htf_df, symbol=symbol)
        ltf_result = self.ltf_analyzer.analyze(ltf_df, symbol=symbol)
        
        # Get enhanced evaluation on the LTF
        # (This calculates stop losses using ATR on the LTF, distance scores, etc.)
        ltf_enhanced_analysis = self.ltf_strategy.analyze(ltf_df, symbol=symbol, name=name)
        ltf_signal = ltf_enhanced_analysis.primary_signal

        mtf_signal = MTFTradingSignal(symbol=symbol, name=name)
        mtf_signal.htf_trend = htf_result.trend
        mtf_signal.ltf_trend = ltf_result.trend
        
        current_price = ltf_result.current_price
        
        # -----------------------------
        # Step 1: HTF POI Selection
        # -----------------------------
        active_htf_bullish_obs = [ob for ob in htf_result.order_blocks if ob.type == 'bullish' and not ob.mitigated]
        
        # Determine if price is mitigating or near an HTF POI
        htf_bullish_poi = None
        
        # Find closest unmitigated HTF OBs
        if active_htf_bullish_obs:
            htf_bullish_poi = min(active_htf_bullish_obs, key=lambda ob: max(0, current_price - ob.top))
            
        is_long_bias = False
        
        # Bias rules: Tapping into HTF POIs
        # We consider a tap if current price is within exorbitant close (e.g., < 1%)
        if htf_bullish_poi:
            distance = (current_price - htf_bullish_poi.top) / htf_bullish_poi.top
            if current_price <= htf_bullish_poi.top and current_price >= htf_bullish_poi.bottom * 0.98:
                mtf_signal.htf_mitigated = True
                mtf_signal.htf_poi_type = "bullish_ob"
                is_long_bias = True
                mtf_signal.reasons.append(f"HTF回撤至日线多头OB {htf_bullish_poi.top:.2f}-{htf_bullish_poi.bottom:.2f}")
            elif 0 < distance < 0.02:
                # Near POI
                mtf_signal.htf_poi_type = "near_bullish_ob"
                is_long_bias = True
                mtf_signal.reasons.append(f"接近日线多头OB区 (相距{distance*100:.1f}%)")

        # Fallback bias: HTF Trend
        if not is_long_bias:
            if htf_result.trend == 'bullish':
                is_long_bias = True
                mtf_signal.reasons.append("顺应HTF多头趋势")

        # -----------------------------
        # Step 2: LTF Confirmation
        # -----------------------------
        recent_ltf_breaks = [sb for sb in ltf_result.structure_breaks if sb.index > len(ltf_df) - 30]
        has_ltf_bullish_choch = any(sb.type == 'choch' and sb.direction == 'bullish' for sb in recent_ltf_breaks)
        has_ltf_bearish_choch = any(sb.type == 'choch' and sb.direction == 'bearish' for sb in recent_ltf_breaks)
        
        ltf_sweep_bullish = any(lvl.swept and lvl.type == 'sell_side' for lvl in ltf_result.liquidity_levels)
        ltf_sweep_bearish = any(lvl.swept and lvl.type == 'buy_side' for lvl in ltf_result.liquidity_levels)

        # -----------------------------
        # Step 3: Synthesis
        # -----------------------------
        if is_long_bias and ltf_signal and ltf_signal.signal_type == 'long':
            mtf_signal.is_valid = True
            mtf_signal.signal_type = "long"
            
            if has_ltf_bullish_choch:
                mtf_signal.ltf_choch_present = True
                mtf_signal.reasons.append("LTF出现多头CHOCH确认信号")
            if ltf_sweep_bullish:
                mtf_signal.ltf_sweep_present = True
                mtf_signal.reasons.append("LTF扫荡下方(Sell-side)流动性")
                
            mtf_signal.ltf_fvg_alignment = ltf_signal.fvg_alignment
            
            mtf_signal.entry_price = ltf_signal.entry_price
            mtf_signal.stop_loss = ltf_signal.stop_loss
            mtf_signal.take_profit_1 = ltf_signal.take_profit_1
            mtf_signal.take_profit_2 = ltf_signal.take_profit_2
            mtf_signal.risk_reward_ratio = ltf_signal.risk_reward_ratio

        else:
            mtf_signal.is_valid = False
            mtf_signal.signal_type = "neutral"
            mtf_signal.warnings.append("LTF未产生有效多头共振，建议观望等待")

        return MTFAnalysisResult(
            symbol=symbol,
            name=name,
            htf_result=htf_result,
            ltf_result=ltf_result,
            signal=mtf_signal
        )
