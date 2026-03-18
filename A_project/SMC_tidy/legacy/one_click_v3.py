#!/usr/bin/env python3
"""
SMC 短线分析脚本 V3
===================

基于 30 分钟和 60 分钟 K 线的短线做多策略。
数据来源: akshare 分钟级接口 (近 30 个交易日)。

Usage:
    python one_click_v3.py                          # 完整流程 (A股800 + 港股300)
    python one_click_v3.py -a 10 -k 10             # 小样本
    python one_click_v3.py --skip-fetch             # 跳过获取，分析已有数据
    python one_click_v3.py --period 30              # 仅用 30 分钟
    python one_click_v3.py --period 60              # 仅用 60 分钟 (默认)
    python one_click_v3.py --web                    # 分析后启动 Web
"""
import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple, Any

import akshare as ak
import numpy as np
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn, MofNCompleteColumn, Progress, SpinnerColumn,
    TaskProgressColumn, TextColumn, TimeElapsedColumn,
)
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent))

from src.config import get_config
from src.core.engine import VectorizedSMCEngine, EngineConfig
from src.core.signals import SignalGenerator, RiskManager
from src.core.visualizer import PremiumChartBuilder
from src.core.types import ZoneType, AnalysisOutput
from src.orchestrator import OrchestratorConfig, AnalysisResult

console = Console()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("smc_v3.log", encoding="utf-8", mode="w"),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 短线专用引擎参数 (较小的 swing length 适配分钟级数据)
# ---------------------------------------------------------------------------
INTRADAY_ENGINE_CONFIG = EngineConfig(
    swing_length=15,
    swing_left=5,
    swing_right=5,
    ob_lookback=60,
    close_mitigation=True,
    ob_overlap_candles=2,
)

# ---------------------------------------------------------------------------
# 数据目录 (独立于 V2 的 daily 数据)
# ---------------------------------------------------------------------------
V3_DATA_DIR = Path("data/intraday")
V3_OUTPUT_DIR = Path("output/intraday")
V3_CHARTS_DIR = V3_OUTPUT_DIR / "charts"
V3_REPORTS_DIR = V3_OUTPUT_DIR / "reports"

def _clean_name(name: str) -> str:
    for ch in '<>:"/\\|?*':
        name = name.replace(ch, "_")
    return name.strip()


def _existing_files(data_dir: Path, suffix: str) -> Dict[str, Path]:
    mapping = {}
    for f in data_dir.glob(f"*_{suffix}.csv"):
        code = f.stem.split("_")[0]
        mapping[code] = f
    return mapping


# ---------------------------------------------------------------------------
# 分钟数据获取
# ---------------------------------------------------------------------------

def fetch_a_spot_top(top_n: int) -> pd.DataFrame:
    """获取 A 股成交额前 N 的代码和名称."""
    console.print(f"[cyan]获取A股实时行情榜单 (成交额 Top {top_n})...[/cyan]")
    try:
        df = ak.stock_zh_a_spot_em()
        if not isinstance(df, pd.DataFrame) or df.empty:
            console.print("[red]A股行情返回为空[/red]")
            return pd.DataFrame()
        stocks = df.nlargest(top_n, "成交额")[["代码", "名称"]].copy()
        stocks["代码"] = stocks["代码"].astype(str).str.zfill(6)
        return stocks.reset_index(drop=True)
    except Exception as e:
        console.print(f"[red]A股行情获取失败: {e}[/red]")
        return pd.DataFrame()


def fetch_a_intraday_batch(
    stocks: pd.DataFrame, data_dir: Path, period: str, force: bool = False,
) -> Tuple[int, int, int]:
    """获取 A 股分钟级数据."""
    suffix = f"{period}min"
    existing = _existing_files(data_dir, suffix)
    success, skipped, failed = 0, 0, 0
    errors = []

    with _progress_bar(f"A股 {period}分钟数据", len(stocks)) as (progress, task):
        for _, row in stocks.iterrows():
            code = str(row["代码"]).zfill(6)
            name = _clean_name(str(row["名称"]))

            if not force and code in existing:
                skipped += 1
                progress.advance(task)
                continue

            try:
                df = ak.stock_zh_a_hist_min_em(symbol=code, period=period, adjust="qfq")
                if df is not None and not df.empty and len(df) >= 50:
                    filepath = data_dir / f"{code}_{name}_{suffix}.csv"
                    df.to_csv(filepath, index=False, encoding="utf-8-sig")
                    success += 1
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                errors.append((code, str(e)[:80]))

            progress.advance(task)
            time.sleep(0.1)

    return success, skipped, failed


def fetch_hk_intraday_batch(
    hk_stocks: List[Tuple[str, str]], data_dir: Path, period: str, force: bool = False,
) -> Tuple[int, int, int]:
    """获取港股分钟级数据."""
    suffix = f"{period}min"
    existing = _existing_files(data_dir, suffix)
    success, skipped, failed = 0, 0, 0
    errors = []

    with _progress_bar(f"港股 {period}分钟数据", len(hk_stocks)) as (progress, task):
        for code, name in hk_stocks:
            code = code.zfill(5)
            clean = _clean_name(name)

            if not force and code in existing:
                skipped += 1
                progress.advance(task)
                continue

            try:
                df = ak.stock_hk_hist_min_em(symbol=code, period=period, adjust="qfq")
                if df is not None and not df.empty and len(df) >= 50:
                    filepath = data_dir / f"{code}_{clean}_{suffix}.csv"
                    df.to_csv(filepath, index=False, encoding="utf-8-sig")
                    success += 1
                else:
                    failed += 1
            except Exception as e:
                failed += 1
                errors.append((code, str(e)[:80]))

            progress.advance(task)
            time.sleep(0.1)

    return success, skipped, failed


def convert_intraday_to_smc(data_dir: Path, suffix: str) -> int:
    """将分钟级 CSV 转为 SMC 标准格式."""
    csv_files = sorted(data_dir.glob(f"*_{suffix}.csv"))
    if not csv_files:
        return 0

    converted = 0
    for f in csv_files:
        if f.stem.endswith("_smc"):
            continue
        out = data_dir / f"{f.stem}_smc.csv"
        try:
            df = pd.read_csv(f)
            col_map = {
                "时间": "timestamp", "开盘": "open", "收盘": "close",
                "最高": "high", "最低": "low", "成交量": "volume", "成交额": "amount",
            }
            df.rename(columns=col_map, inplace=True)
            required = ["open", "high", "low", "close", "volume"]
            if not all(c in df.columns for c in required):
                continue
            for c in required:
                df[c] = pd.to_numeric(df[c], errors="coerce")
            df = df.dropna(subset=required)
            if len(df) < 50:
                continue
            cols_out = (["timestamp"] if "timestamp" in df.columns else []) + required
            df = df.reset_index(drop=True)
            df[cols_out].to_csv(out, index=False)
            converted += 1
        except Exception as e:
            logger.error(f"转换失败 {f.name}: {e}")

    return converted


# ---------------------------------------------------------------------------
# 分析 (使用短线引擎参数)
# ---------------------------------------------------------------------------

class IntradayOrchestrator:
    """短线分析专用调度器，使用小窗口引擎参数."""

    def __init__(self, charts_dir: Path, reports_dir: Path):
        self.engine = VectorizedSMCEngine(INTRADAY_ENGINE_CONFIG)
        self.signal_gen = SignalGenerator(RiskManager(
            account_size=100000, risk_per_trade=0.02, max_position_pct=0.10,
        ))
        self.chart_builder = PremiumChartBuilder()
        self.charts_dir = charts_dir
        self.reports_dir = reports_dir
        self.charts_dir.mkdir(parents=True, exist_ok=True)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def analyze(
        self, df: pd.DataFrame, symbol: str, name: str, timeframe: str,
        generate_chart: bool = True,
    ) -> AnalysisResult:
        start = time.perf_counter()
        result = AnalysisResult(symbol=symbol, name=name)
        try:
            output = self.engine.analyze(df, symbol=symbol, timeframe=timeframe)
            result.output = output
            signal = self.signal_gen.generate(output, symbol=symbol, name=name)
            result.signal = signal
            if generate_chart:
                chart_path = self.charts_dir / f"{symbol}_{_clean_name(name)}_{timeframe}_chart.html"
                fig = self.chart_builder.build(
                    df, output, signal,
                    title=f"{symbol} {name} ({timeframe})",
                    height=800, show_volume=True,
                )
                self.chart_builder.save(fig, chart_path)
                result.chart_path = chart_path
            result.success = True
        except Exception as e:
            result.success = False
            result.error_message = str(e)
            logger.error(f"分析失败 {symbol} ({timeframe}): {e}")
        result.computation_time_ms = (time.perf_counter() - start) * 1000
        return result

    def generate_report(self, results: List[AnalysisResult], timeframe: str) -> Path:
        data = []
        for r in results:
            if r.success and r.signal and r.signal.is_actionable:
                s = r.signal
                data.append({
                    "代码": r.symbol, "名称": r.name,
                    "信号类型": s.direction, "信号强度": round(s.signal_strength, 1),
                    "置信度": round(s.confidence, 1),
                    "预估胜率": f"{s.estimated_win_rate:.1f}%",
                    "盈亏比": round(s.risk_reward_ratio, 2),
                    "入场价": round(s.entry_price, 2),
                    "止损价": round(s.stop_loss, 2),
                    "目标1": round(s.take_profit_1, 2),
                    "目标2": round(s.take_profit_2, 2),
                    "OB重叠度": f"{s.ob_overlap_score:.0f}%",
                    "融合因素": "; ".join(s.confluence_factors),
                })
        df = pd.DataFrame(data)
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        path = self.reports_dir / f"smc_v3_{timeframe}_{ts}.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as w:
            df.to_excel(w, sheet_name="信号汇总", index=False)
        return path


def run_analysis(
    data_dir: Path, orch: IntradayOrchestrator, suffix: str,
    timeframe: str, generate_charts: bool,
) -> Tuple[List, List]:
    """分析分钟级 SMC 数据."""
    smc_files = sorted(data_dir.glob(f"*_{suffix}_smc.csv"))
    if not smc_files:
        return [], []

    a_files, hk_files = [], []
    for f in smc_files:
        code = f.stem.split("_")[0]
        if len(code) == 6 and code.isdigit():
            a_files.append(f)
        elif len(code) == 5 and code.startswith("0"):
            hk_files.append(f)

    a_results = _analyze_files(a_files, f"A股({timeframe})", orch, timeframe, generate_charts)
    hk_results = _analyze_files(hk_files, f"港股({timeframe})", orch, timeframe, generate_charts)
    return a_results, hk_results


def _analyze_files(
    files: List[Path], label: str, orch: IntradayOrchestrator,
    timeframe: str, generate_charts: bool,
) -> List:
    if not files:
        return []
    results = []
    with _progress_bar(f"分析{label}", len(files)) as (progress, task):
        for f in files:
            stem_clean = f.stem.replace("_smc", "")
            idx = stem_clean.rfind(f"_{timeframe}")
            if idx > 0:
                base = stem_clean[:idx]
            else:
                base = stem_clean
            parts = base.split("_", 1)
            symbol = parts[0]
            name = parts[1] if len(parts) > 1 else ""

            try:
                df = pd.read_csv(f)
                r = orch.analyze(df, symbol, name, timeframe, generate_chart=generate_charts)
                results.append(r)
            except Exception as e:
                logger.error(f"分析失败 {symbol}: {e}")
            progress.advance(task)

    results.sort(key=lambda x: x.signal.signal_strength if x.signal else 0, reverse=True)
    return results


def display_signals(results: List, label: str):
    actionable = [r for r in results if r.signal and r.signal.is_actionable]
    if not actionable:
        return
    table = Table(title=f"[bold]{label} 短线做多信号 (Top 20)[/bold]")
    for col in ["代码", "名称", "强度", "胜率", "区域", "入场", "止损", "目标"]:
        table.add_column(col, width=8)
    for r in actionable[:20]:
        s = r.signal
        zone = "折价" if s.zone == ZoneType.DISCOUNT else "溢价" if s.zone == ZoneType.PREMIUM else "平衡"
        table.add_row(r.symbol, r.name[:8], f"{s.signal_strength:.0f}", f"{s.estimated_win_rate:.0f}%",
                      zone, f"{s.entry_price:.2f}", f"{s.stop_loss:.2f}", f"{s.take_profit_1:.2f}")
    console.print(table)


def display_summary(a_results: List, hk_results: List, timeframe: str):
    def stats(results):
        act = [r for r in results if r.signal and r.signal.is_actionable]
        avg = np.mean([r.signal.signal_strength for r in act]) if act else 0
        return len(results), len(act), avg
    a_t, a_a, a_v = stats(a_results)
    hk_t, hk_a, hk_v = stats(hk_results)
    console.print(Panel(
        f"[bold]{timeframe} 短线分析[/bold]\n"
        f"[cyan]A股:[/cyan]  总数 {a_t} | 做多信号 {a_a} | 平均强度 {a_v:.1f}\n"
        f"[magenta]港股:[/magenta]  总数 {hk_t} | 做多信号 {hk_a} | 平均强度 {hk_v:.1f}",
        title="[bold green]完成[/bold green]", border_style="green",
    ))


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def _progress_bar(label, total):
    p = Progress(
        SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
        BarColumn(), MofNCompleteColumn(), TaskProgressColumn(), TimeElapsedColumn(),
        console=console,
    )
    p.start()
    task = p.add_task(f"[cyan]{label}...", total=total)

    class _Ctx:
        def __enter__(self_):
            return p, task
        def __exit__(self_, *a):
            p.stop()

    return _Ctx()


def _start_web(port: int) -> int:
    console.print(Panel.fit(
        f"[bold cyan]SMC V3 短线 Web[/bold cyan]\n[dim]http://localhost:{port}[/dim]",
        border_style="green",
    ))
    from src.web.app import run_app as _run_web
    _setup_v3_web()
    _run_web(port=port)
    return 0


def _setup_v3_web():
    """让 web app 能读取 v3 的 intraday 目录."""
    from src.config import get_config
    config = get_config()
    config._v3_charts_dir = V3_CHARTS_DIR
    config._v3_reports_dir = V3_REPORTS_DIR

    import sys
    import src.web.app as web_module
    # Use sys.modules to avoid shadowing
    web_mod = sys.modules['src.web.app']
    original_setup = web_mod.setup_app

    def patched_setup():
        from fastapi.staticfiles import StaticFiles
        from fastapi.responses import HTMLResponse
        fa = web_mod.app

        V3_CHARTS_DIR.mkdir(parents=True, exist_ok=True)
        V3_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

        fa.mount("/static/charts", StaticFiles(directory=str(V3_CHARTS_DIR)), name="charts_static")
        fa.mount("/static/reports", StaticFiles(directory=str(V3_REPORTS_DIR)), name="reports_static")

        original_load = web_mod._load_top_signals

        def v3_load(reports_dir, charts_dir):
            report_files = sorted(V3_REPORTS_DIR.glob("smc_v3_*.xlsx"), key=lambda f: f.stat().st_mtime, reverse=True)
            if not report_files:
                return original_load(reports_dir, charts_dir)
            try:
                df = pd.read_excel(report_files[0], sheet_name="信号汇总")
            except Exception:
                return original_load(reports_dir, charts_dir)
            if "信号类型" not in df.columns:
                return original_load(reports_dir, charts_dir)
            df = df[df["信号类型"] == "long"].copy()
            df = df.sort_values("信号强度", ascending=False).head(20)
            results = []
            for _, row in df.iterrows():
                code = str(row["代码"])
                if code.isdigit() and len(code) <= 6:
                    code = code.zfill(6)
                name = str(row["名称"])
                chart_file = web_mod._find_chart(V3_CHARTS_DIR, code, name)
                results.append({
                    "code": code, "name": name,
                    "strength": float(row["信号强度"]),
                    "confidence": float(row["置信度"]),
                    "win_rate": str(row["预估胜率"]),
                    "rr": float(row["盈亏比"]),
                    "entry": float(row["入场价"]),
                    "stop": float(row["止损价"]),
                    "tp1": float(row["目标1"]),
                    "tp2": float(row["目标2"]),
                    "ob_overlap": str(row.get("OB重叠度", "")),
                    "confluence": str(row.get("融合因素", "")),
                    "chart_filename": chart_file.name if chart_file else None,
                    "report_file": report_files[0].name,
                })
            return results

        web_mod._load_top_signals = v3_load

        @fa.get("/", response_class=HTMLResponse)
        async def index():
            signals = v3_load(V3_REPORTS_DIR, V3_CHARTS_DIR)
            with_chart = sum(1 for s in signals if s["chart_filename"])
            avg_str = sum(s["strength"] for s in signals) / len(signals) if signals else 0
            report_name = signals[0]["report_file"] if signals else "N/A"

            stats_html = f'''<div class="stats">
                <div class="stat-box"><div class="val" style="color:{web_mod.GREEN}">{len(signals)}</div><div class="lbl">短线买入信号</div></div>
                <div class="stat-box"><div class="val" style="color:{web_mod.BLUE}">{with_chart}</div><div class="lbl">有图表</div></div>
                <div class="stat-box"><div class="val" style="color:{web_mod.YELLOW}">{avg_str:.0f}</div><div class="lbl">平均强度</div></div>
            </div>'''
            # Simple placeholder for the rest of index...
            return web_mod._render_page("SMC V3 短线信号", f"<h1>V3 Web Interface</h1>{stats_html}")

        return fa

    web_mod.setup_app = patched_setup


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="SMC 短线分析 V3 (30/60分钟)")
    parser.add_argument("--a-stocks", "-a", type=int, default=800, help="A股数量")
    parser.add_argument("--hk-stocks", "-k", type=int, default=300, help="港股数量")
    parser.add_argument("--period", type=str, default="60", choices=["30", "60", "both"], help="K线周期")
    parser.add_argument("--force", "-f", action="store_true", help="强制更新")
    parser.add_argument("--skip-fetch", action="store_true", help="跳过获取")
    parser.add_argument("--web", "-w", action="store_true", help="启动 Web")
    parser.add_argument("--port", "-p", type=int, default=8081, help="端口")
    args = parser.parse_args()

    if args.web and args.skip_fetch:
        return _start_web(args.port)

    # 确保目录
    V3_DATA_DIR.mkdir(parents=True, exist_ok=True)
    V3_CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    V3_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    periods = ["30", "60"] if args.period == "both" else [args.period]
    orch = IntradayOrchestrator(V3_CHARTS_DIR, V3_REPORTS_DIR)
    
    for p in periods:
        suffix = f"{p}min"
        if not args.skip_fetch:
            a_spot = fetch_a_spot_top(args.a_stocks)
            if not a_spot.empty:
                fetch_a_intraday_batch(a_spot, V3_DATA_DIR, p, force=args.force)
            from one_click_v2 import get_hk_stock_list
            hk_list = get_hk_stock_list(args.hk_stocks)
            fetch_hk_intraday_batch(hk_list, V3_DATA_DIR, p, force=args.force)
            
        convert_intraday_to_smc(V3_DATA_DIR, suffix)
        a_res, hk_res = run_analysis(V3_DATA_DIR, orch, suffix, suffix, generate_charts=True)
        display_signals(a_res, f"A股({suffix})")
        display_signals(hk_res, f"港股({suffix})")
        display_summary(a_res, hk_res, suffix)

    if args.web:
        return _start_web(args.port)

    return 0

if __name__ == "__main__":
    sys.exit(main())
