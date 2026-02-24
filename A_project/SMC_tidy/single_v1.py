#!/usr/bin/env python3
"""
单股票多周期跟踪脚本 - single_v1.py
专注跟踪: 美团-W (03690)
数据周期: 1分钟, 5分钟, 15分钟, 30分钟, 60分钟, 日线
分析策略: EnhancedSMCStrategy (最复杂的SMC策略)

使用方法:
    python single_v1.py
"""
import sys
import time
from pathlib import Path
import traceback

import akshare as ak
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# 将项目根目录添加到路径，以便能够导入 src 模块
sys.path.insert(0, str(Path(__file__).parent))

from src.smc_analysis.enhanced_strategy import EnhancedSMCStrategy
from src.chart_plot.plotter import SMCChartPlotter

console = Console()

DATA_DIR = Path("data/single")
CHARTS_DIR = Path("output/single/charts")
DATA_DIR.mkdir(parents=True, exist_ok=True)
CHARTS_DIR.mkdir(parents=True, exist_ok=True)

SYMBOL = "03690"
NAME = "美团-W"

TIMEFRAMES = {
    "1min": "1",
    "5min": "5",
    "15min": "15",
    "30min": "30",
    "60min": "60",
    "daily": "daily"
}

def fetch_data(symbol: str, period: str) -> pd.DataFrame:
    """获取指定周期的K线数据并进行标准化"""
    try:
        if period == "daily":
            df = ak.stock_hk_hist(symbol=symbol, period="daily", adjust="qfq")
            col_map = {
                "日期": "timestamp", "开盘": "open", "收盘": "close",
                "最高": "high", "最低": "low", "成交量": "volume", "成交额": "amount"
            }
        else:
            df = ak.stock_hk_hist_min_em(symbol=symbol, period=period, adjust="qfq")
            col_map = {
                "时间": "timestamp", "开盘": "open", "收盘": "close",
                "最高": "high", "最低": "low", "成交量": "volume", "成交额": "amount"
            }
        
        if df is None or df.empty:
            return pd.DataFrame()
            
        df.rename(columns=col_map, inplace=True)
        required = ["open", "high", "low", "close", "volume"]
        
        # 确保关键列为数值型
        for c in required:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
                
        # 移除非法行并重置索引
        df = df.dropna(subset=required).reset_index(drop=True)
        return df
    except Exception as e:
        console.print(f"[red]获取 {period} 数据失败: {e}[/red]")
        return pd.DataFrame()


def run_analysis():
    console.print(Panel.fit(
        f"[bold cyan]单股票多周期深度追踪分析[/bold cyan]\n"
        f"[dim]标的: {NAME} ({SYMBOL})\n"
        f"策略: 复杂 SMC 量化特征分析引擎 (EnhancedSMCStrategy)[/dim]",
        border_style="green"
    ))
    
    # 存储多个周期的分析结果
    results = {}
    
    for tf_name, ak_period in TIMEFRAMES.items():
        with console.status(f"正在获取 {tf_name} 数据并分析..."):
            df = fetch_data(SYMBOL, ak_period)
            if df.empty or len(df) < 50:
                console.print(f"[yellow]{tf_name} 数据不足，已跳过[/yellow]")
                continue
            
            try:
                # 初始化量化特征强化的SMC策略
                # 根据周期动态调整策略基础设置
                tf_param = "daily" if tf_name == "daily" else "60min"
                strategy = EnhancedSMCStrategy(timeframe=tf_param)
                
                # 执行分析
                analysis = strategy.analyze(df, symbol=SYMBOL, name=NAME)
                results[tf_name] = analysis
                
                # 保存K线数据
                data_path = DATA_DIR / f"{SYMBOL}_{NAME}_{tf_name}.csv"
                df.to_csv(data_path, index=False, encoding="utf-8-sig")
                
                # 保存图表
                if analysis.raw_result:
                    plotter = SMCChartPlotter()
                    # attach signal to raw_result for plotter to read
                    analysis.raw_result.primary_signal = analysis.primary_signal
                    fig = plotter.create_chart(df, analysis.raw_result, title=f"{NAME} ({SYMBOL}) - {tf_name}")
                    chart_path = CHARTS_DIR / f"{SYMBOL}_{NAME}_{tf_name}_chart.html"
                    plotter.save_html(fig, chart_path)
                
                # 简单结果输出
                signal = analysis.primary_signal
                sig_color = "red" if signal.signal_type == "short" else "green" if signal.signal_type == "long" else "white"
                
                console.print(f"[green]✓ {tf_name:>5}[/green] 分析完成 | "
                              f"主趋势: [bold]{analysis.trend:^7}[/bold] | "
                              f"市场状态: [bold]{analysis.market_regime:^7}[/bold] | "
                              f"信号: [{sig_color}][bold]{signal.signal_type.upper():^7}[/bold][/{sig_color}] "
                              f"(强度: {signal.signal_strength:.1f})")
                
            except Exception as e:
                console.print(f"[red]分析 {tf_name} 失败: {e}[/red]")
                traceback.print_exc()
            
            # API 请求限流保护
            time.sleep(1)
    
    # 终端表格汇总与最佳机会推荐
    display_results(results)


def display_results(results: dict):
    if not results:
        console.print("[red]无可用分析结果，程序退出。[/red]")
        return
        
    table = Table(title=f"\n[bold]{NAME} ({SYMBOL}) 多周期 SMC 综合分析报告[/bold]", style="cyan")
    table.add_column("周期", style="cyan", justify="center")
    table.add_column("趋势", justify="center")
    table.add_column("市场状态", justify="center")
    table.add_column("位置区间", justify="center")
    table.add_column("交易推荐", justify="center")
    table.add_column("信号强度", justify="center")
    table.add_column("入场", justify="right")
    table.add_column("止损", justify="right")
    table.add_column("盈亏比", justify="right")
    table.add_column("预期胜率", justify="right")
    table.add_column("融合因子", justify="left")

    for tf_name in TIMEFRAMES.keys():
        if tf_name not in results:
            continue
            
        ana = results[tf_name]
        sig = ana.primary_signal
        
        # 渲染颜色
        trend_c = "red" if ana.trend == "bearish" else "green" if ana.trend == "bullish" else "yellow"
        sig_c = "red" if sig.signal_type == "short" else "green" if sig.signal_type == "long" else "yellow"
        
        # 组件核心短句
        factors = " | ".join(sig.confluence_factors[:2]) if sig.confluence_factors else "-"
        if len(sig.confluence_factors) > 2:
            factors += "..."
            
        table.add_row(
            tf_name,
            f"[{trend_c}]{ana.trend}[/{trend_c}]",
            ana.market_regime,
            ana.zone,
            ana.recommendation,
            f"[{sig_c}]{sig.signal_type.upper()} ({sig.signal_strength:.0f})[/{sig_c}]",
            f"{sig.entry_price:.2f}" if sig.signal_type != "neutral" else "-",
            f"{sig.stop_loss:.2f}" if sig.signal_type != "neutral" else "-",
            f"1:{sig.risk_reward_ratio:.1f}" if sig.signal_type != "neutral" else "-",
            f"{ana.estimated_win_rate:.1f}%",
            factors
        )
    
    console.print("\n")
    console.print(table)
    
    # 评选最佳交易周期与分析详情
    actionable = [(k, v) for k, v in results.items() if v.primary_signal.signal_type != "neutral"]
    if actionable:
        # 按综合评分进行排序
        actionable.sort(key=lambda x: x[1].overall_score, reverse=True)
        best_tf, best_ana = actionable[0]
        best_sig = best_ana.primary_signal
        
        details = f"""[bold cyan]✨ 最佳交易周期发掘 ({best_tf})[/bold cyan]
        
[bold]综合机遇评分:[/bold] {best_ana.overall_score:.1f}/100
[bold]建仓策略:[/bold]
  方向: [bold {"green" if best_sig.signal_type=="long" else "red"}]{best_sig.signal_type.upper()}[/]
  入场价: {best_sig.entry_price:.2f}
  止损价: {best_sig.stop_loss:.2f}
  目标1: {best_sig.take_profit_1:.2f} (首要减仓位置)
  目标2: {best_sig.take_profit_2:.2f}
  目标3: {best_sig.take_profit_3:.2f} (波段极限利润)
  建议仓位: 约资金的 {best_sig.position_size_suggestion:.1f}%

[bold]核心驱动逻辑:[/bold]
"""
        for r in best_sig.reasons:
            details += f"  - [green]✓[/green] {r}\n"
            
        if best_sig.warnings:
            details += "\n[bold yellow]风险与警示:[/bold yellow]\n"
            for w in best_sig.warnings:
                details += f"  - [yellow]![/yellow] [yellow]{w}[/yellow]\n"
                
        console.print(Panel(details, border_style="cyan"))
    else:
        details = "\n[bold yellow]目前各个周期均无强烈交易信号，建议持币观望，等待结构突破或流动性扫荡。[/bold yellow]"
        console.print(Panel(details, border_style="yellow"))
        
if __name__ == "__main__":
    run_analysis()
