"""
shared/state.py
---------------
全局状态管理 — 已访问视频去重 + 发布历史。

三个采集器（YouTube / X / Bluesky）原本各自维护 visited set，
现在统一到这里，避免重复加载、不一致问题。

使用方式：
    from shared.state import load_visited, save_visited, is_visited, mark_visited
"""

import json
from pathlib import Path
from shared.paths import VISITED_LOG, PUBLISH_HISTORY


# ==================== 已访问视频去重 ====================

def load_visited() -> set:
    """加载已访问视频 URL 集合"""
    if VISITED_LOG.exists():
        try:
            return set(json.loads(VISITED_LOG.read_text(encoding="utf-8")))
        except Exception:
            return set()
    return set()


def save_visited(visited: set):
    """保存已访问视频 URL 集合"""
    VISITED_LOG.parent.mkdir(parents=True, exist_ok=True)
    VISITED_LOG.write_text(
        json.dumps(list(visited), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def is_visited(url: str) -> bool:
    """检查 URL 是否已访问"""
    return url in load_visited()


def mark_visited(urls):
    """标记 URL 为已访问（支持单个或列表）"""
    visited = load_visited()
    if isinstance(urls, str):
        visited.add(urls)
    else:
        visited.update(urls)
    save_visited(visited)


# ==================== 发布历史 ====================

def load_publish_history() -> dict:
    """加载发布历史"""
    if PUBLISH_HISTORY.exists():
        try:
            return json.loads(PUBLISH_HISTORY.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_publish_history(history: dict):
    """保存发布历史"""
    PUBLISH_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    PUBLISH_HISTORY.write_text(
        json.dumps(history, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
