#!/usr/bin/env python3
"""
SMC Intelligent Trading System - Unified CLI Entry Point
=========================================================

An industrial-grade quantitative analysis tool based on Smart Money Concepts.
Supports A-share and HK-share market analysis with high-performance vectorized engine.

Usage:
    python main.py analyze --a-stocks 500 --hk-stocks 200 --web
    python main.py analyze --skip-fetch --period 60
    python main.py web --port 8080
"""
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd
import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn, MofNCompleteColumn
from rich.table import Table
from rich.panel import Panel

# Add src to path if needed
sys.path.insert(0, str(Path(__file__).parent))

from src.config import get_config, reload_config
from src.orchestrator import SMCOrchestrator, OrchestratorConfig
from src.data_fetch.a_stock import AStockFetcher
from src.data_fetch.hk_stock import HKStockFetcher
from src.web.app import run_app

# CLI Setup
app = typer.Typer(help="SMC Intelligent Trading System")
console = Console()

# Logging Setup
def setup_logging(level=logging.INFO):
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, console=console)]
    )
    # Silence noisy loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


@app.command()
def analyze(
    a_stocks: int = typer.Option(500, "--a-stocks", "-a", help="Number of A-shares to analyze"),
    hk_stocks: int = typer.Option(200, "--hk-stocks", "-k", help="Number of HK-shares to analyze"),
    period: str = typer.Option("daily", "--period", "-p", help="Analysis period: daily, 60 (min)"),
    force: bool = typer.Option(False, "--force", "-f", help="Force refresh data"),
    skip_fetch: bool = typer.Option(False, "--skip-fetch", help="Skip data fetching"),
    no_charts: bool = typer.Option(False, "--no-charts", help="Do not generate charts"),
    web: bool = typer.Option(False, "--web", "-w", help="Start web app after analysis"),
    port: int = typer.Option(8080, help="Web port"),
):
    """Run full SMC analysis pipeline."""
    setup_logging()
    config = get_config()
    config.ensure_directories()
    
    console.print(Panel.fit(
        f"[bold cyan]SMC Intelligent Trading System[/bold cyan]\n"
        f"[dim]Period: {period} | A: {a_stocks} | HK: {hk_stocks}[/dim]",
        border_style="cyan"
    ))

    # 1. Data Fetching
    data_files = []
    if not skip_fetch:
        data_files = asyncio.run(_fetch_all_data(a_stocks, hk_stocks, period, force))
    else:
        console.print("[yellow]Skipping data fetch, searching local files...[/yellow]")
        data_files = _find_local_data(period)

    if not data_files:
        console.print("[red]No data files found to analyze.[/red]")
        raise typer.Exit(1)

    # 2. Analysis
    orchestrator = SMCOrchestrator(config)
    results = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[green]Analyzing stocks...", total=len(data_files))
        
        for file_path, symbol, name in data_files:
            try:
                df = pd.read_csv(file_path)
                res = orchestrator.analyze(
                    df, symbol=symbol, name=name, 
                    timeframe=period, generate_chart=not no_charts
                )
                results.append(res)
            except Exception as e:
                logging.error(f"Error analyzing {symbol}: {e}")
            progress.update(task, advance=1)

    # 3. Reporting
    report_path = orchestrator.generate_report(results)
    
    # Display Top Signals
    _display_top_signals(results)
    
    console.print(f"\n[bold green]✓ Analysis complete![/bold green]")
    console.print(f"Report saved to: [cyan]{report_path}[/cyan]")
    console.print(f"Total analyses: {len(results)} | Successful: {sum(1 for r in results if r.success)}")

    # 4. Web App
    if web:
        console.print(f"\n[bold yellow]Starting Web UI on port {port}...[/bold yellow]")
        run_app(host=config.web.host, port=port)


@app.command()
def web(
    port: int = typer.Option(8080, help="Web port"),
    host: str = typer.Option("0.0.0.0", help="Web host"),
):
    """Start the SMC Web application."""
    setup_logging()
    console.print(f"[bold yellow]Starting SMC Web UI on {host}:{port}...[/bold yellow]")
    run_app(host=host, port=port)


async def _fetch_all_data(a_n, hk_n, period, force) -> List[Tuple[Path, str, str]]:
    """Async data fetching for A and HK stocks."""
    config = get_config()
    files = []
    
    # A-Stocks
    if a_n > 0:
        fetcher = AStockFetcher(config=config)
        console.print(f"[cyan]Fetching A-share spot data (Top {a_n})...[/cyan]")
        spot_df = await fetcher.get_spot_data(top_n=a_n)
        
        async with fetcher:
            tasks = []
            for _, row in spot_df.iterrows():
                tasks.append(fetcher._fetch_single_async(
                    row['代码'], name=row['名称'], period=period, skip_existing=not force
                ))
            
            with Progress(console=console) as progress:
                fetch_task = progress.add_task("[blue]Downloading A-shares...", total=len(tasks))
                for coro in asyncio.as_completed(tasks):
                    res = await coro
                    if res:
                        files.append((Path(res['filename']), res['code'], res['name']))
                    progress.update(fetch_task, advance=1)

    # HK-Stocks
    if hk_n > 0:
        fetcher = HKStockFetcher(config=config)
        console.print(f"[cyan]Fetching HK-share spot data (Top {hk_n})...[/cyan]")
        spot_df = await fetcher.get_spot_data(top_n=hk_n)
        
        async with fetcher:
            tasks = []
            for _, row in spot_df.iterrows():
                tasks.append(fetcher._fetch_single_async(
                    row['代码'], name=row['名称'], period=period, skip_existing=not force
                ))
            
            with Progress(console=console) as progress:
                fetch_task = progress.add_task("[magenta]Downloading HK-shares...", total=len(tasks))
                for coro in asyncio.as_completed(tasks):
                    res = await coro
                    if res:
                        files.append((Path(res['filename']), res['code'], res['name']))
                    progress.update(fetch_task, advance=1)
                    
    return files


def _find_local_data(period: str) -> List[Tuple[Path, str, str]]:
    """Find local CSV files for analysis."""
    config = get_config()
    data_dir = config.raw_data_dir
    suffix = "daily" if period == "daily" else "60min"
    
    files = []
    for f in data_dir.glob(f"*_{suffix}.csv"):
        parts = f.stem.split("_")
        if len(parts) >= 2:
            files.append((f, parts[0], parts[1]))
    return files


def _display_top_signals(results, top_n=10):
    """Display top signals in a beautiful table."""
    # Filter and sort
    signals = [r for r in results if r.success and r.signal and r.signal.is_actionable]
    signals.sort(key=lambda x: x.signal.signal_strength, reverse=True)
    
    if not signals:
        console.print("\n[yellow]No strong signals found today.[/yellow]")
        return

    table = Table(title=f"Top {top_n} SMC Buy Signals", title_style="bold green")
    table.add_column("Symbol", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Strength", justify="right", style="bold green")
    table.add_column("Confidence", justify="right")
    table.add_column("Win Rate", justify="right")
    table.add_column("R:R", justify="right")
    table.add_column("Entry", style="yellow")
    table.add_column("Stop", style="red")
    table.add_column("Target", style="green")

    for r in signals[:top_n]:
        sig = r.signal
        table.add_row(
            sig.symbol,
            sig.name,
            f"{sig.signal_strength:.1f}",
            f"{sig.confidence:.1f}",
            f"{sig.estimated_win_rate:.1f}%",
            f"{sig.risk_reward_ratio:.2f}",
            f"{sig.entry_price:.2f}",
            f"{sig.stop_loss:.2f}",
            f"{sig.take_profit_1:.2f}",
        )

    console.print("\n")
    console.print(table)


if __name__ == "__main__":
    app()
