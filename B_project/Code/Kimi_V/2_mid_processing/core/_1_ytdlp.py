import os
import sys
import glob
import re
import subprocess
from core.utils import *

# 懒加载 YoutubeDL，避免每次下载都重新导入
_YoutubeDL = None

def _get_ytdlp():
    """返回 YoutubeDL 类（仅首次调用时导入）"""
    global _YoutubeDL
    if _YoutubeDL is None:
        from yt_dlp import YoutubeDL
        _YoutubeDL = YoutubeDL
    return _YoutubeDL

def sanitize_filename(filename):
    # Remove or replace illegal characters
    filename = re.sub(r'[<>:"/\\|?*]', '', filename)
    # Ensure filename doesn't start or end with a dot or space
    filename = filename.strip('. ')
    # Use default name if filename is empty
    return filename if filename else 'video'

def update_ytdlp():
    """手动升级 yt-dlp（不在每次下载时自动调用）"""
    global _YoutubeDL
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # 清除缓存，下次调用 _get_ytdlp() 时重新导入新版本
        if 'yt_dlp' in sys.modules:
            del sys.modules['yt_dlp']
        _YoutubeDL = None
        rprint("[green]yt-dlp updated successfully[/green]")
    except subprocess.CalledProcessError as e:
        rprint(f"[yellow]Warning: Failed to update yt-dlp: {e}[/yellow]")
    return _get_ytdlp()

def download_video_ytdlp(url, save_path='output', resolution='1080'):
    os.makedirs(save_path, exist_ok=True)
    ydl_opts = {
        'format': (
            f'bestvideo[height<={resolution}][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
            if resolution != 'best'
            else 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        ),
        'outtmpl': f'{save_path}/%(title)s.%(ext)s',
        'noplaylist': True,
        'writethumbnail': True,
        'postprocessors': [{'key': 'FFmpegThumbnailsConvertor', 'format': 'jpg'}],
    }

    # Read Youtube Cookie File
    cookies_path = load_key("youtube.cookies_path")
    if os.path.exists(cookies_path):
        ydl_opts["cookiefile"] = str(cookies_path)

    # 使用懒加载的 YoutubeDL（不在此处自动升级）
    YoutubeDL = _get_ytdlp()
    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    
    # Check and rename files after download
    for file in os.listdir(save_path):
        if os.path.isfile(os.path.join(save_path, file)):
            filename, ext = os.path.splitext(file)
            new_filename = sanitize_filename(filename)
            if new_filename != filename:
                os.rename(os.path.join(save_path, file), os.path.join(save_path, new_filename + ext))

def find_video_files(save_path='output', exit_if_multiple=True):
    video_files = [file for file in glob.glob(save_path + "/*") if os.path.splitext(file)[1][1:].lower() in load_key("allowed_video_formats")]
    # change \\ to /, this happen on windows
    if sys.platform.startswith('win'):
        video_files = [file.replace("\\", "/") for file in video_files]
    video_files = [file for file in video_files if not file.startswith("output/output")]
    if len(video_files) == 1:
        return video_files[0]
    if exit_if_multiple:
        raise ValueError(f"Number of videos found {len(video_files)} is not unique in {save_path}: {video_files}. Please check.")
    return video_files if video_files else None

if __name__ == '__main__':
    # Example usage
    url = input('Please enter the URL of the video you want to download: ')
    resolution = input('Please enter the desired resolution (360/480/720/1080, default 1080): ')
    resolution = int(resolution) if resolution.isdigit() else 1080
    download_video_ytdlp(url, resolution=resolution)
    print(f"🎥 Video has been downloaded to {find_video_files()}")
