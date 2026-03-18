"""
Configuration management for SMC Analysis Tool using Pydantic Settings.
"""
from pathlib import Path
from typing import Dict, Optional, Any
import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SMCConfig(BaseSettings):
    """SMC analysis configuration."""
    swing_length: int = 50
    close_mitigation: bool = False
    join_consecutive_fvg: bool = True
    overlap_candles: int = 3
    swing_left: int = 10
    swing_right: int = 10


class IntradaySMCConfig(BaseSettings):
    """SMC analysis configuration for intraday timeframes."""
    swing_length: int = 15
    close_mitigation: bool = False
    join_consecutive_fvg: bool = True
    overlap_candles: int = 2
    swing_left: int = 5
    swing_right: int = 5


class DataConfig(BaseSettings):
    """Data fetching configuration."""
    start_date_days: int = 720
    time_interval: str = "daily"
    batch_delay: float = 0.5
    max_retries: int = 3
    retry_delay: float = 1.0
    timeout: int = 30
    concurrent_requests: int = 5


class ChartConfig(BaseSettings):
    """Chart visualization configuration."""
    width: int = 1400
    height: int = 900
    theme: str = "plotly_white"
    show_volume: bool = True
    show_grid: bool = True
    
    # Color scheme (Chinese market style: red=up, green=down)
    colors: Dict[str, str] = {
        "bullish": "#E63946",
        "bearish": "#2D6A4F",
        "fvg_bullish": "#FFB703",
        "fvg_bearish": "#3A86FF",
        "bos": "#FF6B6B",
        "choch": "#4ECDC4",
        "ob_bullish": "#E63946",
        "ob_bearish": "#2D6A4F",
        "liquidity": "#FFD166",
        "swing_high": "#FF9F1C",
        "swing_low": "#2EC4B6",
        "premium": "#FF6B6B",
        "discount": "#4ECDC4",
        "volume": "#6C757D",
    }


class WebConfig(BaseSettings):
    """Web application configuration."""
    host: str = "0.0.0.0"
    port: int = 8080
    title: str = "SMC Technical Analysis"
    refresh_interval: int = 300
    max_stocks_display: int = 50


class AppConfig(BaseSettings):
    """Main application configuration."""
    model_config = SettingsConfigDict(
        env_prefix="SMC_",
        env_nested_delimiter="__",
        extra="ignore"
    )

    smc: SMCConfig = Field(default_factory=SMCConfig)
    smc_intraday: IntradaySMCConfig = Field(default_factory=IntradaySMCConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    chart: ChartConfig = Field(default_factory=ChartConfig)
    web: WebConfig = Field(default_factory=WebConfig)
    
    # Paths
    project_root: Path = Field(default_factory=lambda: Path(__file__).parent.parent)
    
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

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "AppConfig":
        """Load configuration from YAML and Environment variables."""
        if path is None:
            path = Path(__file__).parent.parent / "config.yaml"
        
        yaml_data = {}
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                yaml_data = yaml.safe_load(f) or {}
        
        # Mapping YAML keys to Pydantic fields
        config_dict = {
            "smc": yaml_data.get("smc_analysis", {}),
            "smc_intraday": yaml_data.get("smc_intraday", {}),
            "data": yaml_data.get("data_fetch", {}),
            "chart": yaml_data.get("chart", {}),
            "web": yaml_data.get("web", {}),
        }
        
        return cls(**config_dict)


# Global config instance
_config: Optional[AppConfig] = None


def get_config() -> AppConfig:
    """Get or create global configuration instance."""
    global _config
    if _config is None:
        _config = AppConfig.load()
        _config.ensure_directories()
    return _config


def reload_config() -> AppConfig:
    """Reload configuration from file."""
    global _config
    _config = AppConfig.load()
    _config.ensure_directories()
    return _config
