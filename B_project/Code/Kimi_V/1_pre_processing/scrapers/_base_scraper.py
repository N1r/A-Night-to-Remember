"""
_base_scraper.py
----------------
采集器基类 — 定义标准化的数据格式和公共接口。

所有平台采集器继承此类，只需实现 `fetch()` 方法。

标准视频数据字典格式（所有采集器必须输出此格式）：
{
    'Score': 0,
    'Video File': str,    # 视频 URL 或文件路径
    'title': str,         # 标题
    'Category': str,      # 分类
    'AI Reason': str,     # AI 筛选理由
    'rawtext': str,       # 原始文本描述
    'translated_text': str,
    'Publish Date': str,
    'Replies': int,
    'Reposts': int,
    'viewCount': int,
    'channel_name': str,
    'duration': float,    # 秒
    'Source Language': str,
    'Target Language': str,
    'Dubbing': int,
    'Status': str,
}
"""

import sys
from pathlib import Path
from abc import ABC, abstractmethod
from typing import List, Dict, Optional

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.paths import TASKS_EXCEL
from shared.state import load_visited
from shared.logger import console


# 标准数据字段
STANDARD_COLUMNS = [
    'Score', 'AI Score', 'Video File', 'title', 'Category', 'AI Reason', 'rawtext',
    'translated_text', 'Publish Date', 'Replies', 'Reposts', 'viewCount',
    'channel_name', 'duration', 'Source Language', 'Target Language',
    'Dubbing', 'Status',
]

# 默认值（确保每个字段都有值）
DEFAULT_VALUES = {
    'Score': 0,
    'AI Score': 0,
    'Video File': '',
    'title': '',
    'Category': 'Other',
    'AI Reason': '',
    'rawtext': '',
    'translated_text': '',
    'Publish Date': '',
    'Replies': 0,
    'Reposts': 0,
    'viewCount': 0,
    'channel_name': '',
    'duration': 0.0,
    'Source Language': 'en',
    'Target Language': '简体中文',
    'Dubbing': 0,
    'Status': '',
}


class BaseScraper(ABC):
    """
    采集器基类。

    子类只需要实现：
        name        : 平台名称（用于日志显示）
        fetch()     : 返回标准格式的视频列表
    """

    name: str = "Unknown"

    def __init__(self):
        self.visited_urls = load_visited()

    def is_new(self, url: str) -> bool:
        """检查 URL 是否为新视频（未在已访问集合中）"""
        return url not in self.visited_urls

    def validate_content(self, title: str) -> bool:
        """
        通用内容预筛选
        返回 True 表示内容有效（保留），False 表示应被过滤
        """
        # 1. 硬编码的通用黑名单 (低价值/营销内容)
        GLOBAL_BLACKLIST = [
            "Giveaway", "Winners", "Crypto", "NFT", "Airdrop", 
            "Live now", "Broadcast", "Streaming"
        ]
        
        # 2. 尝试从领域配置读取自定义黑名单
        try:
            from shared.domain import domain
            custom_blacklist = domain.get("scrapers.common_blacklist", [])
            blacklist = GLOBAL_BLACKLIST + custom_blacklist
        except:
            blacklist = GLOBAL_BLACKLIST

        title_lower = title.lower()
        for word in blacklist:
            if word.lower() in title_lower:
                # console.print(f"  [dim yellow]过滤无关内容: {title[:20]}... (包含 '{word}')[/dim yellow]")
                return False
        return True

    @abstractmethod
    def fetch(self) -> List[Dict]:
        """
        采集视频列表。

        Returns
        -------
        List[Dict] : 标准格式的视频数据字典列表
        """
        ...

    def make_entry(self, **kwargs) -> Dict:
        """
        创建标准化的视频数据条目。

        用法：
            return self.make_entry(
                Video_File=url,
                title=title,
                duration=120,
                ...
            )

        参数名中的下划线会被转为空格（如 Video_File -> "Video File"）
        """
        entry = DEFAULT_VALUES.copy()
        for k, v in kwargs.items():
            key = k.replace("_", " ") if k.replace("_", " ") in STANDARD_COLUMNS else k
            # 也支持直接用标准 key 名
            if key in entry:
                entry[key] = v
            elif k in entry:
                entry[k] = v
        return entry

    def run(self) -> List[Dict]:
        """
        执行采集（带异常处理和日志）。

        Returns
        -------
        List[Dict] : 采集到的新视频列表
        """
        try:
            results = self.fetch()
            if results:
                console.print(
                    f"  [green]✅ {self.name}[/green] 采集完成: "
                    f"[bold]{len(results)}[/bold] 条"
                )
            else:
                console.print(f"  [dim]⚪ {self.name}[/dim] 无新内容")
            return results or []
        except Exception as e:
            console.print(f"  [red]❌ {self.name}[/red] 失败: {e}")
            return []
