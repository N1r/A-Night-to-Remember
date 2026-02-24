"""
SMC Premium Visualizer - 机构级可视化模块
===========================================

基于 Plotly 构建的交互式暗色主题图表，
模仿 Bloomberg 终端与 TradingView 尊贵版视觉质感。
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .types import (
    OrderBlock, OBType,
    FairValueGap, FVGType,
    StructureBreak, BreakType,
    LiquidityLevel, LiquidityType,
    SwingPoint,
    MarketState, ZoneType, TrendDirection,
    AnalysisOutput,
)
from .signals import InstitutionalSignal

logger = logging.getLogger(__name__)


@dataclass
class ColorScheme:
    # 背景
    bg_color: str = "#FFFFFF"
    paper_bg: str = "#F3F4F6"
    grid_color: str = "rgba(0, 0, 0, 0.05)"

    # K线 (红涨绿跌)
    bullish_candle: str = "#EF4444"
    bearish_candle: str = "#10B981"
    bullish_fill: str = "rgba(239, 68, 68, 0.8)"
    bearish_fill: str = "rgba(16, 185, 129, 0.8)"

    # OB
    ob_bullish: str = "#EF4444"
    ob_bearish: str = "#10B981"
    ob_bullish_fill: str = "rgba(239, 68, 68, 0.15)"
    ob_bearish_fill: str = "rgba(16, 185, 129, 0.15)"

    # FVG
    fvg_bullish: str = "#F59E0B"
    fvg_bearish: str = "#3B82F6"
    fvg_bullish_fill: str = "rgba(245, 158, 11, 0.1)"
    fvg_bearish_fill: str = "rgba(59, 130, 246, 0.1)"

    # 结构突破
    bos_color: str = "#DC2626"
    choch_color: str = "#059669"

    # 流动性
    liquidity_bsl: str = "#D97706"
    liquidity_ssl: str = "#047857"

    # 波段点
    swing_high: str = "#EA580C"
    swing_low: str = "#0D9488"

    # 区域
    premium_zone: str = "rgba(220, 38, 38, 0.04)"
    discount_zone: str = "rgba(5, 150, 105, 0.04)"

    # 文字
    text_color: str = "#111827"
    text_secondary: str = "#6B7280"

    # 成交量
    volume_bullish: str = "rgba(239, 68, 68, 0.8)"
    volume_bearish: str = "rgba(16, 185, 129, 0.8)"

    # 交易信号
    entry_color: str = "#8B5CF6"
    stop_color: str = "#E11D48"
    tp_color: str = "#10B981"


class PremiumChartBuilder:
    """机构级图表构建器"""

    def __init__(self, color_scheme: Optional[ColorScheme] = None):
        self.colors = color_scheme or ColorScheme()
        self._fig: Optional[go.Figure] = None

    def build(
        self,
        df: pd.DataFrame,
        output: AnalysisOutput,
        signal: Optional[InstitutionalSignal] = None,
        title: Optional[str] = None,
        show_volume: bool = True,
        height: int = 900,
    ) -> go.Figure:
        df = df.reset_index(drop=True).copy()
        n = len(df)

        # 解析时间戳列 (支持 timestamp / date / 时间 / 日期)
        ts_col = None
        for col_name in ("timestamp", "date", "时间", "日期", "datetime"):
            if col_name in df.columns:
                ts_col = col_name
                break
        if ts_col:
            df["_ts"] = pd.to_datetime(df[ts_col], errors="coerce")
            x_vals = df["_ts"]
            use_ts = df["_ts"].notna().all()
        else:
            x_vals = df.index
            use_ts = False

        if not use_ts:
            x_vals = df.index

        self._x_vals = x_vals
        self._use_ts = use_ts
        self._n = n

        if show_volume:
            fig = make_subplots(
                rows=2, cols=1, shared_xaxes=True,
                vertical_spacing=0.03, row_heights=[0.8, 0.2],
                subplot_titles=("", "成交量"),
            )
        else:
            fig = make_subplots(rows=1, cols=1)

        self._add_candlestick(fig, df)
        self._add_swing_points(fig, output.swing_points)
        self._add_order_blocks(fig, output.order_blocks, n)
        self._add_fvgs(fig, output.fvgs, n)
        self._add_structure_breaks(fig, output.structure_breaks)
        self._add_liquidity(fig, output.liquidity_levels, n)
        self._add_zones(fig, output.market_state, n)

        if show_volume:
            self._add_volume(fig, df, output.order_blocks)

        if signal and signal.is_actionable:
            self._add_signal_levels(fig, signal, n)
            self._add_dashboard_panel(fig, signal, output)

        self._apply_layout(fig, title or f"SMC Analysis - {output.symbol}", height, output.timeframe)
        return fig

    # ------------------------------------------------------------------
    # 辅助: 将 K 线 index 映射到 x 轴值
    # ------------------------------------------------------------------
    def _x(self, idx: int):
        """将整数索引映射到 x 轴坐标 (时间戳或整数)."""
        idx = max(0, min(idx, self._n - 1))
        return self._x_vals.iloc[idx] if self._use_ts else idx

    # ------------------------------------------------------------------
    # K 线
    # ------------------------------------------------------------------
    def _add_candlestick(self, fig: go.Figure, df: pd.DataFrame) -> None:
        fig.add_trace(
            go.Candlestick(
                x=self._x_vals,
                open=df["open"], high=df["high"],
                low=df["low"], close=df["close"],
                name="K线",
                increasing_line_color=self.colors.bullish_candle,
                decreasing_line_color=self.colors.bearish_candle,
                increasing_fillcolor=self.colors.bullish_fill,
                decreasing_fillcolor=self.colors.bearish_fill,
                line=dict(width=1), whiskerwidth=0.5,
            ),
            row=1, col=1,
        )

    # ------------------------------------------------------------------
    # 波段点
    # ------------------------------------------------------------------
    def _add_swing_points(self, fig: go.Figure, swing_points: List[SwingPoint]) -> None:
        highs_x, highs_y, lows_x, lows_y = [], [], [], []
        for sp in swing_points:
            if sp.is_high:
                highs_x.append(self._x(sp.index))
                highs_y.append(sp.price)
            else:
                lows_x.append(self._x(sp.index))
                lows_y.append(sp.price)

        if highs_x:
            fig.add_trace(go.Scatter(
                x=highs_x, y=highs_y, mode="markers",
                marker=dict(symbol="triangle-down", size=10,
                            color=self.colors.swing_high,
                            line=dict(color="white", width=1)),
                name="波段高点",
                hovertemplate="高点: %{y:.2f}<extra></extra>",
                showlegend=False,
            ), row=1, col=1)

        if lows_x:
            fig.add_trace(go.Scatter(
                x=lows_x, y=lows_y, mode="markers",
                marker=dict(symbol="triangle-up", size=10,
                            color=self.colors.swing_low,
                            line=dict(color="white", width=1)),
                name="波段低点",
                hovertemplate="低点: %{y:.2f}<extra></extra>",
                showlegend=False,
            ), row=1, col=1)

    # ------------------------------------------------------------------
    # 订单块 (按重要性分层显示)
    # ------------------------------------------------------------------
    def _ob_importance(self, ob: OrderBlock, current_price: float) -> float:
        """计算 OB 重要性评分, 用于视觉分层."""
        score = 0.0
        score += min(20, ob.confluence_count * 10)
        dist_pct = abs(ob.mid_price - current_price) / current_price * 100 if current_price else 10
        score += max(0, 20 - dist_pct * 2)
        score += min(10, ob.overlap_ratio / 5)
        return score

    def _add_order_blocks(self, fig: go.Figure, order_blocks: List[OrderBlock], total_bars: int) -> None:
        active_obs = [ob for ob in order_blocks if not ob.mitigated]
        if not active_obs:
            return

        # 从所有活跃 OB 中找最新价用于排重要性
        # (取最后一根 K 线的 close 作为当前价近似)
        current_price = 0.0
        for ob in active_obs:
            current_price = max(current_price, ob.mid_price)

        # 计算重要性排序
        ob_scores = [(ob, self._ob_importance(ob, current_price)) for ob in active_obs]
        ob_scores.sort(key=lambda t: t[1], reverse=True)

        max_score = max(s for _, s in ob_scores) if ob_scores else 1
        if max_score == 0:
            max_score = 1

        for ob, score in ob_scores:
            if ob.type == OBType.BULLISH:
                base_color = self.colors.ob_bullish
                label = "买盘OB"
            else:
                base_color = self.colors.ob_bearish
                label = "卖盘OB"

            # 根据重要性调整透明度和线宽
            importance_ratio = score / max_score
            opacity = 0.3 + 0.6 * importance_ratio
            line_width = max(1, int(1 + 3 * importance_ratio))

            # 填充色根据重要性调节
            if ob.type == OBType.BULLISH:
                fill_alpha = 0.06 + 0.18 * importance_ratio
                fillcolor = f"rgba(230, 57, 70, {fill_alpha:.2f})"
            else:
                fill_alpha = 0.06 + 0.18 * importance_ratio
                fillcolor = f"rgba(45, 106, 79, {fill_alpha:.2f})"

            end_x = self._x(ob.mitigated_index if ob.mitigated_index else total_bars - 1)

            fig.add_shape(
                type="rect",
                x0=self._x(ob.index), y0=ob.bottom,
                x1=end_x, y1=ob.top,
                line=dict(color=base_color, width=line_width),
                fillcolor=fillcolor, opacity=opacity,
                row=1, col=1,
            )

            label_parts = [label]
            if ob.confluence_count > 1:
                label_parts.append(f"\u00d7{ob.confluence_count}")
            if ob.overlap_ratio > 0:
                label_parts.append(f"{ob.overlap_ratio:.0f}%")

            # 只给重要 OB 加标签 (避免拥挤)
            if importance_ratio >= 0.3:
                mid_x_idx = (ob.index + (ob.mitigated_index or total_bars - 1)) // 2
                fig.add_annotation(
                    x=self._x(mid_x_idx), y=(ob.top + ob.bottom) / 2,
                    text=" ".join(label_parts),
                    font=dict(color="white", size=9 + int(2 * importance_ratio)),
                    bgcolor=base_color, bordercolor="white",
                    borderwidth=1, borderpad=3, showarrow=False,
                    row=1, col=1,
                )

    # ------------------------------------------------------------------
    # FVG
    # ------------------------------------------------------------------
    def _add_fvgs(self, fig: go.Figure, fvgs: List[FairValueGap], total_bars: int) -> None:
        for fvg in fvgs:
            if fvg.mitigated:
                continue
            if fvg.type == FVGType.BULLISH:
                color, fillcolor = self.colors.fvg_bullish, self.colors.fvg_bullish_fill
            else:
                color, fillcolor = self.colors.fvg_bearish, self.colors.fvg_bearish_fill

            end_idx = fvg.mitigated_index or total_bars - 1
            fig.add_shape(
                type="rect",
                x0=self._x(fvg.index), y0=fvg.bottom,
                x1=self._x(end_idx), y1=fvg.top,
                line=dict(color=color, width=1, dash="dot"),
                fillcolor=fillcolor, opacity=0.5,
                row=1, col=1,
            )
            fig.add_annotation(
                x=self._x(min(fvg.index + 2, total_bars - 1)),
                y=(fvg.top + fvg.bottom) / 2,
                text="FVG", font=dict(color=color, size=9),
                showarrow=False, row=1, col=1,
            )

    # ------------------------------------------------------------------
    # 结构突破 (修复线方向: broken_index → index)
    # ------------------------------------------------------------------
    def _add_structure_breaks(self, fig: go.Figure, breaks: List[StructureBreak]) -> None:
        for sb in breaks[-10:]:
            if sb.type == BreakType.BOS:
                color, label = self.colors.bos_color, "BOS"
            else:
                color, label = self.colors.choch_color, "CHoCH"

            # broken_index 是被突破的旧波段点(在前), index 是突破发生点(在后)
            x_start = self._x(min(sb.broken_index, sb.index))
            x_end = self._x(max(sb.broken_index, sb.index))

            fig.add_shape(
                type="line",
                x0=x_start, y0=sb.level,
                x1=x_end, y1=sb.level,
                line=dict(color=color, width=3),
                row=1, col=1,
            )

            mid_idx = (sb.broken_index + sb.index) // 2
            fig.add_annotation(
                x=self._x(mid_idx), y=sb.level,
                text=label,
                font=dict(color="white", size=11, family="Arial Black"),
                bgcolor=color, bordercolor="white",
                borderwidth=1, borderpad=3, showarrow=False,
                row=1, col=1,
            )

    # ------------------------------------------------------------------
    # 流动性
    # ------------------------------------------------------------------
    def _add_liquidity(self, fig: go.Figure, levels: List[LiquidityLevel], total_bars: int) -> None:
        for ll in levels[:10]:
            if ll.type == LiquidityType.BUY_SIDE:
                color, label = self.colors.liquidity_bsl, "BSL"
            else:
                color, label = self.colors.liquidity_ssl, "SSL"

            fig.add_shape(
                type="line",
                x0=self._x(ll.index), y0=ll.level,
                x1=self._x(min(ll.end_index + 10, total_bars - 1)), y1=ll.level,
                line=dict(color=color, width=2, dash="dashdot"),
                row=1, col=1,
            )
            if ll.swept:
                label += " \u2713"
            fig.add_annotation(
                x=self._x(ll.index), y=ll.level,
                text=label, font=dict(color=color, size=9),
                bgcolor="rgba(255,255,255,0.7)",
                showarrow=False, row=1, col=1,
            )

    # ------------------------------------------------------------------
    # 溢价/折价区域
    # ------------------------------------------------------------------
    def _add_zones(self, fig: go.Figure, state: MarketState, total_bars: int) -> None:
        if state.swing_high is None or state.swing_low is None:
            return
        rng = state.swing_high - state.swing_low
        if rng == 0:
            return

        x0, x1 = self._x(0), self._x(total_bars - 1)

        premium_start = state.swing_low + rng * 0.7
        fig.add_shape(
            type="rect", x0=x0, y0=premium_start, x1=x1, y1=state.swing_high,
            fillcolor=self.colors.premium_zone,
            line=dict(color="rgba(255, 107, 107, 0.3)", width=1, dash="dot"),
            row=1, col=1,
        )

        discount_end = state.swing_low + rng * 0.3
        fig.add_shape(
            type="rect", x0=x0, y0=state.swing_low, x1=x1, y1=discount_end,
            fillcolor=self.colors.discount_zone,
            line=dict(color="rgba(78, 205, 196, 0.3)", width=1, dash="dot"),
            row=1, col=1,
        )

        fig.add_annotation(
            x=self._x(5), y=(premium_start + state.swing_high) / 2,
            text=f"溢价区 {'✓' if state.zone == ZoneType.PREMIUM else ''}",
            font=dict(color="rgba(255, 107, 107, 0.7)", size=10),
            showarrow=False, row=1, col=1,
        )
        fig.add_annotation(
            x=self._x(5), y=(state.swing_low + discount_end) / 2,
            text=f"折价区 {'✓' if state.zone == ZoneType.DISCOUNT else ''}",
            font=dict(color="rgba(78, 205, 196, 0.7)", size=10),
            showarrow=False, row=1, col=1,
        )

    # ------------------------------------------------------------------
    # 成交量 (OB 所在 K 线高亮)
    # ------------------------------------------------------------------
    def _add_volume(self, fig: go.Figure, df: pd.DataFrame,
                    order_blocks: List[OrderBlock] = None) -> None:
        ob_indices = set()
        if order_blocks:
            for ob in order_blocks:
                if not ob.mitigated:
                    ob_indices.add(ob.index)

        colors = []
        for i in range(len(df)):
            if i in ob_indices:
                colors.append("#FFD700")  # 金色高亮 OB K 线成交量
            elif df["close"].iloc[i] >= df["open"].iloc[i]:
                colors.append(self.colors.volume_bullish)
            else:
                colors.append(self.colors.volume_bearish)

        fig.add_trace(
            go.Bar(
                x=self._x_vals, y=df["volume"],
                marker_color=colors, opacity=0.6,
                name="成交量", showlegend=False,
            ),
            row=2, col=1,
        )

    # ------------------------------------------------------------------
    # 信号 Entry / SL / TP 水平线 (修复: 用水平线而非错位的散点)
    # ------------------------------------------------------------------
    def _add_signal_levels(self, fig: go.Figure, signal: InstitutionalSignal, total_bars: int) -> None:
        x0 = self._x(0)
        x1 = self._x(total_bars - 1)

        lines = [
            (signal.entry_price, self.colors.entry_color, "Entry", "dash"),
            (signal.stop_loss, self.colors.stop_color, "Stop Loss", "dot"),
            (signal.take_profit_1, self.colors.tp_color, "TP1 (2R)", "dashdot"),
            (signal.take_profit_2, self.colors.tp_color, "TP2 (3R)", "dashdot"),
        ]

        for price, color, label, dash in lines:
            if price <= 0:
                continue
            fig.add_shape(
                type="line", x0=x0, y0=price, x1=x1, y1=price,
                line=dict(color=color, width=2, dash=dash),
                row=1, col=1,
            )
            fig.add_annotation(
                x=x1, y=price,
                text=f" {label} {price:.2f}",
                font=dict(color=color, size=10),
                bgcolor="rgba(255, 255, 255, 0.9)",
                showarrow=False, xanchor="left",
                row=1, col=1,
            )

    # ------------------------------------------------------------------
    # Dashboard 信息面板 (右上角悬浮)
    # ------------------------------------------------------------------
    def _add_dashboard_panel(self, fig: go.Figure,
                             signal: InstitutionalSignal,
                             output: AnalysisOutput) -> None:
        state = output.market_state
        trend_map = {"bullish": "\u2191 看涨", "bearish": "\u2193 看跌", "neutral": "\u2194 震荡"}
        zone_map = {"discount": "折价", "premium": "溢价", "equilibrium": "平衡"}

        panel_lines = [
            f"<b>信号强度: {signal.signal_strength:.0f}/100</b>",
            f"胜率: {signal.estimated_win_rate:.0f}%  R:R 1:{signal.risk_reward_ratio:.1f}",
            f"入场: {signal.entry_price:.2f}  止损: {signal.stop_loss:.2f}",
            f"TP1: {signal.take_profit_1:.2f}  TP2: {signal.take_profit_2:.2f}",
            f"趋势: {trend_map.get(state.trend.value, state.trend.value)}  "
            f"区域: {zone_map.get(state.zone.value, state.zone.value)}",
            f"OB叠加: {signal.ob_confluence_count}  "
            f"FVG: {'一致' if signal.fvg_alignment else '-'}  "
            f"BOS: {'有' if signal.structure_break else '-'}",
        ]

        fig.add_annotation(
            xref="paper", yref="paper",
            x=0.99, y=0.97,
            text="<br>".join(panel_lines),
            font=dict(color=self.colors.text_color, size=11, family="Courier New"),
            bgcolor="rgba(255, 255, 255, 0.95)",
            bordercolor="rgba(0, 0, 0, 0.1)",
            borderwidth=2, borderpad=8,
            showarrow=False, align="left",
            xanchor="right", yanchor="top",
        )

    # ------------------------------------------------------------------
    # 布局
    # ------------------------------------------------------------------
    def _apply_layout(self, fig: go.Figure, title: str, height: int, timeframe: str) -> None:
        fig.update_layout(
            title={"text": title, "x": 0.5,
                   "font": {"size": 18, "color": self.colors.text_color}},
            template="plotly_white",
            paper_bgcolor=self.colors.paper_bg,
            plot_bgcolor=self.colors.bg_color,
            font=dict(color=self.colors.text_color, family="Arial"),
            height=height,
            showlegend=True,
            legend=dict(
                orientation="h", yanchor="bottom", y=1.02,
                xanchor="right", x=1,
                font=dict(size=10, color=self.colors.text_secondary),
                bgcolor="rgba(255, 255, 255, 0.7)",
            ),
            margin=dict(l=60, r=120, t=80, b=50),
            xaxis_rangeslider_visible=False,
            xaxis=dict(showgrid=True, gridcolor=self.colors.grid_color,
                       zerolinecolor=self.colors.grid_color),
            yaxis=dict(showgrid=True, gridcolor=self.colors.grid_color,
                       zerolinecolor=self.colors.grid_color),
        )

        if self._use_ts:
            rangebreaks = [dict(bounds=["sat", "mon"])]
            if timeframe != "daily":
                rangebreaks.append(dict(bounds=[15, 9.5], pattern="hour"))
            fig.update_xaxes(rangebreaks=rangebreaks)

    # ------------------------------------------------------------------
    # 保存
    # ------------------------------------------------------------------
    def save(self, fig: go.Figure, filepath: Path,
             include_plotlyjs: bool = True) -> None:
        config = {
            "displayModeBar": True, "displaylogo": False,
            "modeBarButtonsToRemove": ["pan2d", "lasso2d", "select2d"],
            "responsive": True, "scrollZoom": True,
        }
        fig.write_html(filepath, config=config,
                       include_plotlyjs="cdn" if not include_plotlyjs else True)
        logger.debug(f"图表已保存: {filepath}")


def create_summary_panel(output: AnalysisOutput,
                         signal: Optional[InstitutionalSignal] = None) -> Dict:
    state = output.market_state
    summary = {
        "symbol": output.symbol, "timeframe": output.timeframe,
        "trend": state.trend.value, "zone": state.zone.value,
        "current_price": round(state.current_price, 2),
        "active_bullish_obs": state.active_bullish_obs,
        "active_bearish_obs": state.active_bearish_obs,
        "active_bullish_fvgs": state.active_bullish_fvgs,
        "active_bearish_fvgs": state.active_bearish_fvgs,
        "volatility": round(state.volatility, 2),
        "momentum": round(state.momentum, 2),
        "computation_time_ms": round(output.computation_time_ms, 2),
    }
    if signal:
        summary.update({
            "signal_type": signal.signal_type.value,
            "signal_strength": round(signal.signal_strength, 1),
            "confidence": round(signal.confidence, 1),
            "estimated_win_rate": round(signal.estimated_win_rate, 1),
            "risk_reward_ratio": round(signal.risk_reward_ratio, 2),
            "entry_price": round(signal.entry_price, 2),
            "stop_loss": round(signal.stop_loss, 2),
            "take_profit_1": round(signal.take_profit_1, 2),
            "take_profit_2": round(signal.take_profit_2, 2),
            "is_actionable": signal.is_actionable,
            "reasons": signal.reasons,
            "warnings": signal.warnings,
        })
    return summary
