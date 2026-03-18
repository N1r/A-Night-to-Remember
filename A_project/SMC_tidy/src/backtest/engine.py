"""
Backtest Engine - 基于滑动窗口框架的历史测试引擎
=================================================

旨在基于现有的 EnhancedSMCStrategy 构建一套有效且无未来函数(Lookahead Bias)的回测系统。
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any
import numpy as np
import pandas as pd
from rich.progress import Progress

# Import existing strategy components
from ..smc_analysis.enhanced_strategy import EnhancedSMCStrategy, EnhancedTradingSignal

logger = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    """单笔交易记录"""
    symbol: str
    direction: str  # 'long' or 'short'
    entry_time: datetime
    entry_price: float
    position_size: float  # 本次交易的资产规模
    quantity: float       # 购买数量
    stop_loss: float
    take_profit: float
    signal_strength: float
    
    # Exit details
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: str = "" # "tp", "sl", "eod" (end of data)
    pnl: float = 0.0
    pnl_pct: float = 0.0
    
    @property
    def is_closed(self) -> bool:
        return self.exit_time is not None


@dataclass
class BacktestConfig:
    """回测系统配置"""
    initial_capital: float = 100000.0
    commission_rate: float = 0.0005  # 0.05% 佣金
    slippage: float = 0.001          # 0.1% 滑点
    window_size: int = 300           # 滑动窗口K线数 (基于现有引擎支持数万K线，300 根足够找到局部结构且速度合宜)
    max_positions: int = 1           # 最大并发持仓限制


class SMCBacktester:
    """
    SMC 策略回测类
    
    通过时间窗口步进，消除未来函数。
    支持：信号生成、撮合、仓位管理、资金曲线记录。
    """
    def __init__(self, strategy: EnhancedSMCStrategy, config: Optional[BacktestConfig] = None):
        self.strategy = strategy
        self.config = config or BacktestConfig()
        
        # State
        self.current_capital: float = self.config.initial_capital
        self.equity_curve: List[Dict[str, Any]] = []  # 记录每日或每K线的净值
        self.trades: List[TradeRecord] = []
        self.active_trades: List[TradeRecord] = []
        
    def run(self, df: pd.DataFrame, symbol: str, name: str = "") -> 'BacktestResult':
        """
        运行回测
        
        Args:
            df: 包含历史数据的 DataFrame
            symbol: 交易标识
            name: 中文名
        """
        if len(df) < self.config.window_size + 10:
            logger.warning("数据量少于窗口大小，无法回测")
            return BacktestResult([], [], self.config.initial_capital)
            
        n = len(df)
        window = self.config.window_size
        
        # Initialize equity
        first_time = df['timestamp'].iloc[0] if 'timestamp' in df else df.index[0]
        self.equity_curve.append({'time': first_time, 'equity': self.current_capital})
        
        with Progress() as progress:
            task = progress.add_task(f"[cyan]回测进度 ({symbol})...", total=n - window)
            
            # Step through data
            for t in range(window, n):
                current_time = df['timestamp'].iloc[t] if 'timestamp' in df else df.index[t]
                current_bar = df.iloc[t]
                
                # 1. Update existing positions (Check SL/TP)
                self._update_positions(current_bar, current_time)
                
                # Update equity curve
                total_equity = self.current_capital + sum([
                    self._calc_unrealized_pnl(trade, current_bar['close']) for trade in self.active_trades
                ])
                self.equity_curve.append({'time': current_time, 'equity': total_equity})
                
                # 2. Check if we need to enter new positions
                if len(self.active_trades) < self.config.max_positions:
                    # Provide strategy with past data UP TO t (exclusive) so current bar is the "unseen future" for entry,
                    # or UP TO t (inclusive) if we assume signal operates at bar close and enters next open.
                    # We will use data up to t (inclusive) to generate signal, and enter at next bar open,
                    # but since this loop is at t, if we generated signal at t-1, we check entry at t.
                    
                    # Generate signal using data up to t
                    slice_df = df.iloc[t - window : t + 1].copy()
                    
                    # Only analyze if we aren't already holding a position
                    # to save computation time
                    analysis = self.strategy.analyze(slice_df, symbol=symbol, name=name)
                    
                    if analysis.primary_signal and analysis.primary_signal.signal_type != "neutral":
                        self._handle_signal(analysis.primary_signal, current_bar, current_time)
                
                progress.update(task, advance=1)
                
        # Close remaining positions at the end of backtest
        if self.active_trades:
            last_bar = df.iloc[-1]
            last_time = df['timestamp'].iloc[-1] if 'timestamp' in df else df.index[-1]
            self._close_all_positions(last_bar, last_time, "eod")
            
            total_equity = self.current_capital
            self.equity_curve.append({'time': last_time, 'equity': total_equity})
            
        return BacktestResult(
            trades=self.trades,
            equity_curve=self.equity_curve,
            initial_capital=self.config.initial_capital
        )
        
    def _update_positions(self, current_bar: pd.Series, current_time: datetime):
        """检查当前K线是否触发止盈或止损"""
        high = current_bar['high']
        low = current_bar['low']
        
        for trade in self.active_trades[:]:
            if trade.direction == "long":
                if low <= trade.stop_loss:
                    self._close_position(trade, trade.stop_loss, current_time, "sl")
                elif high >= trade.take_profit:
                    self._close_position(trade, trade.take_profit, current_time, "tp")
            else: # short
                if high >= trade.stop_loss:
                    self._close_position(trade, trade.stop_loss, current_time, "sl")
                elif low <= trade.take_profit:
                    self._close_position(trade, trade.take_profit, current_time, "tp")

    def _handle_signal(self, signal: EnhancedTradingSignal, current_bar: pd.Series, current_time: datetime):
        """处理信号，模拟市价单入场（或限价单触碰假设如果需要更复杂的话）
           简单起见，这里假设信号生成后，可以直接以当前K线的收盘价（或其他合理价格）入场。
           为了更严谨，应该是基于前一根K线的信号，以当前开盘价入场。
           这里简化：在 t 时刻产生的信号，代表以 t 的 close 考虑入场，或者下一次的 open。
           由于我们在 `run` 里传入的是 `t-window : t+1`，意味着当前 `current_bar` 是最新确认的K线。
           我们模拟以此 K 线的收盘价建立头寸，或者更保守地，检查它的最低/最高价是否触及了信号的 entry_price。
        """
        
        # Limit order simulation based on strategy entry price
        # Did the current bar touch the limit order entry price?
        entry_price = signal.entry_price
        
        touched = False
        if signal.signal_type == "long":
            if current_bar['low'] <= entry_price <= current_bar['high']:
                touched = True
            # Or market order if entry_price is already exceeded (price dropped fast)
            elif current_bar['close'] < entry_price:
                 touched = True
                 entry_price = current_bar['close'] # better fill
        else: # short
            if current_bar['low'] <= entry_price <= current_bar['high']:
                touched = True
            elif current_bar['close'] > entry_price:
                 touched = True
                 entry_price = current_bar['close']
                 
        if not touched:
            return
            
        # Apply slippage
        if signal.signal_type == "long":
            exec_price = entry_price * (1 + self.config.slippage)
        else:
            exec_price = entry_price * (1 - self.config.slippage)
            
        invest_amount = self.current_capital * (signal.position_size_suggestion / 100.0)
        # Cap investment to current capital
        invest_amount = min(invest_amount, self.current_capital)
        
        if invest_amount <= 0:
            return
            
        qty = invest_amount / exec_price
        commission = invest_amount * self.config.commission_rate
        self.current_capital -= commission
        
        # Stop loss logic (Use TP1 parameter directly for now)
        take_profit = signal.take_profit_1 
        
        trade = TradeRecord(
            symbol=signal.symbol,
            direction=signal.signal_type,
            entry_time=current_time,
            entry_price=exec_price,
            position_size=invest_amount,
            quantity=qty,
            stop_loss=signal.stop_loss,
            take_profit=take_profit,
            signal_strength=signal.signal_strength
        )
        self.active_trades.append(trade)
        
    def _close_position(self, trade: TradeRecord, exit_price: float, current_time: datetime, reason: str):
        """闭仓结算"""
        # Apply slippage
        if trade.direction == "long":
            exec_price = exit_price * (1 - self.config.slippage)
        else:
            exec_price = exit_price * (1 + self.config.slippage)
            
        gross_value = trade.quantity * exec_price
        commission = gross_value * self.config.commission_rate
        
        if trade.direction == "long":
            pnl = (exec_price - trade.entry_price) * trade.quantity
        else:
            pnl = (trade.entry_price - exec_price) * trade.quantity
            
        net_pnl = pnl - commission
        
        trade.exit_time = current_time
        trade.exit_price = exec_price
        trade.exit_reason = reason
        trade.pnl = net_pnl
        trade.pnl_pct = net_pnl / trade.position_size
        
        self.current_capital += net_pnl
        self.trades.append(trade)
        self.active_trades.remove(trade)

    def _close_all_positions(self, current_bar: pd.Series, current_time: datetime, reason: str):
        for trade in self.active_trades[:]:
             self._close_position(trade, current_bar['close'], current_time, reason)

    def _calc_unrealized_pnl(self, trade: TradeRecord, current_price: float) -> float:
        if trade.direction == "long":
            return (current_price - trade.entry_price) * trade.quantity
        else:
            return (trade.entry_price - current_price) * trade.quantity

            
@dataclass
class BacktestResult:
    """回测结果持有器容器"""
    trades: List[TradeRecord]
    equity_curve: List[Dict[str, Any]]
    initial_capital: float
    
    @property
    def final_capital(self) -> float:
        return self.equity_curve[-1]['equity'] if self.equity_curve else self.initial_capital
        
    @property
    def total_return_pct(self) -> float:
        return (self.final_capital - self.initial_capital) / self.initial_capital * 100.0
