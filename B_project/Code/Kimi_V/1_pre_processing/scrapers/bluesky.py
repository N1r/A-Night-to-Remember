"""
bluesky.py
----------
Bluesky 视频采集器。

通过 Bluesky 公共 API 抓取指定用户的视频帖子。
无需认证（使用公开 API），支持重试机制。

配置来源：configs/config.yaml → bluesky_scrapers.*
"""

import sys
import requests
from pathlib import Path
from typing import List, Dict, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.domain import domain
from _base_scraper import BaseScraper


class BlueskyScraper(BaseScraper):
    name = "Bluesky"

    def __init__(self):
        super().__init__()
        # 领域配置（从 domain profile 读取）
        bs_config = domain.get_scraper_config("bluesky")
        self.check_limit = bs_config.get("check_limit", 10)
        self.targets = bs_config.get("targets", [])
        self.api_root = "https://public.api.bsky.app/xrpc"

        # 带重试的 session
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        self.session.mount("https://", HTTPAdapter(max_retries=retries))

    def _get(self, endpoint, params=None) -> Optional[dict]:
        try:
            resp = self.session.get(f"{self.api_root}/{endpoint}", params=params, timeout=10)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None

    def _resolve_handle(self, handle: str) -> Optional[str]:
        data = self._get("com.atproto.identity.resolveHandle", {"handle": handle})
        return data.get("did") if data else None

    def _get_user_videos(self, handle: str) -> List[Dict]:
        from shared.logger import console
        console.print(f"    [dim]🔍 正在抓取 Bluesky 用户: {handle}...[/dim]")
        
        did = self._resolve_handle(handle)
        if not did:
            console.print(f"      [dim red]无法解析用户 DID: {handle}[/dim red]")
            return []
        
        # Bluesky API: getAuthorFeed
        # 参数: actor, limit, filter (posts_with_video, posts_no_replies, etc)
        # 注意: 'filter' 参数在某些版本的 API 中可能不可用或行为不同
        params = {"actor": did, "limit": self.check_limit, "filter": "posts_with_video"}
        
        try:
            # getAuthorFeed 返回的是 FeedViewPost 列表
            resp = self.session.get(f"{self.api_root}/app.bsky.feed.getAuthorFeed", params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
             return []

        if not data or "feed" not in data:
            console.print(f"      [dim]未获取到 Feed 数据[/dim]")
            return []

        results = []
        for item in data["feed"]:
            # item 结构: { "post": { "uri": "...", "cid": "...", "record": {...}, "embed": {...} }, ... }
            post = item.get("post", {})
            entry = self._parse_item(post, handle)
            if entry and self.is_new(entry["Video File"]):
                results.append(entry)
        
        if results:
            console.print(f"    [dim green]{handle}: 采集到 {len(results)} 个新视频[/dim green]")
        else:
            console.print(f"    [dim]{handle}: 未发现新视频[/dim]")
            
        return results

    def _parse_item(self, post, handle) -> Optional[Dict]:
        try:
            record = post.get("record", {})
            embed = post.get("embed", {})
            
            # 检查是否有视频嵌入
            # 类型通常是 app.bsky.embed.video#view (在 feed 中) 或 app.bsky.embed.video (在 record 中)
            embed_type = embed.get("$type", "")
            
            # 只有当 embed 类型明确为视频时才处理
            if "app.bsky.embed.video" not in embed_type:
                return None

            uri = post.get("uri", "")
            # uri 格式: at://did:plc:.../app.bsky.feed.post/3lb...
            if not uri: return None
            
            post_id = uri.split("/")[-1]
            url = f"https://bsky.app/profile/{handle}/post/{post_id}"
            
            text = record.get("text", "")
            
            # 内容预筛选
            if not self.validate_content(text):
                return None

            publish_date = post.get("indexedAt", "").replace("T", " ").split(".")[0]
            
            # 尝试获取时长
            # 在 feed view 中，embed 可能是 View 类型，结构不同
            # embed: { "$type": "app.bsky.embed.video#view", "cid": "...", "playlist": "...", "thumbnail": "...", "aspectRatio": {...} }
            # 注意: Bluesky API 的 #view 类型通常不直接返回 duration
            # 我们可能需要依赖外部工具 (yt-dlp) 来获取准确时长，或者如果 record 中有 metadata
            
            duration = 0
            # 尝试从 record.embed 中获取 (原始数据)
            if "embed" in record and record["embed"].get("$type") == "app.bsky.embed.video":
                # record.embed 结构可能包含 ref, 但通常没有 duration
                pass
            
            # 暂时 Bluesky API 返回的 feed 中很难直接找到 duration
            # 保持为 0，依靠 workflow_1_pre.py 中的 yt-dlp 补全逻辑
            
            return self.make_entry(
                title=text.replace("\n", " ").strip()[:50] or "No Title",
                rawtext=text,
                duration=duration,
                viewCount=post.get("likeCount", 0),
                Replies=post.get("replyCount", 0),
                Reposts=post.get("repostCount", 0),
                channel_name=handle,
                **{"Video File": url, "Publish Date": publish_date},
            )
        except Exception:
            return None

    def fetch(self) -> List[Dict]:
        if not self.targets:
            return []

        all_videos = []
        for handle in self.targets:
            videos = self._get_user_videos(handle)
            all_videos.extend(videos)
        return all_videos


# 保持旧接口兼容
def fetch_bluesky_main():
    return BlueskyScraper().run()


if __name__ == "__main__":
    res = fetch_bluesky_main()
    print(f"Captured {len(res)} videos.")
