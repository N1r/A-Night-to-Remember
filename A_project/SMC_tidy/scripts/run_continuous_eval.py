#!/usr/bin/env python3
"""
SMC 连续滚动跨期评估入口 - run_continuous_eval.py
=================================================
从指定的结束日期（如今天）开始，每次向前倒退指定的窗口天数，评估在那个截面上的策略表现。
最终聚合多期结果，输出整体策略有效性。

用法:
    python run_continuous_eval.py --end_date 2026-02-23 --periods 12 --step 30
"""

import sys
import argparse
from pathlib import Path
from datetime import timedelta
import pandas as pd
import akshare as ak
from rich.console import Console

sys.path.insert(0, str(Path(__file__).parent))

from src.smc_analysis.enhanced_strategy import EnhancedSMCStrategy
from src.backtest.rolling_evaluator import MonthlyRollingEvaluator
from src.backtest.eval_reporter import generate_eval_report, generate_aggregated_report

console = Console()

def parse_args():
    parser = argparse.ArgumentParser(description="Continuous Rolling Strategy Evaluator")
    parser.add_argument("--end_date", type=str, default=pd.Timestamp.today().strftime('%Y-%m-%d'), help="End date (Today by default, YYYY-MM-DD)")
    parser.add_argument("--periods", type=int, default=12, help="Number of rolling periods to test backwards")
    parser.add_argument("--step", type=int, default=60, help="Days to step backwards per period (evaluation window)")
    parser.add_argument("--top", type=int, default=20, help="Number of top symbols to track per period")
    parser.add_argument("--max_files", type=int, default=20, help="Number of local files to use for testing")
    return parser.parse_args()


def load_local_data(start_date: str, end_date: str, max_files: int = 20) -> dict:
    """从本地 data/processed/ 加载日线数据 (避免网络下载，且控制样本数量)"""
    console.print(f"[cyan]正在从本地加载缓存数据 ({start_date} -> {end_date}), 最多 {max_files} 只标的...[/cyan]")
    symbol_data_map = {}
    
    data_dir = Path("data/processed")
    if not data_dir.exists():
        console.print("[red]错误: data/processed 目录不存在，请先准备数据。[/red]")
        return {}
        
    csv_files = list(data_dir.glob("*_daily_smc.csv"))
    
    for f in csv_files[:max_files]:
        # file name format: 000001_平安银行_daily_smc.csv
        parts = f.name.split('_')
        if len(parts) >= 2:
            symbol = parts[0]
            name = parts[1]
        else:
            symbol = f.stem
            name = f.stem
            
        try:
            df = pd.read_csv(f)
            if df is not None and not df.empty:
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                # Filter by dates
                df = df[(df['timestamp'] >= pd.to_datetime(start_date)) & 
                        (df['timestamp'] <= pd.to_datetime(end_date))]
                        
                for c in ["open", "high", "low", "close", "volume"]:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
                    
                df = df.dropna(subset=["timestamp", "close"]).sort_values("timestamp")
                if len(df) > 100: # SMC needs some history, but 800 was too much for 2yr local files
                    symbol_data_map[symbol] = (name, df)
        except Exception as e:
            console.print(f"[yellow]无法加载 {f.name}: {e}[/yellow]")
            
    console.print(f"[green]成功加载了 {len(symbol_data_map)} 只股票的有效数据[/green]")
    return symbol_data_map


def main():
    args = parse_args()
    end_date = pd.to_datetime(args.end_date)
    
    # 策略需求历史，往前倒推 periods * step + 200 (SMC初始化) 天
    total_days_needed = (args.periods * args.step) + 200
    start_dt = end_date - timedelta(days=total_days_needed)
    
    pool_data = load_local_data(
        start_dt.strftime('%Y-%m-%d'), 
        end_date.strftime('%Y-%m-%d'),
        max_files=args.max_files
    )
    
    if not pool_data:
        console.print("[red]无法获取任何股票数据。[/red]")
        sys.exit(1)
        
    console.print(f"\n[bold magenta]开始连续滚动评价循环[/bold magenta]")
    console.print(f"总期数: {args.periods} | 步长(后视期): {args.step} 天 | 结束日: {args.end_date}\n")
    
    strategy = EnhancedSMCStrategy(timeframe="daily")
    evaluator = MonthlyRollingEvaluator(strategy, top_n=args.top, lookback_days=30, forward_days=args.step)
    
    all_period_stats = []
    
    # 从今天开始，逐步倒退
    for i in range(args.periods):
        current_eval_date = end_date - timedelta(days=i * args.step)
        # 向后追踪到 current_eval_date + step，这绝不能超过今天的最新数据
        # (这已经被截断逻辑内在保证了，因为 `df_fwd` 只能取到现有的 df 最新截止日)
        
        console.print(f"[bold]>>> 第 {i+1}/{args.periods} 期 | 基准日: {current_eval_date.strftime('%Y-%m-%d')}[/bold]")
        
        results = evaluator.evaluate(pool_data, eval_date_str=current_eval_date.strftime('%Y-%m-%d'))
        
        # 每个期保存独立 CSV 明细
        period_date_str = current_eval_date.strftime('%Y%m%d')
        signals_csv = f"output/eval/signals_{period_date_str}.csv"
        
        period_stat = generate_eval_report(results, eval_date_str=current_eval_date.strftime('%Y-%m-%d'), csv_path=signals_csv) 
        all_period_stats.append(period_stat)
        
    console.print("\n[bold magenta]============== 全局测试结束 ==============[/bold magenta]\n")
    generate_aggregated_report(all_period_stats, csv_path="output/eval/continuous_summary.csv")


if __name__ == "__main__":
    main()
