"""
auto_publish_all.py
-------------------
全平台自动化发布主控脚本（精简版）。

执行顺序（并发启动，错峰执行）：
  1. 腾讯视频  —— 全量上传（Playwright）
  2. 抖音      —— 每日 1 条（Playwright，错峰 10s）
  3. 小红书    —— 每日 1 条（Playwright，错峰 20s）
  4. B 站      —— 生成 YAML 并调用 biliup（错峰 5s）

运行方式：
    python 3_post_processing/auto_publish_all.py
    python 3_post_processing/auto_publish_all.py --test-one
"""

import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path
from datetime import datetime

from rich.console import Console
from rich.panel import Panel

# ==================== 路径 & 环境 ====================

PROJECT_ROOT = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).parent / "uploaders"))

ARCHIVES_DIR     = PROJECT_ROOT / "storage" / "ready_to_publish"
DONE_DIR         = ARCHIVES_DIR / "done"
HISTORY_FILE     = PROJECT_ROOT / "storage" / "tasks" / "publish_history.json"
DAILY_QUOTA_FILE = PROJECT_ROOT / "storage" / "tasks" / "daily_quota.json"

for d in [DONE_DIR]:
    d.mkdir(parents=True, exist_ok=True)

console = Console()

# ==================== 状态管理 ====================

from publish_status import (
    load_history, save_history, is_uploaded,
    mark_uploaded as _mark_uploaded,
    scan_and_register, PLATFORMS,
)

REQUIRED_PLATFORMS = ["bilibili", "xiaohongshu", "kuaishou","wechat_channels"]
#REQUIRED_PLATFORMS = ["wechat_channels", "douyin", "xiaohongshu", "bilibili", "kuaishou"]
#

class StateManager:
    """跨平台发布状态管理器"""

    def __init__(self):
        scan_and_register()
        self.daily_quota = self._load_json(DAILY_QUOTA_FILE)
        self.today = datetime.now().strftime("%Y-%m-%d")
        self._cleanup_old_quota()

    def _cleanup_old_quota(self, keep_days: int = 7):
        """删除超过 keep_days 天的配额记录，防止文件无限增长"""
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=keep_days)).strftime("%Y-%m-%d")
        stale = [d for d in list(self.daily_quota) if d < cutoff]
        if stale:
            for d in stale:
                del self.daily_quota[d]
            self._save_json(DAILY_QUOTA_FILE, self.daily_quota)

    def _load_json(self, path: Path) -> dict:
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_json(self, path: Path, data: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def is_uploaded(self, video_name: str, platform: str) -> bool:
        return is_uploaded(video_name, platform)

    def mark_uploaded(self, video_name: str, platform: str):
        _mark_uploaded(video_name, platform)
        self._check_and_archive(video_name)

    def _check_and_archive(self, video_name: str):
        """所有平台均完成时，将文件夹归档到 done/"""
        history = load_history()
        status = history.get(video_name, {})
        all_done = all(status.get(p, False) for p in REQUIRED_PLATFORMS)
        if all_done:
            src = ARCHIVES_DIR / video_name
            dst = DONE_DIR / video_name
            if src.exists():
                try:
                    shutil.move(str(src), str(dst))
                    console.print(
                        f"[bold green]🎉 {video_name} 全平台完成，已归档至 done/[/bold green]"
                    )
                except Exception as e:
                    console.print(f"[red]归档失败: {e}[/red]")

    def can_upload_today(self, platform: str) -> bool:
        if platform == "tencent":
            return True  # 腾讯不限量
        record = self.daily_quota.get(self.today, {})
        return record.get(platform, 0) < 3  # 抖音/小红书/快手 每日 3 条

    def increment_daily_quota(self, platform: str):
        if self.today not in self.daily_quota:
            self.daily_quota[self.today] = {}
        self.daily_quota[self.today][platform] = (
            self.daily_quota[self.today].get(platform, 0) + 1
        )
        self._save_json(DAILY_QUOTA_FILE, self.daily_quota)


# ==================== 动态加载上传器 ====================

import importlib

def _load_uploader(module_name: str):
    """
    从 uploaders/ 目录动态导入上传模块。
    每个模块必须暴露 async run(state_mgr) -> bool 接口。
    """
    try:
        mod = importlib.import_module(module_name)
        if not hasattr(mod, "run"):
            raise AttributeError(f"模块 {module_name} 缺少 run() 函数")
        return mod
    except Exception as e:
        console.print(f"[red]❌ 加载模块 {module_name} 失败: {e}[/red]")
        return None


# ==================== 主控程序 ====================

async def main():
    console.rule(f"[bold blue]全平台自动化发布系统 3.0  {datetime.now().strftime('%Y-%m-%d %H:%M')}[/bold blue]")

    from _base import HEADLESS_MODE
    console.print(
        f"🤖 浏览器模式: {'[green]HEADLESS[/green]' if HEADLESS_MODE else '[yellow]GUI[/yellow]'}"
    )

    # --- Step 0: 元数据预处理 (智能化补全) ---
    try:
        from media.metadata_generator import process_ready_dir
        process_ready_dir(force="--force" in sys.argv or "-f" in sys.argv)
    except Exception as e:
        console.print(f"[yellow]⚠️ 元数据预处理异常 (跳过): {e}[/yellow]")

    state_mgr = StateManager()

    # 检查是否有视频待处理 (优先查找 output_sub.mp4)
    videos = []
    for d in sorted(ARCHIVES_DIR.iterdir()):
        if not d.is_dir() or d.name in ("done", "failed"):
            continue
        
        # 优先使用压制后的视频
        target_video = d / "output_sub.mp4"
        if target_video.exists():
            videos.append(target_video)
        else:
            # 兜底：查找任意 mp4
            vids = list(d.glob("*.mp4"))
            if vids:
                videos.append(vids[0])
            
    # 按修改时间排序
    videos.sort(key=lambda x: x.stat().st_mtime, reverse=True)

    # 解析命令行参数
    parser = argparse.ArgumentParser(prog="auto_publish_all", add_help=False)
    parser.add_argument("--test-one", action="store_true",
                        help="仅处理最新一个视频（测试模式）")
    parser.add_argument("--platforms", type=str, default="",
                        help="逗号分隔的目标平台列表，如 douyin,bilibili")
    headless_group = parser.add_mutually_exclusive_group()
    headless_group.add_argument("--headless", action="store_true",
                                help="强制使用无头浏览器模式")
    headless_group.add_argument("--no-headless", action="store_true",
                                help="强制使用 GUI 浏览器模式")
    args, _ = parser.parse_known_args()

    if args.test_one and videos:
        videos = [videos[0]]
        console.print("[bold yellow]🧪 测试模式：仅处理最新一个视频[/bold yellow]")

    if not videos:
        console.print("[yellow]📂 archives 目录下无新视频，任务结束。[/yellow]")
        return

    selected_platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
    force_headless = True if args.headless else (False if args.no_headless else None)

    # 默认全部平台（暂时注释腾讯由于调试中）
    if not selected_platforms:
        selected_platforms = ["xiaohongshu", "bilibili", "kuaishou"]
        #selected_platforms = ["wechat_channels", "douyin", "xiaohongshu", "bilibili", "kuaishou"]

    console.print(
        Panel(
            f"🚀 [bold green]启动并发发布流[/bold green]\n"
            f"待处理视频总数: {len(videos)}\n"
            f"目标平台: {', '.join(selected_platforms)}",
            border_style="green",
        )
    )

    # ==================== 顺序执行任务流 (适配每日多条限额) ====================
    
    PLATFORM_MAPPING = {
        "tencent": "tencent_uploader",
        "douyin": "douyin_uploader",
        "xiaohongshu": "xhs_uploader",
        "bilibili": "bili_uploader",
        "kuaishou": "ks_uploader",
        "wechat_channels": "wechat_channels_uploader"
    }

    results = []
    
    for platform in selected_platforms:
        module_name = PLATFORM_MAPPING.get(platform)
        if not module_name:
            continue
            
        console.rule(f"[bold blue]🚀 正在处理平台: {platform}[/bold blue]")
        
        uploader_mod = _load_uploader(module_name)
        if not uploader_mod:
            continue
            
        # 针对每个平台循环发布，直到额度耗尽或无视频
        publish_count = 0
        while state_mgr.can_upload_today(platform):
            console.print(f"▶️ [bold cyan]启动第 {publish_count + 1} 个视频发布任务 ({platform})...[/bold cyan]")
            try:
                # 特殊处理 bilibili (使用 thread)
                if platform == "bilibili":
                    success = await asyncio.to_thread(uploader_mod.run, state_mgr)
                else:
                    success = await uploader_mod.run(state_mgr)
                
                results.append((platform, success))
                
                if success:
                    publish_count += 1
                    # 连发之间错峰
                    await asyncio.sleep(5)
                else:
                    # 如果这一个视频没发成（比如没任务了），跳出循环处理下一个平台
                    break
            except Exception as e:
                console.print(f"[red]❌ {platform} 发布过程异常: {e}[/red]")
                results.append((platform, e))
                break
        
        console.print(f"✔️ {platform} 平台处理结束 (本次发布: {publish_count} 条)")
        # 平台之间错峰
        await asyncio.sleep(10)

    console.print(
        Panel.fit(
            "[bold green]🏁 所有平台发布流程已顺序执行完毕[/bold green]",
            border_style="bold green",
        )
    )


if __name__ == "__main__":
    asyncio.run(main())