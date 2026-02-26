import os
import shutil
import re
import json
import requests
import random
from pathlib import Path
from rich.console import Console

console = Console()

# ==================== 配置区 ====================
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.absolute()
SOURCE_DIR = PROJECT_ROOT / "storage" / "processed"
TARGET_DIR = PROJECT_ROOT / "storage" / "ready_to_publish"
HISTORY_FILE = PROJECT_ROOT / "storage" / "tasks" / "organized_history.json"

# API 配置 (同步自 1_bili_upload.py)
API_KEY = 'ak_1lt5CC7fR0YP9l47On12532E7b78k'
API_BASE_URL = 'https://api.longcat.chat/openai'
API_MODEL = 'LongCat-Flash-Chat'

# ==================== 工具函数 ====================

def sanitize_filename(name):
    """清理文件名，去除特殊字符"""
    return re.sub(r'[\\/:*?"<>|]', '_', name).strip()

def simple_read_topic(file_path: str) -> list:
    if not os.path.exists(file_path): return []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            return [item['response']['topic'] for item in data if 'response' in item and 'topic' in item['response']]
        elif isinstance(data, dict) and 'response' in data and 'topic' in data['response']:
             return [data['response']['topic']]
        return []
    except: return []

def quick_read_srt(file_path: str) -> str:
    if not os.path.exists(file_path): return ""
    with open(file_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
        content = f.read()
    pattern = r'\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}'
    lines = [
        line.strip() for line in content.splitlines() 
        if line.strip() and not line.strip().isdigit() and not re.match(pattern, line)
    ]
    return "\n".join(lines)

def translate_with_api(text_content: str) -> str:
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    prompt = """
# Role
你是一名深耕“今日头条”、“腾讯新闻”、“参考消息”等资讯平台的资深政经主笔。你的目标受众是b站中国中年男性群体，关注大国博弈、地缘政治与宏观经济。
你的核心能力是：从琐碎的外媒原声中，提取**最具冲击力的核心观点**，并以“一语定乾坤”的风格重塑标题。

# Construction Rules (硬核政经爆款法则)
1. 固定格式： “一句核心语录” 关键人物，事件的简短定性描述。
2. 严禁使用半角符号，必须使用全角符号。
3. 全文严格在35字以内。
4. 仅输出标题一行，不要任何解释。
"""
    data = {
        "model": API_MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text_content}
        ],
    }
    try:
        response = requests.post(f"{API_BASE_URL}/v1/chat/completions", headers=headers, json=data, timeout=30)
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        console.print(f"⚠️ API 翻译出错: {e}", style="yellow")
        return None

def movie_files_to_topic():
    """将处理好的视频和封面整理到按主题命名的文件夹中，并进行翻译"""
    console.print(f"🚀 开始整理视频文件 (带 AI 翻译)...", style="bold blue")
    
    if not SOURCE_DIR.exists():
        console.print(f"❌ 源目录不存在: {SOURCE_DIR}", style="bold red")
        return

    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    # 加载已整理历史
    history = {}
    if HISTORY_FILE.exists():
        try: history = json.loads(HISTORY_FILE.read_text(encoding='utf-8'))
        except: pass

    processed_count = 0
    
    for folder in SOURCE_DIR.iterdir():
        if not folder.is_dir() or folder.name in history:
            continue
            
        topic_name = folder.name
        console.print(f"🔍 正在处理: {topic_name}")
        
        # 查找资源
        mp4_path = folder / "output_sub.mp4"
        if not mp4_path.exists():
            mp4_path = next(folder.glob("*.mp4"), None)
        if not mp4_path: continue
        
        cover_path = next(folder.glob("*.jpg"), None)
        if not cover_path: continue
            
        # 1. 提取翻译所需信息
        json_path = folder / "gpt_log" / "summary.json"
        topic_list = simple_read_topic(str(json_path))
        srt_path = folder / "trans.srt"
        srt_text = quick_read_srt(str(srt_path))
        
        # 2. 调用 AI 翻译标题
        prompt_content = f"原标题: {topic_name}\n讨论主题: {topic_list}\n部分字幕内容:\n{srt_text[:1000]}"
        translated_title = translate_with_api(prompt_content)
        
        if not translated_title:
            translated_title = topic_name # 保底使用原名
            console.print("⚠️ 翻译失败，使用原始名称", style="yellow")
        else:
            console.print(f"✨ AI 标题: [bold green]{translated_title}[/bold green]")

        # 3. 整理并存放
        clean_topic = sanitize_filename(translated_title)
        topic_folder = TARGET_DIR / clean_topic
        topic_folder.mkdir(exist_ok=True)
        
        try:
            shutil.copy2(mp4_path, topic_folder / f"{clean_topic}.mp4")
            shutil.copy2(cover_path, topic_folder / f"{clean_topic}.jpg")
            
            # 保存元数据
            meta_data = {
                "original_topic": topic_name,
                "translated_title": translated_title,
                "organize_time": str(Path(folder).stat().st_mtime)
            }
            (topic_folder / "metadata.json").write_text(json.dumps(meta_data, ensure_ascii=False, indent=2))
            
            # 记录历史
            history[topic_name] = meta_data
            HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2))
            
            console.print(f"✅ 已存入: {TARGET_DIR.name}/{clean_topic}")
            processed_count += 1
        except Exception as e:
            console.print(f"❌ 整理失败: {e}", style="bold red")

    console.print(f"\n✨ 整理完成，共新增 {processed_count} 个主题。", style="bold green")

if __name__ == "__main__":
    movie_files_to_topic()
