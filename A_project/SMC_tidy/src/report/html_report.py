"""
HTML Report Generator for SMC Analysis
======================================

Generates comprehensive HTML reports with charts, signals, and investment recommendations.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import pandas as pd
import numpy as np

from ..smc_analysis.strategy import StrategyAnalysis, TradingSignal

logger = logging.getLogger(__name__)


class HTMLReportGenerator:
    """Generate comprehensive HTML reports for SMC analysis."""
    
    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_full_report(
        self,
        analyses: List[StrategyAnalysis],
        chart_files: Optional[Dict[str, Path]] = None,
        title: str = "SMC Technical Analysis Report",
    ) -> Path:
        """Generate complete HTML report."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_path = self.output_dir / f"smc_report_{timestamp}.html"
        
        # Sort analyses by score
        analyses_sorted = sorted(analyses, key=lambda x: x.overall_score, reverse=True)
        
        # Generate HTML content
        html = self._generate_html_template(title, analyses_sorted, chart_files)
        
        # Save report
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        logger.debug(f"Report generated: {report_path}")
        return report_path
    
    def _generate_html_template(
        self,
        title: str,
        analyses: List[StrategyAnalysis],
        chart_files: Optional[Dict[str, Path]] = None,
    ) -> str:
        """Generate complete HTML template."""
        
        # Summary statistics
        total = len(analyses)
        buy_signals = sum(1 for a in analyses if a.recommendation in ["买入", "强烈买入"])
        sell_signals = sum(1 for a in analyses if a.recommendation in ["卖出", "强烈卖出"])
        hold_signals = total - buy_signals - sell_signals
        
        avg_score = np.mean([a.overall_score for a in analyses]) if analyses else 0
        avg_win_rate = np.mean([a.historical_win_rate for a in analyses]) if analyses else 0
        
        return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Microsoft YaHei', sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #e8e8e8;
            min-height: 100vh;
        }}
        .header {{
            background: linear-gradient(90deg, #0f3460 0%, #16213e 100%);
            padding: 30px;
            text-align: center;
            border-bottom: 3px solid #e94560;
        }}
        .header h1 {{ color: #fff; font-size: 2.5em; margin-bottom: 10px; }}
        .header .subtitle {{ color: #a8a8a8; font-size: 1.1em; }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
        .summary-section {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }}
        .summary-card {{
            background: linear-gradient(145deg, #1e2746 0%, #232b46 100%);
            border-radius: 15px;
            padding: 25px;
            text-align: center;
            border: 1px solid #333;
        }}
        .summary-card .value {{ font-size: 2.5em; font-weight: bold; margin-bottom: 10px; }}
        .summary-card .label {{ color: #888; font-size: 0.9em; }}
        .value.green {{ color: #4CAF50; }}
        .value.red {{ color: #f44336; }}
        .value.blue {{ color: #2196F3; }}
        .value.yellow {{ color: #FFC107; }}
        .value.white {{ color: #fff; }}
        .signal-box {{
            background: linear-gradient(145deg, #1e2746 0%, #232b46 100%);
            border-radius: 10px;
            padding: 20px;
            margin: 15px 0;
            border-left: 4px solid #e94560;
        }}
        .signal-box.long {{ border-left-color: #4CAF50; }}
        .signal-box.short {{ border-left-color: #f44336; }}
        .badge {{
            display: inline-block;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: 600;
        }}
        .badge.buy {{ background: #4CAF50; color: white; }}
        .badge.strong-buy {{ background: #2E7D32; color: white; }}
        .badge.sell {{ background: #f44336; color: white; }}
        .badge.strong-sell {{ background: #B71C1C; color: white; }}
        .badge.hold {{ background: #FFC107; color: #333; }}
        .section-title {{
            font-size: 1.5em;
            margin: 30px 0 20px 0;
            padding-bottom: 10px;
            border-bottom: 2px solid #e94560;
        }}
        .footer {{ text-align: center; padding: 30px; color: #666; font-size: 0.9em; }}
        .progress-bar {{
            width: 100%; height: 8px;
            background: #333; border-radius: 4px;
            overflow: hidden; margin-top: 10px;
        }}
        .progress-bar .fill {{ height: 100%; border-radius: 4px; }}
        .progress-bar .fill.green {{ background: linear-gradient(90deg, #4CAF50, #8BC34A); }}
        .progress-bar .fill.yellow {{ background: linear-gradient(90deg, #FFC107, #ff9800); }}
        .stocks-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; background: #1e2746; border-radius: 15px; overflow: hidden; }}
        .stocks-table th {{ background: #0f3460; color: #fff; padding: 15px; text-align: left; }}
        .stocks-table td {{ padding: 15px; border-bottom: 1px solid #333; }}
        .stocks-table tr:hover {{ background: rgba(233, 69, 96, 0.1); }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📈 {title}</h1>
        <div class="subtitle">Smart Money Concepts 技术分析报告 | 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
    </div>
    
    <div class="container">
        <div class="summary-section">
            <div class="summary-card">
                <div class="value white">{total}</div>
                <div class="label">分析股票总数</div>
            </div>
            <div class="summary-card">
                <div class="value green">{buy_signals}</div>
                <div class="label">买入信号</div>
            </div>
            <div class="summary-card">
                <div class="value red">{sell_signals}</div>
                <div class="label">卖出信号</div>
            </div>
            <div class="summary-card">
                <div class="value yellow">{hold_signals}</div>
                <div class="label">观望信号</div>
            </div>
            <div class="summary-card">
                <div class="value blue">{avg_score:.1f}</div>
                <div class="label">平均信号强度</div>
            </div>
            <div class="summary-card">
                <div class="value white">{avg_win_rate:.1f}%</div>
                <div class="label">预估胜率</div>
            </div>
        </div>
        
        <h2 class="section-title">🎯 强信号股票 (Top 10)</h2>
        {self._generate_top_signals_html(analyses[:10])}
        
        <h2 class="section-title">📊 全部股票信号</h2>
        {self._generate_table_html(analyses)}
        
        <h2 class="section-title">📚 策略说明</h2>
        <div class="signal-box">
            <h3>OB双重重叠策略 (Order Block Double Overlap)</h3>
            <p style="margin-top: 15px; color: #a8a8a8; line-height: 1.8;">
                该策略基于Smart Money Concepts的核心概念，重点识别机构资金留下的订单块(Order Block)。
                当价格回到订单块区域并形成双重或多重重叠时，表明机构可能在同一价位持续建仓，
                形成强支撑/阻力区域，这是高概率交易机会。
            </p>
        </div>
    </div>
    
    <div class="footer">
        SMC Technical Analysis Tool v2.0 | Powered by Smart Money Concepts
    </div>
</body>
</html>'''
    
    def _generate_top_signals_html(self, analyses: List[StrategyAnalysis]) -> str:
        """Generate HTML for top signals section."""
        html = ""
        
        for analysis in analyses:
            if analysis.primary_signal is None:
                continue
            
            signal = analysis.primary_signal
            badge_class = self._get_badge_class(analysis.recommendation)
            name = getattr(analysis, 'name', '')
            
            html += f'''
        <div class="signal-box {signal.signal_type}">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <h3 style="display: inline;">{analysis.symbol} {name}</h3>
                    <span class="badge {badge_class}" style="margin-left: 15px;">{analysis.recommendation}</span>
                </div>
                <div style="text-align: right;">
                    <div style="font-size: 1.5em; font-weight: bold;">{analysis.current_price:.2f}</div>
                    <div style="color: #888;">当前价格</div>
                </div>
            </div>
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-top: 15px;">
                <div style="background: rgba(0,0,0,0.2); padding: 10px; border-radius: 8px; text-align: center;">
                    <div style="font-size: 0.8em; color: #888;">信号强度</div>
                    <div style="font-size: 1.2em; font-weight: bold;">{signal.signal_strength:.0f}/100</div>
                </div>
                <div style="background: rgba(0,0,0,0.2); padding: 10px; border-radius: 8px; text-align: center;">
                    <div style="font-size: 0.8em; color: #888;">OB重叠度</div>
                    <div style="font-size: 1.2em; font-weight: bold;">{signal.ob_overlap_score:.0f}%</div>
                </div>
                <div style="background: rgba(0,0,0,0.2); padding: 10px; border-radius: 8px; text-align: center;">
                    <div style="font-size: 0.8em; color: #888;">预估胜率</div>
                    <div style="font-size: 1.2em; font-weight: bold;">{analysis.historical_win_rate:.1f}%</div>
                </div>
                <div style="background: rgba(0,0,0,0.2); padding: 10px; border-radius: 8px; text-align: center;">
                    <div style="font-size: 0.8em; color: #888;">盈亏比</div>
                    <div style="font-size: 1.2em; font-weight: bold;">1:{signal.risk_reward_ratio:.1f}</div>
                </div>
            </div>
        </div>
'''
        
        return html
    
    def _generate_table_html(self, analyses: List[StrategyAnalysis]) -> str:
        """Generate full signals table HTML."""
        rows = ""
        
        for analysis in analyses:
            signal = analysis.primary_signal
            badge_class = self._get_badge_class(analysis.recommendation)
            name = getattr(analysis, 'name', '')
            
            rr_ratio = signal.risk_reward_ratio if signal else 0
            zone_text = '溢价区' if analysis.zone == 'premium' else ('折价区' if analysis.zone == 'discount' else '平衡区')
            fill_color = 'green' if analysis.overall_score >= 50 else 'yellow'
            
            rows += f'''
            <tr>
                <td><strong>{analysis.symbol}</strong></td>
                <td>{name}</td>
                <td>{analysis.current_price:.2f}</td>
                <td><span class="badge {badge_class}">{analysis.recommendation}</span></td>
                <td>
                    <div class="progress-bar" style="width: 100px;">
                        <div class="fill {fill_color}" style="width: {analysis.overall_score}%;"></div>
                    </div>
                    <span style="margin-left: 10px;">{analysis.overall_score:.0f}</span>
                </td>
                <td>{analysis.historical_win_rate:.1f}%</td>
                <td>{rr_ratio:.1f}</td>
                <td>{zone_text}</td>
            </tr>
'''
        
        return f'''
        <table class="stocks-table">
            <thead>
                <tr>
                    <th>代码</th>
                    <th>名称</th>
                    <th>当前价</th>
                    <th>建议</th>
                    <th>信号强度</th>
                    <th>预估胜率</th>
                    <th>盈亏比</th>
                    <th>区域</th>
                </tr>
            </thead>
            <tbody>
                {rows}
            </tbody>
        </table>
'''
    
    def _get_badge_class(self, recommendation: str) -> str:
        """Get badge CSS class for recommendation."""
        mapping = {
            "强烈买入": "strong-buy",
            "买入": "buy",
            "卖出": "sell",
            "强烈卖出": "strong-sell",
            "观望": "hold",
        }
        return mapping.get(recommendation, "hold")


def generate_report_from_analyses(
    analyses: List[StrategyAnalysis],
    output_dir: Path,
    title: str = "SMC Investment Analysis Report",
) -> Path:
    """Generate HTML report from strategy analyses."""
    generator = HTMLReportGenerator(output_dir)
    return generator.generate_full_report(analyses, title=title)
