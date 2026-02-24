"""
SMC Core Engine Tests
=====================

Unit tests for the vectorized SMC engine and signal generator.
"""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core import (
    VectorizedSMCEngine,
    EngineConfig,
    SignalGenerator,
    RiskManager,
    InstitutionalSignal,
    PremiumChartBuilder,
    OrderBlock, OBType,
    FairValueGap, FVGType,
    StructureBreak, BreakType,
    SwingPoint,
    MarketState, ZoneType, TrendDirection,
    AnalysisOutput, SignalType,
)
from src.orchestrator import SMCOrchestrator, OrchestratorConfig, analyze_from_file


def create_sample_ohlcv(n_bars: int = 300, seed: int = 42) -> pd.DataFrame:
    """Create sample OHLCV data for testing."""
    np.random.seed(seed)
    
    dates = pd.date_range(start='2024-01-01', periods=n_bars, freq='D')
    
    # Create realistic price pattern
    base_price = 100
    prices = [base_price]
    
    for i in range(n_bars - 1):
        trend = 0.1 if i < n_bars // 2 else -0.05  # Up then down
        noise = np.random.uniform(-1, 1)
        prices.append(prices[-1] + trend + noise)
    
    prices = np.array(prices)
    
    # Create OHLCV
    df = pd.DataFrame({
        'date': dates,
        'open': prices,
        'high': prices + np.random.uniform(0.5, 2, n_bars),
        'low': prices - np.random.uniform(0.5, 2, n_bars),
        'close': prices + np.random.uniform(-0.5, 0.5, n_bars),
        'volume': np.random.randint(1000000, 10000000, n_bars),
    })
    
    # Ensure OHLC consistency
    df['high'] = df[['high', 'open', 'close']].max(axis=1)
    df['low'] = df[['low', 'open', 'close']].min(axis=1)
    
    return df


class TestVectorizedSMCEngine:
    """Test the vectorized SMC engine."""
    
    @pytest.fixture
    def engine(self):
        return VectorizedSMCEngine()
    
    @pytest.fixture
    def sample_data(self):
        return create_sample_ohlcv(300)
    
    def test_engine_initialization(self, engine):
        """Test engine initializes correctly."""
        assert engine is not None
        assert engine.config is not None
        assert engine.config.swing_length == 50
    
    def test_engine_with_custom_config(self):
        """Test engine with custom configuration."""
        config = EngineConfig(swing_length=30, swing_left=5, swing_right=5)
        engine = VectorizedSMCEngine(config)
        
        assert engine.config.swing_length == 30
        assert engine.config.swing_left == 5
    
    def test_analyze_returns_output(self, engine, sample_data):
        """Test analyze returns valid output."""
        result = engine.analyze(sample_data, symbol="TEST")
        
        assert result is not None
        assert isinstance(result, AnalysisOutput)
        assert result.symbol == "TEST"
        assert result.data_points > 0
        assert result.computation_time_ms > 0
    
    def test_analyze_detects_swing_points(self, engine, sample_data):
        """Test swing point detection."""
        result = engine.analyze(sample_data, symbol="TEST")
        
        assert len(result.swing_points) > 0
        
        # Check swing points have valid data
        for sp in result.swing_points:
            assert sp.index >= 0
            assert sp.price > 0
            assert isinstance(sp.is_high, bool)
    
    def test_analyze_detects_order_blocks(self, engine, sample_data):
        """Test order block detection."""
        result = engine.analyze(sample_data, symbol="TEST")
        
        # Should have some OBs
        assert len(result.order_blocks) >= 0
        
        for ob in result.order_blocks:
            assert ob.top > ob.bottom
            assert ob.type in [OBType.BULLISH, OBType.BEARISH]
    
    def test_analyze_detects_fvgs(self, engine, sample_data):
        """Test FVG detection."""
        result = engine.analyze(sample_data, symbol="TEST")
        
        # Check FVG data structure
        for fvg in result.fvgs:
            assert fvg.top > fvg.bottom
            assert fvg.type in [FVGType.BULLISH, FVGType.BEARISH]
    
    def test_analyze_detects_market_state(self, engine, sample_data):
        """Test market state analysis."""
        result = engine.analyze(sample_data, symbol="TEST")
        
        assert result.market_state is not None
        assert result.market_state.trend in [TrendDirection.BULLISH, TrendDirection.BEARISH, TrendDirection.NEUTRAL]
        assert result.market_state.zone in [ZoneType.PREMIUM, ZoneType.DISCOUNT, ZoneType.EQUILIBRIUM]
        assert result.market_state.current_price > 0
    
    def test_analyze_performance(self, engine):
        """Test analysis performance on large dataset."""
        # Create 10,000 bars
        large_data = create_sample_ohlcv(10000)
        
        result = engine.analyze(large_data, symbol="PERF")
        
        # Should complete in under 500ms (reasonable for 10K bars)
        assert result.computation_time_ms < 500
        assert result.data_points == 10000
    
    def test_analyze_with_insufficient_data(self, engine):
        """Test handling of insufficient data."""
        small_data = create_sample_ohlcv(30)
        
        with pytest.raises(ValueError, match="数据点数不足"):
            engine.analyze(small_data, symbol="TEST")
    
    def test_analyze_with_missing_columns(self, engine):
        """Test handling of missing columns."""
        bad_data = pd.DataFrame({
            'date': pd.date_range(start='2024-01-01', periods=100, freq='D'),
            'open': np.random.uniform(10, 20, 100),
            'close': np.random.uniform(10, 20, 100),
        })
        
        with pytest.raises(ValueError, match="缺少必要列"):
            engine.analyze(bad_data, symbol="TEST")


class TestSignalGenerator:
    """Test the signal generator."""
    
    @pytest.fixture
    def generator(self):
        return SignalGenerator()
    
    @pytest.fixture
    def sample_output(self):
        engine = VectorizedSMCEngine()
        df = create_sample_ohlcv(300)
        return engine.analyze(df, symbol="TEST")
    
    def test_generator_initialization(self, generator):
        """Test generator initializes correctly."""
        assert generator is not None
        assert generator.risk_manager is not None
    
    def test_generate_returns_signal(self, generator, sample_output):
        """Test signal generation."""
        signal = generator.generate(sample_output, symbol="TEST", name="Test Stock")
        
        assert signal is not None
        assert isinstance(signal, InstitutionalSignal)
        assert signal.symbol == "TEST"
    
    def test_signal_has_valid_structure(self, generator, sample_output):
        """Test signal has valid structure."""
        signal = generator.generate(sample_output, symbol="TEST")
        
        assert signal.signal_type in [SignalType.LONG, SignalType.SHORT, SignalType.NEUTRAL]
        assert signal.signal_strength >= 0
        assert signal.confidence >= 0
        assert signal.risk_score >= 0
    
    def test_signal_serialization(self, generator, sample_output):
        """Test signal serialization to dict."""
        signal = generator.generate(sample_output, symbol="TEST")
        data = signal.to_dict()
        
        assert 'symbol' in data
        assert 'signal_type' in data
        assert 'signal_strength' in data


class TestRiskManager:
    """Test the risk manager."""
    
    @pytest.fixture
    def risk_manager(self):
        return RiskManager(account_size=100000, risk_per_trade=0.02)
    
    def test_position_size_calculation(self, risk_manager):
        """Test position size calculation."""
        shares = risk_manager.calculate_position_size(
            entry_price=100.0,
            stop_loss=95.0,
        )
        
        # Risk = $5 per share, Account risk = $2000
        # Shares = 2000 / 5 = 400
        assert shares > 0
        assert shares <= 1000  # Within max position limit
    
    def test_stop_loss_calculation(self, risk_manager):
        """Test stop loss calculation."""
        ob = OrderBlock(
            index=0,
            top=105.0,
            bottom=100.0,
            type=OBType.BULLISH,
        )
        
        stop = risk_manager.calculate_stop_loss(
            entry_price=100.0,
            ob=ob,
            atr=2.0,
            is_long=True,
        )
        
        # Stop should be below OB bottom
        assert stop < ob.bottom
    
    def test_take_profit_calculation(self, risk_manager):
        """Test take profit calculation."""
        tp1, tp2, tp3 = risk_manager.calculate_take_profits(
            entry_price=100.0,
            stop_loss=95.0,
            is_long=True,
        )
        
        risk = 5.0
        assert tp1 == 100 + risk * 2  # 110
        assert tp2 == 100 + risk * 3  # 115
        assert tp3 == 100 + risk * 5  # 125
    
    def test_risk_assessment(self, risk_manager):
        """Test risk assessment."""
        engine = VectorizedSMCEngine()
        df = create_sample_ohlcv(300)
        output = engine.analyze(df, symbol="TEST")
        
        generator = SignalGenerator(risk_manager)
        signal = generator.generate(output, symbol="TEST")
        
        risk = risk_manager.assess_risk(signal, output)
        
        assert 0 <= risk <= 100


class TestPremiumChartBuilder:
    """Test the premium chart builder."""
    
    @pytest.fixture
    def builder(self):
        return PremiumChartBuilder()
    
    @pytest.fixture
    def sample_analysis(self):
        engine = VectorizedSMCEngine()
        df = create_sample_ohlcv(200)
        output = engine.analyze(df, symbol="TEST")
        
        generator = SignalGenerator()
        signal = generator.generate(output, symbol="TEST")
        
        return df, output, signal
    
    def test_build_chart(self, builder, sample_analysis):
        """Test chart building."""
        df, output, signal = sample_analysis
        
        fig = builder.build(df, output, signal)
        
        assert fig is not None
        assert len(fig.data) > 0  # Should have traces
    
    def test_chart_save(self, builder, sample_analysis, tmp_path):
        """Test saving chart to file."""
        df, output, signal = sample_analysis
        
        fig = builder.build(df, output, signal)
        filepath = tmp_path / "test_chart.html"
        
        builder.save(fig, filepath)
        
        assert filepath.exists()
        assert filepath.stat().st_size > 0


class TestOrchestrator:
    """Test the orchestrator."""
    
    @pytest.fixture
    def orchestrator(self, tmp_path):
        config = OrchestratorConfig(
            data_dir=tmp_path / "data",
            output_dir=tmp_path / "output",
        )
        return SMCOrchestrator(config)
    
    @pytest.fixture
    def sample_data(self):
        return create_sample_ohlcv(300)
    
    def test_orchestrator_initialization(self, orchestrator):
        """Test orchestrator initializes correctly."""
        assert orchestrator is not None
        assert orchestrator.engine is not None
        assert orchestrator.signal_generator is not None
    
    def test_analyze(self, orchestrator, sample_data):
        """Test full analysis pipeline."""
        result = orchestrator.analyze(
            sample_data,
            symbol="TEST",
            name="Test Stock",
        )
        
        assert result.success
        assert result.output is not None
        assert result.signal is not None
    
    def test_analyze_with_chart(self, orchestrator, sample_data):
        """Test analysis with chart generation."""
        result = orchestrator.analyze(
            sample_data,
            symbol="TEST",
            name="Test Stock",
            generate_chart=True,
        )
        
        assert result.success
        assert result.chart_path is not None
        assert result.chart_path.exists()
    
    def test_stats_tracking(self, orchestrator, sample_data):
        """Test statistics tracking."""
        orchestrator.analyze(sample_data, symbol="TEST1")
        orchestrator.analyze(sample_data, symbol="TEST2")
        
        stats = orchestrator.get_stats()
        
        assert stats['total_analyses'] == 2
        assert stats['successful_analyses'] == 2


# Run tests if executed directly
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
