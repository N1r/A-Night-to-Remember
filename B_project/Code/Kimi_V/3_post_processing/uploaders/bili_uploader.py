"""
bili_uploader.py
----------------
B站视频自动化上传模块。

特点：
  - 通过 API（LongCat/OpenAI/Google）智能翻译英文标题为中文
  - 生成 biliup YAML 配置文件
  - 调用 biliup CLI 工具批量上传
  - 支持定时发布（默认次日 8:00 起，每 45 分钟一个）
  - 支持免费/付费内容随机分割

统一接口：
    run(state_mgr) -> bool     # 注意：B站为同步接口
"""

import json
import os
import random
import re
import shutil
import subprocess
import yaml
import requests
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Tuple, Optional

from _base import (
    ARCHIVES_DIR, PROJECT_ROOT, STORAGE_DIR,
    console, find_video,
)

import sys
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from shared.domain import domain

PLATFORM = "bilibili"

# ==================== API 配置（从 config.yaml 读取，与 metadata_generator 保持一致）====================

def _load_api_config() -> tuple:
    """从 configs/config.yaml 读取 API 配置，与项目其他模块保持一致"""
    try:
        import yaml
        cfg_path = PROJECT_ROOT / "configs" / "config.yaml"
        with open(cfg_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        api = cfg.get("api", {})
        return (
            api.get("key", ""),
            api.get("base_url", "https://api.longcat.chat/openai"),
            api.get("model", "LongCat-Flash-Chat"),
        )
    except Exception:
        return (
            os.environ.get("LONGCAT_API_KEY", ""),
            "https://api.longcat.chat/openai",
            "LongCat-Flash-Chat",
        )

API_KEY, API_BASE_URL, API_MODEL = _load_api_config()

# 从领域配置读取 B站上传参数
_bili_config = domain.get_upload_config("bilibili")
TID = _bili_config.get("tid", 208)
TITLE_PREFIX = _bili_config.get("title_prefix", "[熟肉]")
TAG = _bili_config.get("base_tags", [])
EXTRA_TAGS = _bili_config.get("extra_tags", "")
DESC_TEMPLATE = _bili_config.get("description_template", "► 本期看点：{title}")
TITLE_GEN_PROMPT = _bili_config.get("title_generation_prompt", "你是一名资深视频编辑。")

# 简介模板库（如果 domain profile 中有多个模板，可扩展）
DESC_TEMPLATES = [
    DESC_TEMPLATE,
]


# ==================== 工具函数 ====================

def _ask_gpt(system: str, user: str, model: str = None, temperature: float = 0.7) -> Optional[str]:
    """封装 API 请求"""
    if model is None:
        model = API_MODEL
    headers = {
        "Content-Type": "application/json",
    }
    if API_KEY:
        k = API_KEY.strip()
        if k.lower().startswith("bearer "):
            headers["Authorization"] = k
        else:
            headers["Authorization"] = f"Bearer {k}"
    else:
        print("⚠️ 未检测到 LONGCAT API key，Authorization 头为空")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "stream": False,
    }
    try:
        response = requests.post(
            f"{API_BASE_URL}/v1/chat/completions",
            headers=headers, json=payload, timeout=30,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"❌ API 请求失败: {e}")
        return None


# ==================== 元数据读取 ====================

def _get_meta_title(folder: Path) -> Optional[str]:
    """
    优先读取 metadata.json 中预生成的 B站标题。

    metadata_generator.py 已在 platforms.bilibili.title 中生成了经过 LLM
    策划的标题，直接复用可避免重复调用 API，并保证标题来源一致。
    """
    meta_path = folder / "metadata.json"
    if not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        title = meta.get("platforms", {}).get("bilibili", {}).get("title", "")
        return title if title else None
    except Exception:
        return None


# ==================== 标题翻译 ====================

def _translate_title(folder_name: str) -> str:
    """
    智能翻译文件夹名（英文标题）为中文。
    依次尝试：主 API -> Google 翻译 -> 原文兜底。
    """
    print(f"\n📝 正在翻译标题: {folder_name}")
    translated = folder_name  # 默认兜底

    system_prompt = (
        "你是一个专业的中英翻译助手，请把输入的英文准确翻译成中文，"
        "要求简洁明了，适合做视频标题。只输出翻译结果，不要加任何解释。"
    )

    # 尝试 API 翻译
    try:
        result = _ask_gpt(
            system=system_prompt,
            user=f"请将以下英文标题翻译成中文：{folder_name}",
            temperature=0.3,
        )
        if result and len(result.strip()) > 3:
            translated = result.strip()
            print(f"  ✅ API 翻译成功: {translated}")
            return translated
    except Exception as e:
        print(f"  ⚠️ API 翻译失败: {e}")

    # 兜底：Google 翻译
    try:
        from deep_translator import GoogleTranslator
        result = GoogleTranslator(source="auto", target="zh-CN").translate(folder_name)
        if result:
            translated = result
            print(f"  ✅ Google 翻译兜底成功: {translated}")
    except Exception as ge:
        print(f"  ⚠️ Google 翻译也失败: {ge}，使用原始文件夹名")

    return translated


# ==================== YAML 生成 ====================

def _generate_yaml(
    videos: List[str],
    covers: List[str],
    titles: List[str],
    dtimes: List[int],
    output_path: Path,
    is_paid: bool = False,
):
    """生成 biliup 格式的 YAML 配置文件"""
    streamers = {}
    for v, c, t, dt in zip(videos, covers, titles, dtimes):
        entry = {
            "copyright": 1,
            "source": None,
            "tid": TID,  # 分区 ID: 从 domain profile 读取
            "cover": c,
            "title": t,
            "desc": random.choice(DESC_TEMPLATES).format(title=t),
            "tag": ",".join(
                [tag.strip()[:20] for tag in (TAG + EXTRA_TAGS.split(",")) if tag.strip()][:12]
            ) or "视频",
            "dtime": dt,
            "open-elec": 1,
        }
        if is_paid:
            entry.update({
                "charging_pay": 1,
                "upower_level_id": "1212996740244948080",
            })
        streamers[v] = entry

    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(
            {"submit": "App", "streamers": streamers},
            f, allow_unicode=True, sort_keys=False,
        )
    print(f"📄 已生成: {output_path.name} ({len(streamers)} 个视频)")


# ==================== 对外统一接口 ====================

def run(state_mgr=None) -> bool:
    """
    B站上传入口（批量上传模式）。

    一次性收集所有尚未上传的视频，生成一份统一的 biliup YAML 配置文件并上传。

    Parameters
    ----------
    state_mgr : StateManager 实例（可选）

    Returns
    -------
    bool : 成功上传返回 True；无待办任务或失败返回 False
    """
    console.rule("[bold yellow]B站上传（biliup CLI）批量模式[/bold yellow]")

    ready_dir = ARCHIVES_DIR
    if not ready_dir.exists():
        console.print(f"[red]❌ 目录不存在: {ready_dir}[/red]")
        return False

    # ── 找所有待办视频 ──────────────────────────────────────────
    video_entries = []
    for folder in sorted(ready_dir.iterdir()):
        if not folder.is_dir() or folder.name in ("done", "failed"):
            continue
        if state_mgr and state_mgr.is_uploaded(folder.name, PLATFORM):
            continue
        vid = find_video(folder)
        if not vid:
            continue
        jpg_files = list(folder.glob("*.jpg"))
        video_entries.append((
            str(vid),
            str(jpg_files[0]) if jpg_files else "",
            folder.name,
            folder,
        ))

    if not video_entries:
        console.print("[green]✅ B站无待办任务[/green]")
        return False

    # ── 准备发布数据 ──────────────────────────────────────────────
    videos = []
    covers = []
    titles = []
    dtimes = []

    # ── 定时发布：明天 8:00 起，每隔 45 分钟一个 ──────────────────
    start_time = (
        datetime.now(timezone(timedelta(hours=8)))
        .replace(hour=8, minute=0, second=0, microsecond=0)
        + timedelta(days=1)
    )

    for idx, video_entry in enumerate(video_entries):
        video_path, cover_path, folder_name, folder_path = video_entry
        console.print(f"\n📂 准备视频 ({idx+1}/{len(video_entries)}): {folder_name}")

        # ── 标题：优先 metadata.json → 兜底 LLM 翻译 ─────────────────
        title = _get_meta_title(folder_path)
        if title:
            console.print(f"  ✅ 使用预生成标题: [cyan]{title[:60]}[/cyan]")
        else:
            console.print("  ℹ️ 需调用 LLM 翻译标题...")
            translated = _translate_title(folder_name)
            clean = re.sub(r"[\[【].*?[\]】]", "", translated).strip()
            title = f"{TITLE_PREFIX}{clean}"[:80]
            console.print(f"  ✅ 生成标题: [cyan]{title}[/cyan]")

        dtime = int((start_time + timedelta(minutes=150 * idx)).timestamp())
        
        videos.append(video_path)
        covers.append(cover_path)
        titles.append(title)
        dtimes.append(dtime)

    # ── 生成 YAML ─────────────────────────────────────────────────
    yaml_path = STORAGE_DIR / "tasks" / "biliup_upload.yaml"
    yaml_path.parent.mkdir(parents=True, exist_ok=True)
    _generate_yaml(videos, covers, titles, dtimes, yaml_path, is_paid=False)

    # ── 查找 biliup 可执行文件 ────────────────────────────────────
    biliup_bin = shutil.which("biliup") or os.path.expanduser("~/.local/bin/biliup")
    cookies_path = STORAGE_DIR / "cookies" / "bili_cookies.json"

    console.print(f"\n✨ 批量 YAML 已生成: {yaml_path}")

    if not os.path.isfile(biliup_bin):
        console.print(f"[red]❌ 未找到 biliup 可执行文件[/red]")
        console.print(f"   请手动运行: biliup upload -c {yaml_path} -u {cookies_path}")
        return False

    if not cookies_path.exists():
        console.print(f"[red]❌ 未找到 B站 Cookies: {cookies_path}[/red]")
        return False

    # ── 调用 biliup 上传 ──────────────────────────────────────────
    cmd = [biliup_bin, "-u", str(cookies_path), "upload", "-c", str(yaml_path)]
    console.print(f"\n🚀 开始批量上传到 B站 ({len(videos)} 个视频)...")
    console.print(f"   命令: {' '.join(cmd)}\n")

    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))

    if result.returncode == 0:
        console.print(f"[bold green]✅ B站 {len(videos)} 个视频批量上传完成！[/bold green]")
        if state_mgr:
            for folder_name in [v[2] for v in video_entries]:
                state_mgr.mark_uploaded(folder_name, PLATFORM)
                state_mgr.increment_daily_quota(PLATFORM)
        return True
    else:
        console.print(f"[red]❌ biliup 退出码: {result.returncode}[/red]")
        return False


# ==================== 独立运行入口 ====================

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from auto_publish_all import StateManager
    run(StateManager())
