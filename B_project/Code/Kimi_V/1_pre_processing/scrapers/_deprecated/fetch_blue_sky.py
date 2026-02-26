import requests
import pandas as pd
import os
import sys
import logging
import time
import json
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from colorama import init, Fore, Style

# Fix path to support core imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(PROJECT_ROOT)
from core.utils.config_utils import load_key

# ============= 1. 核心抓取逻辑 =============
class BlueskyFetcher:
    def __init__(self):
        self.check_limit = load_key("bluesky_scrapers.check_limit")
        self.targets = load_key("bluesky_scrapers.targets")
        
        self.api_root = "https://public.api.bsky.app/xrpc"
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        self.session.mount('https://', HTTPAdapter(max_retries=retries))
        
        self.visited_urls = self._load_visited()

    def _load_visited(self) -> set:
        VISITED_LOG = 'storage/tasks/visited_videos.json'
        if os.path.exists(VISITED_LOG):
            try:
                with open(VISITED_LOG, 'r') as f:
                    return set(json.load(f))
            except: return set()
        return set()

    def _get_request(self, endpoint, params=None):
        try:
            url = f"{self.api_root}/{endpoint}"
            res = self.session.get(url, params=params, timeout=10)
            res.raise_for_status()
            return res.json()
        except: return None 

    def resolve_handle(self, handle):
        data = self._get_request("com.atproto.identity.resolveHandle", {"handle": handle})
        return data.get("did") if data else None

    def get_latest_videos(self, handle):
        did = self.resolve_handle(handle)
        if not did:
            return []

        params = {"actor": did, "limit": self.check_limit, "filter": "posts_with_video"}
        data = self._get_request("app.bsky.feed.getAuthorFeed", params)
        
        if not data or "feed" not in data:
            return []

        rows = []
        for item in data["feed"]:
            video_data = self._parse_item(item, handle)
            if video_data:
                if video_data['Video File'] not in self.visited_urls:
                    rows.append(video_data)
        return rows

    def _parse_item(self, item, handle):
        try:
            post = item.get("post", {})
            record = post.get("record", {})
            embed = post.get("embed", {})
            if embed.get('$type') != 'app.bsky.embed.video#view': return None

            uri = post.get("uri", "")
            post_id = uri.split("/")[-1]
            url = f"https://bsky.app/profile/{handle}/post/{post_id}"
            
            raw_text = record.get("text", "")
            publish_date = post.get("indexedAt", "").replace("T", " ").split(".")[0]

            return {
                'Video File': url,
                'title': raw_text.replace("\n", " ").strip()[:50],
                'rawtext': raw_text,
                'translated_text': "",
                'Publish Date': publish_date,
                'Replies': post.get("replyCount", 0),
                'Reposts': post.get("repostCount", 0),
                'viewCount': post.get("likeCount", 0), 
                'channel_name': handle,
                'duration': embed.get('video', {}).get('duration', 0),
                'Source Language': 'en',
                'Target Language': '简体中文',
                'Dubbing': 0,
                'Status': '',
                'Score': 0
            }
        except: return None

def fetch_bluesky_main():
    fetcher = BlueskyFetcher()
    all_videos = []
    if not fetcher.targets:
        return []

    for user in fetcher.targets:
        videos = fetcher.get_latest_videos(user)
        all_videos.extend(videos)
    return all_videos

if __name__ == "__main__":
    res = fetch_bluesky_main()
    print(f"Captured {len(res)} videos.")
