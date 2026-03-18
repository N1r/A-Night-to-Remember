#!/usr/bin/env python3
"""
SMC 一键分析脚本 V2
===================

自动获取 A 股和港股行情，多线程获取历史 K 线，
并调用向量化 SMC 引擎进行全市场扫描，生成交易信号报告。

Usage:
    python one_click_v2.py             # 完整扫描 (默认 A股500, 港股200)
    python one_click_v2.py -a 50 -k 20 # 快速扫描
    python one_click_v2.py --force     # 强制从网络更新所有数据
    python one_click_v2.py --skip-fetch # 跳过数据获取，只进行分析
"""
import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple

import akshare as ak
import numpy as np
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeElapsedColumn
from rich.table import Table

# 添加 src 路径到系统路径
sys.path.insert(0, str(Path(__file__).parent))

from src.config import get_config
from src.core.types import ZoneType
from src.orchestrator import SMCOrchestrator, OrchestratorConfig

console = Console()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 数据获取
# ---------------------------------------------------------------------------

def _clean_name(name: str) -> str:
    """清理股票名称中的特殊字符."""
    for ch in ['<', '>', ':', '"', '/', '\\', '|', '?', '*']:
        name = name.replace(ch, '_')
    return name.strip()


def _existing_raw_files(raw_dir: Path) -> Dict[str, Path]:
    """扫描 raw 目录，建立 代码 -> 文件 的映射."""
    mapping = {}
    for f in raw_dir.glob("*.csv"):
        code = f.stem.split('_')[0]
        mapping[code] = f
    return mapping


def fetch_a_spot(top_n: int) -> pd.DataFrame:
    """获取 A 股实时行情并按成交额排序，取前 N 名."""
    console.print(f"[cyan]获取A股实时行情榜单 (成交额 Top {top_n})...[/cyan]")
    try:
        df = ak.stock_zh_a_spot_em()
        if df is None or df.empty:
            return pd.DataFrame()
        # 按成交额降序
        df = df.sort_values("成交额", ascending=False).head(top_n)
        return df[['代码', '名称']].reset_index(drop=True)
    except Exception as e:
        console.print(f"[red]获取A股榜单失败: {e}[/red]")
        return pd.DataFrame()


def fetch_a_history_batch(
    stocks: pd.DataFrame, raw_dir: Path, force: bool = False,
) -> Tuple[int, int, int]:
    """批量获取 A 股历史日线 K 线."""
    existing = _existing_raw_files(raw_dir)
    success, skipped, failed = 0, 0, 0
    errors = []

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), TaskProgressColumn(), TimeElapsedColumn(), console=console,
    ) as progress:
        task = progress.add_task("[cyan]获取A股历史数据...", total=len(stocks))

        for _, row in stocks.iterrows():
            code = str(row['代码']).zfill(6)
            name = _clean_name(str(row['名称']))
            
            if not force and code in existing:
                skipped += 1
                progress.advance(task)
                continue

            try:
                df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
                if df is not None and not df.empty and len(df) >= 50:
                    filepath = raw_dir / f"{code}_{name}.csv"
                    df.to_csv(filepath, index=False, encoding="utf-8-sig")
                    success += 1
                else:
                    failed += 1
                    errors.append((code, "数据为空或条数不足"))
            except Exception as e:
                failed += 1
                errors.append((code, str(e)))

            progress.advance(task)
            time.sleep(0.1)

    _print_fetch_summary("A股", success, skipped, failed, errors)
    return success, skipped, failed


def get_hk_stock_list(top_n: int) -> List[Tuple[str, str]]:
    """获取港股主板列表 (市值前 N)."""
    console.print(f"[cyan]获取港股实时列表 (市值 Top {top_n})...[/cyan]")
    try:
        df = ak.stock_hk_spot_em()
        if df is None or df.empty:
            return []
        # 港股市值列名可能是 "总市值"
        mkt_col = "总市值" if "总市值" in df.columns else "市值"
        if mkt_col in df.columns:
            df = df.sort_values(mkt_col, ascending=False).head(top_n)
        else:
            df = df.head(top_n)
        
        results = []
        for _, row in df.iterrows():
            results.append((str(row['代码']), _clean_name(str(row['名称']))))
        return results
    except Exception as e:
        console.print(f"[red]获取港股列表失败: {e}[/red]")
        return []


def fetch_hk_history_batch(
    hk_list: List[Tuple[str, str]], raw_dir: Path, force: bool = False,
) -> Tuple[int, int, int]:
    """批量获取港股历史日线 K 线."""
    existing = _existing_raw_files(raw_dir)
    success, skipped, failed = 0, 0, 0
    errors = []

    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), TaskProgressColumn(), TimeElapsedColumn(), console=console,
    ) as progress:
        task = progress.add_task("[magenta]获取港股历史数据...", total=len(hk_list))

        for code, name in hk_list:
            if not force and code in existing:
                skipped += 1
                progress.advance(task)
                continue

            try:
                df = ak.stock_hk_hist(symbol=code, period="daily", adjust="qfq")
                if df is not None and not df.empty and len(df) >= 50:
                    filepath = raw_dir / f"{code}_{name}.csv"
                    df.to_csv(filepath, index=False, encoding="utf-8-sig")
                    success += 1
                else:
                    failed += 1
                    errors.append((code, "数据为空或条数不足"))
            except Exception as e:
                failed += 1
                errors.append((code, str(e)))

            progress.advance(task)
            time.sleep(0.1)

    _print_fetch_summary("港股", success, skipped, failed, errors)
    return success, skipped, failed


def _print_fetch_summary(market: str, success: int, skipped: int, failed: int, errors: List):
    """打印获取结果汇总."""
    total = success + skipped + failed
    console.print(f"[green]✓ {market}: 新获取 {success}, 跳过 {skipped}, 失败 {failed} (总数 {total})[/green]")
    if errors:
        unique_errors = {}
        for code, msg in errors:
            unique_errors.setdefault(msg, []).append(code)
        for msg, codes in list(unique_errors.items())[:5]:
            codes_str = ", ".join(codes[:5]) + (f"...等{len(codes)}只" if len(codes) > 5 else "")
            console.print(f"  [red]错误: {msg}[/red] ({codes_str})")


def batch_convert_to_smc(raw_dir: Path, processed_dir: Path):
    """批量将 raw CSV 转为 SMC 可识别格式."""
    from src.data_fetch.base import batch_convert_to_smc as convert_func
    convert_func(raw_dir, processed_dir)


# ---------------------------------------------------------------------------
# 分析 + 报告
# ---------------------------------------------------------------------------

def analyze_all(
    processed_dir: Path, orchestrator: SMCOrchestrator, generate_charts: bool = True,
) -> Tuple[List, List]:
    """分析所有 processed 数据，分 A股/港股返回."""
    csv_files = sorted(processed_dir.glob("*_smc.csv"))
    if not csv_files:
        csv_files = sorted(processed_dir.glob("*.csv"))
    if not csv_files:
        console.print("[red]没有找到处理后的数据文件[/red]")
        return [], []

    a_files, hk_files = [], []
    for f in csv_files:
        code = f.stem.split('_')[0]
        if len(code) == 6 and code.isdigit():
            a_files.append(f)
        elif len(code) == 5 and code.startswith("0"):
            hk_files.append(f)

    a_results = _run_analysis(a_files, "A股", orchestrator, generate_charts)
    hk_results = _run_analysis(hk_files, "港股", orchestrator, generate_charts)
    return a_results, hk_results


def _run_analysis(
    files: List[Path], market: str, orchestrator: SMCOrchestrator, generate_charts: bool,
) -> List:
    if not files:
        return []
    results = []
    with Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), TaskProgressColumn(), TimeElapsedColumn(), console=console,
    ) as progress:
        task = progress.add_task(f"[cyan]分析{market}...", total=len(files))
        for f in files:
            parts = f.stem.replace("_smc", "").replace("_daily", "").split("_")
            symbol = parts[0] if parts else "UNKNOWN"
            name = parts[1] if len(parts) > 1 else ""
            progress.update(task, description=f"[cyan]{market} {symbol} {name[:6]}...")
            try:
                df = pd.read_csv(f)
                result = orchestrator.analyze(df, symbol, name, generate_chart=generate_charts)
                results.append(result)
            except Exception as e:
                logger.error(f"分析失败 {symbol}: {e}")
            progress.advance(task)

    results.sort(key=lambda x: x.signal.signal_strength if x.signal else 0, reverse=True)
    return results


def display_signals(results: List, market: str):
    actionable = [r for r in results if r.signal and r.signal.is_actionable]
    if not actionable:
        return
    table = Table(title=f"[bold]{market} 做多信号 (Top 20)[/bold]")
    for col, w in [("代码", 8), ("名称", 10), ("强度", 6), ("胜率", 6),
                   ("区域", 6), ("入场", 8), ("止损", 8), ("目标", 8)]:
        table.add_column(col, width=w, justify="right" if w <= 8 and col != "代码" and col != "区域" else "left")
    for r in actionable[:20]:
        s = r.signal
        zone = "折价" if s.zone == ZoneType.DISCOUNT else "溢价" if s.zone == ZoneType.PREMIUM else "平衡"
        table.add_row(r.symbol, r.name[:10], f"{s.signal_strength:.0f}", f"{s.estimated_win_rate:.0f}%",
                      zone, f"{s.entry_price:.2f}", f"{s.stop_loss:.2f}", f"{s.take_profit_1:.2f}")
    console.print(table)


def display_summary(a_results: List, hk_results: List):
    def stats(results):
        act = [r for r in results if r.signal and r.signal.is_actionable]
        avg = np.mean([r.signal.signal_strength for r in act]) if act else 0
        return len(results), len(act), avg

    a_total, a_act, a_avg = stats(a_results)
    hk_total, hk_act, hk_avg = stats(hk_results)
    console.print(Panel(
        f"[cyan]A股:[/cyan]  总数 {a_total} | 做多信号 {a_act} | 平均强度 {a_avg:.1f}\n"
        f"[magenta]港股:[/magenta]  总数 {hk_total} | 做多信号 {hk_act} | 平均强度 {hk_avg:.1f}",
        title="[bold green]分析完成[/bold green]", border_style="green",
    ))


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def _start_web(port: int = 8080) -> int:
    """启动 Web 界面."""
    console.print(Panel.fit(
        f"[bold cyan]SMC Web 界面[/bold cyan]\n"
        f"[dim]http://localhost:{port}[/dim]",
        border_style="green",
    ))
    from src.web.app import run_app
    run_app(port=port)
    return 0


def main():
    parser = argparse.ArgumentParser(description="SMC 一键分析 V2")
    parser.add_argument("--a-stocks", "-a", type=int, default=800, help="A股数量")
    parser.add_argument("--hk-stocks", "-k", type=int, default=300, help="港股数量")
    parser.add_argument("--force", "-f", action="store_true", help="强制重新获取")
    parser.add_argument("--skip-fetch", action="store_true", help="跳过数据获取")
    parser.add_argument("--no-charts", action="store_true", help="不生成图表")
    parser.add_argument("--web", "-w", action="store_true", help="分析完成后启动 Web 界面")
    parser.add_argument("--port", "-p", type=int, default=8080, help="Web 端口 (默认 8080)")
    args = parser.parse_args()

    # 仅启动 Web（不跑分析）
    if args.web and args.skip_fetch and not any([args.force]):
        return _start_web(args.port)

    config = get_config()
    config.ensure_directories()
    raw_dir = config.raw_data_dir
    processed_dir = config.processed_data_dir

    orch = SMCOrchestrator(OrchestratorConfig(
        data_dir=raw_dir, output_dir=config.output_dir,
        charts_dir=config.charts_dir, reports_dir=config.reports_dir,
    ))

    t0 = time.time()
    console.print(Panel.fit(
        f"[bold cyan]SMC 一键分析 V2[/bold cyan]\n"
        f"[dim]A股: {args.a_stocks} | 港股: {args.hk_stocks}[/dim]",
        title="[bold green]开始[/bold green]", border_style="green",
    ))

    try:
        # ---- 1. 数据获取 ----
        if not args.skip_fetch:
            # A股
            console.print(Panel("[bold cyan]A股数据获取[/bold cyan]", border_style="blue"))
            a_spot = fetch_a_spot(args.a_stocks)
            if not a_spot.empty:
                fetch_a_history_batch(a_spot, raw_dir, force=args.force)
            else:
                console.print("[yellow]A股行情为空，跳过历史数据获取[/yellow]")

            # 港股
            console.print(Panel("[bold cyan]港股数据获取[/bold cyan]", border_style="magenta"))
            hk_list = get_hk_stock_list(args.hk_stocks)
            console.print(f"[dim]港股列表: {len(hk_list)} 只[/dim]")
            fetch_hk_history_batch(hk_list, raw_dir, force=args.force)
        else:
            console.print("[yellow]跳过数据获取[/yellow]")

        # ---- 2. 数据转换 ----
        console.print(Panel("[bold cyan]数据格式转换[/bold cyan]", border_style="blue"))
        batch_convert_to_smc(raw_dir, processed_dir)

        # ---- 3. 分析 ----
        console.print(Panel("[bold cyan]SMC 分析[/bold cyan]", border_style="green"))
        a_results, hk_results = analyze_all(processed_dir, orch, generate_charts=not args.no_charts)

        # ---- 4. 报告 ----
        console.print(Panel("[bold cyan]生成报告[/bold cyan]", border_style="yellow"))
        all_results = a_results + hk_results
        report_path = orch.generate_report(all_results)

        display_signals(a_results, "A股")
        display_signals(hk_results, "港股")
        display_summary(a_results, hk_results)

        elapsed = time.time() - t0
        console.print(f"\n[green]✓ 全部完成! 耗时: {elapsed:.1f}秒[/green]")
        console.print(f"[cyan]报告: {report_path}[/cyan]")

        if args.web:
            return _start_web(args.port)
        else:
            console.print(f"[dim]提示: 运行 python one_click_v2.py --web 启动 Web 查看结果[/dim]")
        return 0

    except Exception as e:
        console.print(f"[red]执行失败: {e}[/red]")
        console.print_exception(show_locals=False)
        return 1


if __name__ == "__main__":
    sys.exit(main())
