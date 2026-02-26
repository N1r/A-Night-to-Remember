#!/usr/bin/env python3
"""
publish_status.py
-----------------
独立的上传状态管理工具。

JSON 结构 (storage/tasks/publish_history.json):
{
  "视频标题（文件夹名）": {
    "tencent":      true/false,
    "douyin":       true/false,
    "xiaohongshu":  true/false,
    "bilibili":     false,
    "added_date":   "2026-02-18",
    "last_updated": "2026-02-18"
  }
}

用法:
  python apps/publish_status.py          # 显示所有视频的上传状态
  python apps/publish_status.py --scan   # 扫描 ready_to_publish 目录，自动注册新视频
  python apps/publish_status.py --reset  # 重置某个视频的上传状态（交互式）
"""

import json
import sys
import threading
from pathlib import Path
from datetime import datetime

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

# ==================== 路径配置 ====================
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
VIDEO_DIR    = PROJECT_ROOT / "storage" / "ready_to_publish"
HISTORY_FILE = PROJECT_ROOT / "storage" / "tasks" / "publish_history.json"

PLATFORMS = ["tencent", "douyin", "xiaohongshu", "bilibili", "kuaishou"]

console = Console() if HAS_RICH else None

# 线程锁：防止 asyncio.to_thread 并发写入 publish_history.json
_history_lock = threading.Lock()


def _print(msg: str):
    """统一输出：有 rich 用 console，否则用 print"""
    if console:
        console.print(msg)
    else:
        print(msg)

# ==================== 核心函数 ====================

def load_history() -> dict:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding='utf-8'))
        except:
            return {}
    return {}

def save_history(history: dict):
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding='utf-8')

def scan_and_register():
    """扫描 ready_to_publish 目录，自动注册尚未记录的视频"""
    history = load_history()
    today = datetime.now().strftime("%Y-%m-%d")
    new_count = 0

    for folder in sorted(VIDEO_DIR.iterdir()):
        if not folder.is_dir():
            continue
        # 检查是否有 .mp4 文件（确认是有效的视频文件夹）
        has_video = any(folder.glob("*.mp4"))
        if not has_video:
            continue
        
        name = folder.name
        if name not in history:
            history[name] = {
                "tencent":     False,
                "douyin":      False,
                "xiaohongshu": False,
                "bilibili":    False,
                "kuaishou":    False,
                "added_date":  today,
                "last_updated": today
            }
            new_count += 1
            _print(f"  ➕ 注册新视频: {name}")

    save_history(history)
    _print(f"\n✅ 扫描完成，新注册 {new_count} 个视频。")
    return history

def show_status(history: dict):
    """打印所有视频的上传状态"""
    if not history:
        _print("📭 暂无记录。运行 --scan 来扫描并注册视频。")
        return

    if HAS_RICH:
        table = Table(title="📊 视频上传状态总览", show_lines=True)
        table.add_column("视频标题", style="cyan", max_width=40, no_wrap=False)
        table.add_column("腾讯", justify="center")
        table.add_column("抖音", justify="center")
        table.add_column("小红书", justify="center")
        table.add_column("B站", justify="center")
        table.add_column("快手", justify="center")
        table.add_column("添加日期", style="dim")

        for name, status in history.items():
            def fmt(v): return "✅" if v else "⬜"
            table.add_row(
                name[:40],
                fmt(status.get("tencent")),
                fmt(status.get("douyin")),
                fmt(status.get("xiaohongshu")),
                fmt(status.get("bilibili")),
                fmt(status.get("kuaishou")),
                status.get("added_date", "-")
            )
        console.print(table)
    else:
        _print(f"{'视频标题':<40} {'腾讯':^6} {'抖音':^6} {'小红书':^8} {'B站':^6} {'快手':^6}")
        _print("-" * 80)
        for name, status in history.items():
            def fmt(v): return "✅" if v else "❌"
            _print(f"{name[:40]:<40} {fmt(status.get('tencent')):^6} {fmt(status.get('douyin')):^6} {fmt(status.get('xiaohongshu')):^8} {fmt(status.get('bilibili')):^6} {fmt(status.get('kuaishou')):^6}")

def mark_uploaded(video_name: str, platform: str):
    """标记某视频在某平台已上传（线程安全）"""
    with _history_lock:
        history = load_history()
        today = datetime.now().strftime("%Y-%m-%d")
        if video_name not in history:
            history[video_name] = {p: False for p in PLATFORMS}
            history[video_name]["added_date"] = today
        history[video_name][platform] = True
        history[video_name]["last_updated"] = today
        save_history(history)
    if console:
        console.print(f"✅ 已标记 [{video_name}] 在 [{platform}] 上传完成")
    else:
        print(f"✅ 已标记 [{video_name}] 在 [{platform}] 上传完成")

def reset_video(video_name: str, platform: str = None):
    """重置某视频的上传状态（全部或指定平台）"""
    history = load_history()
    today = datetime.now().strftime("%Y-%m-%d")
    if video_name not in history:
        _print(f"❌ 未找到视频: {video_name}")
        return
    if platform:
        history[video_name][platform] = False
        _print(f"🔄 已重置 [{video_name}] 在 [{platform}] 的状态")
    else:
        for p in PLATFORMS:
            history[video_name][p] = False
        _print(f"🔄 已重置 [{video_name}] 所有平台的状态")
    history[video_name]["last_updated"] = today
    save_history(history)

# ==================== 供 auto_publish_all.py 调用的接口 ====================

def is_uploaded(video_name: str, platform: str) -> bool:
    history = load_history()
    return history.get(video_name, {}).get(platform, False)

def get_pending_videos(platform: str) -> list:
    """返回指定平台尚未上传的视频文件夹路径列表"""
    history = load_history()
    pending = []
    for folder in sorted(VIDEO_DIR.iterdir()):
        if not folder.is_dir():
            continue
        name = folder.name
        status = history.get(name, {})
        if not status.get(platform, False):
            pending.append(folder)
    return pending

# ==================== CLI 入口 ====================

if __name__ == "__main__":
    args = sys.argv[1:]

    if "--scan" in args:
        _print(f"🔍 扫描目录: {VIDEO_DIR}\n")
        history = scan_and_register()
        _print("")
        show_status(history)

    elif "--mark" in args:
        # 用法: --mark "视频名" tencent
        idx = args.index("--mark")
        if idx + 2 < len(args):
            mark_uploaded(args[idx+1], args[idx+2])
        else:
            _print("用法: --mark \"视频名\" <platform>")

    elif "--reset" in args:
        idx = args.index("--reset")
        if idx + 1 < len(args):
            video = args[idx+1]
            plat  = args[idx+2] if idx + 2 < len(args) else None
            reset_video(video, plat)
        else:
            _print("用法: --reset \"视频名\" [platform]")

    else:
        # 默认：显示状态
        history = load_history()
        show_status(history)
