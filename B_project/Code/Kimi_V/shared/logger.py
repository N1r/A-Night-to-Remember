"""
shared/logger.py
----------------
统一日志系统 — 全局唯一 Rich Console 实例。

所有模块都应从这里导入 console，避免各自创建实例。

使用方式：
    from shared.logger import console, log_step
"""

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

# 全局唯一 Console 实例
console = Console()


def log_step(step_num: int, name: str, status: str = "running"):
    """打印步骤状态"""
    icons = {"running": "➡️", "done": "✅", "failed": "❌", "skipped": "⏭️"}
    colors = {"running": "yellow", "done": "green", "failed": "red", "skipped": "dim"}
    icon = icons.get(status, "➡️")
    color = colors.get(status, "yellow")
    console.print(f"{icon} [{color}]Step {step_num}: {name}[/{color}]")


def log_platform(name: str, count: int, extra: str = ""):
    """打印平台采集结果"""
    if count > 0:
        msg = f"  [green]✅ {name}[/green] 采集完成: [bold]{count}[/bold] 条"
        if extra:
            msg += f" [dim]({extra})[/dim]"
    else:
        msg = f"  [dim]⚪ {name}[/dim] 无新内容"
    console.print(msg)


def create_progress():
    """创建统一的 Progress 实例"""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True,
    )
