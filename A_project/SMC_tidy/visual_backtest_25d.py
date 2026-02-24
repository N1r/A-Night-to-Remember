#!/usr/bin/env python3
"""
SMC 多股票 25日周期回测可视化脚本 - visual_backtest_25d.py
======================================================
1. 使用已有数据 (从 data/raw 中读取)
2. 选择前 100 个股票进行测试
3. 每间隔 25 天测试一次各股票信号
4. 生成 HTML 图表及总索引页面
"""

import sys
import os
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
from rich.console import Console
from rich.progress import Progress

# 将项目根目录添加到路径
sys.path.insert(0, str(Path(__file__).parent))

from src.smc_analysis.enhanced_strategy import EnhancedSMCStrategy

console = Console()

# 配置
INTERVAL_DAYS = 10
WINDOW_SIZE = 450
SCORE_THRESHOLD = 0.15
MAX_STOCKS = 1000  # 设置一个足够大的数以涵盖所有 895 只股票
BATCH_OUTPUT_DIR = Path("output/backtest/batch")

def get_available_stocks():
    """从 data/raw 中获取前 100 个已有的日线数据文件"""
    raw_dir = Path("data/raw")
    if not raw_dir.exists():
        console.print("[red]错误: data/raw 目录不存在[/red]")
        return []
    
    # 匹配 _daily.csv 结尾的文件
    files = sorted(list(raw_dir.glob("*_daily.csv")))
    stocks = []
    for f in files[:MAX_STOCKS]:
        parts = f.stem.split('_')
        if len(parts) >= 2:
            stocks.append({
                'symbol': parts[0],
                'name': parts[1],
                'path': f
            })
    return stocks

def load_stock_data(path):
    """加载单只股票的数据并转换列名"""
    try:
        df = pd.read_csv(path)
        
        # 列名映射 (中文 -> 英文)
        mapping = {
            '日期': 'timestamp',
            '开盘': 'open',
            '收盘': 'close',
            '最高': 'high',
            '最低': 'low',
            '成交量': 'volume'
        }
        df = df.rename(columns=mapping)
        
        if 'timestamp' not in df.columns:
            return None
            
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        # 确保数值列为 float
        for col in ['open', 'high', 'low', 'close']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
        return df.dropna(subset=['open', 'high', 'low', 'close'])
    except Exception as e:
        console.print(f"[red]加载 {path.name} 失败: {e}[/red]")
        return None

from plotly.subplots import make_subplots

def create_individual_chart(df, signals, symbol, name):
    """为单只股票创建图表 - 改进版带成交量"""
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.03, subplot_titles=(f'{name} ({symbol}) SMC Backtest', 'Volume'), 
                        row_width=[0.2, 0.7])

    # K线图
    fig.add_trace(go.Candlestick(
        x=df['timestamp'],
        open=df['open'], high=df['high'], low=df['low'], close=df['close'],
        name='Price',
        increasing_line_color='#ef5350', decreasing_line_color='#26a69a',
    ), row=1, col=1)

    # 成交量
    colors = ['#ef5350' if row['close'] > row['open'] else '#26a69a' for _, row in df.iterrows()]
    fig.add_trace(go.Bar(
        x=df['timestamp'], y=df['volume'], 
        name='Volume', marker_color=colors, opacity=0.5
    ), row=2, col=1)

    if signals:
        sig_df = pd.DataFrame(signals)
        # Long
        longs = sig_df[sig_df['type'] == 'long']
        if not longs.empty:
            fig.add_trace(go.Scatter(
                x=longs['timestamp'], y=longs['price'] * 0.98,
                mode='markers+text', 
                marker=dict(symbol='triangle-up', size=14, color='#28a745', line=dict(width=2, color='white')),
                text=[f"{s:.0f}%" + (" ❷" if c >= 2 else "") for s, c in zip(longs['confidence'], longs['ob_confluence'])], textposition="bottom center",
                customdata=longs.apply(lambda r: f"Score: {r['score']:.1f}<br>OBs: {r['ob_confluence']}<br>Reasons: {r['reasons']}", axis=1),
                hovertemplate="<b>Long Signal</b><br>Confidence: %{text}<br>Price: %{y:.2f}<br>%{customdata}<extra></extra>",
                name='Long'
            ), row=1, col=1)

        # Neutrals
        neutrals = sig_df[sig_df['type'] == 'neutral']
        if not neutrals.empty:
            fig.add_trace(go.Scatter(
                x=neutrals['timestamp'], y=neutrals['price'],
                mode='markers', 
                marker=dict(symbol='diamond', size=10, color='#17a2b8', opacity=0.6, line=dict(width=1, color='white')),
                text=[f"{s:.0f}%" for s in neutrals['confidence']],
                customdata=neutrals.apply(lambda r: f"Score: {r['score']:.1f}<br>Reasons: {r['reasons']}", axis=1),
                hovertemplate="<b>Neutral Setup</b><br>Confidence: %{text}<br>Price: %{y:.2f}<br>%{customdata}<extra></extra>",
                name='High Score Neutral'
            ), row=1, col=1)

    fig.update_layout(
        template='plotly_white',
        height=900,
        xaxis_rangeslider_visible=False,
        margin=dict(l=50, r=50, t=80, b=50),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor='white',
        paper_bgcolor='white',
        font=dict(color='#333333')
    )
    
    fig.update_xaxes(gridcolor='#eeeeee', zeroline=False, linecolor='#cccccc')
    fig.update_yaxes(gridcolor='#eeeeee', zeroline=False, linecolor='#cccccc')
    
    output_path = BATCH_OUTPUT_DIR / f"{symbol}_{name}.html"
    fig.write_html(output_path)
    return output_path

def create_index_page(results):
    """创建索引页面 - 现代仪表盘风格"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>SMC Alpha 100 Dashboard</title>
        <meta charset="utf-8">
        <style>
            body { font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #f8f9fa; color: #212529; padding: 40px; margin: 0; }
            .container { max-width: 1200px; margin: 0 auto; }
            header { margin-bottom: 40px; border-bottom: 2px solid #dee2e6; padding-bottom: 20px; }
            h1 { font-size: 2.5rem; margin-bottom: 10px; color: #1a1a1a; letter-spacing: -0.5px; }
            .meta { color: #6c757d; font-size: 0.9rem; }
            table { width: 100%; border-collapse: separate; border-spacing: 0; margin-top: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.05); border-radius: 12px; overflow: hidden; background: #fff; border: 1px solid #e9ecef; }
            th { background: #f1f3f5; padding: 18px; text-align: left; font-weight: 700; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 1px; color: #495057; border-bottom: 1px solid #dee2e6; }
            td { padding: 18px; text-align: left; border-bottom: 1px solid #f1f3f5; font-size: 0.95rem; }
            tr:last-child td { border-bottom: none; }
            tr:hover { background: #f8f9fa; transition: background 0.2s; }
            .symbol { font-family: 'SF Mono', 'Fira Code', monospace; color: #4361ee; font-weight: bold; }
            .stock-name { font-weight: 600; color: #2b2d42; }
            .badge { padding: 6px 12px; border-radius: 6px; font-size: 0.85rem; font-weight: 700; }
            .badge-high { background: #d8f3dc; color: #1b4332; border: 1px solid #b7e4c7; }
            .badge-med { background: #e0f2fe; color: #075985; border: 1px solid #bae6fd; }
            .btn { display: inline-block; padding: 10px 20px; background: #4361ee; color: #fff; text-decoration: none; border-radius: 8px; font-size: 0.85rem; font-weight: 600; transition: all 0.2s; box-shadow: 0 4px 6px rgba(67, 97, 238, 0.2); }
            .btn:hover { background: #3f37c9; transform: translateY(-1px); box-shadow: 0 6px 12px rgba(67, 97, 238, 0.3); }
            .empty { color: #adb5bd; font-style: italic; }
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>SMC Alpha Backtest Dashboard</h1>
                <div class="meta">
                    测试周期: 25天 | 分析窗口: 全量历史 | 逻辑: 单向做多 (Long Only)
                </div>
            </header>
            <table>
                <thead>
                    <tr>
                        <th>代码</th>
                        <th>名称</th>
                        <th>信号统计</th>
                        <th>最高 SMC 置信度</th>
                        <th>综合评分</th>
                        <th>分析报告</th>
                    </tr>
                </thead>
                <tbody>
    """
    
    # 按最高置信度降序排序
    sorted_results = sorted(results, key=lambda x: x['max_confidence'], reverse=True)
    
    for res in sorted_results:
        conf_class = "badge-high" if res['max_confidence'] >= 60 else "badge-med"
        html_content += f"""
                    <td>{res['signal_count']} 个信号" + 
                        (f" <span style='color: #4361ee; font-weight: bold;'>[❷ Conf]</span>" if res['max_ob_confluence'] >= 2 else "") + 
                        (f" <span style='color: #ef5350; font-weight: bold;'>[🔥 Sweep]</span>" if res.get('has_sweep', False) else "") + 
                        (f" <span style='color: #26a69a; font-weight: bold;'>[🧲 FVG]</span>" if res.get('has_fvg', False) else "") + 
                        f"</td>
                    <td><span class="badge {conf_class}">{res['max_confidence']:.1f}%</span></td>
                    <td style="color: #6c757d; font-size: 0.85rem;">{res['max_score']:.1f}</td>
                    <td><a href="{res['file_name']}" class="btn" target="_blank">查看深入分析</a></td>
                </tr>
        """
    
    if not results:
        html_content += "<tr><td colspan='5' class='empty' style='text-align:center; padding: 40px;'>暂无结果，请检查数据加载逻辑</td></tr>"

    html_content += """
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """
    
    index_path = BATCH_OUTPUT_DIR / "index.html"
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    return index_path

from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn, SpinnerColumn
from rich.live import Live
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout

from tqdm import tqdm

def run_batch_backtest():
    BATCH_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stocks = get_available_stocks()
    if not stocks:
        return

    strategy = EnhancedSMCStrategy(timeframe="daily")
    all_analysis_data = []
    
    console.print(f"\n[bold green]>>> 第一阶段：正在对 {len(stocks)} 只股票进行 SMC 全量扫描 (间隔: {INTERVAL_DAYS}天)...[/bold green]")

    # 第一阶段：全量扫描
    pbar = tqdm(stocks, desc="SMC Scanning", unit="stock", dynamic_ncols=True)
    for stock in pbar:
        pbar.set_description(f"Scanning {stock['symbol']}")
        
        df = load_stock_data(stock['path'])
        if df is None or len(df) <= WINDOW_SIZE:
            continue
        
        signals = []
        max_score = 0
        max_confidence = 0
        
        for i in range(WINDOW_SIZE, len(df), INTERVAL_DAYS):
            slice_df = df.iloc[: i + 1].copy()
            analysis = strategy.analyze(slice_df, symbol=stock['symbol'], name=stock['name'])
            
            score = analysis.overall_score
            max_score = max(max_score, score)
            
            primary_sig = analysis.primary_signal
            sig_type = primary_sig.signal_type if primary_sig else "neutral"
            
            if sig_type == "short":
                continue
            
                if sig_type == "long" or (sig_type == "neutral" and score >= SCORE_THRESHOLD):
                    confidence = analysis.primary_signal.confidence if analysis.primary_signal else 0
                    confluence_count = analysis.primary_signal.ob_confluence_count if analysis.primary_signal else 1
                    has_sweep = "Sweep" in (analysis.primary_signal.confluence_factors if analysis.primary_signal else [])
                    has_fvg = analysis.primary_signal.fvg_alignment if analysis.primary_signal else False
                    
                    max_confidence = max(max_confidence, confidence)
                    signals.append({
                        'timestamp': df.loc[i, 'timestamp'],
                        'price': df.loc[i, 'close'],
                        'score': score,
                        'confidence': confidence,
                        'ob_confluence': confluence_count,
                        'has_sweep': has_sweep,
                        'has_fvg': has_fvg,
                        'type': sig_type,
                        'reasons': "<br>".join(analysis.primary_signal.reasons) if analysis.primary_signal else "None"
                    })
        
            all_analysis_data.append({
                'symbol': stock['symbol'],
                'name': stock['name'],
                'signals': signals,
                'df': df,
                'signal_count': len(signals),
                'max_score': max_score,
                'max_confidence': max_confidence,
                'max_ob_confluence': max([s['ob_confluence'] for s in signals]) if signals else 0,
                'has_sweep': any(s['has_sweep'] for s in signals),
                'has_fvg': any(s['has_fvg'] for s in signals)
            })
            
            # 如果发现较好置信度的信号 (>=60%)，实时打印
            if max_confidence >= 60:
                console.log(f"[bold green]✨ 潜力股发现:[/bold green] {stock['symbol']} {stock['name']} | 置信度: [bold yellow]{max_confidence:.1f}%[/bold yellow]")

    # 第二阶段：筛选前 20
    console.print(f"\n[bold green]>>> 第二阶段：筛选 Top 20 置信度股票并生成深度图表...[/bold green]")
    top_20 = sorted(all_analysis_data, key=lambda x: (x['max_confidence'], x['signal_count']), reverse=True)[:20]
    
    final_results = []
    for item in tqdm(top_20, desc="Rendering Reports", unit="report"):
        rel_path = create_individual_chart(item['df'], item['signals'], item['symbol'], item['name'])
        final_results.append({
            'symbol': item['symbol'],
            'name': item['name'],
            'signal_count': item['signal_count'],
            'max_score': item['max_score'],
            'max_confidence': item['max_confidence'],
            'max_ob_confluence': item['max_ob_confluence'],
            'has_sweep': item['has_sweep'],
            'has_fvg': item['has_fvg'],
            'file_name': rel_path.name
        })

    index_path = create_index_page(final_results)
    console.print(f"\n[bold green]✅ 批量回测完成！已输出前 [cyan]{len(final_results)}[/cyan] 位候选者详细报告。[/bold green]")
    console.print(f"📈 索引页面: [link=file://{index_path}]{index_path}[/link]")

if __name__ == "__main__":
    run_batch_backtest()
