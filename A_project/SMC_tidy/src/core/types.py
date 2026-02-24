"""
SMC Core Types - Institutional-grade Data Structures
=====================================================

类型定义模块：定义所有 SMC 核心数据结构，采用 dataclass 实现，
确保类型安全、序列化友好、符合机构级代码规范。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple
import pandas as pd
import numpy as np


class SignalType(Enum):
    """交易信号类型枚举"""
    LONG = "long"
    SHORT = "short"
    NEUTRAL = "neutral"


class TrendDirection(Enum):
    """趋势方向枚举"""
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class ZoneType(Enum):
    """价格区域类型枚举"""
    PREMIUM = "premium"      # 溢价区
    DISCOUNT = "discount"    # 折价区
    EQUILIBRIUM = "equilibrium"  # 平衡区


class OBType(Enum):
    """订单块类型枚举"""
    BULLISH = "bullish"  # 买盘OB
    BEARISH = "bearish"  # 卖盘OB


class FVGType(Enum):
    """公允价值缺口类型枚举"""
    BULLISH = "bullish"  # 看涨缺口
    BEARISH = "bearish"  # 看跌缺口


class BreakType(Enum):
    """结构突破类型枚举"""
    BOS = "bos"      # Break of Structure
    CHOCH = "choch"  # Change of Character


class LiquidityType(Enum):
    """流动性类型枚举"""
    BUY_SIDE = "buy_side"   # 买方流动性 (BSL)
    SELL_SIDE = "sell_side"  # 卖方流动性 (SSL)


@dataclass
class SwingPoint:
    """
    波段点数据结构
    
    代表市场结构中的关键转折点（波段高点或波段低点）。
    
    Attributes:
        index: K线索引位置
        price: 价格水平
        is_high: 是否为波段高点（True=高点，False=低点）
        confirmed: 是否已被后续价格确认
        strength: 波段强度评分 (0-100)
    """
    index: int
    price: float
    is_high: bool
    confirmed: bool = True
    strength: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "index": self.index,
            "price": self.price,
            "type": "swing_high" if self.is_high else "swing_low",
            "confirmed": self.confirmed,
            "strength": self.strength,
        }


@dataclass
class OrderBlock:
    """
    订单块 (Order Block) 数据结构
    
    订单块是机构资金集中进出场的关键区域。
    当价格回到订单块区域时，往往会产生反转或延续行情。
    
    核心属性:
        - top/bottom: 订单块的上下边界
        - type: 买盘OB（bullish）或卖盘OB（bearish）
        - volume: 该区域的成交量
        - mitigated: 是否已被价格回测（mitigation）
        
    高级属性:
        - overlap_ratio: 与近期K线的重叠百分比（重叠度越高信号越强）
        - confluence_count: 该价格区域的OB叠加数量
        - distance_pct: 距当前价格的百分比距离
    """
    index: int
    top: float
    bottom: float
    type: OBType
    volume: float = 0.0
    mitigated: bool = False
    mitigated_index: Optional[int] = None
    overlap_ratio: float = 0.0
    confluence_count: int = 1
    distance_pct: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    
    @property
    def mid_price(self) -> float:
        """订单块中心价格"""
        return (self.top + self.bottom) / 2
    
    @property
    def height(self) -> float:
        """订单块高度"""
        return self.top - self.bottom
    
    @property
    def is_bullish(self) -> bool:
        """是否为买盘OB"""
        return self.type == OBType.BULLISH
    
    @property
    def is_active(self) -> bool:
        """是否为活跃状态（未被回测）"""
        return not self.mitigated
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "index": self.index,
            "top": round(self.top, 4),
            "bottom": round(self.bottom, 4),
            "mid_price": round(self.mid_price, 4),
            "type": self.type.value,
            "volume": self.volume,
            "mitigated": self.mitigated,
            "overlap_ratio": round(self.overlap_ratio, 2),
            "confluence_count": self.confluence_count,
            "distance_pct": round(self.distance_pct, 2),
            "is_active": self.is_active,
        }


@dataclass
class FairValueGap:
    """
    公允价值缺口 (Fair Value Gap / Imbalance) 数据结构
    
    FVG 是由于价格快速移动导致的不平衡区域，
    价格往往会回补（mitigate）这些缺口后继续原方向移动。
    
    形成条件:
        - 看涨FVG: 当前K线低点 > 前一根K线高点
        - 看跌FVG: 当前K线高点 < 前一根K线低点
    """
    index: int
    top: float
    bottom: float
    type: FVGType
    size: float = 0.0
    mitigated: bool = False
    mitigated_index: Optional[int] = None
    
    @property
    def mid_price(self) -> float:
        """缺口中心价格"""
        return (self.top + self.bottom) / 2
    
    @property
    def gap_size(self) -> float:
        """缺口大小"""
        return abs(self.top - self.bottom)
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "index": self.index,
            "top": round(self.top, 4),
            "bottom": round(self.bottom, 4),
            "type": self.type.value,
            "size": round(self.gap_size, 4),
            "mitigated": self.mitigated,
        }


@dataclass
class StructureBreak:
    """
    结构突破 (Structure Break) 数据结构
    
    包括 BOS (Break of Structure) 和 CHoCH (Change of Character)。
    
    BOS: 趋势延续信号，价格突破前高/前低
    CHoCH: 趋势反转信号，价格改变结构方向
    """
    index: int
    level: float
    type: BreakType
    direction: TrendDirection
    broken_index: int  # 被突破的波段点索引
    
    @property
    def is_bos(self) -> bool:
        """是否为BOS"""
        return self.type == BreakType.BOS
    
    @property
    def is_choch(self) -> bool:
        """是否为CHoCH"""
        return self.type == BreakType.CHOCH
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "index": self.index,
            "level": round(self.level, 4),
            "type": self.type.value,
            "direction": self.direction.value,
            "broken_index": self.broken_index,
        }


@dataclass
class LiquidityLevel:
    """
    流动性水平数据结构
    
    代表市场中的潜在流动性区域，通常是止损聚集的位置。
    
    BSL (Buy-Side Liquidity): 买方流动性，位于高点上方
    SSL (Sell-Side Liquidity): 卖方流动性，位于低点下方
    """
    index: int
    level: float
    type: LiquidityType
    end_index: int
    swept: bool = False  # 是否已被扫荡
    
    @property
    def is_bsl(self) -> bool:
        """是否为买方流动性"""
        return self.type == LiquidityType.BUY_SIDE
    
    @property
    def is_ssl(self) -> bool:
        """是否为卖方流动性"""
        return self.type == LiquidityType.SELL_SIDE
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "index": self.index,
            "level": round(self.level, 4),
            "type": self.type.value,
            "swept": self.swept,
        }


@dataclass
class MarketState:
    """
    市场状态综合数据结构
    
    整合所有 SMC 分析结果，提供完整的市场视角。
    """
    trend: TrendDirection = TrendDirection.NEUTRAL
    zone: ZoneType = ZoneType.EQUILIBRIUM
    current_price: float = 0.0
    swing_high: Optional[float] = None
    swing_low: Optional[float] = None
    equilibrium: Optional[float] = None
    
    # 统计指标
    active_bullish_obs: int = 0
    active_bearish_obs: int = 0
    active_bullish_fvgs: int = 0
    active_bearish_fvgs: int = 0
    total_liquidity_levels: int = 0
    swept_liquidity: int = 0
    
    # 结构分析
    last_break: Optional[StructureBreak] = None
    structure_high: Optional[float] = None
    structure_low: Optional[float] = None
    
    # 市场特征
    volatility: float = 0.0
    momentum: float = 0.0
    atr: float = 0.0
    
    @property
    def is_discount(self) -> bool:
        """是否处于折价区"""
        return self.zone == ZoneType.DISCOUNT
    
    @property
    def is_premium(self) -> bool:
        """是否处于溢价区"""
        return self.zone == ZoneType.PREMIUM
    
    @property
    def is_bullish(self) -> bool:
        """是否为看涨趋势"""
        return self.trend == TrendDirection.BULLISH
    
    @property
    def range_size(self) -> float:
        """价格区间大小"""
        if self.swing_high and self.swing_low:
            return self.swing_high - self.swing_low
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "trend": self.trend.value,
            "zone": self.zone.value,
            "current_price": round(self.current_price, 4),
            "swing_high": round(self.swing_high, 4) if self.swing_high else None,
            "swing_low": round(self.swing_low, 4) if self.swing_low else None,
            "equilibrium": round(self.equilibrium, 4) if self.equilibrium else None,
            "active_bullish_obs": self.active_bullish_obs,
            "active_bearish_obs": self.active_bearish_obs,
            "active_bullish_fvgs": self.active_bullish_fvgs,
            "active_bearish_fvgs": self.active_bearish_fvgs,
            "volatility": round(self.volatility, 4),
            "momentum": round(self.momentum, 4),
        }


@dataclass
class AnalysisOutput:
    """
    SMC 分析完整输出数据结构
    
    包含所有分析结果的统一输出格式，便于后续处理和可视化。
    """
    symbol: str
    timestamp: datetime = field(default_factory=datetime.now)
    timeframe: str = "daily"
    
    # 原始数据引用
    ohlcv_df: Optional[pd.DataFrame] = None
    
    # SMC 组件
    swing_points: List[SwingPoint] = field(default_factory=list)
    order_blocks: List[OrderBlock] = field(default_factory=list)
    fvgs: List[FairValueGap] = field(default_factory=list)
    structure_breaks: List[StructureBreak] = field(default_factory=list)
    liquidity_levels: List[LiquidityLevel] = field(default_factory=list)
    
    # 市场状态
    market_state: MarketState = field(default_factory=MarketState)
    
    # 性能指标
    computation_time_ms: float = 0.0
    data_points: int = 0
    
    def get_active_obs(self, ob_type: Optional[OBType] = None) -> List[OrderBlock]:
        """获取活跃的订单块"""
        obs = [ob for ob in self.order_blocks if not ob.mitigated]
        if ob_type:
            obs = [ob for ob in obs if ob.type == ob_type]
        return obs
    
    def get_active_fvgs(self, fvg_type: Optional[FVGType] = None) -> List[FairValueGap]:
        """获取活跃的FVG"""
        fvgs = [fvg for fvg in self.fvgs if not fvg.mitigated]
        if fvg_type:
            fvgs = [fvg for fvg in fvgs if fvg.type == fvg_type]
        return fvgs
    
    def get_recent_breaks(self, lookback: int = 20) -> List[StructureBreak]:
        """获取最近的结构突破"""
        if self.ohlcv_df is None:
            return []
        min_idx = len(self.ohlcv_df) - lookback
        return [sb for sb in self.structure_breaks if sb.index >= min_idx]
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "timeframe": self.timeframe,
            "data_points": self.data_points,
            "computation_time_ms": round(self.computation_time_ms, 2),
            "market_state": self.market_state.to_dict(),
            "swing_points": [sp.to_dict() for sp in self.swing_points],
            "order_blocks": [ob.to_dict() for ob in self.order_blocks],
            "fvgs": [fvg.to_dict() for fvg in self.fvgs],
            "structure_breaks": [sb.to_dict() for sb in self.structure_breaks],
            "liquidity_levels": [ll.to_dict() for ll in self.liquidity_levels],
            "summary": {
                "active_bullish_obs": len(self.get_active_obs(OBType.BULLISH)),
                "active_bearish_obs": len(self.get_active_obs(OBType.BEARISH)),
                "active_bullish_fvgs": len(self.get_active_fvgs(FVGType.BULLISH)),
                "active_bearish_fvgs": len(self.get_active_fvgs(FVGType.BEARISH)),
            },
        }
