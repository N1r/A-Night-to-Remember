"""
Rolling Evaluator - 策略有效的横截面定点滚动测试
=================================================

目标: 在指点截面(如每月月底)，利用过去30天的数据对股票池进行扫描，选出评分最高的前 N 名。
然后在 T+1 到 T+30 的未来数据中验证这些高分信号的实际表现（最大涨幅、收盘涨幅、是否触损）。
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Tuple
import pandas as pd
from rich.progress import Progress

from ..smc_analysis.enhanced_strategy import EnhancedSMCStrategy, EnhancedTradingSignal

logger = logging.getLogger(__name__)

@dataclass
class EvalResult:
    """单个信号在未来窗口的表现"""
    symbol: str
    name: str
    eval_date: pd.Timestamp
    
    # Signal snapshot
    signal_type: str
    entry_price: float
    stop_loss: float
    target_1: float
    target_2: float
    signal_strength: float
    overall_score: float
    
    # Forward tracking results
    forward_days: int = 0
    max_price: float = 0.0
    min_price: float = float('inf')
    end_price: float = 0.0
    
    hit_sl: bool = False
    hit_tp1: bool = False
    hit_tp2: bool = False
    
    max_return_pct: float = 0.0
    end_return_pct: float = 0.0
    
    def calculate_performance(self):
        """基于跟踪期内先后顺序严格计算盈亏"""
        if self.entry_price <= 0:
            return
            
        # 初始假设持仓到期末
        self.end_return_pct = 0.0
        self.max_return_pct = 0.0
        
        if self.signal_type == "long":
            self.max_return_pct = (self.max_price - self.entry_price) / self.entry_price * 100
        elif self.signal_type == "short":
            self.max_return_pct = (self.entry_price - self.min_price) / self.entry_price * 100
            
    def simulate_forward_trade(self, df_fwd: pd.DataFrame):
        """逐日遍历未来数据，判断是否触发止盈或止损，确定最终收益率"""
        if df_fwd.empty or self.entry_price <= 0:
            return
            
        self.forward_days = len(df_fwd)
        self.max_price = df_fwd['high'].max()
        self.min_price = df_fwd['low'].min()
        
        # 默认到期平仓
        final_price = df_fwd['close'].iloc[-1]
        
        for idx, row in df_fwd.iterrows():
            high, low, close = row['high'], row['low'], row['close']
            
            if self.signal_type == "long":
                if low <= self.stop_loss:
                    self.hit_sl = True
                    final_price = self.stop_loss
                    break
                if high >= self.target_1:
                    self.hit_tp1 = True
                    final_price = self.target_1
                    break
                    
            elif self.signal_type == "short":
                if high >= self.stop_loss:
                    self.hit_sl = True
                    final_price = self.stop_loss
                    break
                if low <= self.target_1:
                    self.hit_tp1 = True
                    final_price = self.target_1
                    break
                    
        self.end_price = final_price
        
        if self.signal_type == "long":
            self.end_return_pct = (self.end_price - self.entry_price) / self.entry_price * 100
            self.max_return_pct = (self.max_price - self.entry_price) / self.entry_price * 100
        elif self.signal_type == "short":
            self.end_return_pct = (self.entry_price - self.end_price) / self.entry_price * 100
            self.max_return_pct = (self.entry_price - self.min_price) / self.entry_price * 100


class MonthlyRollingEvaluator:
    def __init__(self, strategy: EnhancedSMCStrategy, top_n: int = 20, lookback_days: int = 30, forward_days: int = 30):
        self.strategy = strategy
        self.top_n = top_n
        self.lookback_days = lookback_days
        self.forward_days = forward_days
        
    def evaluate(self, symbol_data_map: Dict[str, Tuple[str, pd.DataFrame]], eval_date_str: str) -> List[EvalResult]:
        """
        在大盘截面上评价所有股票
        
        Args:
            symbol_data_map: Dict[symbol, Tuple[name, DataFrame]] 历史数据池
            eval_date_str: 'YYYY-MM-DD' 评价基准日 (T)
            
        Returns:
            List[EvalResult]: Top N 的跟踪结果
        """
        eval_date = pd.to_datetime(eval_date_str)
        candidates = []
        
        # 1. Scan phase (T-30 to T)
        with Progress() as progress:
            task = progress.add_task("[cyan]正在扫描横截面信号...", total=len(symbol_data_map))
            
            for symbol, (name, df) in symbol_data_map.items():
                if 'timestamp' not in df.columns:
                    df['timestamp'] = pd.to_datetime(df.index)
                    
                # Get historical window up to T
                mask_history = (df['timestamp'] <= eval_date)
                df_hist = df.loc[mask_history].tail(800) # 取T之前最多800根K线供SMC分析
                
                if len(df_hist) < 50:
                    progress.update(task, advance=1)
                    continue
                    
                # Temporarily relax the distance criteria for cross-sectional scoring
                original_dist = self.strategy.optimal_ob_distance
                self.strategy.optimal_ob_distance = 0.50  # 50% distance allowed for cross-sectional ranking
                
                # Analyze at T
                analysis = self.strategy.analyze(df_hist, symbol=symbol, name=name)
                
                # Restore original
                self.strategy.optimal_ob_distance = original_dist
                
                # For cross-sectional ranking, we might want to accept signals even if they are neutral
                # due to trend or zone filtering. We will manually extract the best OB if primary_signal is neutral.
                if analysis.primary_signal and analysis.primary_signal.signal_type == "neutral":
                    bullish_obs = [ob for ob in analysis.raw_result.order_blocks if ob.type == 'bullish' and not ob.mitigated and ob.overlap_ratio > 0]
                    bearish_obs = [ob for ob in analysis.raw_result.order_blocks if ob.type == 'bearish' and not ob.mitigated and ob.overlap_ratio > 0]
                    
                    if bullish_obs:
                        bullish_obs.sort(key=lambda x: x.overlap_ratio, reverse=True)
                        best = bullish_obs[0]
                        analysis.primary_signal.signal_type = "long"
                        analysis.primary_signal.entry_price = best.top
                        analysis.primary_signal.stop_loss = best.bottom * 0.98
                        analysis.primary_signal.take_profit_1 = best.top * 1.05
                        analysis.primary_signal.take_profit_2 = best.top * 1.10
                        analysis.overall_score = best.overlap_ratio
                    elif bearish_obs:
                        bearish_obs.sort(key=lambda x: x.overlap_ratio, reverse=True)
                        best = bearish_obs[0]
                        analysis.primary_signal.signal_type = "short"
                        analysis.primary_signal.entry_price = best.bottom
                        analysis.primary_signal.stop_loss = best.top * 1.02
                        analysis.primary_signal.take_profit_1 = best.bottom * 0.95
                        analysis.primary_signal.take_profit_2 = best.bottom * 0.90
                        analysis.overall_score = best.overlap_ratio
                
                if analysis.primary_signal and analysis.primary_signal.signal_type == "long":
                    candidates.append((analysis.overall_score, analysis, df))
                    
                progress.update(task, advance=1)

        # 2. Select Top N
        # Sort by overall_score descending
        candidates.sort(key=lambda x: x[0], reverse=True)
        top_candidates = candidates[:self.top_n]
        
        results = []
        
        # 3. Forward tracking phase (T+1 to T+forward_days)
        with Progress() as progress:
            task = progress.add_task("[green]正在验证后市表现...", total=len(top_candidates))
            
            for score, analysis, df in top_candidates:
                signal = analysis.primary_signal
                
                # Get forward window
                mask_forward = (df['timestamp'] > eval_date)
                df_fwd = df.loc[mask_forward].head(self.forward_days)
                
                # Create result record
                res = EvalResult(
                    symbol=signal.symbol,
                    name=signal.name,
                    eval_date=eval_date,
                    signal_type=signal.signal_type,
                    entry_price=signal.entry_price, # 以策略生成的标准入场价计
                    stop_loss=signal.stop_loss,
                    target_1=signal.take_profit_1,
                    target_2=signal.take_profit_2,
                    signal_strength=signal.signal_strength,
                    overall_score=analysis.overall_score
                )
                
                if not df_fwd.empty:
                    res.simulate_forward_trade(df_fwd)
                
                results.append(res)
                progress.update(task, advance=1)
                
        return results
