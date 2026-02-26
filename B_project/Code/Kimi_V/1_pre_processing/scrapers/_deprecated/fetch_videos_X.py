import asyncio
import json
import os
import random
import sys
import pandas as pd
import platform
import re
from twikit import Client
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.panel import Panel

# 设置项目根目录与路径
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(os.path.join(PROJECT_ROOT, "2_mid_processing"))

from core.utils.config_utils import load_key

# Initialize Rich Console
console = Console()

# 预设的高质量政治类切片博主列表
POLITICS_ACCOUNTS = [
    'Acyn', 'atrupar', 'clashreport', 'mrjeffu', 'joeroganhq'
]

# 适配项目结构的路径
OUTPUT_FILE = os.path.join(PROJECT_ROOT, 'storage', 'tasks', 'tasks_setting.xlsx')
COOKIES_PATH = os.path.join(PROJECT_ROOT, '1_pre_processing', 'scrapers', 'twitter_cookies.json')
if not os.path.exists(COOKIES_PATH):
    COOKIES_PATH = os.path.join(PROJECT_ROOT, '1_pre_processing', 'scrapers', 'cookies.json')

def get_existing_ids(filepath):
    """从现有的 Excel 文件中读取已抓取的视频 URL"""
    if os.path.exists(filepath):
        try:
            df = pd.read_excel(filepath)
            if 'Video File' in df.columns:
                return set(df['Video File'].astype(str).tolist())
        except Exception as e:
            console.print(f"[yellow]读取现有文件失败: {e}[/yellow]")
    return set()

def get_val(obj, key, default=None):
    if obj is None: return default
    if isinstance(obj, dict): return obj.get(key, default)
    return getattr(obj, key, default)

def parse_counts(val):
    if not val: return 0
    if isinstance(val, int): return val
    val = str(val).upper().replace(',', '').strip()
    try:
        if 'K' in val: return int(float(val.replace('K', '')) * 1000)
        if 'M' in val: return int(float(val.replace('M', '')) * 1000000)
        return int(float(val))
    except: return 0

async def fetch_account_videos(client, screen_name, seen_urls, count=20):
    account_videos = []
    
    try:
        await asyncio.sleep(random.uniform(1, 2))
        user = await client.get_user_by_screen_name(screen_name)
        
        # 混合抓取：Tweets 栏目和 Media 栏目
        all_tweets = []
        for tab in ['Tweets', 'Media']:
            try:
                ts = await user.get_tweets(tab, count=count)
                if ts: all_tweets.extend(ts)
                await asyncio.sleep(1)
            except: pass

        # 根据 ID 去重并按时间排序
        unique_tweets = sorted({t.id: t for t in all_tweets}.values(), 
                               key=lambda x: get_val(x, 'created_at', ''), reverse=True)
        
        new_count = 0
        for tweet in unique_tweets:
            created_at = get_val(tweet, 'created_at', 'unknown')
            
            is_retweet = hasattr(tweet, 'retweeted_tweet') and tweet.retweeted_tweet
            is_quote = hasattr(tweet, 'quoted_tweet') and tweet.quoted_tweet
            
            target_tweet = tweet
            source_type = "原创"
            if is_retweet:
                target_tweet = tweet.retweeted_tweet
                source_type = "转发"
            elif is_quote and not (hasattr(tweet, 'media') and tweet.media):
                target_tweet = tweet.quoted_tweet
                source_type = "引用"

            media = get_val(target_tweet, 'media')
            if media:
                video_url = None
                v_info = {}
                for media_item in media:
                    m_type = get_val(media_item, 'type')
                    if m_type in ['video', 'animated_gif']:
                        v_info = get_val(media_item, 'video_info')
                        if not v_info: v_info = media_item
                            
                        variants = get_val(v_info, 'variants', [])
                        valid = []
                        for v in variants:
                            v_url = get_val(v, 'url')
                            v_bitrate = get_val(v, 'bitrate', 0)
                            if v_url: valid.append({'url': v_url, 'bitrate': v_bitrate or 0})
                        
                        if valid:
                            video_url = max(valid, key=lambda x: x['bitrate'])['url']
                            break
                
                if video_url:
                    if video_url in seen_urls:
                        continue
                    
                    likes = get_val(target_tweet, 'favorite_count', 0)
                    retweets = get_val(target_tweet, 'retweet_count', 0)
                    views = get_val(target_tweet, 'view_count', 0)
                    
                    duration_ms = get_val(v_info, 'duration_ms', 0)
                    duration_sec = duration_ms / 1000 if duration_ms else 0
                    if duration_sec == 0:
                        duration_sec = get_val(target_tweet, 'duration', 0)

                    data = {
                        'Score': 0,
                        'Video File': video_url,
                        'title': get_val(target_tweet, 'text', '').replace('\n', ' ')[:100],
                        'rawtext': get_val(target_tweet, 'text', '').replace('\n', ' '),
                        'translated_text': "",
                        'Publish Date': created_at,
                        'Replies': 0,
                        'Reposts': parse_counts(retweets),
                        'viewCount': parse_counts(views),
                        'channel_name': f"X_{screen_name}",
                        'source_type': source_type,
                        'duration': duration_sec,
                        'Source Language': 'en',
                        'Target Language': load_key("target_language"),
                        'Dubbing': 0,
                        'Status': ''
                    }
                    account_videos.append(data)
                    seen_urls.add(video_url)
                    new_count += 1
            
    except Exception as e:
        console.print(f"  [bold red]获取 @{screen_name} 失败: {e}[/bold red]")
        
    return account_videos

async def main():
    client = Client('en-US')
    if not os.path.exists(COOKIES_PATH):
        console.print(f"[bold red]错误: 找不到 {COOKIES_PATH}[/bold red]")
        return []
    
    try:
        client.load_cookies(COOKIES_PATH)
    except Exception as e:
        try:
            with open(COOKIES_PATH, 'r', encoding='utf-8') as f:
                playwright_cookies = json.load(f)
            twikit_cookies = {c['name']: c['value'] for c in playwright_cookies}
            temp_cookies_path = COOKIES_PATH + ".temp.json"
            with open(temp_cookies_path, 'w', encoding='utf-8') as f:
                json.dump(twikit_cookies, f)
            client.load_cookies(temp_cookies_path)
            os.remove(temp_cookies_path)
        except Exception as e2:
            console.print(f"[bold red]Cookie 加载失败: {e2}[/bold red]")
            return []
    
    seen_urls = get_existing_ids(OUTPUT_FILE)
    all_new_videos = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("[cyan]采集 X 数据...", total=len(POLITICS_ACCOUNTS))
        for screen_name in POLITICS_ACCOUNTS:
            progress.update(task, description=f"🔍 正在处理 X: @{screen_name}")
            videos = await fetch_account_videos(client, screen_name, seen_urls, count=20)
            all_new_videos.extend(videos)
            progress.advance(task)

    return all_new_videos

def fetch_X_main():
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    return asyncio.run(main())

if __name__ == '__main__':
    res = fetch_X_main()
    print(f"Captured {len(res)} videos.")
