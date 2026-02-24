"""
Advanced SMC Trading Strategy Analysis Module
==============================================

Professional quantitative analysis for Smart Money Concepts trading.

Key Features:
- Order Block Double Overlap Strategy (OB底部买盘双重重叠)
- Premium/Discount Zone Analysis
- Market Structure Analysis
- Win Rate & Risk/Reward Calculation
- Signal Strength Scoring
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import json

import numpy as np
import pandas as pd

from ..smc_analysis import SMCAnalyzer, AnalysisResult, OrderBlock

logger = logging.getLogger(__name__)


@dataclass
class TradingSignal:
    """Trading signal with detailed analysis."""
    symbol: str
    timestamp: datetime
    signal_type: str  # 'long', 'short', 'neutral'
    entry_price: float
    stop_loss: float
    take_profit_1: float
    take_profit_2: float
    risk_reward_ratio: float
    signal_strength: float  # 0-100
    confidence: float  # 0-100
    
    # Signal components
    ob_overlap_score: float = 0.0
    fvg_alignment: bool = False
    liquidity_sweep: bool = False
    structure_break: bool = False
    premium_discount: str = "equilibrium"
    
    # Reasoning
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp.isoformat(),
            'signal_type': self.signal_type,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'take_profit_1': self.take_profit_1,
            'take_profit_2': self.take_profit_2,
            'risk_reward_ratio': self.risk_reward_ratio,
            'signal_strength': self.signal_strength,
            'confidence': self.confidence,
            'ob_overlap_score': self.ob_overlap_score,
            'fvg_alignment': self.fvg_alignment,
            'liquidity_sweep': self.liquidity_sweep,
            'structure_break': self.structure_break,
            'premium_discount': self.premium_discount,
            'reasons': self.reasons,
            'warnings': self.warnings,
        }


@dataclass
class StrategyAnalysis:
    """Complete strategy analysis result."""
    symbol: str
    name: str = ""  # 股票名称
    current_price: float = 0.0
    trend: str = "neutral"
    zone: str = "equilibrium"
    
    # Signals
    primary_signal: Optional[TradingSignal] = None
    secondary_signals: List[TradingSignal] = field(default_factory=list)
    
    # Statistics
    active_bullish_obs: int = 0
    active_bearish_obs: int = 0
    overlapping_obs: int = 0
    
    # Win rate estimation
    historical_win_rate: float = 0.0
    estimated_rr: float = 0.0
    
    # Overall assessment
    overall_score: float = 0.0
    recommendation: str = "HOLD"
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'current_price': self.current_price,
            'trend': self.trend,
            'zone': self.zone,
            'primary_signal': self.primary_signal.to_dict() if self.primary_signal else None,
            'active_bullish_obs': self.active_bullish_obs,
            'active_bearish_obs': self.active_bearish_obs,
            'overlapping_obs': self.overlapping_obs,
            'historical_win_rate': self.historical_win_rate,
            'estimated_rr': self.estimated_rr,
            'overall_score': self.overall_score,
            'recommendation': self.recommendation,
        }


class AdvancedSMCStrategy:
    """
    Advanced SMC Trading Strategy Analyzer.
    
    Key Strategies:
    1. OB Double Overlap - 底部买盘订单块双重重叠
    2. Premium/Discount Entry - 溢价/折价区入场
    3. Structure Break Confirmation - 结构突破确认
    4. FVG Fill Strategy - 公允价值缺口回补
    5. Liquidity Sweep - 流动性扫荡
    """
    
    # Strategy parameters
    MIN_OB_OVERLAP = 30.0  # Minimum overlap percentage for signal
    STRONG_OVERLAP = 50.0  # Strong overlap threshold
    MIN_RR_RATIO = 2.0    # Minimum risk/reward ratio
    
    def __init__(self, analyzer: Optional[SMCAnalyzer] = None):
        self.analyzer = analyzer or SMCAnalyzer()
    
    def analyze_strategy(
        self,
        df: pd.DataFrame,
        symbol: str = "UNKNOWN",
    ) -> StrategyAnalysis:
        """
        Perform complete strategy analysis.
        
        Args:
            df: OHLCV DataFrame
            symbol: Stock symbol
            
        Returns:
            StrategyAnalysis with signals and recommendations
        """
        # Run base SMC analysis
        result = self.analyzer.analyze(df, symbol=symbol)
        
        # Initialize strategy analysis
        analysis = StrategyAnalysis(
            symbol=symbol,
            current_price=result.current_price,
            trend=result.trend,
            zone=result.premium_discount,
            active_bullish_obs=sum(1 for ob in result.order_blocks if ob.type == 'bullish' and not ob.mitigated),
            active_bearish_obs=sum(1 for ob in result.order_blocks if ob.type == 'bearish' and not ob.mitigated),
            overlapping_obs=sum(1 for ob in result.order_blocks if ob.overlap_ratio > self.MIN_OB_OVERLAP),
        )
        
        # Generate primary signal
        analysis.primary_signal = self._generate_primary_signal(df, result)
        
        # Calculate overall score
        analysis.overall_score = self._calculate_overall_score(analysis, result)
        
        # Generate recommendation
        analysis.recommendation = self._generate_recommendation(analysis)
        
        # Estimate win rate based on signal quality
        analysis.historical_win_rate = self._estimate_win_rate(analysis, result)
        analysis.estimated_rr = analysis.primary_signal.risk_reward_ratio if analysis.primary_signal else 0.0
        
        return analysis
    
    def _generate_primary_signal(
        self,
        df: pd.DataFrame,
        result: AnalysisResult,
    ) -> Optional[TradingSignal]:
        """Generate primary trading signal."""
        current_price = result.current_price
        
        # Find best bullish OB (for long signals)
        bullish_obs = [
            ob for ob in result.order_blocks 
            if ob.type == 'bullish' 
            and not ob.mitigated 
            and ob.overlap_ratio > self.MIN_OB_OVERLAP
        ]
        
        # Determine signal direction based on zone and OBs
        signal_type = "neutral"
        best_ob = None
        
        # Long signal conditions:
        # 1. Price in discount zone
        # 2. Active bullish OB with overlap
        # 3. Trend is bullish or neutral
        if result.premium_discount == "discount" and bullish_obs:
            # Find closest bullish OB above current price
            nearby_bullish = [ob for ob in bullish_obs if ob.bottom <= current_price]
            if nearby_bullish:
                best_ob = max(nearby_bullish, key=lambda x: x.overlap_ratio)
                signal_type = "long"
        
        # If no clear signal, check for structure breaks
        if signal_type == "neutral":
            recent_breaks = [
                sb for sb in result.structure_breaks
                if sb.index > len(df) - 20  # Recent 20 candles
            ]
            if recent_breaks:
                last_break = recent_breaks[-1]
                if last_break.type == "bos" and last_break.direction == "bullish":
                    signal_type = "long"
        
        if signal_type == "neutral" or best_ob is None:
            # Still generate a neutral signal with analysis
            return self._create_neutral_signal(result)
        
        # Calculate levels
        if signal_type == "long":
            entry_price = best_ob.bottom
            stop_loss = best_ob.bottom - (best_ob.top - best_ob.bottom) * 0.1  # 10% below OB
            take_profit_1 = current_price + (current_price - stop_loss) * 2  # 2R
            take_profit_2 = current_price + (current_price - stop_loss) * 3  # 3R
        
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit_1 - entry_price)
        rr_ratio = reward / risk if risk > 0 else 0
        
        # Calculate signal strength
        strength = self._calculate_signal_strength(best_ob, result)
        
        # Generate reasons
        reasons = []
        if best_ob.overlap_ratio > self.STRONG_OVERLAP:
            reasons.append(f"强OB双重重叠 ({best_ob.overlap_ratio:.0f}%)")
        elif best_ob.overlap_ratio > self.MIN_OB_OVERLAP:
            reasons.append(f"OB重叠 ({best_ob.overlap_ratio:.0f}%)")
        
        if result.premium_discount == "discount" and signal_type == "long":
            reasons.append("价格处于折价区")
        
        if result.trend == signal_type:
            reasons.append(f"趋势方向一致 ({result.trend})")
        
        # Check FVG alignment
        fvg_alignment = any(
            fvg.type == "bullish" and signal_type == "long"
            for fvg in result.fvg_list[-3:]  # Recent FVGs
        )
        if fvg_alignment:
            reasons.append("FVG方向一致")
        
        # Generate warnings
        warnings = []
        if result.trend != signal_type and result.trend != "neutral":
            warnings.append(f"趋势方向不匹配 (当前: {result.trend})")
        
        if rr_ratio < self.MIN_RR_RATIO:
            warnings.append(f"盈亏比不足 ({rr_ratio:.1f})")
        
        return TradingSignal(
            symbol=result.symbol,
            timestamp=datetime.now(),
            signal_type=signal_type,
            entry_price=round(entry_price, 2),
            stop_loss=round(stop_loss, 2),
            take_profit_1=round(take_profit_1, 2),
            take_profit_2=round(take_profit_2, 2),
            risk_reward_ratio=round(rr_ratio, 2),
            signal_strength=round(strength, 1),
            confidence=round(min(100, strength * 1.2), 1),
            ob_overlap_score=round(best_ob.overlap_ratio, 1),
            fvg_alignment=fvg_alignment,
            liquidity_sweep=any(lvl.swept for lvl in result.liquidity_levels),
            structure_break=len([sb for sb in result.structure_breaks if sb.index > len(df) - 10]) > 0,
            premium_discount=result.premium_discount,
            reasons=reasons,
            warnings=warnings,
        )
    
    def _create_neutral_signal(self, result: AnalysisResult) -> TradingSignal:
        """Create neutral signal with analysis."""
        return TradingSignal(
            symbol=result.symbol,
            timestamp=datetime.now(),
            signal_type="neutral",
            entry_price=result.current_price,
            stop_loss=0.0,
            take_profit_1=0.0,
            take_profit_2=0.0,
            risk_reward_ratio=0.0,
            signal_strength=0.0,
            confidence=0.0,
            premium_discount=result.premium_discount,
            reasons=["等待更明确的信号"],
            warnings=["当前无明确交易机会"],
        )
    
    def _calculate_signal_strength(
        self,
        ob: OrderBlock,
        result: AnalysisResult,
    ) -> float:
        """Calculate signal strength score (0-100)."""
        score = 0.0
        
        # OB overlap score (max 40 points)
        if ob.overlap_ratio >= self.STRONG_OVERLAP:
            score += 40
        elif ob.overlap_ratio >= self.MIN_OB_OVERLAP:
            score += ob.overlap_ratio * 0.8
        
        # Zone alignment (max 20 points)
        if result.premium_discount == "discount" and ob.type == "bullish":
            score += 20
        elif result.premium_discount == "premium" and ob.type == "bearish":
            score += 20
        
        # Trend alignment (max 15 points)
        if result.trend == ob.type:
            score += 15
        elif result.trend == "neutral":
            score += 7.5
        
        # Active OB count (max 10 points)
        active_count = sum(1 for o in result.order_blocks if not o.mitigated)
        score += min(10, active_count * 2)
        
        # Recent FVG alignment (max 10 points)
        recent_fvgs = [fvg for fvg in result.fvg_list if not fvg.mitigated]
        aligned_fvgs = [fvg for fvg in recent_fvgs if fvg.type == ob.type]
        score += min(10, len(aligned_fvgs) * 3)
        
        # Structure break (max 5 points)
        recent_breaks = [sb for sb in result.structure_breaks if sb.type == "bos"]
        if recent_breaks:
            score += 5
        
        return min(100, score)
    
    def _calculate_overall_score(
        self,
        analysis: StrategyAnalysis,
        result: AnalysisResult,
    ) -> float:
        """Calculate overall opportunity score."""
        if analysis.primary_signal is None:
            return 0.0
        
        score = analysis.primary_signal.signal_strength * 0.6
        
        # Add points for multiple overlapping OBs
        if analysis.overlapping_obs >= 2:
            score += 10
        elif analysis.overlapping_obs >= 1:
            score += 5
        
        # Add points for active structure
        score += min(10, analysis.active_bullish_obs + analysis.active_bearish_obs)
        
        return min(100, score)
    
    def _generate_recommendation(self, analysis: StrategyAnalysis) -> str:
        """Generate trading recommendation."""
        if analysis.primary_signal is None:
            return "观望"
        
        if analysis.overall_score >= 70:
            if analysis.primary_signal.signal_type == "long":
                return "强烈买入"
            elif analysis.primary_signal.signal_type == "short":
                return "强烈卖出"
        
        if analysis.overall_score >= 50:
            if analysis.primary_signal.signal_type == "long":
                return "买入"
            elif analysis.primary_signal.signal_type == "short":
                return "卖出"
        
        if analysis.overall_score >= 30:
            return "观望/轻仓"
        
        return "观望"
    
    def _estimate_win_rate(
        self,
        analysis: StrategyAnalysis,
        result: AnalysisResult,
    ) -> float:
        """
        Estimate historical win rate based on signal characteristics.
        
        This is a simplified estimation based on typical SMC strategy performance.
        """
        base_win_rate = 45.0  # Base win rate
        
        if analysis.primary_signal is None:
            return base_win_rate
        
        # Adjust based on signal strength
        base_win_rate += analysis.primary_signal.signal_strength * 0.2
        
        # Adjust for OB overlap
        if analysis.primary_signal.ob_overlap_score >= self.STRONG_OVERLAP:
            base_win_rate += 10
        elif analysis.primary_signal.ob_overlap_score >= self.MIN_OB_OVERLAP:
            base_win_rate += 5
        
        # Adjust for zone
        if analysis.zone != "equilibrium":
            base_win_rate += 5
        
        # Adjust for trend alignment
        if result.trend == analysis.primary_signal.signal_type:
            base_win_rate += 8
        
        # Adjust for FVG alignment
        if analysis.primary_signal.fvg_alignment:
            base_win_rate += 5
        
        return min(70, base_win_rate)  # Cap at 70%


def batch_analyze_strategies(
    data_dir: Path,
    output_dir: Path,
) -> List[StrategyAnalysis]:
    """
    Batch analyze all stocks in a directory.
    
    Args:
        data_dir: Directory with SMC format CSV files
        output_dir: Output directory for results
        
    Returns:
        List of StrategyAnalysis results
    """
    strategy = AdvancedSMCStrategy()
    results = []
    
    csv_files = list(data_dir.glob("*_smc.csv"))
    
    for csv_file in csv_files:
        try:
            df = pd.read_csv(csv_file)
            symbol = csv_file.stem.replace("_smc", "").split("_")[0]
            
            analysis = strategy.analyze_strategy(df, symbol)
            results.append(analysis)
            
            logger.debug(f"Analyzed {symbol}: Score {analysis.overall_score:.1f}, Rec: {analysis.recommendation}")
            
        except Exception as e:
            logger.error(f"Error analyzing {csv_file}: {e}")
    
    return results
