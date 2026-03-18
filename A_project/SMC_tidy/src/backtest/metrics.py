"""
Backtest Metrics - 回测评估与绩效统计
===================================
提供交易结果的数据统计与分析工具。
"""

import pandas as pd
import numpy as np
from typing import Dict, Any
from .engine import BacktestResult

def calculate_metrics(result: BacktestResult) -> Dict[str, Any]:
    """计算回测的各项指标"""
    trades = result.trades
    equity_curve = pd.DataFrame(result.equity_curve)
    
    metrics = {
        "Total Trades": len(trades),
        "Initial Capital": result.initial_capital,
        "Final Capital": result.final_capital,
        "Total Return (%)": result.total_return_pct,
    }
    
    if len(trades) == 0:
        return metrics
        
    # Win rate
    winning_trades = [t for t in trades if t.pnl > 0]
    metrics["Win Rate (%)"] = len(winning_trades) / len(trades) * 100
    
    # Profit factors
    gross_profit = sum(t.pnl for t in winning_trades)
    losing_trades = [t for t in trades if t.pnl <= 0]
    gross_loss = abs(sum(t.pnl for t in losing_trades))
    
    metrics["Profit Factor"] = gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    # Averages
    avg_win = np.mean([t.pnl_pct for t in winning_trades]) if winning_trades else 0
    avg_loss = abs(np.mean([t.pnl_pct for t in losing_trades])) if losing_trades else 0
    metrics["Avg Risk/Reward"] = avg_win / avg_loss if avg_loss > 0 else 0
    
    # Drawdown
    if not equity_curve.empty:
        equity_curve['peak'] = equity_curve['equity'].cummax()
        equity_curve['drawdown'] = (equity_curve['peak'] - equity_curve['equity']) / equity_curve['peak']
        metrics["Max Drawdown (%)"] = equity_curve['drawdown'].max() * 100
    else:
        metrics["Max Drawdown (%)"] = 0.0

    return metrics
