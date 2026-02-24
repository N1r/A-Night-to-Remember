"""
Comprehensive Market Situation Report Generator
================================================

Analyzes all generated HTML charts and creates a unified market analysis report.

Features:
- Chart content extraction
- Market-wide signal aggregation  
- Investment recommendations
- Win rate statistics
- Risk assessment
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from bs4 import BeautifulSoup
import base64

import pandas as pd
import numpy as np

from ..smc_analysis.enhanced_strategy import EnhancedSMCStrategy, EnhancedStrategyAnalysis

logger = logging.getLogger(__name__)


class MarketSituationReport:
    """Generate comprehensive market situation report."""
    
    def __init__(self, charts_dir: Path, output_dir: Path):
        self.charts_dir = Path(charts_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.strategy = EnhancedSMCStrategy()
    
    def analyze_all_charts(
        self,
        data_dir: Path,
        top_n: int = None,
    ) -> Dict:
        """
        Analyze all stocks and generate comprehensive report.
        
        Args:
            data_dir: Directory with SMC format CSV files
            top_n: Limit to top N stocks (None for all)
            
        Returns:
            Analysis results dictionary
        """
        from ..smc_analysis.enhanced_strategy import batch_enhanced_analyze
        
        # Run enhanced analysis on all stocks
        analyses = batch_enhanced_analyze(data_dir, self.output_dir)
        
        if not analyses:
            return {"error": "No analyses completed"}
        
        # Sort by score
        analyses.sort(key=lambda x: x.overall_score, reverse=True)
        
        if top_n:
            analyses = analyses[:top_n]
        
        # Calculate market-wide statistics
        stats = self._calculate_market_stats(analyses)
        
        # Generate report
        report_path = self._generate_comprehensive_report(analyses, stats)
        
        # Generate Excel summary
        excel_path = self._generate_excel_summary(analyses, stats)
        
        return {
            "analyses": analyses,
            "stats": stats,
            "report_path": str(report_path),
            "excel_path": str(excel_path),
        }
    
    def _calculate_market_stats(
        self,
        analyses: List[EnhancedStrategyAnalysis],
    ) -> Dict:
        """Calculate market-wide statistics."""
        total = len(analyses)
        
        # Signal counts
        strong_buy = sum(1 for a in analyses if a.recommendation == "强烈买入")
        buy = sum(1 for a in analyses if a.recommendation == "买入")
        strong_sell = sum(1 for a in analyses if a.recommendation == "强烈卖出")
        sell = sum(1 for a in analyses if a.recommendation == "卖出")
        hold = total - strong_buy - buy - strong_sell - sell
        
        # Zone distribution
        discount = sum(1 for a in analyses if a.zone == "discount")
        premium = sum(1 for a in analyses if a.zone == "premium")
        equilibrium = total - discount - premium
        
        # Trend distribution
        bullish = sum(1 for a in analyses if a.trend == "bullish")
        bearish = sum(1 for a in analyses if a.trend == "bearish")
        neutral_trend = total - bullish - bearish
        
        # OB statistics
        total_bullish_obs = sum(a.active_bullish_obs for a in analyses)
        total_bearish_obs = sum(a.active_bearish_obs for a in analyses)
        total_overlapping = sum(a.overlapping_obs for a in analyses)
        
        # Average scores
        avg_score = np.mean([a.overall_score for a in analyses]) if analyses else 0
        avg_win_rate = np.mean([a.estimated_win_rate for a in analyses]) if analyses else 0
        
        # High priority signals
        high_priority = sum(1 for a in analyses if a.action_priority == "high")
        medium_priority = sum(1 for a in analyses if a.action_priority == "medium")
        
        # Market regime
        trending = sum(1 for a in analyses if a.market_regime == "trending")
        ranging = sum(1 for a in analyses if a.market_regime == "ranging")
        choppy = sum(1 for a in analyses if a.market_regime == "choppy")
        
        return {
            "total_stocks": total,
            "strong_buy_signals": strong_buy,
            "buy_signals": buy,
            "strong_sell_signals": strong_sell,
            "sell_signals": sell,
            "hold_signals": hold,
            "discount_zone": discount,
            "premium_zone": premium,
            "equilibrium_zone": equilibrium,
            "bullish_trend": bullish,
            "bearish_trend": bearish,
            "neutral_trend": neutral_trend,
            "total_bullish_obs": total_bullish_obs,
            "total_bearish_obs": total_bearish_obs,
            "total_overlapping_obs": total_overlapping,
            "avg_score": avg_score,
            "avg_win_rate": avg_win_rate,
            "high_priority_signals": high_priority,
            "medium_priority_signals": medium_priority,
            "trending_stocks": trending,
            "ranging_stocks": ranging,
            "choppy_stocks": choppy,
        }
    
    def _generate_comprehensive_report(
        self,
        analyses: List[EnhancedStrategyAnalysis],
        stats: Dict,
    ) -> Path:
        """Generate comprehensive HTML report."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        report_path = self.output_dir / f"市场局势分析_{timestamp}.html"
        
        html = self._build_html(analyses, stats)
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        logger.debug(f"Report generated: {report_path}")
        return report_path
    
    def _build_html(
        self,
        analyses: List[EnhancedStrategyAnalysis],
        stats: Dict,
    ) -> str:
        """Build comprehensive HTML report."""
        
        # Market summary
        market_summary = self._generate_market_summary(stats)
        
        # Top signals section
        top_signals_html = self._generate_top_signals_section(analyses[:10])
        
        # All signals table
        all_signals_html = self._generate_all_signals_table(analyses)
        
        # Charts section
        charts_section = self._generate_charts_section(analyses[:20])
        
        # Investment recommendations
        recommendations = self._generate_recommendations(analyses, stats)
        
        return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>SMC市场局势分析报告</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
            background: linear-gradient(135deg, #0f0f23 0%, #1a1a3e 100%);
            color: #e8e8e8;
            min-height: 100vh;
            line-height: 1.6;
        }}
        
        .header {{
            background: linear-gradient(90deg, #1a1a3e 0%, #2d2d5a 100%);
            padding: 40px 20px;
            text-align: center;
            border-bottom: 3px solid #e94560;
        }}
        
        .header h1 {{
            color: #fff;
            font-size: 2.8em;
            margin-bottom: 15px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }}
        
        .header .subtitle {{
            color: #a8a8d8;
            font-size: 1.2em;
        }}
        
        .container {{
            max-width: 1600px;
            margin: 0 auto;
            padding: 30px 20px;
        }}
        
        .section {{
            background: rgba(30, 30, 60, 0.6);
            border-radius: 15px;
            padding: 25px;
            margin: 25px 0;
            border: 1px solid rgba(255,255,255,0.1);
        }}
        
        .section-title {{
            font-size: 1.6em;
            color: #fff;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #e94560;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        
        .stat-card {{
            background: linear-gradient(145deg, #252550 0%, #1e1e40 100%);
            border-radius: 12px;
            padding: 20px;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.05);
            transition: transform 0.3s ease;
        }}
        
        .stat-card:hover {{
            transform: translateY(-3px);
        }}
        
        .stat-card .value {{
            font-size: 2.2em;
            font-weight: bold;
            margin-bottom: 8px;
        }}
        
        .stat-card .label {{
            color: #888;
            font-size: 0.9em;
        }}
        
        .value.green {{ color: #4CAF50; }}
        .value.red {{ color: #f44336; }}
        .value.blue {{ color: #2196F3; }}
        .value.yellow {{ color: #FFC107; }}
        .value.purple {{ color: #9C27B0; }}
        .value.white {{ color: #fff; }}
        
        .signal-card {{
            background: linear-gradient(145deg, #252550 0%, #1e1e40 100%);
            border-radius: 12px;
            padding: 20px;
            margin: 15px 0;
            border-left: 4px solid #e94560;
        }}
        
        .signal-card.long {{ border-left-color: #4CAF50; }}
        .signal-card.short {{ border-left-color: #f44336; }}
        .signal-card.neutral {{ border-left-color: #FFC107; }}
        
        .signal-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }}
        
        .signal-title {{
            font-size: 1.3em;
            font-weight: bold;
        }}
        
        .badge {{
            display: inline-block;
            padding: 6px 16px;
            border-radius: 20px;
            font-size: 0.9em;
            font-weight: bold;
        }}
        
        .badge.strong-buy {{ background: linear-gradient(90deg, #2E7D32, #4CAF50); color: white; }}
        .badge.buy {{ background: #4CAF50; color: white; }}
        .badge.strong-sell {{ background: linear-gradient(90deg, #B71C1C, #f44336); color: white; }}
        .badge.sell {{ background: #f44336; color: white; }}
        .badge.hold {{ background: #FFC107; color: #333; }}
        .badge.light {{ background: rgba(255,255,255,0.1); color: #aaa; }}
        
        .signal-details {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 12px;
            margin-top: 15px;
        }}
        
        .detail-item {{
            background: rgba(0,0,0,0.2);
            padding: 12px;
            border-radius: 8px;
            text-align: center;
        }}
        
        .detail-item .label {{
            font-size: 0.85em;
            color: #888;
            margin-bottom: 5px;
        }}
        
        .detail-item .value {{
            font-size: 1.1em;
            font-weight: bold;
        }}
        
        .levels-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 15px;
            margin-top: 15px;
            padding: 15px;
            background: rgba(0,0,0,0.2);
            border-radius: 10px;
        }}
        
        .level-item {{
            text-align: center;
        }}
        
        .level-item .label {{
            font-size: 0.85em;
            color: #888;
        }}
        
        .level-item .value {{
            font-size: 1.2em;
            font-weight: bold;
        }}
        
        .value.blue {{ color: #2196F3; }}
        .value.red {{ color: #f44336; }}
        .value.green {{ color: #4CAF50; }}
        
        .confluence-list {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 10px;
        }}
        
        .confluence-tag {{
            background: rgba(76, 175, 80, 0.2);
            color: #4CAF50;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85em;
        }}
        
        .warning-tag {{
            background: rgba(255, 152, 0, 0.2);
            color: #ff9800;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85em;
        }}
        
        .chart-container {{
            background: rgba(0,0,0,0.2);
            border-radius: 10px;
            padding: 15px;
            margin: 15px 0;
        }}
        
        .chart-placeholder {{
            height: 250px;
            background: #1a1a3a;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #555;
            font-size: 0.9em;
        }}
        
        /* Chart Cards Grid */
        .charts-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(700px, 1fr));
            gap: 25px;
            margin: 20px 0;
        }}
        
        .chart-card {{
            background: linear-gradient(145deg, #1e2746 0%, #232b46 100%);
            border-radius: 15px;
            overflow: hidden;
            border: 1px solid rgba(255,255,255,0.1);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }}
        
        .chart-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 10px 30px rgba(233, 69, 96, 0.2);
        }}
        
        .chart-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 15px 20px;
            background: rgba(0,0,0,0.3);
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        
        .chart-title {{
            font-weight: bold;
            font-size: 1.1em;
            color: #fff;
        }}
        
        .chart-badge {{
            padding: 5px 15px;
            border-radius: 15px;
            font-size: 0.85em;
            font-weight: 600;
        }}
        
        .badge-strong-buy {{ background: #2E7D32; color: white; }}
        .badge-buy {{ background: #4CAF50; color: white; }}
        .badge-strong-sell {{ background: #B71C1C; color: white; }}
        .badge-sell {{ background: #f44336; color: white; }}
        .badge-hold {{ background: #FFC107; color: #333; }}
        
        .chart-score {{
            color: #888;
            font-size: 0.9em;
        }}
        
        .chart-iframe {{
            width: 100%;
            height: 500px;
            border: none;
            background: #fff;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        
        th {{
            background: #1a1a3e;
            color: #fff;
            padding: 12px;
            text-align: left;
            font-weight: 600;
            border-bottom: 2px solid #e94560;
        }}
        
        td {{
            padding: 12px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }}
        
        tr:hover {{
            background: rgba(233, 69, 96, 0.05);
        }}
        
        .progress-bar {{
            width: 100%;
            height: 6px;
            background: #333;
            border-radius: 3px;
            overflow: hidden;
            margin-top: 5px;
        }}
        
        .progress-bar .fill {{
            height: 100%;
            border-radius: 3px;
        }}
        
        .fill.green {{ background: linear-gradient(90deg, #4CAF50, #8BC34A); }}
        .fill.red {{ background: linear-gradient(90deg, #f44336, #ff5722); }}
        .fill.yellow {{ background: linear-gradient(90deg, #FFC107, #ff9800); }}
        
        .recommendation-box {{
            background: linear-gradient(145deg, #1a3a1a 0%, #0f2f0f 100%);
            border-radius: 12px;
            padding: 25px;
            margin: 20px 0;
            border: 1px solid rgba(76, 175, 80, 0.3);
        }}
        
        .recommendation-box h3 {{
            color: #4CAF50;
            margin-bottom: 15px;
        }}
        
        .recommendation-box ul {{
            list-style: none;
            padding-left: 0;
        }}
        
        .recommendation-box li {{
            padding: 8px 0;
            padding-left: 20px;
            position: relative;
        }}
        
        .recommendation-box li::before {{
            content: "✓";
            position: absolute;
            left: 0;
            color: #4CAF50;
        }}
        
        .footer {{
            text-align: center;
            padding: 40px 20px;
            color: #666;
            font-size: 0.9em;
        }}
        
        .two-column {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-top: 15px;
        }}
        
        @media (max-width: 768px) {{
            .header h1 {{ font-size: 2em; }}
            .stats-grid {{ grid-template-columns: repeat(2, 1fr); }}
            .two-column {{ grid-template-columns: 1fr; }}
            .levels-grid {{ grid-template-columns: repeat(2, 1fr); }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📈 SMC 智能资金市场局势分析</h1>
        <div class="subtitle">
            Smart Money Concepts 综合技术分析报告<br>
            生成时间: {datetime.now().strftime('%Y年%m月%d日 %H:%M')}
        </div>
    </div>
    
    <div class="container">
        <!-- Market Summary -->
        {market_summary}
        
        <!-- Top Signals -->
        <div class="section">
            <h2 class="section-title">🎯 高分信号股票 (Top 10)</h2>
            {top_signals_html}
        </div>
        
        <!-- All Signals Table -->
        <div class="section">
            <h2 class="section-title">📋 全部股票信号一览</h2>
            {all_signals_html}
        </div>
        
        <!-- Charts Preview -->
        <div class="section">
            <h2 class="section-title">📊 图表预览</h2>
            {charts_section}
        </div>
        
        <!-- Investment Recommendations -->
        <div class="section">
            <h2 class="section-title">💡 投资建议</h2>
            {recommendations}
        </div>
        
        <!-- Strategy Explanation -->
        <div class="section">
            <h2 class="section-title">📚 策略说明</h2>
            <div class="recommendation-box">
                <h3>核心策略：OB双重重叠</h3>
                <p style="color: #aaa; margin-bottom: 15px;">
                    基于Smart Money Concepts的核心概念，重点识别机构资金留下的订单块(Order Block)。
                    当价格多次回到同一价位区域并形成重叠时，表明机构可能在该位置持续建仓。
                </p>
                <ul>
                    <li><strong>买入信号</strong>：折价区 + 牛市OB双重重叠 + 趋势一致</li>
                    <li><strong>卖出信号</strong>：溢价区 + 熊市OB双重重叠 + 趋势一致</li>
                    <li><strong>信号强度</strong>：OB重叠度 > 50% 为强信号，> 70% 为极强信号</li>
                    <li><strong>多OB叠加</strong>：多个OB在同一价格区域形成更强支撑/阻力</li>
                    <li><strong>风控建议</strong>：单笔风险不超过账户的 2-5%</li>
                </ul>
            </div>
        </div>
        
        <!-- Risk Warning -->
        <div class="section" style="border-left-color: #ff9800;">
            <h2 class="section-title" style="color: #ff9800;">⚠️ 风险提示</h2>
            <p style="color: #aaa;">
                本报告基于技术分析生成，仅供参考，不构成投资建议。
                股市有风险，投资需谨慎。历史表现不代表未来收益。
                请根据自身风险承受能力和投资目标做出决策。
            </p>
        </div>
    </div>
    
    <div class="footer">
        SMC Technical Analysis Tool v2.0 | 智能资金概念分析
    </div>
</body>
</html>'''
    
    def _generate_market_summary(self, stats: Dict) -> str:
        """Generate market summary section."""
        # Determine market sentiment
        buy_signals = stats['strong_buy_signals'] + stats['buy_signals']
        sell_signals = stats['strong_sell_signals'] + stats['sell_signals']
        
        if buy_signals > sell_signals * 1.5:
            sentiment = "偏多"
            sentiment_color = "green"
        elif sell_signals > buy_signals * 1.5:
            sentiment = "偏空"
            sentiment_color = "red"
        else:
            sentiment = "震荡"
            sentiment_color = "yellow"
        
        return f'''
        <div class="section">
            <h2 class="section-title">🌍 市场概况</h2>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="value white">{stats['total_stocks']}</div>
                    <div class="label">分析股票总数</div>
                </div>
                <div class="stat-card">
                    <div class="value {sentiment_color}">{sentiment}</div>
                    <div class="label">市场情绪</div>
                </div>
                <div class="stat-card">
                    <div class="value green">{buy_signals}</div>
                    <div class="label">买入信号</div>
                </div>
                <div class="stat-card">
                    <div class="value red">{sell_signals}</div>
                    <div class="label">卖出信号</div>
                </div>
                <div class="stat-card">
                    <div class="value blue">{stats['avg_score']:.1f}</div>
                    <div class="label">平均信号强度</div>
                </div>
                <div class="stat-card">
                    <div class="value yellow">{stats['avg_win_rate']:.1f}%</div>
                    <div class="label">平均预估胜率</div>
                </div>
            </div>
            
            <div class="stats-grid" style="margin-top: 30px;">
                <div class="stat-card">
                    <div class="value green">{stats['discount_zone']}</div>
                    <div class="label">折价区股票</div>
                </div>
                <div class="stat-card">
                    <div class="value red">{stats['premium_zone']}</div>
                    <div class="label">溢价区股票</div>
                </div>
                <div class="stat-card">
                    <div class="value blue">{stats['bullish_trend']}</div>
                    <div class="label">上涨趋势</div>
                </div>
                <div class="stat-card">
                    <div class="value red">{stats['bearish_trend']}</div>
                    <div class="label">下跌趋势</div>
                </div>
                <div class="stat-card">
                    <div class="value purple">{stats['high_priority_signals']}</div>
                    <div class="label">高优先级信号</div>
                </div>
                <div class="stat-card">
                    <div class="value yellow">{stats['total_overlapping_obs']}</div>
                    <div class="label">重叠OB总数</div>
                </div>
            </div>
        </div>
'''
    
    def _generate_top_signals_section(
        self,
        analyses: List[EnhancedStrategyAnalysis],
    ) -> str:
        """Generate top signals section."""
        html = ""
        
        for analysis in analyses:
            if analysis.primary_signal is None:
                continue
            
            signal = analysis.primary_signal
            
            # Badge class
            rec_map = {
                "强烈买入": "strong-buy",
                "买入": "buy",
                "强烈卖出": "strong-sell",
                "卖出": "sell",
            }
            badge_class = rec_map.get(analysis.recommendation, "hold")
            
            # Border class
            border_class = signal.signal_type
            
            # Progress color
            progress_color = "green" if analysis.overall_score >= 50 else "yellow"
            
            html += f'''
            <div class="signal-card {border_class}">
                <div class="signal-header">
                    <div class="signal-title">{signal.symbol} {signal.name}</div>
                    <span class="badge {badge_class}">{analysis.recommendation}</span>
                </div>
                
                <div class="signal-details">
                    <div class="detail-item">
                        <div class="label">当前价</div>
                        <div class="value">{analysis.current_price:.2f}</div>
                    </div>
                    <div class="detail-item">
                        <div class="label">信号强度</div>
                        <div class="value">{signal.signal_strength:.0f}/100</div>
                        <div class="progress-bar">
                            <div class="fill {progress_color}" style="width: {signal.signal_strength}%;"></div>
                        </div>
                    </div>
                    <div class="detail-item">
                        <div class="label">OB重叠度</div>
                        <div class="value">{signal.ob_overlap_score:.0f}%</div>
                    </div>
                    <div class="detail-item">
                        <div class="label">预估胜率</div>
                        <div class="value">{analysis.estimated_win_rate:.1f}%</div>
                    </div>
                    <div class="detail-item">
                        <div class="label">盈亏比</div>
                        <div class="value">1:{signal.risk_reward_ratio:.1f}</div>
                    </div>
                    <div class="detail-item">
                        <div class="label">区域</div>
                        <div class="value">{'溢价' if analysis.zone == 'premium' else '折价' if analysis.zone == 'discount' else '平衡'}</div>
                    </div>
                </div>
                
                {self._generate_levels_html(signal)}
                
                <div class="two-column">
                    <div>
                        <h4 style="color: #4CAF50; margin-top: 15px;">✓ 融合因素</h4>
                        <div class="confluence-list">
                            {''.join(f'<span class="confluence-tag">{f}</span>' for f in signal.confluence_factors[:5])}
                        </div>
                    </div>
                    <div>
                        <h4 style="color: #ff9800; margin-top: 15px;">⚠ 风险提示</h4>
                        <div class="confluence-list">
                            {''.join(f'<span class="warning-tag">{w}</span>' for w in signal.warnings[:3])}
                        </div>
                    </div>
                </div>
            </div>
'''
        
        return html
    
    def _generate_levels_html(self, signal) -> str:
        """Generate trading levels HTML."""
        if signal.signal_type == "neutral":
            return ""
        
        return f'''
                <div class="levels-grid">
                    <div class="level-item">
                        <div class="label">入场价</div>
                        <div class="value blue">{signal.entry_price:.2f}</div>
                    </div>
                    <div class="level-item">
                        <div class="label">止损价</div>
                        <div class="value red">{signal.stop_loss:.2f}</div>
                    </div>
                    <div class="level-item">
                        <div class="label">目标1 (2R)</div>
                        <div class="value green">{signal.take_profit_1:.2f}</div>
                    </div>
                    <div class="level-item">
                        <div class="label">目标2 (3R)</div>
                        <div class="value green">{signal.take_profit_2:.2f}</div>
                    </div>
                </div>
'''
    
    def _generate_all_signals_table(
        self,
        analyses: List[EnhancedStrategyAnalysis],
    ) -> str:
        """Generate all signals table."""
        rows = ""
        
        for analysis in analyses:
            signal = analysis.primary_signal
            
            # Recommendation badge
            rec_map = {
                "强烈买入": ("strong-buy", "#2E7D32"),
                "买入": ("buy", "#4CAF50"),
                "强烈卖出": ("strong-sell", "#B71C1C"),
                "卖出": ("sell", "#f44336"),
            }
            badge_info = rec_map.get(analysis.recommendation, ("hold", "#FFC107"))
            
            progress_color = "green" if analysis.overall_score >= 50 else "yellow"
            rr = signal.risk_reward_ratio if signal else 0
            
            rows += f'''
                <tr>
                    <td><strong>{analysis.symbol}</strong></td>
                    <td>{analysis.name}</td>
                    <td>{analysis.current_price:.2f}</td>
                    <td><span class="badge {badge_info[0]}">{analysis.recommendation}</span></td>
                    <td>
                        <div class="progress-bar" style="width: 80px;">
                            <div class="fill {progress_color}" style="width: {analysis.overall_score}%;"></div>
                        </div>
                        <span style="margin-left: 5px;">{analysis.overall_score:.0f}</span>
                    </td>
                    <td>{analysis.estimated_win_rate:.1f}%</td>
                    <td>{rr:.1f}</td>
                    <td>{'溢价' if analysis.zone == 'premium' else '折价' if analysis.zone == 'discount' else '平衡'}</td>
                    <td>{analysis.active_bullish_obs}/{analysis.active_bearish_obs}</td>
                    <td><span class="badge light">{analysis.action_priority}</span></td>
                </tr>
'''
        
        return f'''
        <table>
            <thead>
                <tr>
                    <th>代码</th>
                    <th>名称</th>
                    <th>当前价</th>
                    <th>建议</th>
                    <th>强度</th>
                    <th>胜率</th>
                    <th>盈亏比</th>
                    <th>区域</th>
                    <th>OB</th>
                    <th>优先级</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
'''
    
    def _generate_charts_section(
        self,
        analyses: List[EnhancedStrategyAnalysis],
    ) -> str:
        """Generate charts section with embedded SMC charts (Top 20)."""
        
        # Section header
        html = '''
        <h2 class="section-title">📊 SMC技术分析图表 (Top 20)</h2>
        <p style="color: #888; margin-bottom: 20px;">以下展示信号强度最高的20只股票的SMC分析图表</p>
        <div class="charts-grid">
'''
        
        charts_dir = self.charts_dir
        embedded_count = 0
        
        for analysis in analyses[:20]:
            # Find chart file - try multiple patterns
            patterns = [
                charts_dir / f"{analysis.symbol}_{analysis.name}_chart.html",
                charts_dir / f"{analysis.symbol}_{analysis.name.replace('-', '')}_chart.html",
                charts_dir / f"{analysis.symbol}_chart.html",
            ]
            
            chart_file = None
            for p in patterns:
                if p.exists():
                    chart_file = p
                    break
            
            if chart_file and chart_file.exists():
                embedded_count += 1
                
                # Copy chart to reports directory for iframe access
                report_chart_path = self.output_dir / chart_file.name
                if not report_chart_path.exists():
                    try:
                        import shutil
                        shutil.copy(chart_file, report_chart_path)
                    except Exception as e:
                        logger.debug(f"Could not copy chart: {e}")
                
                # Badge color based on recommendation
                badge_class = {
                    "强烈买入": "badge-strong-buy",
                    "买入": "badge-buy",
                    "强烈卖出": "badge-strong-sell",
                    "卖出": "badge-sell",
                    "观望": "badge-hold",
                }.get(analysis.recommendation, "badge-hold")
                
                html += f'''
            <div class="chart-card">
                <div class="chart-header">
                    <span class="chart-title">{analysis.symbol} {analysis.name}</span>
                    <span class="chart-badge {badge_class}">{analysis.recommendation}</span>
                    <span class="chart-score">强度: {analysis.overall_score:.0f}</span>
                </div>
                <iframe src="{chart_file.name}" class="chart-iframe" loading="lazy"></iframe>
            </div>
'''
        
        html += '</div>'
        
        if embedded_count == 0:
            html = '''
            <h2 class="section-title">📊 SMC技术分析图表</h2>
            <p style="color: #888;">暂无图表数据。请先生成图表文件。</p>
'''
        
        return html
    
    def _generate_recommendations(
        self,
        analyses: List[EnhancedStrategyAnalysis],
        stats: Dict,
    ) -> str:
        """Generate investment recommendations."""
        
        # Buy recommendations
        buy_stocks = [
            a for a in analyses 
            if a.recommendation in ["强烈买入", "买入"]
        ][:5]
        
        # Sell recommendations
        sell_stocks = [
            a for a in analyses 
            if a.recommendation in ["强烈卖出", "卖出"]
        ][:5]
        
        buy_html = ""
        for a in buy_stocks:
            s = a.primary_signal
            buy_html += f'''
            <li>
                <strong>{a.symbol} {a.name}</strong>: 
                入场 {s.entry_price:.2f} | 止损 {s.stop_loss:.2f} | 
                目标 {s.take_profit_1:.2f} ~ {s.take_profit_2:.2f} |
                强度 {a.overall_score:.0f} | 胜率 {a.estimated_win_rate:.0f}%
            </li>
'''
        
        sell_html = ""
        for a in sell_stocks:
            s = a.primary_signal
            sell_html += f'''
            <li>
                <strong>{a.symbol} {a.name}</strong>: 
                入场 {s.entry_price:.2f} | 止损 {s.stop_loss:.2f} |
                强度 {a.overall_score:.0f} | 胜率 {a.estimated_win_rate:.0f}%
            </li>
'''
        
        # Overall market advice
        if stats['avg_win_rate'] > 55:
            market_advice = "当前市场胜率较高，可适当参与。建议分批建仓，严格执行止损。"
        elif stats['avg_win_rate'] > 50:
            market_advice = "市场信号中等，建议观望为主，精选高分信号参与。"
        else:
            market_advice = "当前市场信号较弱，建议以观望为主，等待更明确信号。"
        
        return f'''
        <div class="two-column">
            <div class="recommendation-box">
                <h3>🟢 买入机会</h3>
                <ul>
                    {buy_html if buy_html else '<li>暂无强烈买入信号</li>'}
                </ul>
            </div>
            
            <div class="recommendation-box" style="background: linear-gradient(145deg, #3a1a1a 0%, #2f0f0f 100%); border-color: rgba(244, 67, 54, 0.3);">
                <h3 style="color: #f44336;">🔴 卖出/减仓</h3>
                <ul>
                    {sell_html if sell_html else '<li>暂无强烈卖出信号</li>'}
                </ul>
            </div>
        </div>
        
        <div class="recommendation-box" style="margin-top: 20px;">
            <h3>📌 综合建议</h3>
            <p style="color: #aaa; margin: 15px 0;">{market_advice}</p>
            <ul>
                <li>优先关注信号强度 > 60 的股票</li>
                <li>OB重叠度 > 50% 的信号更可靠</li>
                <li>多OB叠加区域支撑/阻力更强</li>
                <li>建议单笔风险控制在账户的 2-5%</li>
                <li>严格执行止损，避免情绪化交易</li>
            </ul>
        </div>
'''
    
    def _generate_excel_summary(
        self,
        analyses: List[EnhancedStrategyAnalysis],
        stats: Dict,
    ) -> Path:
        """Generate Excel summary."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        excel_path = self.output_dir / f"投资建议汇总_{timestamp}.xlsx"
        
        # Main summary
        summary_data = []
        for a in analyses:
            s = a.primary_signal
            summary_data.append({
                '股票代码': a.symbol,
                '股票名称': a.name,
                '当前价': a.current_price,
                '操作建议': a.recommendation,
                '信号强度': a.overall_score,
                '预估胜率': f"{a.estimated_win_rate:.1f}%",
                '盈亏比': s.risk_reward_ratio if s else 0,
                '价格区域': a.zone,
                '趋势': a.trend,
                '入场价': s.entry_price if s else 0,
                '止损价': s.stop_loss if s else 0,
                '目标1': s.take_profit_1 if s else 0,
                '目标2': s.take_profit_2 if s else 0,
                'OB重叠度': f"{s.ob_overlap_score:.0f}%" if s else "N/A",
                'OB叠加数': s.ob_confluence_count if s else 0,
                '市场状态': a.market_regime,
                '风险评分': s.risk_score if s else 0,
                '建议仓位%': s.position_size_suggestion if s else 0,
                '优先级': a.action_priority,
                '融合因素': "; ".join(s.confluence_factors) if s and s.confluence_factors else "",
                '风险提示': "; ".join(s.warnings) if s and s.warnings else "",
            })
        
        df = pd.DataFrame(summary_data)
        
        # Create Excel with multiple sheets
        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='信号汇总', index=False)
            
            # Statistics sheet
            stats_df = pd.DataFrame([stats])
            stats_df.to_excel(writer, sheet_name='市场统计', index=False)
            
            # Buy signals only
            buy_df = df[df['操作建议'].isin(['强烈买入', '买入'])]
            buy_df.to_excel(writer, sheet_name='买入信号', index=False)
            
            # Sell signals only
            sell_df = df[df['操作建议'].isin(['强烈卖出', '卖出'])]
            sell_df.to_excel(writer, sheet_name='卖出信号', index=False)
        
        logger.debug(f"Excel summary generated: {excel_path}")
        return excel_path


def generate_market_report(
    data_dir: Path,
    charts_dir: Path,
    output_dir: Path,
) -> Dict:
    """Generate comprehensive market situation report."""
    reporter = MarketSituationReport(charts_dir, output_dir)
    return reporter.analyze_all_charts(data_dir)
