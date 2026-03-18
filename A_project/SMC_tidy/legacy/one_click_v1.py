#!/usr/bin/env python3
"""
SMC Unified Analysis (V1)
=========================

Combines V2 (Daily) and V3 (Intraday) analysis to find high-conviction LONG signals
that appear on BOTH timeframes simultaneously.
"""
import argparse
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent))

from src.config import get_config
from src.orchestrator import SMCOrchestrator, OrchestratorConfig
from one_click_v2 import fetch_a_spot, fetch_a_history_batch, get_hk_stock_list, fetch_hk_history_batch, analyze_all as v2_run_analysis, batch_convert_to_smc as convert_raw_to_smc
from one_click_v3 import IntradayOrchestrator, run_analysis as v3_run_analysis, fetch_a_spot_top, fetch_a_intraday_batch, fetch_hk_intraday_batch, convert_intraday_to_smc

console = Console()

V3_DATA_DIR = Path("data/intraday")
V3_CHARTS_DIR = Path("output/intraday/charts")
V3_REPORTS_DIR = Path("output/intraday/reports")

def main():
    parser = argparse.ArgumentParser(description="SMC Unified Analysis (Daily + 60min)")
    parser.add_argument("--a-stocks", "-a", type=int, default=800, help="Number of A-shares to check")
    parser.add_argument("--hk-stocks", "-k", type=int, default=300, help="Number of HK-shares to check")
    parser.add_argument("--force", "-f", action="store_true", help="Force fetch data")
    parser.add_argument("--skip-fetch", action="store_true", help="Skip data fetch")
    args = parser.parse_args()

    config = get_config()
    config.ensure_directories()
    raw_dir = config.raw_data_dir
    processed_dir = config.processed_data_dir

    V3_DATA_DIR.mkdir(parents=True, exist_ok=True)
    V3_CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    V3_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    console.print(Panel.fit(
        "[bold cyan]SMC V1 Unified Analysis (LongTerm + ShortTerm)[/bold cyan]\n"
        "Finding confluence between Daily and 60min SMC signals.",
        border_style="green"
    ))

    t0 = time.time()

    if not args.skip_fetch:
        console.print("[cyan]Fetching Daily Data...[/cyan]")
        a_spot = fetch_a_spot(args.a_stocks)
        if not a_spot.empty:
            fetch_a_history_batch(a_spot, raw_dir, force=args.force)
        hk_list = get_hk_stock_list(args.hk_stocks)
        fetch_hk_history_batch(hk_list, raw_dir, force=args.force)

        console.print("[cyan]Fetching 60min Intraday Data...[/cyan]")
        a_spot_top = fetch_a_spot_top(args.a_stocks)
        if not a_spot_top.empty:
            fetch_a_intraday_batch(a_spot_top, V3_DATA_DIR, "60", force=args.force)
        fetch_hk_intraday_batch(hk_list, V3_DATA_DIR, "60", force=args.force)

    console.print("[cyan]Running Conversions...[/cyan]")
    convert_raw_to_smc(raw_dir, processed_dir)
    convert_intraday_to_smc(V3_DATA_DIR, "60min")

    console.print("[cyan]Running V2 (Daily) Analysis (Logic Only)...[/cyan]")
    orch_v2 = SMCOrchestrator(OrchestratorConfig(
        data_dir=raw_dir, output_dir=config.output_dir,
        charts_dir=config.charts_dir, reports_dir=config.reports_dir,
    ))
    v2_a_res, v2_hk_res = v2_run_analysis(processed_dir, orch_v2, generate_charts=False)

    console.print("[cyan]Running V3 (60min) Analysis (Logic Only)...[/cyan]")
    orch_v3 = IntradayOrchestrator(V3_CHARTS_DIR, V3_REPORTS_DIR)
    v3_a_res, v3_hk_res = v3_run_analysis(V3_DATA_DIR, orch_v3, "60min", "60min", generate_charts=False)

    # Intersection Logic
    def find_confluence(v2_results, v3_results):
        v2_map = {r.symbol: r for r in v2_results if r.signal and r.signal.is_actionable and r.signal.direction == "long"}
        v3_map = {r.symbol: r for r in v3_results if r.signal and r.signal.is_actionable and r.signal.direction == "long"}

        confluence = []
        for sym, r_v2 in v2_map.items():
            if sym in v3_map:
                confluence.append({
                    "symbol": sym,
                    "name": r_v2.name,
                    "v2_strength": r_v2.signal.signal_strength,
                    "v3_strength": v3_map[sym].signal.signal_strength,
                    "average_strength": (r_v2.signal.signal_strength + v3_map[sym].signal.signal_strength) / 2
                })
        
        return sorted(confluence, key=lambda x: x["average_strength"], reverse=True)

    a_confluence = find_confluence(v2_a_res, v3_a_res)
    hk_confluence = find_confluence(v2_hk_res, v3_hk_res)

    def generate_top_charts(confluence_list, p_dir, v3_dir, orch2, orch3):
        if not confluence_list:
            return
        
        import pandas as pd
        top_20 = confluence_list[:20]
        console.print(f"[cyan]Generating detailed charts for Top {len(top_20)} Confluence Signals...[/cyan]")
        
        for item in top_20:
            sym = item['symbol']
            name = item['name']
            
            # Find V2 File
            v2_files = list(p_dir.glob(f"{sym}_*_smc.csv"))
            if v2_files:
                df_v2 = pd.read_csv(v2_files[0])
                orch2.analyze(df_v2, sym, name, generate_chart=True)
            
            # Find V3 File
            v3_files = list(v3_dir.glob(f"{sym}_*60min_smc.csv"))
            if v3_files:
                df_v3 = pd.read_csv(v3_files[0])
                orch3.analyze(df_v3, sym, name, "60min", generate_chart=True)

    generate_top_charts(a_confluence, processed_dir, V3_DATA_DIR, orch_v2, orch_v3)
    generate_top_charts(hk_confluence, processed_dir, V3_DATA_DIR, orch_v2, orch_v3)

    def display_confluence(items, market):
        if not items:
            console.print(f"[yellow]No {market} confluence signals found.[/yellow]")
            return
        table = Table(title=f"[bold]{market} UNIFIED CONFIRMED LONG (Daily + 60min)[/bold]")
        table.add_column("Symbol")
        table.add_column("Name")
        table.add_column("Daily Strength", style="green")
        table.add_column("60min Strength", style="blue")
        table.add_column("Avg Strength", style="yellow", justify="right")
        
        for item in items:
            table.add_row(
                item["symbol"], item["name"],
                f"{item['v2_strength']:.0f}",
                f"{item['v3_strength']:.0f}",
                f"{item['average_strength']:.1f}"
            )
        console.print(table)

    console.print("\n")
    display_confluence(a_confluence, "A-Share")
    console.print("\n")
    display_confluence(hk_confluence, "HK-Share")

    console.print(f"\n[green]✓ Unified Analysis Completed in {time.time() - t0:.1f}s[/green]")
    console.print("[dim]Note: HTML charts only generated for the Top 20 confluence symbols.[/dim]")

if __name__ == "__main__":
    sys.exit(main())
