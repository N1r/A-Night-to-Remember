import os
import sys
import asyncio
from pathlib import Path
from rich.console import Console

# 设置项目根目录并将其添加到 sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 同时确保 2_mid_processing 在路径中
sys.path.append(os.path.join(PROJECT_ROOT, "2_mid_processing"))

console = Console()

async def post_process_workflow():
    console.print("[bold magenta]=== 阶段 3: 后处理 (Post-processing - Batch Mode) ===[/bold magenta]")

    # Step 0: 集中视频压制 (如果在阶段 2 跳过了)
    force_reencode = "--force" in sys.argv or "-f" in sys.argv
    console.print("🎥 [bold]Step 0:[/bold] 扫描并进行集中视频压制 (FFmpeg)...")
    try:
        from core._7_1_ass_into_vid import merge_subtitles_to_video
        archives_dir = Path(PROJECT_ROOT) / "storage" / "ready_to_publish"
        if archives_dir.exists():
            for d in archives_dir.iterdir():
                if d.is_dir() and d.name not in ("done", "failed"):
                    output_sub = d / "output_sub.mp4"
                    ass_file = d / "artifacts" / "subtitle.ass"
                    # 寻找可能的原始视频
                    raw_videos = list(d.glob("video_raw*"))
                    
                    if force_reencode and output_sub.exists():
                        output_sub.unlink()
                        console.print(f"[dim]🗑️ 强制压制模式：已删除旧的 {d.name}/output_sub.mp4[/dim]")

                    if raw_videos and ass_file.exists() and not output_sub.exists():
                        console.print(f"[cyan]发现未压制（或已删除）视频: {d.name}，正在集中压制...[/cyan]")
                        success = merge_subtitles_to_video(
                            video_file=str(raw_videos[0]),
                            ass_file=str(ass_file),
                            output_path=str(output_sub)
                        )
                        if not success:
                            console.print(f"[red]⚠️ {d.name} 压制失败！[/red]")
    except Exception as e:
        console.print(f"[yellow]⚠️ 集中压制步骤异常: {e}[/yellow]")

    # Step 1: 整理与重命名
    console.print("🚀 [bold]Step 1:[/bold] 正在整理待发布素材 (主题化命名)...")
    try:
        from media.common.file_move_topic import process_and_move_files
        process_and_move_files()
    except Exception as e:
        console.print(f"[yellow]⚠️ 整理脚本执行失败: {e}[/yellow]")

    # Step 2: 元数据生成（显式步骤，auto_publish_all 已有元数据时会自动跳过）
    console.print("\n🧠 [bold]Step 2:[/bold] 多平台元数据生成...")
    try:
        from media.metadata_generator import process_ready_dir
        process_ready_dir(force="--force" in sys.argv or "-f" in sys.argv)
    except Exception as e:
        console.print(f"[yellow]⚠️ 元数据生成失败 ({e})，继续...[/yellow]")

    # Step 3: 无头浏览器 Cookie 有效性验证
    console.print("\n🔍 [bold]Step 3:[/bold] 验证各平台 Cookie 有效性...")
    invalid_platforms = []
    try:
        from verify_cookies import verify_all_cookies, print_verification_results
        cookie_results = await verify_all_cookies()
        all_valid = print_verification_results(cookie_results)
        if not all_valid:
            invalid_platforms = [k for k, (v, _) in cookie_results.items() if not v]
            console.print(
                f"\n[yellow]⚠️  失效平台: {', '.join(invalid_platforms)}\n"
                f"   发布时将自动跳过，或先运行 python get_all_cookies.py 重新登录[/yellow]"
            )
        else:
            console.print("[bold green]✅ 所有平台 Cookie 均有效！[/bold green]")
    except Exception as e:
        console.print(f"[yellow]⚠️ Cookie 验证跳过 ({e})，继续发布流程...[/yellow]")

    # Step 4: 全平台发布
    console.print("\n🚀 [bold]Step 4:[/bold] 开始执行全平台发布流程...")
    try:
        from auto_publish_all import main as publish_main
        await publish_main()
    except Exception as e:
        console.print(f"[red]❌ 发布流程异常: {e}[/red]")

    console.print("[bold green]✅ 所有视频后期处理任务执行完毕！[/bold green]")

if __name__ == "__main__":
    asyncio.run(post_process_workflow())