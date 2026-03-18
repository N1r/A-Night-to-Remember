"""
Backtest Reporter - 回测输出与可视化
===================================
用于生成回测报告面板和导出历史记录。
"""

import pandas as pd
from typing import Dict, Any
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from .engine import BacktestResult
from .metrics import calculate_metrics

console = Console()

def generate_report(result: BacktestResult, csv_path: str = "output/single/trades_history.csv") -> None:
    """在终端打印回测报告，并导出交易记录到 CSV"""
    metrics = calculate_metrics(result)
    
    # Export to CSV
    if result.trades:
        trades_dict = []
        for t in result.trades:
            trades_dict.append({
                "Symbol": t.symbol,
                "Direction": t.direction,
                "Entry Time": t.entry_time,
                "Entry Price": round(t.entry_price, 2),
                "Exit Time": t.exit_time,
                "Exit Price": round(t.exit_price, 2) if t.exit_price else None,
                "Exit Reason": t.exit_reason,
                "Size": round(t.position_size, 2),
                "PnL": round(t.pnl, 2),
                "PnL %": round(t.pnl_pct * 100, 2),
                "Signal Strength": round(t.signal_strength, 1)
            })
        df_trades = pd.DataFrame(trades_dict)
        
        # Ensure dir
        import os
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        df_trades.to_csv(csv_path, index=False, encoding="utf-8-sig")
        console.print(f"[dim]交易记录已保存至: {csv_path}[/dim]")
    
    # Display Rich Panel
    _print_metrics_table(metrics)


def _print_metrics_table(metrics: Dict[str, Any]):
    table = Table(title="[bold cyan]回测绩效评估报告[/bold cyan]", show_header=False, style="cyan")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    
    def format_val(k, v):
        if isinstance(v, float):
            return f"{v:.2f}"
        return str(v)
        
    for k, v in metrics.items():
        if "Return" in k or "Profit" in k:
            color = "green" if v > 0 else "red"
            val_str = f"[{color}]{format_val(k,v)}[/{color}]"
        elif "Drawdown" in k:
            color = "red" if v > 10 else "yellow" if v > 0 else "white"
            val_str = f"[{color}]{format_val(k,v)}[/{color}]"
        else:
            val_str = format_val(k,v)
            
        table.add_row(k, val_str)
        
    console.print()
    console.print(table)
    console.print()
