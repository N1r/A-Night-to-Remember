"""
Base Strategy Interface for SMC Analysis.
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple, Dict, Any
import pandas as pd
from .types import AnalysisOutput, InstitutionalSignal


class BaseStrategy(ABC):
    """
    Abstract Base Class for all SMC-based trading strategies.
    """
    
    @abstractmethod
    def generate_signal(
        self, 
        output: AnalysisOutput, 
        symbol: str = "UNKNOWN", 
        name: str = ""
    ) -> InstitutionalSignal:
        """
        Generate a trading signal from SMC analysis output.
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the name of the strategy."""
        pass
