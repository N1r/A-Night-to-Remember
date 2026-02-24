"""
Enhanced chart visualization module with improved clarity and readability.
"""
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from ..config import get_config, ChartConfig
from typing import Any
from ..smc_analysis import AnalysisResult, OrderBlock, FairValueGap, LiquidityLevel, StructureBreak

logger = logging.getLogger(__name__)


class SMCChartPlotter:
    """
    Enhanced SMC chart plotter with improved clarity and visual design.
    
    Features:
    - Clear candlestick charts with proper coloring
    - Distinct markers for each SMC indicator
    - Volume profile display
    - Premium/Discount zone highlighting
    - Interactive tooltips
    - Responsive design
    """
    
    def __init__(self, config: Optional[ChartConfig] = None):
        self.config = config or get_config().chart
        self.colors = self.config.colors
    
    def create_chart(
        self,
        df: pd.DataFrame,
        analysis_result: AnalysisResult,
        title: Optional[str] = None,
        show_volume: bool = True,
    ) -> go.Figure:
        """
        Create comprehensive SMC chart with all indicators.
        
        Args:
            df: OHLCV DataFrame
            analysis_result: SMC analysis result
            title: Chart title
            show_volume: Whether to show volume subplot
            
        Returns:
            Plotly Figure object
        """
        # Create subplot structure
        if show_volume and self.config.show_volume:
            fig = make_subplots(
                rows=2, cols=1,
                shared_xaxes=True,
                vertical_spacing=0.03,
                row_heights=[0.8, 0.2],
                subplot_titles=('Price', 'Volume'),
            )
        else:
            fig = make_subplots(rows=1, cols=1)
        
        # Reset index and resolve time column
        df = df.reset_index(drop=True)
        df_plot = df.copy()
        # Find timestamp column
        ts_col = None
        for col_name in ("timestamp", "date", "时间", "日期", "datetime"):
            if col_name in df_plot.columns:
                ts_col = col_name
                break
        if ts_col:
            dt_series = pd.to_datetime(df_plot[ts_col], errors="coerce")
            df_plot["_ts"] = dt_series.dt.strftime('%Y-%m-%d %H:%M')
            df_plot.index = range(len(df_plot))
        else:
            df_plot["_ts"] = range(len(df_plot))
            df_plot.index = range(len(df_plot))
        
        # Add candlestick
        self._current_obs = analysis_result.order_blocks
        self._add_candlestick(fig, df_plot, show_volume)
        
        # Add SMC indicators
        self._add_order_blocks(fig, df_plot, analysis_result.order_blocks, show_volume)
        self._add_fvgs(fig, df_plot, analysis_result.fvg_list, show_volume)
        self._add_liquidity(fig, df_plot, analysis_result.liquidity_levels, show_volume)
        self._add_structure_breaks(fig, df_plot, analysis_result.structure_breaks, show_volume)
        self._add_swing_points(fig, df_plot, analysis_result.raw_smc_data.get('swing_highs_lows'), show_volume)
        
        # Add volume bars if enabled
        if show_volume and self.config.show_volume:
            self._add_volume(fig, df_plot)
        
        # Add premium/discount zone
        self._add_premium_discount_zone(fig, df_plot, analysis_result, show_volume)
        
        # Add signals and dashboard
        signal = getattr(analysis_result, 'primary_signal', None)
        if signal is None and hasattr(analysis_result, 'signal'):
            signal = analysis_result.signal # In case it's MTF result
        if signal:
            self._add_signal_annotation(fig, df_plot, signal)
            self._add_dashboard_panel(fig, df_plot, signal)
        
        # Apply layout
        self._apply_layout(fig, title or f"SMC Analysis - {analysis_result.symbol}")
        
        return fig
    
    def _x(self, df: pd.DataFrame, idx: int):
        idx = max(0, min(idx, len(df) - 1))
        return df['_ts'].iloc[idx]
        
    def _add_candlestick(
        self,
        fig: go.Figure,
        df: pd.DataFrame,
        has_volume_subplot: bool,
    ) -> None:
        """Add candlestick chart with Chinese market styling."""
        row = 1
        col = 1
        
        fig.add_trace(
            go.Candlestick(
                x=df['_ts'],
                open=df["open"],
                high=df["high"],
                low=df["low"],
                close=df["close"],
                name="Price",
                increasing_line_color=self.colors['bullish'],
                decreasing_line_color=self.colors['bearish'],
                increasing_fillcolor=self.colors['bullish'],
                decreasing_fillcolor="rgba(255,255,255,0.8)",
                line=dict(width=1),
                whiskerwidth=0.5,
            ),
            row=row, col=col,
        )
    
    def _add_order_blocks(
        self,
        fig: go.Figure,
        df: pd.DataFrame,
        order_blocks: List[OrderBlock],
        has_volume_subplot: bool,
    ) -> None:
        """Add Order Blocks with clear visual distinction."""
        row = 1
        col = 1
        
        for ob in order_blocks:
            if ob.mitigated:
                continue  # Only show active OBs for clarity
            
            # Determine importance and colors
            confluence = getattr(ob, 'confluence_count', 1)
            opacity = min(0.8, 0.2 + 0.15 * confluence)
            line_width = min(4, max(1, confluence))
            color = self.colors['ob_bullish'] if ob.type == 'bullish' else self.colors['ob_bearish']
            fillcolor = f"rgba(230, 57, 70, {opacity})" if ob.type == 'bullish' else f"rgba(45, 106, 79, {opacity})" 
            
            # Calculate end index
            end_idx = ob.mitigated_index if ob.mitigated_index else len(df) - 1
            x0 = self._x(df, ob.index)
            x1 = self._x(df, end_idx)
            mid_x = getattr(ob, 'confluence_count', 1)
            
            # Add rectangle
            fig.add_shape(
                type="rect",
                x0=x0,
                y0=ob.bottom,
                x1=x1,
                y1=ob.top,
                line=dict(color=color, width=line_width),
                fillcolor=fillcolor,
                opacity=opacity,
                row=row, col=col,
            )
            
            # Add label
            mid_idx = int((ob.index + end_idx) / 2)
            mid_x = self._x(df, mid_idx)
            mid_y = (ob.top + ob.bottom) / 2
            
            volume_str = self._format_volume(ob.volume)
            overlap_str = f" | {ob.overlap_ratio:.0f}%重合" if ob.overlap_ratio > 0 else ""
            label = f"{'买盘OB' if ob.type == 'bullish' else '卖盘OB'}" + (f"x{confluence}" if confluence>1 else "") + f" | {volume_str}{overlap_str}"
            
            fig.add_annotation(
                x=mid_x,
                y=mid_y,
                text=label,
                font=dict(color="white", size=10),
                bgcolor=color,
                bordercolor="white",
                borderwidth=1,
                showarrow=False,
                row=row, col=col,
            )
    
    def _add_fvgs(
        self,
        fig: go.Figure,
        df: pd.DataFrame,
        fvgs: List[FairValueGap],
        has_volume_subplot: bool,
    ) -> None:
        """Add Fair Value Gaps."""
        row = 1
        col = 1
        
        for fvg in fvgs:
            if fvg.mitigated:
                continue
            
            color = self.colors['fvg_bullish'] if fvg.type == "bullish" else self.colors['fvg_bearish']
            fillcolor = f"rgba(255, 183, 3, 0.1)" if fvg.type == "bullish" else f"rgba(58, 134, 255, 0.1)"
            
            end_idx = fvg.mitigated_index if fvg.mitigated_index else len(df) - 1
            x0 = self._x(df, fvg.index)
            x1 = self._x(df, end_idx)
            
            fig.add_shape(
                type="rect",
                x0=x0,
                y0=fvg.bottom,
                x1=x1,
                y1=fvg.top,
                line=dict(color=color, width=1, dash="dot"),
                fillcolor=fillcolor,
                opacity=0.5,
                row=row, col=col,
            )
            
            # Add gap label
            fig.add_annotation(
                x=self._x(df, min(fvg.index + 2, len(df)-1)),
                y=(fvg.top + fvg.bottom) / 2,
                text=f"FVG",
                font=dict(color=color, size=9),
                showarrow=False,
                row=row, col=col,
            )
    
    def _add_liquidity(
        self,
        fig: go.Figure,
        df: pd.DataFrame,
        liquidity_levels: List[LiquidityLevel],
        has_volume_subplot: bool,
    ) -> None:
        """Add Liquidity Levels."""
        row = 1
        col = 1
        
        for liq in liquidity_levels[:10]:  # Limit to top 10 for clarity
            color = self.colors['liquidity']
            
            fig.add_shape(
                type="line",
                x0=self._x(df, liq.index),
                y0=liq.level,
                x1=self._x(df, liq.end_index),
                y1=liq.level,
                line=dict(color=color, width=2, dash="dashdot"),
                row=row, col=col,
            )
            
            fig.add_annotation(
                x=self._x(df, liq.index),
                y=liq.level,
                text=f"{'买方' if liq.type == 'buy_side' else '卖方'}流动性",
                font=dict(color=color, size=9),
                bgcolor="rgba(255,255,255,0.8)",
                showarrow=False,
                row=row, col=col,
            )
    
    def _add_structure_breaks(
        self,
        fig: go.Figure,
        df: pd.DataFrame,
        structure_breaks: List[StructureBreak],
        has_volume_subplot: bool,
    ) -> None:
        """Add BOS and CHOCH markers."""
        row = 1
        col = 1
        
        for sb in structure_breaks[-10:]:  # Show last 10 for clarity
            if sb.type == "bos":
                color = self.colors['bos']
                label = "BOS"
            else:
                color = self.colors['choch']
                label = "CHOCH"
            
            # Add structure line
            fig.add_shape(
                type="line",
                x0=self._x(df, sb.broken_index),
                y0=sb.level,
                x1=self._x(df, sb.index),
                y1=sb.level,
                line=dict(color=color, width=3),
                row=row, col=col,
            )
            
            # Add label
            mid_idx = int((sb.index + sb.broken_index) / 2)
            mid_x = self._x(df, mid_idx)
            
            fig.add_annotation(
                x=mid_x,
                y=sb.level,
                text=label,
                font=dict(color="white", size=11, family="Arial Black"),
                bgcolor=color,
                bordercolor="white",
                borderwidth=1,
                showarrow=False,
                row=row, col=col,
            )
    
    def _add_swing_points(
        self,
        fig: go.Figure,
        df: pd.DataFrame,
        swing_data: Optional[pd.DataFrame],
        has_volume_subplot: bool,
    ) -> None:
        """Add Swing Highs and Lows markers."""
        if swing_data is None:
            return
        
        row = 1
        col = 1
        
        highs_x, highs_y = [], []
        lows_x, lows_y = [], []
        
        for i in range(len(swing_data["HighLow"])):
            if pd.isna(swing_data["HighLow"][i]):
                continue
            
            if swing_data["HighLow"][i] == 1:  # High
                highs_x.append(self._x(df, i))
                highs_y.append(swing_data["Level"][i])
            else:  # Low
                lows_x.append(self._x(df, i))
                lows_y.append(swing_data["Level"][i])
        
        # Add swing highs
        if highs_x:
            fig.add_trace(
                go.Scatter(
                    x=highs_x,
                    y=highs_y,
                    mode="markers",
                    marker=dict(
                        symbol="triangle-down",
                        size=12,
                        color=self.colors['swing_high'],
                        line=dict(color="white", width=1),
                    ),
                    name="Swing High",
                    showlegend=False,
                ),
                row=row, col=col,
            )
        
        # Add swing lows
        if lows_x:
            fig.add_trace(
                go.Scatter(
                    x=lows_x,
                    y=lows_y,
                    mode="markers",
                    marker=dict(
                        symbol="triangle-up",
                        size=12,
                        color=self.colors['swing_low'],
                        line=dict(color="white", width=1),
                    ),
                    name="Swing Low",
                    showlegend=False,
                ),
                row=row, col=col,
            )
    
    def _add_volume(
        self,
        fig: go.Figure,
        df: pd.DataFrame,
    ) -> None:
        """Add volume subplot."""
        # highlight order block origin bars
        ob_indices = set()
        if hasattr(self, '_current_obs'):
            for ob in self._current_obs:
                if not ob.mitigated:
                    ob_indices.add(ob.index)
        
        colors = [
            "#FFD700" if i in ob_indices else 
            (self.colors['bullish'] if df['close'].iloc[i] >= df['open'].iloc[i] else  self.colors['bearish'])
            for i in range(len(df))
        ]
        
        fig.add_trace(
            go.Bar(
                x=df['_ts'],
                y=df['volume'],
                marker_color=colors,
                opacity=0.7,
                name="Volume",
                showlegend=False,
            ),
            row=2, col=1,
        )
    
    def _add_premium_discount_zone(
        self,
        fig: go.Figure,
        df: pd.DataFrame,
        analysis_result: AnalysisResult,
        has_volume_subplot: bool,
    ) -> None:
        """Add premium/discount zone indicator."""
        swing_data = analysis_result.raw_smc_data.get('swing_highs_lows')
        if swing_data is None:
            return
        
        row = 1
        col = 1
        
        # Find recent swing high and low
        swing_high = None
        swing_low = None
        
        for i in range(len(swing_data["HighLow"]) - 1, -1, -1):
            if pd.isna(swing_data["HighLow"][i]):
                continue
            
            level = swing_data["Level"][i]
            
            if swing_data["HighLow"][i] == 1 and swing_high is None:
                swing_high = level
            elif swing_data["HighLow"][i] == -1 and swing_low is None:
                swing_low = level
            
            if swing_high is not None and swing_low is not None:
                break
        
        if swing_high is None or swing_low is None:
            return
        
        # Add zone rectangles
        range_size = swing_high - swing_low
        premium_start = swing_low + (range_size * 0.7)
        discount_end = swing_low + (range_size * 0.3)
        
        # Premium zone (top 30%)
        fig.add_shape(
            type="rect",
            x0=self._x(df, 0),
            y0=premium_start,
            x1=self._x(df, len(df) - 1),
            y1=swing_high,
            fillcolor=f"rgba(255, 107, 107, 0.05)",
            line=dict(color="rgba(255, 107, 107, 0.3)", width=1, dash="dot"),
            row=row, col=col,
        )
        
        # Discount zone (bottom 30%)
        fig.add_shape(
            type="rect",
            x0=self._x(df, 0),
            y0=swing_low,
            x1=self._x(df, len(df) - 1),
            y1=discount_end,
            fillcolor=f"rgba(78, 205, 196, 0.05)",
            line=dict(color="rgba(78, 205, 196, 0.3)", width=1, dash="dot"),
            row=row, col=col,
        )
        
        # Add zone labels
        fig.add_annotation(
            x=self._x(df, 10),
            y=(premium_start + swing_high) / 2,
            text=f"溢价区 ({analysis_result.premium_discount == 'premium'})",
            font=dict(color=self.colors['premium'], size=10),
            showarrow=False,
            row=row, col=col,
        )
        
        fig.add_annotation(
            x=self._x(df, 10),
            y=(swing_low + discount_end) / 2,
            text=f"折价区 ({analysis_result.premium_discount == 'discount'})",
            font=dict(color=self.colors['discount'], size=10),
            showarrow=False,
            row=row, col=col,
        )
    

    def _add_signal_annotation(self, fig: go.Figure, df: pd.DataFrame, signal: Any) -> None:
        if not signal or signal.signal_type == "neutral": return
        x0_val = self._x(df, 0)
        x1_val = self._x(df, len(df) - 1)
        
        levels = [
            (signal.entry_price, "#FFD700", "Entry", "dash"),
            (signal.stop_loss, "#FF4444", "Stop Loss", "dot"),
            (signal.take_profit_1, "#00E676", "TP1", "dashdot"),
        ]
        if getattr(signal, 'take_profit_2', 0):
            levels.append((signal.take_profit_2, "#00E676", "TP2", "dashdot"))
            
        for price, color, text, dash in levels:
            if price <= 0: continue
            fig.add_shape(
                type="line", x0=x0_val, y0=price, x1=x1_val, y1=price,
                line=dict(color=color, width=2, dash=dash), row=1, col=1
            )
            fig.add_annotation(
                x=x1_val, y=price, text=f" {text} {price:.2f}",
                font=dict(color=color, size=10), showarrow=False, xanchor="left", row=1, col=1
            )
            
    def _add_dashboard_panel(self, fig: go.Figure, df: pd.DataFrame, signal: Any) -> None:
        if not signal: return
        panel_text = (
            f"<b>信号类型: {signal.signal_type.upper()} | 强度: {getattr(signal, 'signal_strength', 0):.0f}</b><br>"
            f"入场: {signal.entry_price:.2f} | 止损: {signal.stop_loss:.2f}<br>"
            f"盈亏比: 1:{getattr(signal, 'risk_reward_ratio', 0):.1f}<br>"
        )
        if hasattr(signal, 'estimated_win_rate'):
            panel_text += f"预估胜率: {signal.estimated_win_rate:.1f}%<br>"
        if hasattr(signal, 'reasons') and signal.reasons:
            panel_text += f"理由: {', '.join(signal.reasons[:2])}"

        fig.add_annotation(
            xref="paper", yref="paper", x=0.99, y=0.98,
            text=panel_text, font=dict(color="#FFF", size=11, family="Arial"),
            bgcolor="rgba(20,20,30,0.8)", bordercolor="#444", borderwidth=1, borderpad=6,
            showarrow=False, align="left", xanchor="right", yanchor="top"
        )
    def _apply_layout(self, fig: go.Figure, title: str) -> None:
        """Apply chart layout settings."""
        fig.update_layout(
            title={
                'text': title,
                'x': 0.5,
                'font': {'size': 18, 'color': '#2C3E50'},
            },
            template=self.config.theme,
            height=self.config.height,
            width=self.config.width,
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
                font=dict(size=10),
            ),
            margin=dict(l=50, r=50, t=80, b=50),
            xaxis_rangeslider_visible=False,
            xaxis=dict(
                showgrid=self.config.show_grid,
                gridcolor='rgba(200,200,200,0.3)',
            ),
            yaxis=dict(
                showgrid=self.config.show_grid,
                gridcolor='rgba(200,200,200,0.3)',
            ),
        )
        
        # Hide non-trading hours gaps by using category axis
        fig.update_xaxes(
            type='category',
            nticks=15,
        )
    
    def save_html(
        self,
        fig: go.Figure,
        filepath: Path,
        include_plotlyjs: bool = True,
    ) -> None:
        """Save chart to HTML file."""
        config = {
            'displayModeBar': True,
            'displaylogo': False,
            'modeBarButtonsToRemove': ['pan2d', 'lasso2d', 'select2d'],
            'responsive': True,
        }
        
        fig.write_html(
            filepath,
            config=config,
            include_plotlyjs='cdn' if not include_plotlyjs else True,
        )
        
        logger.debug(f"Chart saved: {filepath}")
    
    def _format_volume(self, volume: float) -> str:
        """Format volume for display."""
        if pd.isna(volume) or volume == 0:
            return "N/A"
        
        if abs(volume) >= 1e8:
            return f"{abs(volume) / 1e8:.2f}亿"
        elif abs(volume) >= 1e4:
            return f"{abs(volume) / 1e4:.2f}万"
        else:
            return f"{abs(volume):.0f}"


def create_summary_card(analysis_result: AnalysisResult) -> Dict[str, Any]:
    """Create a summary card for the analysis result."""
    return {
        'symbol': analysis_result.symbol,
        'trend': analysis_result.trend,
        'premium_discount': analysis_result.premium_discount,
        'current_price': analysis_result.current_price,
        'active_obs': analysis_result.active_obs,
        'active_fvgs': analysis_result.active_fvgs,
        'overlapping_obs': analysis_result.overlapping_obs,
        'timestamp': analysis_result.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
    }
