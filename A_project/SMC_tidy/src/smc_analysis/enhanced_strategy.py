"""
Enhanced SMC Strategy with Advanced Quantitative Features
=========================================================

Professional-grade quantitative analysis for Smart Money Concepts.

Key Improvements:
1. Multi-OB Confluence Analysis (多OB叠加分析)
2. Price Distance Scoring (价格距离评分)
3. Volume-Weighted OB Ranking (成交量加权OB排名)
4. Market Regime Detection (市场状态检测)
5. Risk Score Calculation (风险评分)
6. Historical Pattern Recognition (历史模式识别)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import json

import numpy as np
import pandas as pd

from ..smc_analysis import SMCAnalyzer, AnalysisResult, OrderBlock, FairValueGap

logger = logging.getLogger(__name__)


@dataclass
class EnhancedTradingSignal:
    """Enhanced trading signal with comprehensive analysis."""
    symbol: str
    name: str = ""
    timestamp: datetime = None
    
    # Basic signal info
    signal_type: str = "neutral"
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit_1: float = 0.0
    take_profit_2: float = 0.0
    take_profit_3: float = 0.0  # Extended target
    risk_reward_ratio: float = 0.0
    
    # Signal scoring
    signal_strength: float = 0.0
    confidence: float = 0.0
    
    # OB Analysis
    ob_overlap_score: float = 0.0
    ob_confluence_count: int = 0  # Multiple OBs at same level
    ob_distance_score: float = 0.0  # Distance from current price
    ob_volume_score: float = 0.0  # Volume weight
    
    # Market Structure
    trend: str = "neutral"
    zone: str = "equilibrium"
    fvg_alignment: bool = False
    liquidity_sweep: bool = False
    structure_break: bool = False
    market_regime: str = "ranging"  # trending, ranging, choppy
    
    # Risk Assessment
    risk_score: float = 0.0  # 0-100, higher = riskier
    position_size_suggestion: float = 0.0  # Suggested % of portfolio
    
    # Analysis
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    confluence_factors: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'name': self.name,
            'signal_type': self.signal_type,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'take_profit_1': self.take_profit_1,
            'take_profit_2': self.take_profit_2,
            'take_profit_3': self.take_profit_3,
            'risk_reward_ratio': self.risk_reward_ratio,
            'signal_strength': self.signal_strength,
            'confidence': self.confidence,
            'ob_overlap_score': self.ob_overlap_score,
            'ob_confluence_count': self.ob_confluence_count,
            'ob_distance_score': self.ob_distance_score,
            'trend': self.trend,
            'zone': self.zone,
            'market_regime': self.market_regime,
            'risk_score': self.risk_score,
            'position_size_suggestion': self.position_size_suggestion,
            'reasons': self.reasons,
            'warnings': self.warnings,
            'confluence_factors': self.confluence_factors,
        }


@dataclass
class EnhancedStrategyAnalysis:
    """Enhanced strategy analysis result."""
    symbol: str
    name: str = ""
    current_price: float = 0.0
    trend: str = "neutral"
    zone: str = "equilibrium"
    
    # Primary Signal
    primary_signal: Optional[EnhancedTradingSignal] = None
    
    # Raw Analysis Result from underlying SMCAnalyzer
    raw_result: Any = None
    
    # OB Statistics
    total_bullish_obs: int = 0
    total_bearish_obs: int = 0
    active_bullish_obs: int = 0
    active_bearish_obs: int = 0
    overlapping_obs: int = 0
    
    # Confluence Analysis
    high_confluence_obs: int = 0  # OBs with strong overlap
    multi_ob_zones: int = 0  # Zones with multiple OBs
    
    # Market State
    market_regime: str = "ranging"
    volatility: float = 0.0
    momentum: float = 0.0
    
    # Performance Estimates
    estimated_win_rate: float = 0.0
    estimated_rr: float = 0.0
    max_drawdown_risk: float = 0.0
    
    # Overall Assessment
    overall_score: float = 0.0
    recommendation: str = "观望"
    action_priority: str = "low"  # high, medium, low
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'name': self.name,
            'current_price': self.current_price,
            'trend': self.trend,
            'zone': self.zone,
            'primary_signal': self.primary_signal.to_dict() if self.primary_signal else None,
            'total_bullish_obs': self.total_bullish_obs,
            'total_bearish_obs': self.total_bearish_obs,
            'active_bullish_obs': self.active_bullish_obs,
            'active_bearish_obs': self.active_bearish_obs,
            'overlapping_obs': self.overlapping_obs,
            'market_regime': self.market_regime,
            'estimated_win_rate': self.estimated_win_rate,
            'estimated_rr': self.estimated_rr,
            'overall_score': self.overall_score,
            'recommendation': self.recommendation,
            'action_priority': self.action_priority,
        }


class EnhancedSMCStrategy:
    """
    Enhanced SMC Strategy with Advanced Quantitative Analysis.
    
    Key Features:
    1. Multi-OB Confluence Detection
    2. Volume-Weighted Signal Scoring  
    3. Market Regime Classification
    4. Risk-Adjusted Position Sizing
    5. Dynamic Win Rate Estimation
    
    Supports both daily (long-term) and intraday (short-term) analysis.
    """
    
    # Strategy parameters (optimized for Chinese market)
    #MIN_OB_OVERLAP = 30.0

    MIN_OB_OVERLAP = 5.0
    STRONG_OVERLAP = 50.0
    VERY_STRONG_OVERLAP = 70.0
    MIN_RR_RATIO = 2.0
    OPTIMAL_RR_RATIO = 3.0
    
    # OB distance thresholds (adjusted for timeframe)
    CLOSE_OB_DISTANCE_DAILY = 0.02  # 2% from current price
    OPTIMAL_OB_DISTANCE_DAILY = 0.05  # 5% from current price
    CLOSE_OB_DISTANCE_INTRADAY = 0.01  # 1% for 60min
    OPTIMAL_OB_DISTANCE_INTRADAY = 0.03  # 3% for 60min
    
    # Win rate base estimates (from historical SMC performance)
    BASE_WIN_RATE = 45.0
    STRONG_SIGNAL_WIN_RATE = 55.0
    VERY_STRONG_WIN_RATE = 65.0
    
    def __init__(
        self, 
        analyzer: Optional[SMCAnalyzer] = None,
        timeframe: str = "daily",
    ):
        """
        Initialize Enhanced SMC Strategy.
        
        Args:
            analyzer: SMC Analyzer instance
            timeframe: "daily" for long-term or "60min" for short-term
        """
        self.timeframe = timeframe
        
        # Create analyzer with appropriate config
        if analyzer is not None:
            self.analyzer = analyzer
        else:
            self.analyzer = SMCAnalyzer(
                timeframe="daily" if timeframe == "daily" else "intraday"
            )
        
        # Adjust thresholds based on timeframe
        if timeframe == "60min":
            self.close_ob_distance = self.CLOSE_OB_DISTANCE_INTRADAY
            self.optimal_ob_distance = self.OPTIMAL_OB_DISTANCE_INTRADAY
            self.position_size_multiplier = 0.5  # Smaller positions for intraday
        else:
            self.close_ob_distance = self.CLOSE_OB_DISTANCE_DAILY
            self.optimal_ob_distance = self.OPTIMAL_OB_DISTANCE_DAILY
            self.position_size_multiplier = 1.0
    
    def analyze(
        self,
        df: pd.DataFrame,
        symbol: str = "UNKNOWN",
        name: str = "",
    ) -> EnhancedStrategyAnalysis:
        """
        Perform enhanced SMC analysis.
        
        Args:
            df: OHLCV DataFrame
            symbol: Stock symbol
            name: Stock name
            
        Returns:
            EnhancedStrategyAnalysis with comprehensive signals
        """
        # Run base SMC analysis
        result = self.analyzer.analyze(df, symbol=symbol)
        
        # Initialize enhanced analysis
        analysis = EnhancedStrategyAnalysis(
            symbol=symbol,
            name=name,
            current_price=result.current_price,
            trend=result.trend,
            zone=result.premium_discount,
            raw_result=result,
        )
        
        # Calculate OB statistics
        self._calculate_ob_statistics(analysis, result)
        
        # Detect market regime
        analysis.market_regime = self._detect_market_regime(df, result)
        
        # Calculate volatility and momentum
        analysis.volatility = self._calculate_volatility(df)
        analysis.momentum = self._calculate_momentum(df)
        
        # Generate primary signal
        analysis.primary_signal = self._generate_enhanced_signal(df, result, symbol, name)
        
        # Calculate overall score
        analysis.overall_score = self._calculate_overall_score(analysis, result)
        
        # Generate recommendation
        analysis.recommendation = self._generate_recommendation(analysis)
        analysis.action_priority = self._determine_action_priority(analysis)
        
        # Estimate performance
        analysis.estimated_win_rate = self._estimate_win_rate(analysis)
        analysis.estimated_rr = analysis.primary_signal.risk_reward_ratio if analysis.primary_signal else 0
        analysis.max_drawdown_risk = self._estimate_drawdown_risk(analysis)
        
        return analysis
    
    def _calculate_ob_statistics(
        self,
        analysis: EnhancedStrategyAnalysis,
        result: AnalysisResult,
    ) -> None:
        """Calculate comprehensive OB statistics."""
        for ob in result.order_blocks:
            if ob.type == 'bullish':
                analysis.total_bullish_obs += 1
                if not ob.mitigated:
                    analysis.active_bullish_obs += 1
            else:
                analysis.total_bearish_obs += 1
                if not ob.mitigated:
                    analysis.active_bearish_obs += 1
            
            if ob.overlap_ratio > self.MIN_OB_OVERLAP:
                analysis.overlapping_obs += 1
            if ob.overlap_ratio > self.STRONG_OVERLAP:
                analysis.high_confluence_obs += 1
        
        # Detect multi-OB zones (multiple OBs at similar price levels)
        analysis.multi_ob_zones = self._detect_multi_ob_zones(result.order_blocks)
    
    def _detect_multi_ob_zones(self, order_blocks: List[OrderBlock]) -> int:
        """Detect zones with multiple overlapping OBs."""
        if len(order_blocks) < 2:
            return 0
        
        zones = []
        tolerance = 0.03  # 3% price tolerance for minute data
        
        for ob in order_blocks:
            if ob.mitigated:
                continue
            
            ob_level = (ob.top + ob.bottom) / 2
            found_zone = False
            
            for zone in zones:
                if abs(zone['level'] - ob_level) / zone['level'] < tolerance:
                    zone['count'] += 1
                    zone['overlap_sum'] += ob.overlap_ratio
                    found_zone = True
                    break
            
            if not found_zone:
                zones.append({
                    'level': ob_level,
                    'count': 1,
                    'overlap_sum': ob.overlap_ratio,
                })
        
        return sum(1 for z in zones if z['count'] >= 2)
    
    def _detect_market_regime(
        self,
        df: pd.DataFrame,
        result: AnalysisResult,
    ) -> str:
        """Detect current market regime."""
        if len(df) < 50:
            return "unknown"
        
        # Calculate ADX-like indicator
        recent_df = df.tail(50)
        
        high = recent_df['high']
        low = recent_df['low']
        close = recent_df['close']
        
        # True Range
        tr = np.maximum(high - low, np.abs(high - close.shift(1)))
        tr = tr.dropna()
        
        # Average True Range
        atr = tr.rolling(14).mean().iloc[-1]
        
        # Price change
        price_change = (close.iloc[-1] - close.iloc[-20]) / close.iloc[-20]
        
        # Regime detection
        if abs(price_change) > 0.1:  # 10% move in 20 periods
            return "trending"
        elif atr / close.iloc[-1] > 0.03:  # High volatility
            return "choppy"
        else:
            return "ranging"
    
    def _calculate_volatility(self, df: pd.DataFrame) -> float:
        """Calculate current volatility (ATR-based)."""
        if len(df) < 14:
            return 0.0
        
        recent = df.tail(14)
        tr = np.maximum(
            recent['high'] - recent['low'],
            np.abs(recent['high'] - recent['close'].shift(1))
        )
        atr = tr.mean()
        
        return (atr / recent['close'].iloc[-1]) * 100  # As percentage
    
    def _calculate_momentum(self, df: pd.DataFrame) -> float:
        """Calculate price momentum."""
        if len(df) < 10:
            return 0.0
        
        close = df['close']
        momentum = (close.iloc[-1] - close.iloc[-10]) / close.iloc[-10] * 100
        
        return momentum
    
    def _generate_enhanced_signal(
        self,
        df: pd.DataFrame,
        result: AnalysisResult,
        symbol: str,
        name: str,
    ) -> EnhancedTradingSignal:
        """Generate enhanced trading signal."""
        current_price = result.current_price
        
        # Find best OBs
        bullish_obs = [
            ob for ob in result.order_blocks 
            if ob.type == 'bullish' and not ob.mitigated and ob.overlap_ratio > self.MIN_OB_OVERLAP
        ]
        bearish_obs = [
            ob for ob in result.order_blocks 
            if ob.type == 'bearish' and not ob.mitigated and ob.overlap_ratio > self.MIN_OB_OVERLAP
        ]
        
        signal_type = "neutral"
        best_ob = None
        confluence_obs = []
        
        # Long signal logic
        if result.premium_discount == "discount" and bullish_obs:
            # Find OBs within optimal distance
            price_distance = lambda ob: abs(ob.top - current_price) / current_price
            nearby_bullish = [ob for ob in bullish_obs if price_distance(ob) < self.optimal_ob_distance]
            
            if nearby_bullish:
                # Sort by overlap and volume
                nearby_bullish.sort(key=lambda x: (x.overlap_ratio, x.volume), reverse=True)
                best_ob = nearby_bullish[0]
                confluence_obs = [ob for ob in nearby_bullish if abs(ob.top - best_ob.top) / best_ob.top < 0.05]
                signal_type = "long"
                
        # Short signal logic
        if signal_type == "neutral" and result.premium_discount == "premium" and bearish_obs:
            price_distance = lambda ob: abs(ob.bottom - current_price) / current_price
            nearby_bearish = [ob for ob in bearish_obs if price_distance(ob) < self.optimal_ob_distance]
            
            if nearby_bearish:
                # Sort by overlap and volume
                nearby_bearish.sort(key=lambda x: (x.overlap_ratio, x.volume), reverse=True)
                best_ob = nearby_bearish[0]
                confluence_obs = [ob for ob in nearby_bearish if abs(ob.bottom - best_ob.bottom) / best_ob.bottom < 0.05]
                signal_type = "short"
        
        if signal_type == "neutral":
            return self._create_neutral_enhanced_signal(result, symbol, name)
        
        # ATR calculation for Stop Loss Buffer
        recent_df = df.tail(14)
        tr = np.maximum(
            recent_df['high'] - recent_df['low'],
            np.abs(recent_df['high'] - recent_df['close'].shift(1))
        )
        atr = tr.mean()
        # Default fallback to 0.1% if ATR calculation fails
        sl_buffer = max(atr * 0.5, current_price * 0.001) if not pd.isna(atr) else current_price * 0.001

        # Calculate entry, stop, targets
        if signal_type == "long":
            entry_price = best_ob.top
            stop_loss = best_ob.bottom - sl_buffer
            risk = max(entry_price - stop_loss, entry_price * 0.001)
            take_profit_1 = entry_price + risk * 2
            take_profit_2 = entry_price + risk * 3
            take_profit_3 = entry_price + risk * 5
        elif signal_type == "short":
            entry_price = best_ob.bottom
            stop_loss = best_ob.top + sl_buffer
            risk = max(stop_loss - entry_price, entry_price * 0.001)
            take_profit_1 = entry_price - risk * 2
            take_profit_2 = entry_price - risk * 3
            take_profit_3 = entry_price - risk * 5
        
        rr_ratio = 2.0  # Base R:R for TP1
        
        # Calculate enhanced scores
        ob_distance_score = self._calculate_distance_score(best_ob, current_price)
        ob_volume_score = self._calculate_volume_score(best_ob, result.order_blocks)
        
        # Signal strength
        strength = self._calculate_enhanced_strength(
            best_ob, result, confluence_obs, ob_distance_score, ob_volume_score
        )
        
        # Risk score
        risk_score = self._calculate_risk_score(analysis=None, result=result, df=df)
        
        # Position size suggestion
        position_size = self._calculate_position_size(risk_score, strength)
        
        # Build reasons and confluence factors
        reasons = []
        confluence_factors = []
        
        if best_ob.overlap_ratio >= self.VERY_STRONG_OVERLAP:
            reasons.append(f"极强OB双重重叠 ({best_ob.overlap_ratio:.0f}%)")
            confluence_factors.append("OB极强重叠")
        elif best_ob.overlap_ratio >= self.STRONG_OVERLAP:
            reasons.append(f"强OB双重重叠 ({best_ob.overlap_ratio:.0f}%)")
            confluence_factors.append("OB强重叠")
        
        if len(confluence_obs) >= 2:
            reasons.append(f"多OB叠加 ({len(confluence_obs)}个OB)")
            confluence_factors.append("多OB叠加")
        
        if result.premium_discount == "discount" and signal_type == "long":
            reasons.append("价格处于折价区")
            confluence_factors.append("折价区买入")
        elif result.premium_discount == "premium" and signal_type == "short":
            reasons.append("价格处于溢价区")
            confluence_factors.append("溢价区卖出")
        
        if result.trend == signal_type:
            reasons.append(f"趋势方向一致 ({result.trend})")
            confluence_factors.append("趋势一致")
        
        # Check FVG confluence
        aligned_fvgs = [
            fvg for fvg in result.fvg_list
            if not fvg.mitigated and (fvg.type == "bullish" and signal_type == "long")
        ]
        if aligned_fvgs:
            reasons.append(f"FVG方向一致 ({len(aligned_fvgs)}个)")
            confluence_factors.append("FVG一致")
        
        # Check liquidity (Sweep is crucial for institutional entry)
        if any(lvl.swept for lvl in result.liquidity_levels):
            reasons.append("🔥 机构流动性掠夺 (Sweep)")
            confluence_factors.append("Sweep")
            
        if result.liquidity_levels:
            reasons.append(f"流动性储备 ({len(result.liquidity_levels)}个)")
            confluence_factors.append("Liquidity")
        
        # Warnings
        warnings = []
        if result.trend != signal_type and result.trend != "neutral":
            warnings.append(f"趋势方向不匹配")
        
        if ob_distance_score < 50:
            warnings.append("OB距离较远")
        
        if risk_score > 70:
            warnings.append("高风险环境")
        
        return EnhancedTradingSignal(
            symbol=symbol,
            name=name,
            timestamp=datetime.now(),
            signal_type=signal_type,
            entry_price=round(entry_price, 2),
            stop_loss=round(stop_loss, 2),
            take_profit_1=round(take_profit_1, 2),
            take_profit_2=round(take_profit_2, 2),
            take_profit_3=round(take_profit_3, 2),
            risk_reward_ratio=rr_ratio,
            signal_strength=round(strength, 1),
            confidence=round(min(100, strength * 1.1), 1),
            ob_overlap_score=round(best_ob.overlap_ratio, 1),
            ob_confluence_count=len(confluence_obs),
            ob_distance_score=round(ob_distance_score, 1),
            ob_volume_score=round(ob_volume_score, 1),
            trend=result.trend,
            zone=result.premium_discount,
            fvg_alignment=len(aligned_fvgs) > 0,
            liquidity_sweep=any(lvl.swept for lvl in result.liquidity_levels),
            structure_break=len([sb for sb in result.structure_breaks if sb.index > len(df) - 10]) > 0,
            market_regime=self._detect_market_regime(df, result),
            risk_score=round(risk_score, 1),
            position_size_suggestion=round(position_size, 2),
            reasons=reasons,
            warnings=warnings,
            confluence_factors=confluence_factors,
        )
    
    def _create_neutral_enhanced_signal(
        self,
        result: AnalysisResult,
        symbol: str,
        name: str,
    ) -> EnhancedTradingSignal:
        """Create neutral signal."""
        return EnhancedTradingSignal(
            symbol=symbol,
            name=name,
            timestamp=datetime.now(),
            signal_type="neutral",
            entry_price=result.current_price,
            trend=result.trend,
            zone=result.premium_discount,
            reasons=["等待更明确的信号"],
            warnings=["当前无明确交易机会"],
        )
    
    def _calculate_distance_score(
        self,
        ob: OrderBlock,
        current_price: float,
    ) -> float:
        """Calculate OB distance score (closer = higher score)."""
        ob_level = (ob.top + ob.bottom) / 2
        distance_pct = abs(ob_level - current_price) / current_price * 100
        
        if distance_pct < 1:
            return 100
        elif distance_pct < 2:
            return 90
        elif distance_pct < 3:
            return 80
        elif distance_pct < 5:
            return 70
        elif distance_pct < 7:
            return 50
        else:
            return max(0, 50 - (distance_pct - 7) * 5)
    
    def _calculate_volume_score(
        self,
        ob: OrderBlock,
        all_obs: List[OrderBlock],
    ) -> float:
        """Calculate volume-weighted score."""
        if not all_obs:
            return 50
        
        volumes = [o.volume for o in all_obs if o.volume > 0]
        if not volumes:
            return 50
        
        max_vol = max(volumes)
        min_vol = min(volumes)
        
        if max_vol == min_vol:
            return 50
        
        vol_score = (ob.volume - min_vol) / (max_vol - min_vol) * 100
        return vol_score
    
    def _calculate_enhanced_strength(
        self,
        ob: OrderBlock,
        result: AnalysisResult,
        confluence_obs: List[OrderBlock],
        distance_score: float,
        volume_score: float,
    ) -> float:
        """Calculate comprehensive signal strength."""
        score = 0.0
        
        # OB overlap (max 30)
        if ob.overlap_ratio >= self.VERY_STRONG_OVERLAP:
            score += 30
        elif ob.overlap_ratio >= self.STRONG_OVERLAP:
            score += 25
        else:
            score += ob.overlap_ratio * 0.5
        
        # Confluence (max 40) - 大幅提升权重
        # 如果有 2 个 OB，给 30 分；3 个及以上给 40 分
        if len(confluence_obs) >= 2:
            score += 30 if len(confluence_obs) == 2 else 40
        else:
            score += len(confluence_obs) * 5
        
        # Zone alignment (max 15)
        if result.premium_discount == "discount" and ob.type == "bullish":
            score += 15
        elif result.premium_discount == "premium" and ob.type == "bearish":
            score += 15
        
        # Trend alignment (max 10)
        if result.trend == ob.type:
            score += 10
        
        # FVG Alignment (max 15) - 磁吸效应
        if result.fvg_list:
            aligned_fvgs = [f for f in result.fvg_list if not f.mitigated and f.type == ob.type]
            if aligned_fvgs:
                score += 15
        
        # Liquidity Sweep (max 20) - 机构掠夺（扫损后拉回）
        # 极高权重：代表机构在此处进行了止损狩猎
        any_sweep = any(lvl.swept for lvl in result.liquidity_levels)
        if any_sweep:
            score += 20
            
        # Structure Break (max 10) - 结构打破确认
        if result.structure_breaks:
            recent_break = any(sb.index > len(result.ohlcv) - 15 for sb in result.structure_breaks)
            if recent_break:
                score += 10

        # Active OB count (max 7)
        active = sum(1 for o in result.order_blocks if not o.mitigated)
        score += min(7, active)
        
        return min(100, score)
    
    def _calculate_risk_score(
        self,
        analysis: Optional[EnhancedStrategyAnalysis],
        result: AnalysisResult,
        df: pd.DataFrame,
    ) -> float:
        """Calculate risk score (higher = riskier)."""
        risk = 0.0
        
        # Volatility risk
        volatility = self._calculate_volatility(df)
        risk += min(30, volatility * 10)
        
        # Trend conflict risk
        if result.trend not in ["bullish", "bearish"]:
            risk += 15
        
        # OB scarcity risk
        active_obs = sum(1 for o in result.order_blocks if not o.mitigated)
        if active_obs < 2:
            risk += 20
        
        # FVG risk
        active_fvgs = sum(1 for f in result.fvg_list if not f.mitigated)
        if active_fvgs > 5:
            risk += 10  # Too many gaps can be risky
        
        return min(100, risk)
    
    def _calculate_position_size(
        self,
        risk_score: float,
        signal_strength: float,
    ) -> float:
        """Calculate suggested position size (% of portfolio)."""
        # Base position
        base_size = 5.0  # 5% base
        
        # Adjust for risk
        risk_factor = 1 - (risk_score / 150)
        
        # Adjust for signal strength
        strength_factor = signal_strength / 80
        
        position = base_size * risk_factor * strength_factor
        
        return max(1.0, min(10.0, position))
    
    def _calculate_overall_score(
        self,
        analysis: EnhancedStrategyAnalysis,
        result: AnalysisResult,
    ) -> float:
        """Calculate overall opportunity score."""
        if analysis.primary_signal is None:
            return 0.0
        
        score = analysis.primary_signal.signal_strength * 0.5
        
        # Multi-OB zones bonus (max 30) - 显著提升权重
        score += min(30, analysis.multi_ob_zones * 15)
        
        # High confluence OBs bonus (显著提升)
        score += min(15, analysis.high_confluence_obs * 5)
        
        # Active structure bonus
        active_obs = analysis.active_bullish_obs + analysis.active_bearish_obs
        score += min(10, active_obs * 2)
        
        # Market regime alignment
        if analysis.market_regime == "trending" and analysis.trend != "neutral":
            score += 10
        
        return min(100, score)
    
    def _generate_recommendation(self, analysis: EnhancedStrategyAnalysis) -> str:
        """Generate trading recommendation."""
        if analysis.primary_signal is None:
            return "观望"
        
        signal = analysis.primary_signal
        
        if analysis.overall_score >= 70 and signal.signal_type == "long":
            return "强烈买入"
        if analysis.overall_score >= 70 and signal.signal_type == "short":
            return "强烈卖出"
        if analysis.overall_score >= 50 and signal.signal_type == "long":
            return "买入"
        if analysis.overall_score >= 50 and signal.signal_type == "short":
            return "卖出"
        if analysis.overall_score >= 35:
            return "轻仓试探"
        
        return "观望"
    
    def _determine_action_priority(self, analysis: EnhancedStrategyAnalysis) -> str:
        """Determine action priority level."""
        if analysis.overall_score >= 70:
            return "high"
        elif analysis.overall_score >= 50:
            return "medium"
        else:
            return "low"
    
    def _estimate_win_rate(self, analysis: EnhancedStrategyAnalysis) -> float:
        """Estimate win rate based on signal characteristics."""
        if analysis.primary_signal is None:
            return self.BASE_WIN_RATE
        
        signal = analysis.primary_signal
        
        # Base rate
        win_rate = self.BASE_WIN_RATE
        
        # Adjust for OB overlap
        if signal.ob_overlap_score >= self.VERY_STRONG_OVERLAP:
            win_rate += 15
        elif signal.ob_overlap_score >= self.STRONG_OVERLAP:
            win_rate += 10
        elif signal.ob_overlap_score >= self.MIN_OB_OVERLAP:
            win_rate += 5
        
        # Adjust for confluence
        if signal.ob_confluence_count >= 2:
            win_rate += 8
        
        # Adjust for zone
        if analysis.zone in ["premium", "discount"]:
            win_rate += 5
        
        # Adjust for trend alignment
        if signal.trend == analysis.trend:
            win_rate += 5
        
        # Adjust for FVG
        if signal.fvg_alignment:
            win_rate += 3
        
        # Adjust for risk (inverse)
        win_rate -= signal.risk_score * 0.1
        
        return min(70, max(35, win_rate))
    
    def _estimate_drawdown_risk(self, analysis: EnhancedStrategyAnalysis) -> float:
        """Estimate maximum drawdown risk."""
        if analysis.primary_signal is None:
            return 5.0
        
        # Risk based on volatility and signal characteristics
        base_risk = 5.0
        base_risk += analysis.volatility * 0.5
        base_risk += analysis.primary_signal.risk_score * 0.05
        
        return min(25.0, base_risk)


def batch_enhanced_analyze(
    data_dir: Path,
    output_dir: Path,
) -> List[EnhancedStrategyAnalysis]:
    """Batch analyze all stocks with enhanced strategy."""
    strategy = EnhancedSMCStrategy()
    results = []
    
    csv_files = list(data_dir.glob("*_smc.csv"))
    if not csv_files:
        csv_files = list(data_dir.glob("*.csv"))
    
    for csv_file in csv_files:
        try:
            df = pd.read_csv(csv_file)
            
            # Extract symbol and name from filename
            stem = csv_file.stem.replace("_smc", "").replace("_daily", "")
            parts = stem.split("_")
            symbol = parts[0] if parts else "UNKNOWN"
            name = parts[1] if len(parts) > 1 else ""
            
            analysis = strategy.analyze(df, symbol, name)
            results.append(analysis)
            
            logger.debug(f"Analyzed {symbol}: Score {analysis.overall_score:.1f}")
            
        except Exception as e:
            logger.error(f"Error analyzing {csv_file}: {e}")
    
    return results
