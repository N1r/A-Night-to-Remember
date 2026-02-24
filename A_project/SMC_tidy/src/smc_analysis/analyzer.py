"""
Enhanced SMC (Smart Money Concepts) analyzer with comprehensive analysis methods.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import warnings

import numpy as np
import pandas as pd

# Suppress pkg_resources warning
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from smartmoneyconcepts.smc import smc

from ..config import get_config, SMCConfig

logger = logging.getLogger(__name__)


@dataclass
class OrderBlock:
    """Order Block data structure."""
    index: int
    top: float
    bottom: float
    volume: float
    type: str  # 'bullish' or 'bearish'
    mitigated: bool
    mitigated_index: Optional[int]
    overlap_ratio: float = 0.0
    distance_pct: float = 0.0  # Distance from current price as percentage


@dataclass
class FairValueGap:
    """Fair Value Gap data structure."""
    index: int
    top: float
    bottom: float
    type: str  # 'bullish' or 'bearish'
    mitigated: bool
    mitigated_index: Optional[int]
    size: float


@dataclass
class LiquidityLevel:
    """Liquidity Level data structure."""
    index: int
    level: float
    type: str  # 'buy_side' or 'sell_side'
    end_index: int
    swept: bool


@dataclass
class StructureBreak:
    """Structure Break (BOS/CHOCH) data structure."""
    index: int
    level: float
    type: str  # 'bos' or 'choch'
    direction: str  # 'bullish' or 'bearish'
    broken_index: int


@dataclass
class AnalysisResult:
    """Complete SMC analysis result."""
    symbol: str
    timestamp: datetime
    ohlcv: pd.DataFrame
    
    # SMC indicators
    order_blocks: List[OrderBlock] = field(default_factory=list)
    fvg_list: List[FairValueGap] = field(default_factory=list)
    liquidity_levels: List[LiquidityLevel] = field(default_factory=list)
    structure_breaks: List[StructureBreak] = field(default_factory=list)
    
    # Market state
    trend: str = "neutral"  # 'bullish', 'bearish', 'neutral'
    premium_discount: str = "equilibrium"  # 'premium', 'discount', 'equilibrium'
    current_price: float = 0.0
    
    # Statistics
    active_obs: int = 0
    active_fvgs: int = 0
    overlapping_obs: int = 0
    
    # Raw SMC data
    raw_smc_data: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp.isoformat(),
            'trend': self.trend,
            'premium_discount': self.premium_discount,
            'current_price': self.current_price,
            'active_obs': self.active_obs,
            'active_fvgs': self.active_fvgs,
            'overlapping_obs': self.overlapping_obs,
            'order_blocks': [
                {
                    'index': ob.index,
                    'top': ob.top,
                    'bottom': ob.bottom,
                    'type': ob.type,
                    'volume': ob.volume,
                    'mitigated': ob.mitigated,
                    'overlap_ratio': ob.overlap_ratio,
                }
                for ob in self.order_blocks
            ],
            'fvg_list': [
                {
                    'index': fvg.index,
                    'top': fvg.top,
                    'bottom': fvg.bottom,
                    'type': fvg.type,
                    'size': fvg.size,
                }
                for fvg in self.fvg_list
            ],
        }


class SMCAnalyzer:
    """
    Enhanced Smart Money Concepts analyzer.
    
    Provides comprehensive market analysis including:
    - Order Blocks (OB)
    - Fair Value Gaps (FVG)
    - Break of Structure (BOS)
    - Change of Character (CHOCH)
    - Liquidity Levels
    - Premium/Discount Zones
    - Swing Highs/Lows
    - Market Structure
    
    Supports both daily (long-term) and intraday (short-term) analysis.
    """
    
    def __init__(
        self, 
        config: Optional[SMCConfig] = None,
        timeframe: str = "daily",
    ):
        """
        Initialize SMC Analyzer.
        
        Args:
            config: SMC configuration (if None, loads from config file)
            timeframe: "daily" for long-term or "intraday" for short-term
        """
        app_config = get_config()
        
        if config is not None:
            self.config = config
        elif timeframe == "intraday":
            self.config = app_config.smc_intraday
        else:
            self.config = app_config.smc
        
        self.timeframe = timeframe
    
    def analyze(
        self,
        df: pd.DataFrame,
        symbol: str = "UNKNOWN",
        overlap_candles: Optional[int] = None,
    ) -> AnalysisResult:
        """
        Perform complete SMC analysis on OHLCV data.
        
        Args:
            df: DataFrame with OHLCV data
            symbol: Stock symbol for reference
            overlap_candles: Number of candles for overlap analysis
            
        Returns:
            AnalysisResult with all SMC indicators
        """
        # Prepare data
        df = self._prepare_dataframe(df)
        
        # Get current price
        current_price = df['close'].iloc[-1]
        
        # Calculate all SMC indicators
        swing_highs_lows = smc.swing_highs_lows(
            df,
            swing_length=self.config.swing_length,
        )
        
        fvg_data = smc.fvg(
            df,
            join_consecutive=self.config.join_consecutive_fvg,
        )
        
        bos_choch_data = smc.bos_choch(df, swing_highs_lows)
        
        ob_data = smc.ob(
            df,
            swing_highs_lows,
            close_mitigation=self.config.close_mitigation,
        )
        
        liquidity_data = smc.liquidity(df, swing_highs_lows)
        previous_high_low = smc.previous_high_low(df, time_frame="1D")
        
        # Build result
        result = AnalysisResult(
            symbol=symbol,
            timestamp=datetime.now(),
            ohlcv=df,
            current_price=current_price,
            raw_smc_data={
                'swing_highs_lows': swing_highs_lows,
                'fvg': fvg_data,
                'bos_choch': bos_choch_data,
                'ob': ob_data,
                'liquidity': liquidity_data,
                'previous_high_low': previous_high_low,
            }
        )
        
        # Process Order Blocks
        result.order_blocks = self._process_order_blocks(
            df, ob_data, current_price, overlap_candles
        )
        
        # Process FVGs
        result.fvg_list = self._process_fvgs(df, fvg_data)
        
        # Process Liquidity
        result.liquidity_levels = self._process_liquidity(df, liquidity_data)
        
        # Process Structure Breaks
        result.structure_breaks = self._process_structure_breaks(df, bos_choch_data)
        
        # Determine trend
        result.trend = self._determine_trend(df, swing_highs_lows)
        
        # Determine premium/discount zone
        result.premium_discount = self._determine_premium_discount(
            df, swing_highs_lows, current_price
        )
        
        # Calculate statistics
        result.active_obs = sum(1 for ob in result.order_blocks if not ob.mitigated)
        result.active_fvgs = sum(1 for fvg in result.fvg_list if not fvg.mitigated)
        result.overlapping_obs = sum(
            1 for ob in result.order_blocks if ob.overlap_ratio > 0
        )
        
        return result
    
    def _prepare_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare dataframe for SMC analysis."""
        df = df.copy()
        
        # Ensure required columns
        required = ['open', 'high', 'low', 'close', 'volume']
        missing = [col for col in required if col not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {missing}")
        
        # Convert to numeric
        for col in required:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Remove invalid rows
        df = df.dropna(subset=required)
        df = df.reset_index(drop=True)
        
        return df
    
    def _process_order_blocks(
        self,
        df: pd.DataFrame,
        ob_data: pd.DataFrame,
        current_price: float,
        overlap_candles: Optional[int] = None,
    ) -> List[OrderBlock]:
        """Process Order Blocks with overlap analysis."""
        order_blocks = []
        overlap_candles = overlap_candles or self.config.overlap_candles
        
        if len(df) < overlap_candles:
            return order_blocks
        
        last_candles = df.tail(overlap_candles)
        
        for i in range(len(ob_data["OB"])):
            ob_value = ob_data["OB"][i]
            
            if pd.isna(ob_value) or abs(ob_value) != 1:
                continue
            
            ob_top = ob_data["Top"][i]
            ob_bottom = ob_data["Bottom"][i]
            ob_volume = ob_data["OBVolume"][i] if not pd.isna(ob_data["OBVolume"][i]) else 0
            ob_height = ob_top - ob_bottom
            
            # Determine OB type
            ob_type = "bullish" if ob_value == 1 else "bearish"
            
            # Check mitigation
            mitigated_index = ob_data["MitigatedIndex"][i]
            is_mitigated = mitigated_index != 0
            
            # Calculate overlap with recent candles
            total_overlap_ratio = 0.0
            for _, candle in last_candles.iterrows():
                overlap_top = min(ob_top, candle['high'])
                overlap_bottom = max(ob_bottom, candle['low'])
                
                if overlap_top > overlap_bottom:
                    overlap_height = overlap_top - overlap_bottom
                    overlap_ratio = (overlap_height / ob_height) * 100
                    total_overlap_ratio += overlap_ratio
            
            # Calculate distance from current price
            if ob_type == "bullish":
                distance = current_price - ob_top
            else:
                distance = ob_bottom - current_price
            
            distance_pct = (distance / current_price) * 100 if current_price > 0 else 0
            
            order_blocks.append(OrderBlock(
                index=i,
                top=ob_top,
                bottom=ob_bottom,
                volume=ob_volume,
                type=ob_type,
                mitigated=is_mitigated,
                mitigated_index=int(mitigated_index) if is_mitigated else None,
                overlap_ratio=total_overlap_ratio,
                distance_pct=distance_pct,
            ))
        
        return order_blocks
    
    def _process_fvgs(
        self,
        df: pd.DataFrame,
        fvg_data: pd.DataFrame,
    ) -> List[FairValueGap]:
        """Process Fair Value Gaps."""
        fvgs = []
        
        for i in range(len(fvg_data["FVG"])):
            fvg_value = fvg_data["FVG"][i]
            
            if pd.isna(fvg_value):
                continue
            
            fvg_top = fvg_data["Top"][i]
            fvg_bottom = fvg_data["Bottom"][i]
            
            # Determine FVG type (positive = bullish gap)
            fvg_type = "bullish" if fvg_value > 0 else "bearish"
            
            # Check mitigation
            mitigated_index = fvg_data["MitigatedIndex"][i]
            is_mitigated = mitigated_index != 0
            
            fvgs.append(FairValueGap(
                index=i,
                top=fvg_top,
                bottom=fvg_bottom,
                type=fvg_type,
                mitigated=is_mitigated,
                mitigated_index=int(mitigated_index) if is_mitigated else None,
                size=abs(fvg_top - fvg_bottom),
            ))
        
        return fvgs
    
    def _process_liquidity(
        self,
        df: pd.DataFrame,
        liquidity_data: pd.DataFrame,
    ) -> List[LiquidityLevel]:
        """Process Liquidity Levels."""
        levels = []
        
        for i in range(len(liquidity_data["Liquidity"])):
            liq_value = liquidity_data["Liquidity"][i]
            
            if pd.isna(liq_value):
                continue
            
            level = liquidity_data["Level"][i]
            end_index = liquidity_data["End"][i]
            
            # Determine liquidity type
            liq_type = "buy_side" if liq_value > 0 else "sell_side"
            
            # Sweep logic: Price pierces the level but closes inside.
            swept = False
            start_check = int(end_index)
            # Check up to 5 candles after the liquidity level formed/ended
            end_check = min(len(df), start_check + 5)
            for idx in range(start_check, end_check):
                row = df.iloc[idx]
                if liq_type == "buy_side":
                    # Wick higher than BSL, but body closes below it
                    if row['high'] > level and row['close'] < level:
                        swept = True
                        break
                elif liq_type == "sell_side":
                    # Wick lower than SSL, but body closes above it
                    if row['low'] < level and row['close'] > level:
                        swept = True
                        break

            levels.append(LiquidityLevel(
                index=i,
                level=level,
                type=liq_type,
                end_index=int(end_index),
                swept=swept,
            ))
        
        return levels
    
    def _process_structure_breaks(
        self,
        df: pd.DataFrame,
        bos_choch_data: pd.DataFrame,
    ) -> List[StructureBreak]:
        """Process BOS and CHOCH signals."""
        breaks = []
        
        for i in range(len(bos_choch_data["BOS"])):
            bos_value = bos_choch_data["BOS"][i]
            
            if not pd.isna(bos_value):
                level = bos_choch_data["Level"][i]
                broken_index = bos_choch_data["BrokenIndex"][i]
                
                breaks.append(StructureBreak(
                    index=i,
                    level=level,
                    type="bos",
                    direction="bullish" if bos_value > 0 else "bearish",
                    broken_index=int(broken_index),
                ))
        
        for i in range(len(bos_choch_data["CHOCH"])):
            choch_value = bos_choch_data["CHOCH"][i]
            
            if not pd.isna(choch_value):
                level = bos_choch_data["Level"][i]
                broken_index = bos_choch_data["BrokenIndex"][i]
                
                breaks.append(StructureBreak(
                    index=i,
                    level=level,
                    type="choch",
                    direction="bullish" if choch_value > 0 else "bearish",
                    broken_index=int(broken_index),
                ))
        
        # Sort by index
        breaks.sort(key=lambda x: x.index)
        
        return breaks
    
    def _determine_trend(
        self,
        df: pd.DataFrame,
        swing_highs_lows: pd.DataFrame,
    ) -> str:
        """Determine current market trend based on structure."""
        # Get recent swing points
        recent_swings = []
        for i in range(len(swing_highs_lows["HighLow"]) - 1, max(0, len(swing_highs_lows["HighLow"]) - 10), -1):
            if not pd.isna(swing_highs_lows["HighLow"][i]):
                recent_swings.append({
                    'index': i,
                    'type': 'high' if swing_highs_lows["HighLow"][i] == 1 else 'low',
                    'level': swing_highs_lows["Level"][i],
                })
        
        if len(recent_swings) < 2:
            return "neutral"
        
        recent_swings.reverse()  # Oldest to newest
        
        # Check for higher highs and higher lows (bullish)
        # or lower highs and lower lows (bearish)
        highs = [s for s in recent_swings if s['type'] == 'high']
        lows = [s for s in recent_swings if s['type'] == 'low']
        
        if len(highs) >= 2 and len(lows) >= 2:
            if highs[-1]['level'] > highs[-2]['level'] and lows[-1]['level'] > lows[-2]['level']:
                return "bullish"
            elif highs[-1]['level'] < highs[-2]['level'] and lows[-1]['level'] < lows[-2]['level']:
                return "bearish"
        
        return "neutral"
    
    def _determine_premium_discount(
        self,
        df: pd.DataFrame,
        swing_highs_lows: pd.DataFrame,
        current_price: float,
    ) -> str:
        """Determine if current price is in premium, discount, or equilibrium zone."""
        # Find recent swing high and low
        swing_high = None
        swing_low = None
        
        for i in range(len(swing_highs_lows["HighLow"]) - 1, -1, -1):
            if pd.isna(swing_highs_lows["HighLow"][i]):
                continue
            
            level = swing_highs_lows["Level"][i]
            
            if swing_highs_lows["HighLow"][i] == 1 and swing_high is None:
                swing_high = level
            elif swing_highs_lows["HighLow"][i] == -1 and swing_low is None:
                swing_low = level
            
            if swing_high is not None and swing_low is not None:
                break
        
        if swing_high is None or swing_low is None:
            return "equilibrium"
        
        # Calculate equilibrium (50% level)
        range_size = swing_high - swing_low
        equilibrium = swing_low + (range_size * 0.5)
        
        # Define premium and discount zones
        premium_threshold = swing_low + (range_size * 0.7)
        discount_threshold = swing_low + (range_size * 0.3)
        
        if current_price >= premium_threshold:
            return "premium"
        elif current_price <= discount_threshold:
            return "discount"
        else:
            return "equilibrium"


def analyze_ob_overlap(analysis_result: AnalysisResult) -> Dict[str, Any]:
    """Generate overlap analysis statistics."""
    if not analysis_result.order_blocks:
        return {
            'total_obs': 0,
            'active_obs': 0,
            'overlapping_obs': 0,
            'overlap_percentage': 0,
            'avg_overlap_ratio': 0,
        }
    
    total = len(analysis_result.order_blocks)
    active = sum(1 for ob in analysis_result.order_blocks if not ob.mitigated)
    overlapping = sum(1 for ob in analysis_result.order_blocks if ob.overlap_ratio > 0)
    avg_overlap = np.mean([ob.overlap_ratio for ob in analysis_result.order_blocks])
    
    return {
        'total_obs': total,
        'active_obs': active,
        'overlapping_obs': overlapping,
        'overlap_percentage': (overlapping / total * 100) if total > 0 else 0,
        'avg_overlap_ratio': avg_overlap,
    }
