"""
SMC Web Application - 买入信号 Top 20
=====================================

基于 FastAPI 的轻量 Web 应用，
从最新 smc_report Excel 中读取信号强度前20的买入信号，
展示对应的 SMC 分析图表。
"""
import logging
from pathlib import Path
from typing import List, Optional, Dict

import pandas as pd
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from ..config import get_config

logger = logging.getLogger(__name__)

app = FastAPI(title="SMC 买入信号 Top 20")

DARK_BG = "#0a0e17"
CARD_BG = "#161b22"
BORDER = "#30363d"
GREEN = "#3fb950"
RED = "#f85149"
BLUE = "#58a6ff"
YELLOW = "#d29922"
GRAY = "#8b949e"

TOP_N = 20


def _load_top_signals(reports_dir: Path, charts_dir: Path) -> List[Dict]:
    """从最新 smc_report Excel 读取信号强度前20的买入信号."""
    report_files = sorted(
        reports_dir.glob("smc_report_*.xlsx"),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    if not report_files:
        return []

    try:
        df = pd.read_excel(report_files[0], sheet_name="信号汇总")
    except Exception as e:
        logger.error(f"读取报告失败: {e}")
        return []

    # 仅保留 long 信号，按信号强度降序取前 TOP_N
    df = df[df["信号类型"] == "long"].copy()
    df = df.sort_values("信号强度", ascending=False).head(TOP_N)

    results = []
    for _, row in df.iterrows():
        code = str(row["代码"]).zfill(6) if str(row["代码"]).isdigit() and len(str(row["代码"])) <= 6 else str(row["代码"])
        name = str(row["名称"])

        # 匹配图表文件
        chart_file = _find_chart(charts_dir, code, name)

        results.append({
            "code": code,
            "name": name,
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


def _find_chart(charts_dir: Path, code: str, name: str) -> Optional[Path]:
    """在 charts 目录中查找匹配的图表文件."""
    raw = code.lstrip("0") or "0"
    # 尝试多种代码格式: 原始、6位补零、5位补零、去零
    code_variants = list(dict.fromkeys([code, raw.zfill(6), raw.zfill(5), raw]))
    for c in code_variants:
        exact = charts_dir / f"{c}_{name}_chart.html"
        if exact.exists():
            return exact
    for c in code_variants:
        for f in charts_dir.glob(f"{c}_*_chart.html"):
            return f
    return None


def _render_page(title: str, body: str) -> str:
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:{DARK_BG};color:#e6edf3;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Microsoft YaHei',sans-serif}}
a{{color:{BLUE};text-decoration:none}}
a:hover{{text-decoration:underline}}
.header{{
    background:linear-gradient(90deg,{CARD_BG},#1c2128);
    border-bottom:2px solid {BORDER};padding:16px 24px;
    display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px
}}
.header h1{{font-size:1.4em}}
.header .sub{{font-size:0.85em;color:{GRAY}}}
.container{{max-width:1600px;margin:0 auto;padding:20px}}
.stats{{display:flex;gap:16px;margin-bottom:20px;flex-wrap:wrap}}
.stat-box{{
    background:{CARD_BG};border:1px solid {BORDER};border-radius:8px;
    padding:12px 20px;text-align:center;min-width:120px
}}
.stat-box .val{{font-size:1.8em;font-weight:600}}
.stat-box .lbl{{font-size:0.8em;color:{GRAY};margin-top:2px}}
.signal-list{{display:flex;flex-direction:column;gap:14px}}
.signal-card{{
    background:{CARD_BG};border:1px solid {BORDER};border-radius:10px;
    overflow:hidden;transition:box-shadow 0.2s
}}
.signal-card:hover{{box-shadow:0 4px 16px rgba(0,0,0,0.4)}}
.signal-head{{
    padding:14px 18px;display:flex;align-items:center;justify-content:space-between;
    flex-wrap:wrap;gap:10px;border-bottom:1px solid {BORDER};cursor:pointer
}}
.signal-head .left{{display:flex;align-items:center;gap:12px}}
.rank{{
    width:30px;height:30px;border-radius:50%;background:{BLUE};color:#fff;
    display:flex;align-items:center;justify-content:center;font-weight:700;font-size:0.9em
}}
.rank.top3{{background:{GREEN}}}
.code{{font-weight:600;color:{BLUE};font-size:1.1em}}
.name{{color:#e6edf3}}
.strength{{
    font-size:1.2em;font-weight:700;padding:4px 12px;border-radius:6px
}}
.strength.high{{color:{GREEN};background:rgba(63,185,80,0.15)}}
.strength.mid{{color:{YELLOW};background:rgba(210,153,34,0.15)}}
.metrics{{
    display:flex;gap:16px;padding:10px 18px;flex-wrap:wrap;font-size:0.88em;color:{GRAY}
}}
.metrics span{{display:flex;align-items:center;gap:4px}}
.metrics .v{{color:#e6edf3;font-weight:500}}
.metrics .entry{{color:{BLUE}}}
.metrics .stop{{color:{RED}}}
.metrics .tp{{color:{GREEN}}}
.chart-frame{{display:none;border-top:1px solid {BORDER}}}
.chart-frame.open{{display:block}}
.chart-frame iframe{{width:100%;height:75vh;border:none;background:#fff}}
.no-chart{{padding:40px;text-align:center;color:{GRAY};font-size:0.95em}}
.viewer{{width:100%;border:none;border-radius:8px;background:#fff}}
.back-link{{display:inline-block;margin-bottom:16px;padding:8px 16px;border-radius:6px;background:#21262d;border:1px solid {BORDER}}}
.empty{{text-align:center;padding:60px 20px;color:{GRAY};font-size:1.1em}}
</style>
</head>
<body>
{body}
<script>
function toggle(id) {{
    const el = document.getElementById(id);
    if (el) el.classList.toggle('open');
}}
</script>
</body>
</html>'''


def setup_app() -> FastAPI:
    """配置并返回 FastAPI 应用."""
    config = get_config()
    charts_dir = config.charts_dir
    reports_dir = config.reports_dir

    if charts_dir.exists():
        app.mount("/static/charts", StaticFiles(directory=str(charts_dir)), name="charts_static")
    if reports_dir.exists():
        app.mount("/static/reports", StaticFiles(directory=str(reports_dir)), name="reports_static")

    @app.get("/", response_class=HTMLResponse)
    async def index():
        signals = _load_top_signals(reports_dir, charts_dir)

        with_chart = sum(1 for s in signals if s["chart_filename"])
        avg_str = sum(s["strength"] for s in signals) / len(signals) if signals else 0
        report_name = signals[0]["report_file"] if signals else "N/A"

        stats_html = f'''<div class="stats">
            <div class="stat-box"><div class="val" style="color:{GREEN}">{len(signals)}</div><div class="lbl">买入信号</div></div>
            <div class="stat-box"><div class="val" style="color:{BLUE}">{with_chart}</div><div class="lbl">有图表</div></div>
            <div class="stat-box"><div class="val" style="color:{YELLOW}">{avg_str:.0f}</div><div class="lbl">平均强度</div></div>
        </div>'''

        cards_html = ""
        for i, s in enumerate(signals):
            rank_cls = "rank top3" if i < 3 else "rank"
            str_cls = "high" if s["strength"] >= 70 else "mid"
            chart_id = f"chart_{i}"

            chart_inner = ""
            if s["chart_filename"]:
                chart_inner = f'<iframe src="/static/charts/{s["chart_filename"]}" loading="lazy"></iframe>'
            else:
                chart_inner = '<div class="no-chart">暂无图表</div>'

            cards_html += f'''
<div class="signal-card">
    <div class="signal-head" onclick="toggle('{chart_id}')">
        <div class="left">
            <div class="{rank_cls}">{i+1}</div>
            <span class="code">{s["code"]}</span>
            <span class="name">{s["name"]}</span>
        </div>
        <div class="strength {str_cls}">{s["strength"]:.0f}</div>
    </div>
    <div class="metrics">
        <span>胜率 <b class="v">{s["win_rate"]}</b></span>
        <span>盈亏比 <b class="v">1:{s["rr"]:.0f}</b></span>
        <span>入场 <b class="v entry">{s["entry"]:.2f}</b></span>
        <span>止损 <b class="v stop">{s["stop"]:.2f}</b></span>
        <span>目标1 <b class="v tp">{s["tp1"]:.2f}</b></span>
        <span>目标2 <b class="v tp">{s["tp2"]:.2f}</b></span>
        <span>OB重叠 <b class="v">{s["ob_overlap"]}</b></span>
    </div>
    <div id="{chart_id}" class="chart-frame">
        {chart_inner}
    </div>
</div>'''

        body = f'''<div class="header">
    <h1>SMC 买入信号 Top {TOP_N}</h1>
    <span class="sub">数据来源: {report_name}</span>
</div>
<div class="container">
    {stats_html}
    <div class="signal-list">
        {cards_html if cards_html else '<div class="empty">暂无买入信号，请先运行 one_click_v2.py</div>'}
    </div>
</div>'''
        return _render_page(f"SMC 买入信号 Top {TOP_N}", body)

    @app.get("/chart/{filename}", response_class=HTMLResponse)
    async def view_chart(filename: str):
        filepath = charts_dir / filename
        if not filepath.exists():
            return HTMLResponse("<h1>文件不存在</h1>", status_code=404)
        body = f'''<div class="header"><h1>SMC 图表</h1></div>
<div class="container">
    <a href="/" class="back-link">← 返回列表</a>
    <iframe src="/static/charts/{filename}" class="viewer" style="height:85vh;"></iframe>
</div>'''
        return _render_page("SMC 图表", body)

    return app


def run_app(host: str = "0.0.0.0", port: int = 8080, reload: bool = False):
    """启动 Web 应用."""
    import uvicorn
    setup_app()
    uvicorn.run(app, host=host, port=port, reload=reload, log_level="info")


if __name__ == "__main__":
    run_app()
