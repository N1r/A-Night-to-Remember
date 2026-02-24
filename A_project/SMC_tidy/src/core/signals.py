"""
SMC Signal Generator & Risk Manager
===================================

机构级交易信号生成与风险管理模块。

核心功能:
    - 信号生成器: 基于SMC组件生成高置信度交易信号
    - 风险管理器: 计算仓位、止损止盈、风险评分
    - 机构级信号输出: 完整的交易参数与风险指标
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd

from .types import (
    OrderBlock, OBType,
    FairValueGap, FVGType,
    StructureBreak, BreakType,
    MarketState, ZoneType, TrendDirection,
    AnalysisOutput, SignalType,
)
from .engine import AnalysisOutput

logger = logging.getLogger(__name__)


@dataclass
class InstitutionalSignal:
    """
    机构级交易信号数据结构
    
    包含完整的交易参数、风险评估和决策依据，
    符合机构交易员的信息需求。
    
    核心参数:
        - 入场价、止损价、止盈目标
        - 风险回报比 (R:R)
        - 建议仓位百分比
        
    信号评估:
        - 信号强度评分 (0-100)
        - 置信度评分 (0-100)
        - 胜率预估
        
    风险指标:
        - 风险评分 (0-100, 越高风险越大)
        - 最大回撤预估
        - 建议仓位
    """
    symbol: str
    name: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    timeframe: str = "daily"
    
    # 基础信号信息
    signal_type: SignalType = SignalType.NEUTRAL
    direction: str = "neutral"
    
    # 交易参数
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit_1: float = 0.0    # 目标1 (2R)
    take_profit_2: float = 0.0    # 目标2 (3R)
    take_profit_3: float = 0.0    # 目标3 (5R)
    
    # 风险参数
    risk_reward_ratio: float = 0.0
    risk_amount: float = 0.0      # 单位风险 (入场-止损)
    risk_percent: float = 2.0     # 建议风险百分比
    
    # 信号评分
    signal_strength: float = 0.0  # 信号强度 (0-100)
    confidence: float = 0.0       # 置信度 (0-100)
    estimated_win_rate: float = 0.0  # 预估胜率
    
    # OB 分析
    ob_overlap_score: float = 0.0
    ob_confluence_count: int = 0
    ob_distance_score: float = 0.0
    ob_volume_score: float = 0.0
    
    # 市场状态
    trend: TrendDirection = TrendDirection.NEUTRAL
    zone: ZoneType = ZoneType.EQUILIBRIUM
    fvg_alignment: bool = False
    liquidity_sweep: bool = False
    structure_break: bool = False
    market_regime: str = "ranging"
    
    # 风险评估
    risk_score: float = 0.0       # 综合风险评分
    volatility_risk: float = 0.0
    trend_risk: float = 0.0
    position_size_pct: float = 0.0  # 建议仓位百分比
    max_drawdown_risk: float = 0.0
    
    # 决策依据
    reasons: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    confluence_factors: List[str] = field(default_factory=list)
    
    @property
    def is_long(self) -> bool:
        return self.signal_type == SignalType.LONG
    
    @property
    def is_short(self) -> bool:
        return self.signal_type == SignalType.SHORT
    
    @property
    def is_actionable(self) -> bool:
        return self.signal_type != SignalType.NEUTRAL and self.signal_strength >= 40
    
    @property
    def risk_per_share(self) -> float:
        """每股风险金额"""
        return abs(self.entry_price - self.stop_loss)
    
    @property
    def reward_per_share(self) -> float:
        """每股潜在收益 (TP1)"""
        return abs(self.take_profit_1 - self.entry_price)
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "symbol": self.symbol,
            "name": self.name,
            "timestamp": self.timestamp.isoformat(),
            "timeframe": self.timeframe,
            "signal_type": self.signal_type.value,
            "direction": self.direction,
            "entry_price": round(self.entry_price, 4),
            "stop_loss": round(self.stop_loss, 4),
            "take_profit_1": round(self.take_profit_1, 4),
            "take_profit_2": round(self.take_profit_2, 4),
            "take_profit_3": round(self.take_profit_3, 4),
            "risk_reward_ratio": round(self.risk_reward_ratio, 2),
            "signal_strength": round(self.signal_strength, 1),
            "confidence": round(self.confidence, 1),
            "estimated_win_rate": round(self.estimated_win_rate, 1),
            "ob_overlap_score": round(self.ob_overlap_score, 1),
            "ob_confluence_count": self.ob_confluence_count,
            "trend": self.trend.value,
            "zone": self.zone.value,
            "fvg_alignment": self.fvg_alignment,
            "liquidity_sweep": self.liquidity_sweep,
            "structure_break": self.structure_break,
            "risk_score": round(self.risk_score, 1),
            "position_size_pct": round(self.position_size_pct, 2),
            "reasons": self.reasons,
            "warnings": self.warnings,
            "confluence_factors": self.confluence_factors,
            "is_actionable": self.is_actionable,
        }


class RiskManager:
    """
    风险管理器
    
    基于账户规模、风险偏好和市场波动率，
    计算最优仓位大小和风险参数。
    
    核心方法:
        - calculate_position_size: 计算仓位大小
        - calculate_stop_loss: 计算止损位置
        - calculate_take_profits: 计算止盈目标
        - assess_risk: 评估综合风险
    """
    
    # 默认风险参数
    DEFAULT_RISK_PER_TRADE = 0.02  # 单笔风险 2%
    MAX_RISK_PER_TRADE = 0.05      # 最大单笔风险 5%
    MIN_RISK_REWARD = 2.0          # 最小盈亏比
    OPTIMAL_RISK_REWARD = 3.0      # 最优盈亏比
    
    def __init__(
        self,
        account_size: float = 100000.0,
        risk_per_trade: float = 0.02,
        max_position_pct: float = 0.10,
    ):
        """
        初始化风险管理器
        
        Args:
            account_size: 账户规模
            risk_per_trade: 单笔风险比例 (默认 2%)
            max_position_pct: 最大仓位比例 (默认 10%)
        """
        self.account_size = account_size
        self.risk_per_trade = min(risk_per_trade, self.MAX_RISK_PER_TRADE)
        self.max_position_pct = max_position_pct
    
    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss: float,
        atr: Optional[float] = None,
        volatility_factor: float = 1.0,
    ) -> float:
        """
        计算建议仓位大小 (股数)
        
        基于固定风险比例法 (Fixed Fractional):
            仓位 = (账户 × 风险比例) / (入场价 - 止损价)
        
        Args:
            entry_price: 入场价格
            stop_loss: 止损价格
            atr: 当前 ATR (用于调整仓位)
            volatility_factor: 波动率调整因子
            
        Returns:
            float: 建议买入股数
        """
        if entry_price == 0 or stop_loss == 0:
            return 0.0
        
        risk_per_share = abs(entry_price - stop_loss)
        if risk_per_share == 0:
            return 0.0
        
        # 固定风险金额
        risk_amount = self.account_size * self.risk_per_trade
        
        # 波动率调整
        if atr and atr > 0:
            # 高波动环境下减少仓位
            vol_adjustment = min(1.0, atr / risk_per_share)
            risk_amount *= vol_adjustment
        
        # 计算股数
        shares = risk_amount / risk_per_share
        
        # 应用最大仓位限制
        max_shares = (self.account_size * self.max_position_pct) / entry_price
        shares = min(shares, max_shares)
        
        return round(shares, 0)
    
    def calculate_position_pct(
        self,
        entry_price: float,
        stop_loss: float,
    ) -> float:
        """
        计算仓位百分比
        
        Args:
            entry_price: 入场价格
            stop_loss: 止损价格
            
        Returns:
            float: 建议仓位百分比 (0-100)
        """
        if entry_price == 0:
            return 0.0
        
        shares = self.calculate_position_size(entry_price, stop_loss)
        position_value = shares * entry_price
        position_pct = (position_value / self.account_size) * 100
        
        return min(position_pct, self.max_position_pct * 100)
    
    def calculate_stop_loss(
        self,
        entry_price: float,
        ob: OrderBlock,
        atr: float,
        is_long: bool = True,
    ) -> float:
        """
        计算止损价格
        
        策略:
            - 看涨: 止损设在OB底部下方 (留出ATR缓冲)
            - 看跌: 止损设在OB顶部上方
            
        Args:
            entry_price: 入场价格
            ob: 订单块对象
            atr: 当前 ATR
            is_long: 是否为做多信号
            
        Returns:
            float: 止损价格
        """
        buffer = atr * 0.5 if atr > 0 else entry_price * 0.005
        
        if is_long:
            # 做多止损 = OB底部 - 缓冲
            return ob.bottom - buffer
        else:
            # 做空止损 = OB顶部 + 缓冲
            return ob.top + buffer
    
    def calculate_take_profits(
        self,
        entry_price: float,
        stop_loss: float,
        is_long: bool = True,
    ) -> Tuple[float, float, float]:
        """
        计算止盈目标
        
        采用多目标策略:
            - TP1: 2R (保守目标)
            - TP2: 3R (标准目标)
            - TP3: 5R (激进目标)
            
        Args:
            entry_price: 入场价格
            stop_loss: 止损价格
            is_long: 是否为做多信号
            
        Returns:
            Tuple[float, float, float]: TP1, TP2, TP3
        """
        risk = abs(entry_price - stop_loss)
        
        if is_long:
            tp1 = entry_price + risk * 2
            tp2 = entry_price + risk * 3
            tp3 = entry_price + risk * 5
        else:
            tp1 = entry_price - risk * 2
            tp2 = entry_price - risk * 3
            tp3 = entry_price - risk * 5
        
        return round(tp1, 4), round(tp2, 4), round(tp3, 4)
    
    def assess_risk(
        self,
        signal: InstitutionalSignal,
        output: AnalysisOutput,
    ) -> float:
        """
        评估综合风险评分
        
        风险来源:
            1. 波动率风险: 高波动率增加不确定性
            2. 趋势风险: 趋势方向与信号方向不一致
            3. 区域风险: 价格处于不利区域
            4. OB稀缺风险: 活跃OB数量不足
            5. 流动性风险: 缺乏流动性目标
            
        Args:
            signal: 交易信号
            output: SMC分析输出
            
        Returns:
            float: 综合风险评分 (0-100)
        """
        risk = 0.0
        state = output.market_state
        
        # 波动率风险 (最大 25 分)
        vol_risk = min(25, state.volatility * 8)
        risk += vol_risk
        
        # 趋势风险 (最大 20 分)
        if signal.signal_type == SignalType.LONG and state.trend == TrendDirection.BEARISH:
            risk += 20
        elif signal.signal_type == SignalType.SHORT and state.trend == TrendDirection.BULLISH:
            risk += 20
        elif state.trend == TrendDirection.NEUTRAL:
            risk += 10
        
        # 区域风险 (最大 15 分)
        if signal.signal_type == SignalType.LONG and state.zone == ZoneType.PREMIUM:
            risk += 15
        elif signal.signal_type == SignalType.SHORT and state.zone == ZoneType.DISCOUNT:
            risk += 15
        
        # OB稀缺风险 (最大 20 分)
        active_obs = state.active_bullish_obs + state.active_bearish_obs
        if active_obs < 2:
            risk += 20
        elif active_obs < 4:
            risk += 10
        
        # 流动性风险 (最大 10 分)
        if state.total_liquidity_levels == 0:
            risk += 10
        elif state.swept_liquidity > state.total_liquidity_levels * 0.5:
            risk += 5  # 大部分流动性已被扫荡
        
        # 结构风险 (最大 10 分)
        recent_breaks = output.get_recent_breaks(20)
        if not recent_breaks:
            risk += 10  # 缺乏近期结构突破
        
        return min(100, risk)


class SignalGenerator:
    """
    交易信号生成器
    
    基于 SMC 分析结果，生成机构级交易信号。
    
    核心策略 (单向做多):
        1. OB双重重叠策略
            - 在折价区寻找买盘OB双重重叠
            - 只做多，不做空
            
        2. 融合因素分析
            - FVG方向一致
            - 流动性目标存在
            - 结构突破确认
            
        3. 风险调整
            - 根据波动率调整止损缓冲
            - 根据信号强度调整仓位
    
    使用示例:
        >>> generator = SignalGenerator()
        >>> signal = generator.generate(output, symbol="000001", name="平安银行")
        >>> print(signal.to_dict())
    """
    
    # 策略参数
    MIN_OB_OVERLAP = 15.0       # 最小OB重叠度 (降低阈值)
    STRONG_OB_OVERLAP = 30.0    # 强OB重叠度
    VERY_STRONG_OB_OVERLAP = 50.0  # 极强OB重叠度
    MIN_SIGNAL_STRENGTH = 40.0  # 最小可交易信号强度
    
    # 胜率基准 (基于历史SMC策略表现)
    BASE_WIN_RATE = 45.0
    STRONG_SIGNAL_WIN_RATE = 55.0
    VERY_STRONG_WIN_RATE = 65.0
    
    # 单向做多模式
    LONG_ONLY = True  # 只做多，不做空
    
    def __init__(self, risk_manager: Optional[RiskManager] = None):
        """
        初始化信号生成器
        
        Args:
            risk_manager: 风险管理器实例
        """
        self.risk_manager = risk_manager or RiskManager()
    
    def generate(
        self,
        output: AnalysisOutput,
        symbol: str = "UNKNOWN",
        name: str = "",
    ) -> InstitutionalSignal:
        """
        生成交易信号 (单向做多模式)
        
        Args:
            output: SMC 分析输出
            symbol: 股票代码
            name: 股票名称
            
        Returns:
            InstitutionalSignal: 完整的交易信号 (只做多或观望)
        """
        signal = InstitutionalSignal(
            symbol=symbol,
            name=name,
            timeframe=output.timeframe,
            trend=output.market_state.trend,
            zone=output.market_state.zone,
        )
        
        state = output.market_state
        
        # 单向做多模式：只寻找买盘OB
        best_ob = self._find_best_bullish_ob(output)
        
        if best_ob is None:
            signal.signal_type = SignalType.NEUTRAL
            signal.reasons = ["等待折价区买盘OB"]
            signal.warnings = ["当前无做多机会"]
            return signal
        
        # 单向做多：信号类型固定为 long
        signal.signal_type = SignalType.LONG
        signal.direction = "long"
        
        # 计算交易参数
        signal.entry_price = best_ob.bottom
        signal.stop_loss = self.risk_manager.calculate_stop_loss(
            signal.entry_price, best_ob, state.atr, is_long=True
        )
        
        tp1, tp2, tp3 = self.risk_manager.calculate_take_profits(
            signal.entry_price, signal.stop_loss, is_long=True
        )
        signal.take_profit_1 = tp1
        signal.take_profit_2 = tp2
        signal.take_profit_3 = tp3
        
        # 计算盈亏比
        risk = abs(signal.entry_price - signal.stop_loss)
        reward = abs(signal.take_profit_1 - signal.entry_price)
        signal.risk_reward_ratio = reward / risk if risk > 0 else 0
        
        # OB 分析指标
        signal.ob_overlap_score = best_ob.overlap_ratio
        signal.ob_confluence_count = best_ob.confluence_count
        signal.ob_distance_score = self._calculate_distance_score(best_ob, state.current_price)
        signal.ob_volume_score = self._calculate_volume_score(best_ob, output.order_blocks)
        
        # 融合因素检查
        signal.fvg_alignment = self._check_fvg_alignment(output, SignalType.LONG)
        signal.liquidity_sweep = any(ll.swept for ll in output.liquidity_levels)
        signal.structure_break = len(output.get_recent_breaks(20)) > 0
        signal.market_regime = self._detect_market_regime(output)
        
        # 计算信号强度
        signal.signal_strength = self._calculate_signal_strength(
            best_ob, output, signal
        )
        signal.confidence = min(100, signal.signal_strength * 1.1)
        
        # 风险评估
        signal.risk_score = self.risk_manager.assess_risk(signal, output)
        signal.position_size_pct = self.risk_manager.calculate_position_pct(
            signal.entry_price, signal.stop_loss
        )
        
        # 预估胜率
        signal.estimated_win_rate = self._estimate_win_rate(signal, output)
        
        # 生成原因和警告
        signal.reasons = self._generate_reasons(best_ob, output, signal)
        signal.warnings = self._generate_warnings(signal, output)
        signal.confluence_factors = self._generate_confluence_factors(signal, output)
        
        return signal
    
    def _find_best_bullish_ob(self, output: AnalysisOutput) -> Optional[OrderBlock]:
        """
        寻找最佳买盘OB (单向做多)
        
        筛选条件:
            1. 必须是买盘OB (bullish)
            2. 未被回测 (活跃状态)
            3. 价格在折价区优先
            4. 距离当前价格合理范围内
        """
        state = output.market_state
        current_price = state.current_price
        
        candidates = []
        
        for ob in output.order_blocks:
            # 只选择买盘OB
            if ob.type != OBType.BULLISH:
                continue
            if ob.mitigated:
                continue
            
            # 计算距离
            distance_pct = abs(ob.mid_price - current_price) / current_price * 100
            
            # 选择距离合理的 OB
            if distance_pct < 20:  # 放宽距离限制
                distance_score = self._calculate_distance_score(ob, current_price)
                zone_bonus = 15 if state.zone == ZoneType.DISCOUNT else 0
                candidates.append((ob, distance_score, distance_pct, zone_bonus))
        
        if not candidates:
            return None
        
        # 排序: 优先折价区、近距离、高叠加数
        candidates.sort(key=lambda x: (
            x[3] - x[2] + x[0].confluence_count * 5
        ), reverse=True)
        
        return candidates[0][0]
    
    def _calculate_distance_score(
        self,
        ob: OrderBlock,
        current_price: float,
    ) -> float:
        """
        计算OB距离评分
        
        距离越近，评分越高 (0-100)
        """
        ob_mid = ob.mid_price
        distance_pct = abs(ob_mid - current_price) / current_price * 100
        
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
        """计算成交量评分"""
        volumes = [o.volume for o in all_obs if o.volume > 0]
        if not volumes:
            return 50.0
        
        max_vol = max(volumes)
        min_vol = min(volumes)
        
        if max_vol == min_vol:
            return 50.0
        
        return (ob.volume - min_vol) / (max_vol - min_vol) * 100
    
    def _check_fvg_alignment(
        self,
        output: AnalysisOutput,
        signal_type: SignalType,
    ) -> bool:
        """检查FVG方向是否与信号方向一致"""
        recent_fvgs = output.get_active_fvgs()
        
        for fvg in recent_fvgs:
            if signal_type == SignalType.LONG and fvg.type == FVGType.BULLISH:
                return True
            if signal_type == SignalType.SHORT and fvg.type == FVGType.BEARISH:
                return True
        
        return False
    
    def _detect_market_regime(self, output: AnalysisOutput) -> str:
        """检测市场状态"""
        state = output.market_state
        
        if state.volatility > 3:
            return "choppy"
        elif abs(state.momentum) > 10:
            return "trending"
        else:
            return "ranging"
    
    def _calculate_signal_strength(
        self,
        ob: OrderBlock,
        output: AnalysisOutput,
        signal: InstitutionalSignal,
    ) -> float:
        """
        计算信号强度评分 (0-100)
        
        评分维度:
            1. 区域匹配 (最大 25 分)
            2. 趋势匹配 (最大 20 分)
            3. OB距离评分 (最大 20 分)
            4. OB叠加数 (最大 15 分)
            5. FVG一致 (最大 10 分)
            6. 结构突破 (最大 10 分)
        """
        score = 0.0
        state = output.market_state
        
        # 区域匹配评分 (最重要)
        if signal.signal_type == SignalType.LONG and state.zone == ZoneType.DISCOUNT:
            score += 25
        elif signal.signal_type == SignalType.SHORT and state.zone == ZoneType.PREMIUM:
            score += 25
        elif state.zone == ZoneType.EQUILIBRIUM:
            score += 10
        
        # 趋势匹配评分 (单向做多)
        if state.trend == TrendDirection.BULLISH:
            score += 20
        elif state.trend == TrendDirection.NEUTRAL:
            score += 10
        else:
            # 看跌趋势中做多，扣分
            score += 5
        
        # OB距离评分 (首要权重)
        distance_score = signal.ob_distance_score
        score += distance_score * 0.4  # Max 40 points
        
        # OB叠加数评分
        score += min(15, ob.confluence_count * 7)
        
        # FVG与结构突破一致性，结合新鲜度
        active_fvgs = [f for f in output.fvgs if not f.mitigated and (f.index > output.data_points - 10)]
        fvg_freshness = any((f.type == FVGType.BULLISH and signal.signal_type == SignalType.LONG) for f in active_fvgs)
        if fvg_freshness:
            score += 15
        elif signal.fvg_alignment:
            score += 5
            
        recent_breaks = output.get_recent_breaks(5)
        if len(recent_breaks) > 0:
            score += 15
        elif signal.structure_break:
            score += 5
            
        # 成交量维度评分 (Volume Score)
        score += signal.ob_volume_score * 0.1  # Max 10 points
        
        # OB重叠度加分 (如果有)
        if ob.overlap_ratio >= self.STRONG_OB_OVERLAP:
            score += 15
        elif ob.overlap_ratio >= self.MIN_OB_OVERLAP:
            score += 5
        
        return min(100, score)
    
    def _estimate_win_rate(
        self,
        signal: InstitutionalSignal,
        output: AnalysisOutput,
    ) -> float:
        win_rate = self.BASE_WIN_RATE
        
        has_zone = signal.zone == ZoneType.DISCOUNT
        has_trend = signal.trend == TrendDirection.BULLISH
        has_confluence = signal.ob_confluence_count >= 2
        
        # 核心因素线性累加
        if has_zone: win_rate += 8
        if signal.ob_confluence_count >= 1: win_rate += 4
        if has_trend: win_rate += 5
        if signal.fvg_alignment: win_rate += 3
        if signal.structure_break: win_rate += 3
        
        # 胜率非线性加成: 折价区 + 看涨趋势 + OB叠加 = 质变效果
        if has_zone and has_trend and has_confluence:
            win_rate += 12  # 额外奖励分数，因为叠加效果更强
            signal.reasons.append("达成核心三要素共振 (折价区 + 顺势 + OB叠加)")
            
        if signal.ob_overlap_score >= self.STRONG_OB_OVERLAP:
            win_rate += 5
        elif signal.ob_overlap_score >= self.MIN_OB_OVERLAP:
            win_rate += 2
            
        win_rate -= signal.risk_score * 0.1
        
        if signal.signal_strength >= 60:
            win_rate += 5
        
        return max(35, min(85, win_rate))
    
    def _generate_reasons(
        self,
        ob: OrderBlock,
        output: AnalysisOutput,
        signal: InstitutionalSignal,
    ) -> List[str]:
        """生成交易理由"""
        reasons = []
        
        # OB重叠
        if ob.overlap_ratio >= self.VERY_STRONG_OB_OVERLAP:
            reasons.append(f"极强OB双重重叠 ({ob.overlap_ratio:.0f}%)")
        elif ob.overlap_ratio >= self.STRONG_OB_OVERLAP:
            reasons.append(f"强OB双重重叠 ({ob.overlap_ratio:.0f}%)")
        else:
            reasons.append(f"OB重叠 ({ob.overlap_ratio:.0f}%)")
        
        # OB叠加
        if ob.confluence_count >= 2:
            reasons.append(f"多OB叠加 ({ob.confluence_count}个)")
        
        # 价格区域
        if signal.zone == ZoneType.DISCOUNT and signal.is_long:
            reasons.append("价格处于折价区")
        elif signal.zone == ZoneType.PREMIUM and signal.is_short:
            reasons.append("价格处于溢价区")
        
        # 趋势方向
        if signal.signal_type == SignalType.LONG and signal.trend == TrendDirection.BULLISH:
            reasons.append("趋势方向一致 (看涨)")
        elif signal.signal_type == SignalType.SHORT and signal.trend == TrendDirection.BEARISH:
            reasons.append("趋势方向一致 (看跌)")
        
        # FVG
        if signal.fvg_alignment:
            reasons.append("FVG方向一致")
        
        # 流动性
        if output.liquidity_levels:
            reasons.append(f"流动性目标 ({len(output.liquidity_levels)}个)")
        
        return reasons
    
    def _generate_warnings(
        self,
        signal: InstitutionalSignal,
        output: AnalysisOutput,
    ) -> List[str]:
        """生成风险警告"""
        warnings = []
        
        # 趋势不一致
        if signal.signal_type == SignalType.LONG and signal.trend == TrendDirection.BEARISH:
            warnings.append("趋势方向不一致 (看跌趋势中做多)")
        elif signal.signal_type == SignalType.SHORT and signal.trend == TrendDirection.BULLISH:
            warnings.append("趋势方向不一致 (看涨趋势中做空)")
        
        # OB距离过远
        if signal.ob_distance_score < 50:
            warnings.append("OB距离当前价格较远")
        
        # 高风险环境
        if signal.risk_score > 70:
            warnings.append("高风险交易环境")
        
        # 盈亏比不足
        if signal.risk_reward_ratio < 2:
            warnings.append(f"盈亏比不足 (R:R = {signal.risk_reward_ratio:.1f})")
        
        # 缺乏结构突破
        if not signal.structure_break:
            warnings.append("缺乏近期结构突破确认")
        
        return warnings
    
    def _generate_confluence_factors(
        self,
        signal: InstitutionalSignal,
        output: AnalysisOutput,
    ) -> List[str]:
        """生成融合因素"""
        factors = []
        
        if signal.ob_overlap_score >= self.STRONG_OB_OVERLAP:
            factors.append("OB强重叠")
        
        if signal.ob_confluence_count >= 2:
            factors.append("多OB叠加")
        
        if signal.zone == ZoneType.DISCOUNT and signal.is_long:
            factors.append("折价区买入")
        elif signal.zone == ZoneType.PREMIUM and signal.is_short:
            factors.append("溢价区卖出")
        
        if signal.trend == TrendDirection.BULLISH and signal.is_long:
            factors.append("趋势一致")
        elif signal.trend == TrendDirection.BEARISH and signal.is_short:
            factors.append("趋势一致")
        
        if signal.fvg_alignment:
            factors.append("FVG一致")
        
        if signal.structure_break:
            factors.append("结构突破")
        
        if signal.liquidity_sweep:
            factors.append("流动性扫荡")
        
        return factors
