import os
import re
import shutil
import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from rapidfuzz import fuzz, process
import requests

# ==================== 配置区 ====================
API_KEY = os.environ.get("LONGCAT_API_KEY", "ak_1lt5CC7fR0YP9l47On12532E7b78k")
API_BASE_URL = 'https://api.longcat.chat/openai'
API_MODEL = 'LongCat-Flash-Chat'

# ==================== 路径配置 ====================
# 获取项目根目录 (该文件在 3_post_processing/media/common/ 下，深度为 4 层)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.absolute()
SOURCE_DIR = PROJECT_ROOT / "storage" / "ready_to_publish" 
TARGET_DIR = PROJECT_ROOT / "archives"
HISTORY_FILE = PROJECT_ROOT / "storage" / "tasks" / "organized_history.json"
TASKS_EXCEL = PROJECT_ROOT / "storage" / "tasks" / "tasks_setting.xlsx"

# ==================== 文件处理 ====================
def simple_read_topic(file_path: str) -> list:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return [item['response']['topic'] for item in data if 'response' in item and 'topic' in item['response']]
    except Exception:
        return []

def quick_read_srt(file_path: str) -> str:
    """极简读取 SRT 纯文本"""
    if not os.path.exists(file_path):
        return ""
    with open(file_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
        content = f.read()
    
    pattern = r'\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}'
    lines = [
        line.strip() for line in content.splitlines() 
        if line.strip() and not line.strip().isdigit() and not re.match(pattern, line)
    ]
    return "\n".join(lines)

def sanitize_filename(filename):
    """清理文件名，确保符合系统规范且不含非法字符"""
    if not filename: return "untitled"
    filename = re.sub(r'[\\/:*?\"<>|#\n\r\t]', '_', str(filename))
    return filename.strip()[:100]

# ==================== API 与翻译 ====================
def translate_with_api(text: str) -> str:
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    prompt = """你是一名资深政经主笔。请从提供的内容中提取最具冲击力的核心语录，并重塑为一个吸引人的中文标题。格式：人物：“语录” 描述。仅输出一行。"""
    data = {
        "model": API_MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text}
        ],
        "stream": False,
    }
    try:
        response = requests.post(f"{API_BASE_URL}/v1/chat/completions", headers=headers, json=data, timeout=30)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  ⚠️ API 请求失败: {e}")
        return None

def _normalize_for_match(text: str) -> str:
    """将文本规范化：去除标点、特殊字符、多余空格，统一小写，用于匹配比较"""
    text = re.sub(r'https?://\S+', '', text)           # 去除 URL
    text = re.sub(r'[^\w\s]', ' ', text)               # 去除所有标点符号
    text = re.sub(r'\s+', ' ', text).strip().lower()    # 合并空格并小写
    return text

def get_channel_info(file_path, target_name):
    """通过模糊匹配文件夹名，获取 Excel 中对应的频道名、描述和 AI 标题。

    匹配策略（优先级从高到低）：
      1. 匹配 `title` 列（Step 1 生成的中文标题，与文件夹名同源）
      2. 匹配 `rawtext` 列（原始英文推文，兜底）
    """
    try:
        if not os.path.exists(file_path):
            return {"channel_name": "精选新闻", "description": "暂无描述", "ai_title": None}

        df = pd.read_excel(file_path)
        normalized_target = _normalize_for_match(target_name)

        def _try_match(col: str, threshold: int = 75):
            if col not in df.columns:
                return None, None
            choices_raw = df[col].astype(str).tolist()
            choices_norm = [_normalize_for_match(c) for c in choices_raw]
            m = process.extractOne(
                normalized_target,
                choices_norm,
                scorer=fuzz.token_set_ratio,
            )
            if m and m[1] >= threshold:
                idx = choices_norm.index(m[0])
                return idx, m[1]
            return None, m[1] if m else 0

        # 1. 先匹配中文 title 列（文件夹名与 title_cn 同源，命中率高）
        idx, score = _try_match("title", threshold=75)
        col_used = "title"

        # 2. 若 title 列匹配失败，再尝试 rawtext 列
        if idx is None:
            idx2, score2 = _try_match("rawtext", threshold=80)
            if idx2 is not None:
                idx, score, col_used = idx2, score2, "rawtext"

        if idx is not None:
            row = df.iloc[idx]
            display = str(df[col_used].iloc[idx])[:60]
            print(f"  📎 Excel 匹配成功 [{col_used}] (score={score:.0f}): {display}...")
            return {
                "channel_name": row.get('channel_name', '精选新闻'),
                "description": row.get('rawtext', '暂无描述'),
                "ai_title": row.get('title', None),
                "original_link": row.get('Video File', ''),
                "ai_reason": row.get('AI Reason', ''),
                "category": row.get('Category', ''),
                "publish_date": row.get('Publish Date', ''),
                "translated_text": row.get('translated_text', ''),
                "suitability_score": row.get('Score', 'N/A'),
                "source_lang": row.get('Source Language', 'en'),
                "target_lang": row.get('Target Language', 'zh-CN')
            }
        else:
            print(f"  ⚠️ Excel 未找到匹配项 (best={score:.0f})")
    except Exception as e:
        print(f"  ⚠️ Excel 读取异常: {e}")
    return {"channel_name": "精选新闻", "description": "暂无描述", "ai_title": None}

def process_and_move_files():
    """主程序：整理 -> 重命名 -> 归档"""
    print(f"🚀 开始执行整理任务...")
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

    history = {}
    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass

    folders = [
        f for f in SOURCE_DIR.iterdir() 
        if f.is_dir() and f.name.upper() not in ["ERROR", "DONE", "FAILED", "ORGANIZED", "TEST_VIDEO_AUTO_IGNORE"]
    ]
    
    print(f"📊 发现 {len(folders)} 个待整理任务")
    
    for folder in folders:
        folder_name = folder.name
        if not (folder / "output_sub.mp4").exists(): continue
        if folder_name in history: continue

        print(f"\n--- 正在整理: {folder_name} ---")
        try:
            info = get_channel_info(TASKS_EXCEL, folder_name)
            raw_title = info.get('ai_title')
            
            # 提前准备 topic_list 防止 NameError
            topic_list = []
            json_path = folder / 'gpt_log' / 'summary.json'
            if json_path.exists():
                topic_list = simple_read_topic(str(json_path))

            if not raw_title:
                print(f"  ⚠️ Excel 中未找到 AI 标题，尝试即时生成...")
                srt_content = quick_read_srt(str(folder / 'trans.srt'))
                # 使用 topic_list 增强生成效果
                raw_title = translate_with_api(f"Original Title: {folder_name}\nTopics: {topic_list}\nTranscript: {srt_content[:1000]}")
            
            if not raw_title:
                raw_title = folder_name
                
            safe_title = sanitize_filename(raw_title)
            topic_folder = TARGET_DIR / safe_title
            topic_folder.mkdir(parents=True, exist_ok=True)
            
            # 拷贝视频
            shutil.copy2(str(folder / "output_sub.mp4"), str(topic_folder / f"{safe_title}.mp4"))
            
            # 拷贝封面
            cover = next(folder.glob("*_new*.*"), None) or next(folder.glob("*.jpg"), None)
            if cover:
                shutil.copy2(str(cover), str(topic_folder / f"{safe_title}{cover.suffix}"))
            
            meta_data = {
                "original_topic": folder_name,
                "translated_title": raw_title,
                "organize_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "channel": info.get('channel_name', ""),
                "src_folder": str(folder),
                "original_link": info.get('original_link', ''),
                "ai_reason": info.get('ai_reason', ''),
                "category": info.get('category', ''),
                "publish_date": str(info.get('publish_date', '')),
                "translated_text": info.get('translated_text', '')
            }
            (topic_folder / "metadata.json").write_text(json.dumps(meta_data, ensure_ascii=False, indent=2))
            
            # 举一反三：构建内容极其详尽的人类可读 metadata.txt
            score_val = info.get('suitability_score', 'N/A')
            if isinstance(score_val, (int, float)) and score_val > 1000:
                score_display = f"{score_val/1000:.1f} (AI核心分)"
            else:
                score_display = str(score_val)

            metadata_txt = f"""VideoLingo 视频发布存档报告
================================================================================
【核心信息】
中文标题: {raw_title}
内容分类: {info.get('category', '未分类')}
评估分值: {score_display}
推荐理由: {info.get('ai_reason', '无')}

--------------------------------------------------------------------------------
【原始推文内容】
{info.get('description', '无')}

【推文中文翻译】
{info.get('translated_text', '（暂无翻译）')}

--------------------------------------------------------------------------------
【溯源与技术信息】
原始链接: {info.get('original_link', '无')}
发布日期: {info.get('publish_date', '无')}
采集频道: {info.get('channel_name', '未知')}
源语言: {info.get('source_lang', 'en')} -> {info.get('target_lang', 'zh-CN')}
原始素材目录: {folder_name}
物理整理路径: {str(topic_folder)}
整理时间: {meta_data['organize_time']}
================================================================================
"""
            (topic_folder / "metadata.txt").write_text(metadata_txt, encoding='utf-8')
            history[folder_name] = meta_data
            HISTORY_FILE.write_text(json.dumps(history, ensure_ascii=False, indent=2))
            print(f"  ✨ 整理完成: {safe_title}")

        except Exception as e:
            print(f"  ❌ 出错: {e}")
            continue

if __name__ == "__main__":
    process_and_move_files()
