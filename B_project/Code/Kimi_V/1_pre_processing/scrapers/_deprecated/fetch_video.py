import asyncio
import aiohttp
import pandas as pd
import re
import os
import sys
import platform
import time
import json
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from tqdm.asyncio import tqdm
from colorama import init, Fore, Style

# Fix path to support core imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(PROJECT_ROOT)
from core.utils.config_utils import load_key

# ============= 1. API 交互逻辑 =============
class YouTubeAPI:
    def __init__(self):
        self.api_key = load_key("youtube_scrapers.api_key")
        self.channels = load_key("youtube_scrapers.channels")
        self.fetch_limit = load_key("youtube_scrapers.fetch_limit")
        self.filters = load_key("youtube_scrapers.filters")
        self.concurrent_limit = load_key("youtube_scrapers.concurrent_limit")
        
        self.base_url = "https://www.googleapis.com/youtube/v3"
        self.session: Optional[aiohttp.ClientSession] = None
        self.semaphore = asyncio.Semaphore(self.concurrent_limit)
        
        # 加载已访问历史
        self.visited_urls = self._load_visited()

    def _load_visited(self) -> set:
        VISITED_LOG = 'storage/tasks/visited_videos.json'
        if os.path.exists(VISITED_LOG):
            try:
                with open(VISITED_LOG, 'r') as f:
                    return set(json.load(f))
            except: return set()
        return set()

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session: await self.session.close()

    async def _make_request(self, url: str, params: dict = None) -> Optional[dict]:
        async with self.semaphore:
            try:
                async with self.session.get(url, params=params) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        return None
            except:
                return None

    async def get_latest_videos(self, channel_id: str, channel_name: str) -> List[Dict]:
        search_params = {
            "part": "snippet", "channelId": channel_id, "order": "date",
            "maxResults": self.fetch_limit + 5, "type": "video", "key": self.api_key
        }
        search_data = await self._make_request(f"{self.base_url}/search", search_params)
        if not search_data or 'items' not in search_data:
            return []

        video_ids = [item['id']['videoId'] for item in search_data['items']]
        videos_params = {
            "part": "snippet,contentDetails,statistics",
            "id": ",".join(video_ids), "key": self.api_key
        }
        videos_data = await self._make_request(f"{self.base_url}/videos", videos_params)
        
        valid_videos = []
        if videos_data and 'items' in videos_data:
            items = sorted(videos_data['items'], key=lambda x: x['snippet']['publishedAt'], reverse=True)
            for item in items:
                if len(valid_videos) >= self.fetch_limit: break
                video = self._parse_video_data(item, channel_name)
                if video: 
                    if video['Video File'] not in self.visited_urls:
                        valid_videos.append(video)
        
        return valid_videos

    def _parse_video_data(self, item: Dict, channel_name: str) -> Optional[Dict]:
        try:
            title = item['snippet']['title']
            url = f"https://www.youtube.com/watch?v={item['id']}"
            
            # 关键词黑名单过滤
            blacklist = self.filters.get('blacklist_keywords', [])
            if any(word.upper() in title.upper() for word in blacklist):
                return None

            # 时长过滤
            duration = self._parse_duration(item['contentDetails'].get('duration', 'PT0S'))
            if not (self.filters['min_duration'] <= duration <= self.filters['max_duration']):
                return None
            
            stats = item.get('statistics', {})
            return {
                'Video File': url,
                'title': title,
                'rawtext': item['snippet'].get('description', '')[:500].replace('\n', ' '),
                'translated_text': "",
                'Publish Date': item['snippet']['publishedAt'],
                'Replies': int(stats.get('commentCount', 0)),
                'Reposts': 0, 
                'viewCount': int(stats.get('viewCount', 0)),
                'channel_name': channel_name,
                'duration': duration,
                'Source Language': 'en',
                'Target Language': '简体中文',
                'Dubbing': 0,
                'Status': '',
                'Score': 0
            }
        except: return None

    @staticmethod
    def _parse_duration(duration_str: str) -> int:
        match = re.match(r'PT(\d+H)?(\d+M)?(\d+S)?', duration_str)
        if not match: return 0
        h = int(match.group(1)[:-1]) if match.group(1) else 0
        m = int(match.group(2)[:-1]) if match.group(2) else 0
        s = int(match.group(3)[:-1]) if match.group(3) else 0
        return h * 3600 + m * 60 + s

async def fetch_video_main_async():
    async with YouTubeAPI() as api:
        tasks = [api.get_latest_videos(cid, name) for name, cid in api.channels.items()]
        all_videos = []
        for coro in asyncio.as_completed(tasks):
            all_videos.extend(await coro)
        return all_videos

def fetch_video_main():
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(fetch_video_main_async())

if __name__ == "__main__":
    res = fetch_video_main()
    print(f"Captured {len(res)} videos.")
