#!/usr/bin/env python3
"""
SMC 横截面滚动评估入口 - run_monthly_eval.py
===========================================
在指定基准日期，提取池中所有股票过去30天的数据进行策略打分，选出 Top N，
并在接下来的30天真实历史中验证其表现。

用法:
    python run_monthly_eval.py --date 2024-01-31 --top 20
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
import akshare as ak
from rich.console import Console
from rich.progress import Progress

sys.path.insert(0, str(Path(__file__).parent))

from src.smc_analysis.enhanced_strategy import EnhancedSMCStrategy
from src.backtest.rolling_evaluator import MonthlyRollingEvaluator
from src.backtest.eval_reporter import generate_eval_report

console = Console()

# 默认提供一个较小的测试池 (以恒生科技指数和一些蓝筹为例，便于演示)
DEFAULT_POOL = {
    "00700": "腾讯控股",
    "09988": "阿里巴巴-W",
    "03690": "美团-W",
    "09999": "网易-S",
    "09618": "京东集团-SW",
    "00981": "中芯国际",
    "01810": "小米集团-W",
    "02015": "理想汽车-W",
    "09868": "小鹏汽车-W",
    "02018": "瑞声科技",
    "00241": "阿里健康",
    "06618": "京东健康",
    "01024": "快手-W",
    "09888": "百度集团-SW",
    "09961": "携程集团-S",
    "02318": "中国平安",
    "00005": "汇丰控股",
    "00388": "香港交易所",
    "01299": "友邦保险",
    "00883": "中国海洋石油",
    "00941": "中国移动"
}

def parse_args():
    parser = argparse.ArgumentParser(description="Monthly Rolling Strategy Evaluator")
    parser.add_argument("--date", type=str, required=True, help="Evaluation base date (YYYY-MM-DD)")
    parser.add_argument("--top", type=int, default=20, help="Number of top symbols to track")
    parser.add_argument("--lookback", type=int, default=30, help="Days to look back for scoring")
    parser.add_argument("--forward", type=int, default=30, help="Days to forward track performance")
    return parser.parse_args()


def fetch_pool_data(pool: dict, start_date: str, end_date: str) -> dict:
    """获取所有股票在 [start_date, end_date] 期间的 K 线"""
    console.print(f"[cyan]正在批量获取股票池数据 ({start_date} -> {end_date})...[/cyan]")
    symbol_data_map = {}
    
    with Progress() as progress:
        task = progress.add_task("[yellow]下载数据...", total=len(pool))
        for symbol, name in pool.items():
            try:
                df = ak.stock_hk_hist(
                    symbol=symbol, 
                    period="daily", 
                    start_date=start_date.replace('-',''), 
                    end_date=end_date.replace('-',''), 
                    adjust="qfq"
                )
                if df is not None and not df.empty:
                    df.rename(columns={
                        "日期": "timestamp", "开盘": "open", "收盘": "close",
                        "最高": "high", "最低": "low", "成交量": "volume"
                    }, inplace=True)
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    
                    for c in ["open", "high", "low", "close", "volume"]:
                        df[c] = pd.to_numeric(df[c], errors="coerce")
                        
                    df = df.dropna(subset=["timestamp", "close"]).sort_values("timestamp")
                    symbol_data_map[symbol] = (name, df)
            except Exception as e:
                pass # 忽略下载失败的个股
            progress.update(task, advance=1)
            
    console.print(f"[green]成功获取了 {len(symbol_data_map)} 只股票的有效数据[/green]")
    return symbol_data_map


def main():
    args = parse_args()
    
    eval_date = pd.to_datetime(args.date)
    # We need data from `eval_date - 800 days` (for strategy calculation stability) 
    # to `eval_date + forward_days`
    start_dt = eval_date - timedelta(days=800)
    end_dt = eval_date + timedelta(days=args.forward + 10) # 加一点buffer给节假日
    
    pool_data = fetch_pool_data(
        DEFAULT_POOL, 
        start_dt.strftime('%Y-%m-%d'), 
        end_dt.strftime('%Y-%m-%d')
    )
    
    if not pool_data:
        console.print("[red]无法获取任何股票数据，程序退出。[/red]")
        sys.exit(1)
        
    console.print(f"\n[bold]基准评测日[/bold]: {args.date} | [bold]追踪期[/bold]: 后 {args.forward} 天")
    
    # Init Strategy
    strategy = EnhancedSMCStrategy(timeframe="daily")
    evaluator = MonthlyRollingEvaluator(strategy, top_n=args.top, lookback_days=args.lookback, forward_days=args.forward)
    
    # Run Eval
    results = evaluator.evaluate(pool_data, eval_date_str=args.date)
    
    # Report
    summary_path = f"output/eval/rolling_top{args.top}_{args.date}.csv"
    generate_eval_report(results, csv_path=summary_path)

if __name__ == "__main__":
    main()
