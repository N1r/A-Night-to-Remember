#!/usr/8n/env python3
"""
SMC 策略历史回测入口 - run_backtest.py
===================================
通过滑动窗口方式，在历史数据上无头（无视觉UI）回测 EnhancedSMCStrategy 并输出绩效报告。

用法:
    python run_backtest.py --symbol 03690 --timeframe 60min --start 2023-01-01
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

import akshare as ak
import pandas as pd
from rich.console import Console

# 将项目根目录添加到路径
sys.path.insert(0, str(Path(__file__).parent))

from src.smc_analysis.enhanced_strategy import EnhancedSMCStrategy
from src.backtest.engine import SMCBacktester, BacktestConfig
from src.backtest.reporter import generate_report

console = Console()

def parse_args():
    parser = argparse.ArgumentParser(description="SMC Strategy Backtester")
    parser.add_argument("--symbol", type=str, default="03690", help="Stock symbol (e.g., 03690, sh600000)")
    parser.add_argument("--name", type=str, default="美团-W", help="Stock name")
    parser.add_argument("--timeframe", type=str, default="60min", choices=["15min", "30min", "60min", "daily"], help="Timeframe")
    parser.add_argument("--start", type=str, default="2024-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=datetime.today().strftime('%Y-%m-%d'), help="End date (YYYY-MM-DD)")
    parser.add_argument("--window", type=int, default=300, help="Sliding window size (bars)")
    parser.add_argument("--capital", type=float, default=100000.0, help="Initial capital")
    return parser.parse_args()


def fetch_historical_data(symbol: str, timeframe: str, start_date: str, end_date: str) -> pd.DataFrame:
    """获取并清洗历史数据"""
    console.print(f"正在拉取 {symbol} ({timeframe}) 历史数据自 {start_date} 至 {end_date}...")
    try:
        if timeframe == "daily":
            # akshare daily qfq
            df = ak.stock_hk_hist(symbol=symbol, period="daily", start_date=start_date.replace('-',''), end_date=end_date.replace('-',''), adjust="qfq")
            col_map = {
                "日期": "timestamp", "开盘": "open", "收盘": "close",
                "最高": "high", "最低": "low", "成交量": "volume", "成交额": "amount"
            }
        else:
            # em minute data (might not support very long history depending on AKShare API limitations)
            df = ak.stock_hk_hist_min_em(symbol=symbol, period=timeframe.replace('min',''), start_date=start_date, end_date=end_date, adjust="qfq")
            col_map = {
                "时间": "timestamp", "开盘": "open", "收盘": "close",
                "最高": "high", "最低": "low", "成交量": "volume", "成交额": "amount"
            }
            
        if df is None or df.empty:
            console.print("[red]获取数据失败或数据为空[/red]")
            return pd.DataFrame()
            
        df.rename(columns=col_map, inplace=True)
        required = ["timestamp", "open", "high", "low", "close", "volume"]
        
        for c in ["open", "high", "low", "close", "volume"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
                
        df = df.dropna(subset=required).reset_index(drop=True)
        # Ensure timestamp is datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values("timestamp").reset_index(drop=True)
        
        console.print(f"[green]✓ 数据加载成功, 共 {len(df)} 根K线[/green]")
        return df
        
    except Exception as e:
        console.print(f"[red]获取数据异常: {e}[/red]")
        return pd.DataFrame()


def main():
    args = parse_args()
    
    # 1. Fetch data
    df = fetch_historical_data(args.symbol, args.timeframe, args.start, args.end)
    if df.empty:
        sys.exit(1)
        
    # 2. Setup strategy and backtester
    strategy = EnhancedSMCStrategy(timeframe="daily" if args.timeframe == "daily" else "60min")
    config = BacktestConfig(
        initial_capital=args.capital,
        window_size=args.window,
        max_positions=1 
    )
    backtester = SMCBacktester(strategy=strategy, config=config)
    
    # 3. Run
    console.print(f"[bold cyan]开始回测 {args.name} ({args.symbol}) ...[/bold cyan]")
    result = backtester.run(df, symbol=args.symbol, name=args.name)
    
    # 4. Report
    report_path = f"output/backtest/trades_{args.symbol}_{args.timeframe}.csv"
    generate_report(result, csv_path=report_path)


if __name__ == "__main__":
    main()
