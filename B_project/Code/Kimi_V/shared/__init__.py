"""
shared/__init__.py
------------------
全局共享模块 — 提供路径、日志、配置、状态管理、领域配置、美学配置。

使用方式：
    from shared import PROJECT_ROOT, console, domain, aesthetics
    from shared.domain import domain
    from shared.aesthetics import aesthetics
    from shared.state import load_visited, save_visited
"""

from shared.paths import *
from shared.logger import console
from shared.state import load_visited, save_visited
from shared.domain import domain, get_domain
from shared.aesthetics import aesthetics, get_aesthetics
