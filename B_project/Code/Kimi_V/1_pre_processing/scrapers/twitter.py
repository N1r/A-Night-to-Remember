"""
twitter.py
----------
X (Twitter) 视频采集器。

通过 twikit 库抓取指定博主的推文中的视频，
支持原创/转发/引用三种来源。

配置来源：
  - 账号列表：configs/domains/<domain>.yaml → scrapers.twitter.accounts
  - Cookie 路径：1_pre_processing/scrapers/twitter_cookies.json
"""

import asyncio
import json
import os
import random
import sys
import platform
from pathlib import Path
from typing import List, Dict

PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from twikit import Client
from core.utils.config_utils import load_key
from shared.paths import TASKS_EXCEL, PRE_PROCESSING
from shared.domain import domain
from _base_scraper import BaseScraper


# 从领域配置读取账号列表
def _get_accounts() -> list:
    accounts = domain.get("scrapers.twitter.accounts", [])
    return accounts if accounts else []


# Cookie 文件路径
COOKIES_PATH = PRE_PROCESSING / "scrapers" / "twitter_cookies.json"
if not COOKIES_PATH.exists():
    COOKIES_PATH = PRE_PROCESSING / "scrapers" / "cookies.json"


def _get_val(obj, key, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _parse_counts(val):
    if not val:
        return 0
    if isinstance(val, int):
        return val
    val = str(val).upper().replace(",", "").strip()
    try:
        if "K" in val:
            return int(float(val.replace("K", "")) * 1000)
        if "M" in val:
            return int(float(val.replace("M", "")) * 1000000)
        return int(float(val))
    except Exception:
        return 0


class TwitterScraper(BaseScraper):
    name = "X (Twitter)"

    def __init__(self):
        super().__init__()
        self.client = Client("en-US")
        self._load_cookies()

    def _load_cookies(self):
        """加载 Twitter Cookie（兼容 Playwright 格式和 twikit 格式）"""
        if not COOKIES_PATH.exists():
            raise FileNotFoundError(f"找不到 Cookie 文件: {COOKIES_PATH}")

        try:
            self.client.load_cookies(str(COOKIES_PATH))
        except Exception:
            # Playwright 格式转 twikit 格式
            with open(COOKIES_PATH, "r", encoding="utf-8") as f:
                playwright_cookies = json.load(f)
            twikit_cookies = {c["name"]: c["value"] for c in playwright_cookies}
            temp_path = str(COOKIES_PATH) + ".temp.json"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(twikit_cookies, f)
            try:
                self.client.load_cookies(temp_path)
            finally:
                # 无论成功或异常，均确保临时文件被删除
                if os.path.exists(temp_path):
                    os.remove(temp_path)

    async def _fetch_account(self, screen_name: str, count: int = 20) -> List[Dict]:
        """抓取单个账号的视频"""
        results = []
        try:
            from shared.logger import console
            console.print(f"    [dim]🔍 正在抓取 X 用户: @{screen_name}...[/dim]")
            await asyncio.sleep(random.uniform(1, 2))
            user = await self.client.get_user_by_screen_name(screen_name)

            # 混合抓取 Tweets + Media
            all_tweets = []
            for tab in ["Tweets", "Media"]:
                try:
                    # console.print(f"      [dim]抓取 {tab} 标签页...[/dim]")
                    ts = await user.get_tweets(tab, count=count)
                    if ts:
                        all_tweets.extend(ts)
                    await asyncio.sleep(1)
                except Exception:
                    pass
            
            # console.print(f"      [dim]获取到 {len(all_tweets)} 条推文，正在去重...[/dim]")

            # 去重排序
            unique = sorted(
                {t.id: t for t in all_tweets}.values(),
                key=lambda x: _get_val(x, "created_at", ""),
                reverse=True,
            )
            
            # console.print(f"      [dim]去重后剩余 {len(unique)} 条，开始解析视频...[/dim]")

            for tweet in unique:
                created_at = _get_val(tweet, "created_at", "unknown")
                is_retweet = hasattr(tweet, "retweeted_tweet") and tweet.retweeted_tweet
                is_quote = hasattr(tweet, "quoted_tweet") and tweet.quoted_tweet

                target_tweet = tweet
                source_type = "原创"
                if is_retweet:
                    target_tweet = tweet.retweeted_tweet
                    source_type = "转发"
                elif is_quote and not (hasattr(tweet, "media") and tweet.media):
                    target_tweet = tweet.quoted_tweet
                    source_type = "引用"

                media = _get_val(target_tweet, "media")
                if not media:
                    continue

                video_url = None
                v_info = {}
                for media_item in media:
                    m_type = _get_val(media_item, "type")
                    if m_type in ["video", "animated_gif"]:
                        v_info = _get_val(media_item, "video_info") or media_item
                        variants = _get_val(v_info, "variants", [])
                        # 过滤掉 bitrate=0 的 HTTP 流变体（m3u8 等），只保留直链 MP4
                        valid = [
                            {"url": _get_val(v, "url"), "bitrate": _get_val(v, "bitrate", 0)}
                            for v in variants
                            if _get_val(v, "url") and _get_val(v, "bitrate", 0) > 0
                        ]
                        # 若过滤后为空（全为 HTTP 流），降级使用任何可用 URL
                        if not valid:
                            valid = [
                                {"url": _get_val(v, "url"), "bitrate": 0}
                                for v in variants if _get_val(v, "url")
                            ]
                        if valid:
                            video_url = max(valid, key=lambda x: x["bitrate"])["url"]
                            break

                if not video_url or not self.is_new(video_url):
                    continue

                duration_ms = _get_val(v_info, "duration_ms", 0)
                # 尝试多个来源获取时长
                if duration_ms:
                    duration_sec = duration_ms / 1000
                else:
                    # 尝试从 tweet 对象的其他字段获取
                    # 有时 twikit 将 duration 直接放在 media 对象中
                    duration_ms_alt = _get_val(media_item, "duration_ms", 0)
                    if duration_ms_alt:
                        duration_sec = duration_ms_alt / 1000
                    else:
                        duration_sec = _get_val(target_tweet, "duration", 0)

                # 如果仍然获取不到时长，让其保持为 0，以便 workflow_1_pre.py 调用 yt-dlp 补全
                # 但需要注意的是，直接使用 video_url (mp4直链) 可能无法通过 yt-dlp 获取时长
                # 更好的方式是保存原始推文链接
                
                # 构造原始推文链接
                tweet_url = f"https://x.com/{screen_name}/status/{target_tweet.id}"
                
                # 内容预筛选
                title_text = _get_val(target_tweet, "text", "").replace("\n", " ")
                if not self.validate_content(title_text):
                    continue

                entry = self.make_entry(
                    title=title_text[:100],
                    rawtext=title_text,
                    duration=duration_sec,
                    viewCount=_parse_counts(_get_val(target_tweet, "view_count", 0)),
                    Reposts=_parse_counts(_get_val(target_tweet, "retweet_count", 0)),
                    channel_name=f"X_{screen_name}",
                    **{
                        "Video File": video_url, # 这里仍然保存 MP4 直链供下载使用
                        "Original URL": tweet_url, # 保存原始链接用于元数据补全
                        "Publish Date": str(created_at),
                        "Target Language": load_key("target_language") or "简体中文",
                    },
                )
                entry["source_type"] = source_type
                results.append(entry)
                # console.print(f"      [dim green]+ 发现视频: {entry['title'][:20]}...[/dim green]")

            if results:
                console.print(f"    [dim green]@{screen_name}: 采集到 {len(results)} 个新视频[/dim green]")
            else:
                console.print(f"    [dim]@{screen_name}: 未发现新视频[/dim]")

        except Exception as e:
            from shared.logger import console
            console.print(f"  [red]获取 @{screen_name} 失败: {e}[/red]")

        return results

    async def _fetch_async(self) -> List[Dict]:
        from shared.logger import create_progress
        accounts = _get_accounts()
        if not accounts:
            return []
        all_videos = []
        with create_progress() as progress:
            task = progress.add_task("[cyan]采集 X 数据...", total=len(accounts))
            for screen_name in accounts:
                progress.update(task, description=f"🔍 处理 X: @{screen_name}")
                videos = await self._fetch_account(screen_name, count=20)
                all_videos.extend(videos)
                progress.advance(task)
        return all_videos

    def fetch(self) -> List[Dict]:
        if platform.system() == "Windows":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        return asyncio.run(self._fetch_async())


# 保持旧接口兼容
def fetch_X_main():
    return TwitterScraper().run()


if __name__ == "__main__":
    res = fetch_X_main()
    print(f"Captured {len(res)} videos.")
