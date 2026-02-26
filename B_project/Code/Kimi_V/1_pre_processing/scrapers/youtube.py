"""
youtube.py
----------
YouTube 视频采集器。

通过 YouTube Data API v3 获取指定频道的最新视频，
支持并发抓取、时长过滤、关键词黑名单。

配置来源：
  - 技术配置：configs/config.yaml → youtube_scrapers.api_key / concurrent_limit
  - 领域配置：configs/domains/<domain>.yaml → scrapers.youtube.*
"""

import asyncio
import aiohttp
import re
import sys
import platform
from pathlib import Path
from typing import List, Dict, Optional

PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.utils.config_utils import load_key
from shared.domain import domain
from _base_scraper import BaseScraper


class YouTubeScraper(BaseScraper):
    name = "YouTube"

    def __init__(self):
        super().__init__()
        # 技术配置（不随领域变化）
        self.api_key = load_key("youtube_scrapers.api_key")
        self.concurrent_limit = load_key("youtube_scrapers.concurrent_limit") or 5

        # 领域配置（从 domain profile 读取）
        yt_config = domain.get_scraper_config("youtube")
        self.channels = yt_config.get("channels", {})
        self.fetch_limit = yt_config.get("fetch_limit", 5)
        self.filters = yt_config.get("filters", {})

        self.base_url = "https://www.googleapis.com/youtube/v3"
        # Semaphore 在 __init__ 中创建，所有请求共享同一个限速器
        self._semaphore: Optional[asyncio.Semaphore] = None

    # ---------- API ----------

    async def _request(self, session, url, params=None) -> Optional[dict]:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.concurrent_limit)
        async with self._semaphore:
            try:
                async with session.get(url, params=params) as resp:
                    return await resp.json() if resp.status == 200 else None
            except Exception:
                return None

    async def _get_channel_videos(self, session, channel_id, channel_name) -> List[Dict]:
        search_params = {
            "part": "snippet", "channelId": channel_id, "order": "date",
            "maxResults": self.fetch_limit + 5, "type": "video", "key": self.api_key,
        }
        search_data = await self._request(session, f"{self.base_url}/search", search_params)
        if not search_data or "items" not in search_data:
            return []

        video_ids = [item["id"]["videoId"] for item in search_data["items"]]
        detail_params = {
            "part": "snippet,contentDetails,statistics",
            "id": ",".join(video_ids), "key": self.api_key,
        }
        detail_data = await self._request(session, f"{self.base_url}/videos", detail_params)

        results = []
        if detail_data and "items" in detail_data:
            items = sorted(detail_data["items"], key=lambda x: x["snippet"]["publishedAt"], reverse=True)
            for item in items:
                if len(results) >= self.fetch_limit:
                    break
                entry = self._parse(item, channel_name)
                if entry and self.is_new(entry["Video File"]):
                    results.append(entry)

        if results:
            print(f"    {channel_name}: 采集到 {len(results)} 个新视频")
        else:
            print(f"    {channel_name}: 未发现符合条件的新视频")

        return results

    def _parse(self, item, channel_name) -> Optional[Dict]:
        try:
            title = item["snippet"]["title"]

            # 关键词黑名单过滤
            blacklist = self.filters.get("blacklist_keywords", [])
            if any(w.upper() in title.upper() for w in blacklist):
                return None

            # 时长过滤
            duration = self._parse_duration(item["contentDetails"].get("duration", "PT0S"))
            min_d = self.filters.get("min_duration", 0)
            max_d = self.filters.get("max_duration", 99999)
            if not (min_d <= duration <= max_d):
                return None

            stats = item.get("statistics", {})
            url = f"https://www.youtube.com/watch?v={item['id']}"

            return self.make_entry(
                Score=0,
                title=title,
                rawtext=item["snippet"].get("description", "")[:500].replace("\n", " "),
                duration=duration,
                viewCount=int(stats.get("viewCount", 0)),
                Replies=int(stats.get("commentCount", 0)),
                channel_name=channel_name,
                **{"Video File": url, "Publish Date": item["snippet"]["publishedAt"]},
            )
        except Exception:
            return None

    @staticmethod
    def _parse_duration(dur_str: str) -> int:
        match = re.match(r"PT(\d+H)?(\d+M)?(\d+S)?", dur_str)
        if not match:
            return 0
        h = int(match.group(1)[:-1]) if match.group(1) else 0
        m = int(match.group(2)[:-1]) if match.group(2) else 0
        s = int(match.group(3)[:-1]) if match.group(3) else 0
        return h * 3600 + m * 60 + s

    # ---------- 异步主逻辑 ----------

    async def _fetch_async(self) -> List[Dict]:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
            tasks = [
                self._get_channel_videos(session, cid, name)
                for name, cid in self.channels.items()
            ]
            all_videos = []
            for coro in asyncio.as_completed(tasks):
                all_videos.extend(await coro)
            return all_videos

    # ---------- 标准接口 ----------

    def fetch(self) -> List[Dict]:
        if platform.system() == "Windows":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        return asyncio.run(self._fetch_async())


# 保持旧接口兼容
def fetch_video_main():
    return YouTubeScraper().run()


if __name__ == "__main__":
    res = fetch_video_main()
    print(f"Captured {len(res)} videos.")
