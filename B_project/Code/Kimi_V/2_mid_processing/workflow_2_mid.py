"""
workflow_2_mid.py
-----------------
阶段 2：视频处理工作流（Pipeline 模式）。

核心处理链：
  1. yt-dlp 下载视频
  2. ASR 语音识别
  3. NLP 句子切分
  4. 语义切分
  5. 摘要 + 术语提取
  6. 全文翻译
  7. 字幕切分对齐
  8. ASS/SRT 时间轴生成
  9. FFmpeg 字幕压制
  10. 封面提取
  11. 归档到 ready_to_publish

运行方式：
    python 2_mid_processing/workflow_2_mid.py
    python 2_mid_processing/workflow_2_mid.py --max=5   # 批量处理 5 个
"""

import argparse
import os
import shutil
import subprocess
import sys
import pandas as pd
from pathlib import Path

# ==================== 路径设置 ====================
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

sys.path.insert(0, str(Path(__file__).parent))  # 确保 core/ 可导入

from shared.paths import TASKS_EXCEL, READY_DIR, OUTPUT_DIR as GLOBAL_OUTPUT
from shared.logger import console, log_step, Panel


# ==================== Pipeline 定义 ====================

class Pipeline:
    """
    视频处理 Pipeline — 顺序执行一系列步骤。

    每个步骤是一个 (name, callable) 元组。
    如果某一步失败，可选择跳过或终止。
    """

    def __init__(self, steps: list = None):
        self.steps = steps or []

    def add(self, name: str, func):
        self.steps.append((name, func))
        return self

    def run(self, fail_fast: bool = True) -> list:
        """
        依次执行所有步骤。

        Returns
        -------
        list : 每步的 (name, success: bool, error: str|None) 三元组
        """
        results = []
        for i, (name, func) in enumerate(self.steps, 1):
            log_step(i, name, "running")
            try:
                func()
                log_step(i, name, "done")
                results.append((name, True, None))
            except Exception as e:
                log_step(i, name, "failed")
                console.print(f"[red]   ❌ 错误: {e}[/red]")
                results.append((name, False, str(e)))
                if fail_fast:
                    break
        return results


# ==================== 核心处理函数 ====================

def _build_pipeline():
    """
    构建视频处理 Pipeline。

    将 core/ 目录下的各模块按序编排：
        download → ASR → split → translate → subtitle → encode
    """
    from core._1_ytdlp import download_video_ytdlp, find_video_files
    from core._2_asr import transcribe
    from core._3_1_split_nlp import split_by_spacy
    from core._3_2_split_meaning import split_sentences_by_meaning
    from core._4_1_summarize import get_summary
    from core._4_2_translate import translate_all
    from core._5_split_sub import split_for_sub_main
    from core._6_gen_sub import align_timestamp_main
    from core._7_1_ass_into_vid import merge_subtitles_to_video

    pipe = Pipeline()
    pipe.add("语音识别 (ASR)", transcribe)
    pipe.add("自然语言切分 (NLP Split)", split_by_spacy)
    pipe.add("基于语义的精细切分", split_sentences_by_meaning)
    pipe.add("内容摘要与术语提取", get_summary)
    pipe.add("全文翻译", translate_all)
    pipe.add("字幕切分与对齐", split_for_sub_main)
    pipe.add("时间轴校准与 SRT/ASS 生成", align_timestamp_main)

    return pipe


def _extract_cover(video_file: str, output_dir: str):
    """从视频中提取封面帧"""
    raw_cover = os.path.join(output_dir, "cover_raw.jpg")
    final_cover = os.path.join(output_dir, "cover.png")

    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", video_file, "-ss", "00:00:05", "-vframes", "1", raw_cover],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        console.print(f"[yellow]⚠️ ffmpeg 封面提取失败: {e.stderr.decode(errors='replace').strip()}[/yellow]")
        return

    if os.path.exists(raw_cover):
        shutil.copy(raw_cover, final_cover)
        console.print(f"✨ 封面已保存: {final_cover}")
    else:
        console.print("[yellow]⚠️ 封面提取失败：输出文件未生成[/yellow]")


def _archive_to_publish(title: str, output_dir: str):
    """将处理结果归档到 ready_to_publish/，并清理冗余文件"""
    from core._1_ytdlp import find_video_files

    safe_title = "".join(
        [c for c in title if c.isalnum() or c in (" ", "-", "_")]
    ).strip()
    target_dir = READY_DIR / safe_title
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建附属文件夹收集中间产物
    artifacts_dir = target_dir / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)

    # 1. 移动核心产物
    # 移动原始视频
    video_file = find_video_files(exit_if_multiple=False)
    if video_file:
        shutil.move(video_file, str(target_dir / ("video_raw" + os.path.splitext(video_file)[1])))

    # 移动压制后视频
    output_video = os.path.join(output_dir, "output_sub.mp4")
    if os.path.exists(output_video):
        shutil.move(output_video, str(target_dir / "output_sub.mp4"))

    # 移动封面
    output_cover = os.path.join(output_dir, "cover.png")
    if os.path.exists(output_cover):
        shutil.move(output_cover, str(target_dir / "cover.png"))

    # 2. 移动中间产物及日志
    # 字幕文件
    for ext in ["*.srt", "*.ass"]:
        for f in Path(output_dir).glob(ext):
            shutil.move(str(f), str(artifacts_dir / f.name))

    # LOG 目录
    src_log = os.path.join(output_dir, "log")
    if os.path.exists(src_log):
        shutil.move(src_log, str(target_dir / "processing_logs"))

    # 3. 清理剩余的琐碎文件 (如 cover_raw.jpg 等)
    for f in Path(output_dir).iterdir():
        if f.is_file():
            try:
                f.unlink()
            except OSError as e:
                console.print(f"[yellow]⚠️ 无法删除文件 {f.name}: {e}[/yellow]")
        elif f.is_dir() and f.name not in ["artifacts", "processing_logs"]:
            try:
                shutil.rmtree(f)
            except OSError as e:
                console.print(f"[yellow]⚠️ 无法删除目录 {f.name}: {e}[/yellow]")

    console.print(f"📦 已归档并清理工作分片: [cyan]{safe_title}[/cyan]")


# ==================== 单视频处理 ====================

def process_single_video(url: str, title: str):
    """处理单个视频的完整流程"""
    console.print(
        f"\n🎬 [bold magenta]开始处理视频: {title}[/bold magenta]"
    )

    output_dir = os.path.join(str(PROJECT_ROOT), "output")

    # 1. 强力清理并预热工作区
    if os.path.exists(output_dir):
        try:
            shutil.rmtree(output_dir)
        except Exception as e:
            console.print(f"[yellow]⚠️ 初始清理失败，尝试暴力清理文件: {e}[/yellow]")
            # 备选：清理目录下所有 mp4
            for p in Path(output_dir).glob("*.mp4"):
                try:
                    p.unlink()
                except OSError:
                    pass
    
    # 确保目录及其所需子目录全部存在
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(os.path.join(output_dir, "log"), exist_ok=True)
    os.makedirs(os.path.join(output_dir, "audio"), exist_ok=True)

    # 2. 下载
    console.print(f"📥 正在下载: {url}")
    from core._1_ytdlp import download_video_ytdlp, find_video_files
    download_video_ytdlp(url)

    # 3. 执行 Pipeline
    pipe = _build_pipeline()
    results = pipe.run(fail_fast=True)

    # 检查是否有失败步骤
    failed = [(name, err) for name, ok, err in results if not ok]
    if failed:
        console.print(f"[red]❌ {len(failed)} 个步骤失败，跳过后续处理[/red]")
        return False

    # 4. 封面提取
    console.print("🎨 正在提取封面...")
    try:
        video_file = find_video_files(exit_if_multiple=False)
        if video_file:
            _extract_cover(video_file, output_dir)
    except Exception as e:
        console.print(f"[yellow]⚠️ 封面提取失败: {e}[/yellow]")

    # 5. 归档
    _archive_to_publish(title, output_dir)

    console.print(f"✅ 视频 [cyan]{title}[/cyan] 处理完成")
    return True


# ==================== 批量工作流 ====================

def mid_process_workflow():
    console.print(
        Panel.fit(
            "[bold cyan]阶段 2: 视频处理 Pipeline[/bold cyan]\n"
            "[dim]下载 → ASR → 翻译 → 字幕 → 压制 → 归档[/dim]",
            border_style="cyan",
        )
    )

    if not TASKS_EXCEL.exists():
        console.print("[red]❌ 任务列表不存在，请先运行阶段 1。[/red]")
        return

    df = pd.read_excel(TASKS_EXCEL)
    if df.empty:
        console.print("[yellow]⚠️ 任务列表为空。[/yellow]")
        return

    if "Status" not in df.columns:
        df["Status"] = ""

    pending = df[~df["Status"].isin(["done", "error"])]
    if pending.empty:
        console.print("[green]✅ 所有任务均已完成。[/green]")
        return

    # 解析命令行参数
    parser = argparse.ArgumentParser(prog="workflow_2_mid", add_help=False)
    parser.add_argument("--max", type=int, default=10, metavar="N",
                        help="本次最多处理的任务数（默认 3）")
    args, _ = parser.parse_known_args()
    max_tasks = args.max

    num_to_process = min(max_tasks, len(pending))
    console.print(
        f"📅 本次批量处理 [bold green]{num_to_process}[/bold green] 个任务 "
        f"[dim](共 {len(pending)} 个待处理)[/dim]"
    )

    processed = 0
    for idx, task in pending.iterrows():
        if processed >= num_to_process:
            break

        try:
            success = process_single_video(task["Video File"], task["title"])
            if success:
                # 重新读取 Excel 以防其他进程修改（虽然当前主要是单进程，但这是个好习惯）
                # 这里为了简单直接更新内存中的 df 并保存
                df.at[idx, "Status"] = "done"
                df.to_excel(TASKS_EXCEL, index=False)
                console.print(f"📝 任务状态已更新为 [bold green]done[/bold green]")
                processed += 1
        except Exception as e:
            console.print(f"[red]❌ '{task['title']}' 处理失败: {e}[/red]")
            # 记录错误状态
            df.at[idx, "Status"] = "error"
            df.to_excel(TASKS_EXCEL, index=False)
            continue

    console.print(
        f"[bold green]✨ 批量处理完成 (成功: {processed}/{num_to_process})[/bold green]"
    )


if __name__ == "__main__":
    mid_process_workflow()