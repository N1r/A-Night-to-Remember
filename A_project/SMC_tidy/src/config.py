"""
Configuration management for SMC Analysis Tool.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any
import yaml


@dataclass
class SMCConfig:
    """SMC analysis configuration."""
    swing_length: int = 50
    close_mitigation: bool = False
    join_consecutive_fvg: bool = True
    overlap_candles: int = 3
    swing_left: int = 10
    swing_right: int = 10


@dataclass
class IntradaySMCConfig:
    """SMC analysis configuration for intraday (60min) timeframe."""
    swing_length: int = 15
    close_mitigation: bool = False
    join_consecutive_fvg: bool = True
    overlap_candles: int = 2
    swing_left: int = 5
    swing_right: int = 5


@dataclass
class DataConfig:
    """Data fetching configuration."""
    start_date_days: int = 720
    time_interval: str = "daily"
    batch_delay: float = 0.5
    max_retries: int = 3
    retry_delay: float = 1.0
    timeout: int = 30
    concurrent_requests: int = 5


@dataclass
class ChartConfig:
    """Chart visualization configuration."""
    width: int = 1400
    height: int = 900
    theme: str = "plotly_white"
    show_volume: bool = True
    show_grid: bool = True
    
    # Color scheme (Chinese market style: red=up, green=down)
    colors: Dict[str, str] = field(default_factory=lambda: {
        "bullish": "#E63946",      # Red for up
        "bearish": "#2D6A4F",      # Green for down
        "fvg_bullish": "#FFB703",  # Gold for bullish FVG
        "fvg_bearish": "#3A86FF",  # Blue for bearish FVG
        "bos": "#FF6B6B",          # Coral for BOS
        "choch": "#4ECDC4",        # Teal for CHOCH
        "ob_bullish": "#E63946",   # Red for bullish OB
        "ob_bearish": "#2D6A4F",   # Green for bearish OB
        "liquidity": "#FFD166",    # Yellow for liquidity
        "swing_high": "#FF9F1C",   # Orange for swing high
        "swing_low": "#2EC4B6",    # Cyan for swing low
        "premium": "#FF6B6B",      # Premium zone
        "discount": "#4ECDC4",     # Discount zone
        "volume": "#6C757D",       # Volume bars
    })


@dataclass
class WebConfig:
    """Web application configuration."""
    host: str = "0.0.0.0"
    port: int = 8080
    title: str = "SMC Technical Analysis"
    refresh_interval: int = 300  # seconds
    max_stocks_display: int = 50


@dataclass
class AppConfig:
    """Main application configuration."""
    smc: SMCConfig = field(default_factory=SMCConfig)
    smc_intraday: IntradaySMCConfig = field(default_factory=IntradaySMCConfig)
    data: DataConfig = field(default_factory=DataConfig)
    chart: ChartConfig = field(default_factory=ChartConfig)
    web: WebConfig = field(default_factory=WebConfig)
    
    # Paths
    project_root: Path = field(default_factory=lambda: Path(__file__).parent.parent)
    
    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"
    
    @property
    def raw_data_dir(self) -> Path:
        return self.data_dir / "raw"
    
    @property
    def processed_data_dir(self) -> Path:
        return self.data_dir / "processed"
    
    @property
    def output_dir(self) -> Path:
        return self.project_root / "output"
    
    @property
    def charts_dir(self) -> Path:
        return self.output_dir / "charts"
    
    @property
    def reports_dir(self) -> Path:
        return self.output_dir / "reports"
    
    @classmethod
    def from_yaml(cls, path: Optional[Path] = None) -> "AppConfig":
        """Load configuration from YAML file."""
        if path is None:
            path = cls().project_root / "config.yaml"
        
        if not path.exists():
            return cls()
        
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        
        return cls(
            smc=SMCConfig(**data.get("smc_analysis", {})),
            smc_intraday=IntradaySMCConfig(**data.get("smc_intraday", {})),
            data=DataConfig(**data.get("data_fetch", {})),
            chart=ChartConfig(**data.get("chart", {})),
            web=WebConfig(**data.get("web", {})),
        )
    
    def ensure_directories(self) -> None:
        """Create all necessary directories."""
        for directory in [
            self.data_dir,
            self.raw_data_dir,
            self.processed_data_dir,
            self.output_dir,
            self.charts_dir,
            self.reports_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)


# Global config instance
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Get or create global configuration instance."""
    global _config
    if _config is None:
        _config = AppConfig.from_yaml()
        _config.ensure_directories()
    return _config


def reload_config() -> AppConfig:
    """Reload configuration from file."""
    global _config
    _config = AppConfig.from_yaml()
    _config.ensure_directories()
    return _config
