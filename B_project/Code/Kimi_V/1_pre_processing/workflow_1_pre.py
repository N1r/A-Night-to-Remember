"""
workflow_1_pre.py
-----------------
阶段 1：智能采集工作流。

全自动执行：
  1. 多平台并发采集（YouTube / X / Bluesky）
  2. 增量过滤（跳过已访问视频）
  3. AI 并发筛选（打分 + 分类 + 中文标题生成）
  4. 合并写入任务列表 Excel

运行方式：
    python 1_pre_processing/workflow_1_pre.py
"""

import os
import sys
import importlib
import pandas as pd
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from yt_dlp import YoutubeDL

# ==================== 路径设置 ====================
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# 确保 2_mid_processing 路径可用（config_utils 依赖所在）
sys.path.append(str(PROJECT_ROOT / "2_mid_processing"))
sys.path.append(str(Path(__file__).parent / "scrapers"))

from shared.paths import TASKS_EXCEL, VISITED_LOG
from shared.state import load_visited, save_visited
from shared.logger import console, create_progress, Panel, Table
from core.utils.config_utils import load_key
from core.utils.ask_gpt import ask_gpt

# ==================== 数据格式 ====================

from _base_scraper import STANDARD_COLUMNS

# ==================== 采集器注册表 ====================

SCRAPERS = [
    "youtube",
    "twitter",
    "bluesky",
]


def _load_scrapers():
    """动态加载所有采集器模块"""
    loaded = []
    for name in SCRAPERS:
        try:
            mod = importlib.import_module(name)
            # 找到继承 BaseScraper 的类
            from _base_scraper import BaseScraper
            for attr_name in dir(mod):
                attr = getattr(mod, attr_name)
                if (isinstance(attr, type) and issubclass(attr, BaseScraper)
                        and attr is not BaseScraper):
                    loaded.append(attr())
                    break
        except Exception as e:
            console.print(f"[red]❌ 加载采集器 {name} 失败: {e}[/red]")
    return loaded

def get_video_duration(url: str) -> float:
    """使用 yt-dlp 获取视频时长（不下载视频）"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'simulate': True,
        'skip_download': True,
        'extract_flat': 'in_playlist', # 尽可能快地提取信息
        'socket_timeout': 10,          # 10秒连接超时
        'retries': 3,                  # 重试3次
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return float(info.get('duration', 0))
    except Exception as e:
        # console.print(f"[dim yellow]⚠️ 无法获取时长: {url} ({e})[/dim yellow]")
        return 0.0

# ==================== AI 筛选 ====================

def _evaluate_single(v: dict) -> dict:
    """AI 评估单个视频的质量和传播潜力"""
    from shared.domain import domain

    raw_text = v.get("rawtext", v["title"])
    
    # 如果时长为0，尝试补充获取
    duration = v.get("duration", 0)
    if duration <= 0:
        duration = get_video_duration(v["Video File"])
        v["duration"] = duration
    
    # 评分逻辑：时长加权
    # 最佳区间: 60s - 180s (1-3分钟) -> 权重加分
    # 次佳区间: 180s - 300s (3-5分钟) -> 权重稍低
    # 其他: 降权
    
    duration_score_bonus = 0
    if 60 <= duration <= 180:
        duration_score_bonus = 5  # 黄金时长加分
    elif 180 < duration <= 300:
        duration_score_bonus = 3  # 次佳时长加分
    elif duration > 0 and duration < 60:
         duration_score_bonus = -2 # 太短
    
    # 从领域配置读取筛选参数
    categories, context = domain.get_screening_prompt()
    categories_str = "|".join(categories)

    prompt = f"""
你是专注于中文社交媒体（抖音/小红书/B站）的内容运营专家。请评估下面提供的内容片段是否具备成为爆款的潜力（无需理会出处与链接）。

【内容概要】{raw_text}s
【视频时长】{duration:.1f}s

评分标准（满分30分）：
- 25-30分：强烈信息差或颠覆性结论 / 重磅人物失言或罕见表态 / 政策反转或重大冲突 / 天然具备"转发冲动"
- 15-24分：有实质信息量，观点清晰，目标受众有共鸣，但缺乏"一眼爆款"特质
- 5-14分：信息普通，角度平庸，难以突破流量池
- 0-4分：内容无关、广告性质、或信息量极少

仅返回 JSON，不要输出任何其他内容：
{{
  "score": <整数 0-30>,
  "title_cn": "提炼20字以内的中文标题，让人'一眼看出为什么值得看'，可用疑问/反转/数字句式，严禁凭空编造",
  "reason": "此内容的核心传播价值点，以逗号分隔的2-4个关键词或短语（例：立场反转,罕见表态），20字以内",
  "category": "{categories_str}"
}}"""
    try:
        ai_res = ask_gpt(prompt, resp_type="json", log_title="video_screening")
        base_score = ai_res.get("score", 15)
        
        # 应用时长加权
        final_ai_score = base_score + duration_score_bonus
        v["AI Score"] = final_ai_score # 保存单独的 AI 评分
        
        v["title"] = ai_res.get("title_cn", v["title"])
        v["AI Reason"] = ai_res.get("reason", "评估完成")
        v["Category"] = ai_res.get("category", "Other")
        
        # 在理由中补充时长评价
        if duration_score_bonus > 0:
            v["AI Reason"] += f" [时长适宜 {duration:.0f}s]"
        elif duration_score_bonus < 0:
            v["AI Reason"] += f" [时长偏短 {duration:.0f}s]"
            
    except Exception as e:
        console.print(f"  [dim yellow]⚠️ AI 评估失败 [{v.get('title', '')[:20]}]: {e}[/dim yellow]")
        v["AI Score"] = 10
        v["AI Reason"] = f"AI 评估失败: {str(e)[:60]}"
        v["Category"] = "Other"

    # 综合权重：AI 分 * 1000 + 热度加权
    # 使用处理后的 AI Score 计算总分
    v["Score"] = v.get("AI Score", 0) * 1000 + (v.get("viewCount", 0) / 1000) + v.get("Reposts", 0)
    return v


def _ai_screening(videos: list) -> list:
    """并发 AI 筛选"""
    if not videos:
        return []

    console.print(
        f"\n[bold magenta]🤖 正在对 {len(videos)} 个视频进行 AI 并发筛选...[/bold magenta]"
    )

    with create_progress() as progress:
        task = progress.add_task("[cyan]评估中...", total=len(videos))
        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(_evaluate_single, v) for v in videos]
            for future in futures:
                try:
                    results.append(future.result())
                except Exception as e:
                    console.print(f"  [dim red]⚠️ 评估任务异常: {e}[/dim red]")
                progress.advance(task)

    return results


# ==================== 主工作流 ====================

def pre_process_workflow():
    console.print(
        Panel.fit(
            "[bold blue]VideoLingo 智能采集工作流[/bold blue]\n"
            "[dim]全自动采集、AI 智能筛选、增量更新系统[/dim]",
            border_style="cyan",
        )
    )

    visited = load_visited()

    # 获取现有 Excel 中的 URL（用于增量对比）
    existing_urls = set()
    if TASKS_EXCEL.exists():
        try:
            df_old = pd.read_excel(TASKS_EXCEL)
            if "Video File" in df_old.columns:
                existing_urls = set(df_old["Video File"].dropna().astype(str).tolist())
        except Exception as e:
            console.print(f"[yellow]⚠️ 读取现有 Excel 失败，全量更新: {e}[/yellow]")

    # ==================== 1. 多平台采集 ====================

    all_fetched = []
    scrapers = _load_scrapers()

    console.print(f"\n[bold green]📡 共加载 {len(scrapers)} 个采集器[/bold green]")

    with console.status("[bold green]正在执行全平台内容采集..."):
        # 并行执行所有采集器
        with ThreadPoolExecutor(max_workers=len(scrapers) + 2) as executor:
            # 提交任务
            future_to_scraper = {executor.submit(s.run): s for s in scrapers}
            
            for future in future_to_scraper:
                try:
                    results = future.result()
                    if results:
                        all_fetched.extend(results)
                except Exception as e:
                    s_name = future_to_scraper[future].name
                    console.print(f"[red]❌ 采集器 {s_name} 异常: {e}[/red]")

    if not all_fetched:
        console.print(
            Panel.fit(
                "[yellow]本次巡检未发现任何新内容。[/yellow]",
                title="采集报告",
                border_style="yellow",
            )
        )
        return

    # ==================== 2. 增量过滤 ====================

    new_videos = []
    seen_in_batch = set()
    for v in all_fetched:
        url = str(v["Video File"])
        if url not in existing_urls and url not in seen_in_batch:
            new_videos.append(v)
            seen_in_batch.add(url)

    if not new_videos:
        console.print(
            Panel.fit(
                f"[cyan]共采集 {len(all_fetched)} 条，均为历史记录。[/cyan]",
                title="增量结果",
                border_style="blue",
            )
        )
        return

    console.print(
        f"\n✨ [bold green]增量发现 {len(new_videos)} 条全新内容[/bold green] "
        f"[dim](已过滤 {len(all_fetched) - len(new_videos)} 条重复)[/dim]"
    )

    # ==================== 3. AI 筛选 ====================

    screened = _ai_screening(new_videos)

    # ==================== 4. 合并保存 ====================

    new_df = pd.DataFrame(screened)
    if TASKS_EXCEL.exists():
        try:
            old_df = pd.read_excel(TASKS_EXCEL)
            for col in STANDARD_COLUMNS:
                if col not in old_df.columns:
                    old_df[col] = ""
            final_df = pd.concat([old_df, new_df], ignore_index=True)
        except Exception:
            final_df = new_df
    else:
        final_df = new_df

    final_df.drop_duplicates(subset=["Video File"], keep="first", inplace=True)

    for col in STANDARD_COLUMNS:
        if col not in final_df.columns:
            final_df[col] = ""

    final_df = final_df[STANDARD_COLUMNS].copy()
    final_df["Score"] = pd.to_numeric(final_df["Score"], errors="coerce").fillna(0)
    final_df.sort_values(by="Score", ascending=False, inplace=True)

    TASKS_EXCEL.parent.mkdir(parents=True, exist_ok=True)
    final_df.to_excel(TASKS_EXCEL, index=False)

    # 更新访问记录
    for v in all_fetched:
        visited.add(v["Video File"])
    save_visited(visited)

    # ==================== 5. 汇总输出 ====================

    table = Table(title="✨ 采集与 AI 筛选任务汇总")
    table.add_column("来源", style="cyan")
    table.add_column("时长", style="yellow")
    table.add_column("分类", style="blue")
    table.add_column("评分", style="magenta")
    table.add_column("推荐标题", style="green")
    table.add_column("评估理由", style="dim")

    sorted_new = sorted(screened, key=lambda x: x["Score"], reverse=True)
    for v in sorted_new[:15]:
        display_score = f"{v['Score'] / 1000:.1f}"
        table.add_row(
            v["channel_name"],
            f"{v['duration']:.1f}s",
            v.get("Category", "N/A"),
            display_score,
            v["title"][:25] + "...",
            v.get("AI Reason", "")[:20] + "...",
        )

    console.print(table)
    console.print(
        f"\n[bold green]✅ 采集工作流执行完毕！新增 {len(screened)} 条任务。[/bold green]"
    )


if __name__ == "__main__":
    pre_process_workflow()
