import pytest
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from src.backtest.engine import SMCBacktester, BacktestConfig, TradeRecord
from src.backtest.metrics import calculate_metrics

class MockSignal:
    def __init__(self, ttype, price, sl, tp, size):
        self.signal_type = ttype
        self.entry_price = price
        self.stop_loss = sl
        self.take_profit_1 = tp
        self.signal_strength = 90
        self.position_size_suggestion = size
        self.symbol = "TEST"

class MockStrategy:
    def __init__(self):
        self.call_count = 0
        
    def analyze(self, df, symbol, name):
        self.call_count += 1
        class Res:
            primary_signal = None
        res = Res()
        
        # Trigger long on 10th call
        if self.call_count == 10:
            res.primary_signal = MockSignal("long", df.iloc[-1]['close'], df.iloc[-1]['close'] * 0.9, df.iloc[-1]['close'] * 1.2, 10.0)
        return res

def test_backtester_flow():
    # Make dummy df
    dates = pd.date_range("2024-01-01", periods=100)
    df = pd.DataFrame({
        "timestamp": dates,
        "open": np.linspace(10, 20, 100),
        "high": np.linspace(11, 21, 100),
        "low": np.linspace(9, 19, 100),
        "close": np.linspace(10, 20, 100),
        "volume": np.ones(100) * 1000
    })
    
    config = BacktestConfig(initial_capital=100000, window_size=10, max_positions=1, slippage=0.0, commission_rate=0.0)
    tester = SMCBacktester(MockStrategy(), config)
    res = tester.run(df, "TEST", "Test Name")
    
    metrics = calculate_metrics(res)
    assert metrics["Total Trades"] > 0
    assert "Final Capital" in metrics
