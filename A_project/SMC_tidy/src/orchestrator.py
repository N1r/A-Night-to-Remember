"""
SMC Orchestrator - 统一调度入口
================================

高内聚、低耦合的系统协调器，整合所有模块：
    - Data Pipeline
    - SMC Engine
    - Signal Generator
    - Premium Visualizer

设计原则:
    - 单一入口点
    - 模块可替换
    - 错误优雅处理
    - 完整日志追踪
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple, Union

import pandas as pd
import numpy as np

from .core.engine import VectorizedSMCEngine, EngineConfig
from .core.signals import SignalGenerator, RiskManager, InstitutionalSignal
from .core.visualizer import PremiumChartBuilder, create_summary_panel
from .core.types import AnalysisOutput

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorConfig:
    """Orchestrator 配置"""
    # 路径配置
    data_dir: Path = None
    output_dir: Path = None
    charts_dir: Path = None
    reports_dir: Path = None
    
    # 引擎配置
    swing_length: int = 50
    swing_left: int = 10
    swing_right: int = 10
    
    # 风险配置
    account_size: float = 100000.0
    risk_per_trade: float = 0.02
    max_position_pct: float = 0.10
    
    # 图表配置
    chart_height: int = 900
    show_volume: bool = True
    
    def __post_init__(self):
        if self.data_dir is None:
            self.data_dir = Path("data/raw")
        if self.output_dir is None:
            self.output_dir = Path("output")
        if self.charts_dir is None:
            self.charts_dir = self.output_dir / "charts"
        if self.reports_dir is None:
            self.reports_dir = self.output_dir / "reports"
        
        # 确保目录存在
        for d in [self.data_dir, self.output_dir, self.charts_dir, self.reports_dir]:
            d.mkdir(parents=True, exist_ok=True)


@dataclass
class AnalysisResult:
    """完整分析结果"""
    symbol: str
    name: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 核心输出
    output: Optional[AnalysisOutput] = None
    signal: Optional[InstitutionalSignal] = None
    
    # 文件路径
    chart_path: Optional[Path] = None
    
    # 状态
    success: bool = True
    error_message: str = ""
    computation_time_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "symbol": self.symbol,
            "name": self.name,
            "timestamp": self.timestamp.isoformat(),
            "success": self.success,
            "error_message": self.error_message,
            "computation_time_ms": round(self.computation_time_ms, 2),
            "output": self.output.to_dict() if self.output else None,
            "signal": self.signal.to_dict() if self.signal else None,
            "chart_path": str(self.chart_path) if self.chart_path else None,
        }


class SMCOrchestrator:
    """
    SMC 分析系统统一协调器
    
    整合数据获取、SMC 分析、信号生成、可视化输出。
    
    使用示例:
        >>> orchestrator = SMCOrchestrator()
        >>> result = orchestrator.analyze(df, symbol="000001", name="平安银行")
        >>> print(result.signal.to_dict())
    """
    
    def __init__(self, config: Optional[OrchestratorConfig] = None):
        """
        初始化 Orchestrator
        
        Args:
            config: 配置对象
        """
        self.config = config or OrchestratorConfig()
        
        # 初始化各模块
        engine_config = EngineConfig(
            swing_length=self.config.swing_length,
            swing_left=self.config.swing_left,
            swing_right=self.config.swing_right,
        )
        self.engine = VectorizedSMCEngine(engine_config)
        
        risk_manager = RiskManager(
            account_size=self.config.account_size,
            risk_per_trade=self.config.risk_per_trade,
            max_position_pct=self.config.max_position_pct,
        )
        self.signal_generator = SignalGenerator(risk_manager)
        
        self.chart_builder = PremiumChartBuilder()
        
        # 统计
        self._stats = {
            "total_analyses": 0,
            "successful_analyses": 0,
            "failed_analyses": 0,
            "total_time_ms": 0.0,
        }
    
    def analyze(
        self,
        df: pd.DataFrame,
        symbol: str = "UNKNOWN",
        name: str = "",
        timeframe: str = "daily",
        generate_chart: bool = True,
    ) -> AnalysisResult:
        """
        执行完整分析
        
        Args:
            df: OHLCV DataFrame
            symbol: 股票代码
            name: 股票名称
            timeframe: 时间框架
            generate_chart: 是否生成图表
            
        Returns:
            AnalysisResult: 完整分析结果
        """
        start_time = time.perf_counter()
        result = AnalysisResult(symbol=symbol, name=name)
        
        self._stats["total_analyses"] += 1
        
        try:
            # 1. 数据验证
            df = self._validate_data(df)
            
            # 2. SMC 分析
            output = self.engine.analyze(df, symbol=symbol, timeframe=timeframe)
            result.output = output
            
            # 3. 信号生成
            signal = self.signal_generator.generate(output, symbol=symbol, name=name)
            result.signal = signal
            
            # 4. 图表生成
            if generate_chart:
                chart_path = self.config.charts_dir / f"{symbol}_{name}_chart.html"
                fig = self.chart_builder.build(
                    df, output, signal,
                    title=f"{symbol} {name} - SMC分析",
                    height=self.config.chart_height,
                    show_volume=self.config.show_volume,
                )
                self.chart_builder.save(fig, chart_path)
                result.chart_path = chart_path
            
            result.success = True
            self._stats["successful_analyses"] += 1
            
        except Exception as e:
            result.success = False
            result.error_message = str(e)
            self._stats["failed_analyses"] += 1
            logger.error(f"分析失败 {symbol}: {e}")
        
        result.computation_time_ms = (time.perf_counter() - start_time) * 1000
        self._stats["total_time_ms"] += result.computation_time_ms
        
        return result
    
    def _validate_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """验证和清洗数据"""
        if df is None or df.empty:
            raise ValueError("输入数据为空")
        
        df = df.copy()
        
        # 标准化列名
        column_map = {
            '日期': 'date', '时间': 'date', 'datetime': 'date',
            '开盘': 'open', '最高': 'high', '最低': 'low',
            '收盘': 'close', '成交量': 'volume',
        }
        df.rename(columns={k: v for k, v in column_map.items() if k in df.columns}, inplace=True)
        
        # 验证必要列
        required = ['open', 'high', 'low', 'close', 'volume']
        missing = [col for col in required if col not in df.columns]
        if missing:
            raise ValueError(f"缺少必要列: {missing}")
        
        # 移除无效行
        df = df.dropna(subset=required).reset_index(drop=True)
        
        if len(df) < 50:
            raise ValueError(f"数据点不足: {len(df)} < 50")
        
        return df
    
    def batch_analyze(
        self,
        data_files: List[Tuple[Path, str, str]],
        timeframe: str = "daily",
        generate_charts: bool = True,
        max_results: Optional[int] = None,
    ) -> List[AnalysisResult]:
        """
        批量分析
        
        Args:
            data_files: [(文件路径, 代码, 名称), ...]
            timeframe: 时间框架
            generate_charts: 是否生成图表
            max_results: 最大结果数量
            
        Returns:
            List[AnalysisResult]: 分析结果列表
        """
        results = []
        
        for i, (file_path, symbol, name) in enumerate(data_files):
            if max_results and i >= max_results:
                break
            
            try:
                df = pd.read_csv(file_path)
                result = self.analyze(
                    df, symbol, name, timeframe, generate_charts
                )
                results.append(result)
                
                logger.debug(f"完成分析: {symbol} - 强度: {result.signal.signal_strength:.1f}" if result.signal else f"完成分析: {symbol} - 无信号")
                
            except Exception as e:
                logger.error(f"分析失败 {file_path}: {e}")
                results.append(AnalysisResult(
                    symbol=symbol,
                    name=name,
                    success=False,
                    error_message=str(e),
                ))
        
        # 按信号强度排序
        results.sort(
            key=lambda x: x.signal.signal_strength if x.signal else 0,
            reverse=True
        )
        
        return results
    
    def generate_report(
        self,
        results: List[AnalysisResult],
        output_path: Optional[Path] = None,
    ) -> Path:
        """
        生成综合报告
        
        Args:
            results: 分析结果列表
            output_path: 输出路径
            
        Returns:
            Path: 报告文件路径
        """
        if output_path is None:
            output_path = self.config.reports_dir / f"smc_report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"
        
        # 准备数据
        data = []
        for r in results:
            if r.success and r.signal and r.signal.is_actionable:
                data.append({
                    '代码': r.symbol,
                    '名称': r.name,
                    '信号类型': r.signal.direction,
                    '信号强度': round(r.signal.signal_strength, 1),
                    '置信度': round(r.signal.confidence, 1),
                    '预估胜率': f"{r.signal.estimated_win_rate:.1f}%",
                    '盈亏比': round(r.signal.risk_reward_ratio, 2),
                    '入场价': round(r.signal.entry_price, 2),
                    '止损价': round(r.signal.stop_loss, 2),
                    '目标1': round(r.signal.take_profit_1, 2),
                    '目标2': round(r.signal.take_profit_2, 2),
                    '建议仓位%': round(r.signal.position_size_pct, 2),
                    '风险评分': round(r.signal.risk_score, 1),
                    'OB重叠度': f"{r.signal.ob_overlap_score:.0f}%",
                    '融合因素': "; ".join(r.signal.confluence_factors),
                    '风险警告': "; ".join(r.signal.warnings),
                })
        
        df = pd.DataFrame(data)
        
        # 保存 Excel
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='信号汇总', index=False)
            
            # 统计摘要
            if results:
                summary = self._create_summary_stats(results)
                pd.DataFrame([summary]).to_excel(writer, sheet_name='统计摘要', index=False)
        
        logger.debug(f"报告已生成: {output_path}")
        return output_path
    
    def _create_summary_stats(self, results: List[AnalysisResult]) -> Dict:
        """创建统计摘要"""
        successful = [r for r in results if r.success]
        signals = [r.signal for r in successful if r.signal]
        
        long_signals = [s for s in signals if s.is_long]
        short_signals = [s for s in signals if s.is_short]
        actionable = [s for s in signals if s.is_actionable]
        
        return {
            '总分析数': len(results),
            '成功分析数': len(successful),
            '失败分析数': len(results) - len(successful),
            '做多信号数': len(long_signals),
            '做空信号数': len(short_signals),
            '可操作信号数': len(actionable),
            '平均信号强度': round(np.mean([s.signal_strength for s in signals]) if signals else 0, 1),
            '平均置信度': round(np.mean([s.confidence for s in signals]) if signals else 0, 1),
            '平均预估胜率': round(np.mean([s.estimated_win_rate for s in signals]) if signals else 0, 1),
            '平均盈亏比': round(np.mean([s.risk_reward_ratio for s in signals]) if signals else 0, 2),
            '总计算时间(ms)': round(self._stats['total_time_ms'], 2),
        }
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return self._stats.copy()


def analyze_from_file(
    file_path: Union[str, Path],
    symbol: str = None,
    name: str = "",
    timeframe: str = "daily",
    config: Optional[OrchestratorConfig] = None,
) -> AnalysisResult:
    """
    从文件分析（便捷函数）
    
    Args:
        file_path: 数据文件路径
        symbol: 股票代码（默认从文件名提取）
        name: 股票名称
        timeframe: 时间框架
        config: 配置对象
        
    Returns:
        AnalysisResult: 分析结果
    """
    file_path = Path(file_path)
    
    if symbol is None:
        # 从文件名提取
        symbol = file_path.stem.split('_')[0]
    
    df = pd.read_csv(file_path)
    
    orchestrator = SMCOrchestrator(config)
    return orchestrator.analyze(df, symbol, name, timeframe)
