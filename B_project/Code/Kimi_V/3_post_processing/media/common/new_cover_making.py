import os
import re
import json
import random
import subprocess
import requests
import pandas as pd
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from rapidfuzz import fuzz

# 尝试导入 jieba 进行智能名词识别
try:
    import jieba
    import jieba.posseg as pseg
    HAS_JIEBA = True
except ImportError:
    HAS_JIEBA = False
    print("🚩 提示：未安装 jieba，将使用基础随机逻辑。建议运行 'pip install jieba'")

# ==================== 全局常量与配置 ====================
# 获取项目根目录 (3层深度: 3_post_processing/media/common)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'storage', 'ready_to_publish')
COVER_SUFFIX = '.jpg'
NEW_COVER_SUFFIX = '.png'

# ===== 导入 aesthetics 配置 =====
import sys as _sys
if PROJECT_ROOT not in _sys.path:
    _sys.path.insert(0, PROJECT_ROOT)

try:
    from shared.aesthetics import aesthetics
    _cover_cfg = aesthetics.get_cover_config()
    _AESTHETICS_OK = True
except Exception:
    _cover_cfg = {}
    _AESTHETICS_OK = False

# 尺寸
TARGET_WIDTH = _cover_cfg.get("width", 1920)
TARGET_HEIGHT = _cover_cfg.get("height", 1080)

# API 配置（优先读取环境变量，回退到默认值）
API_KEY = os.environ.get("LONGCAT_API_KEY", "ak_1lt5CC7fR0YP9l47On12532E7b78k")
API_BASE_URL = 'https://api.longcat.chat/openai'
API_MODEL = 'LongCat-Flash-Chat'

# 视觉规范（从 aesthetics 读取，带 fallback）
HIGHLIGHT_COLOR = _cover_cfg.get("highlight_color", "#FFD700")
NORMAL_COLOR    = _cover_cfg.get("normal_color", "#FFFFFF")
ACCENT_COLOR    = _cover_cfg.get("accent_color", "#E21918")
_bg_box = _cover_cfg.get("bg_box_color", [0, 0, 0, 230])
BG_BOX_COLOR    = tuple(_bg_box) if isinstance(_bg_box, list) else (0, 0, 0, 230)
BLUR_RADIUS     = _cover_cfg.get("blur_radius", 2)
OVERLAY_ALPHA   = _cover_cfg.get("overlay_alpha", 80)

# 标签文字
TAG_TEXT     = _cover_cfg.get("tag_text", " 🌐 GLOBAL NEWS • 深度直击 ")
TAG_FONTSIZE = _cover_cfg.get("tag_fontsize", 45)
TAG_Y        = _cover_cfg.get("tag_position_y", 60)

# 标题
TITLE_FONTSIZE = _cover_cfg.get("title_fontsize", 135)
TITLE_MAX_LINES = _cover_cfg.get("title_max_lines", 2)
TITLE_PADDING  = _cover_cfg.get("title_padding", 50)
TITLE_BAR_W    = _cover_cfg.get("title_bar_width", 20)

# 自动选择字体（优先从 aesthetics 配置读取）
def get_font_path():
    # 优先使用 aesthetics 配置中的字体路径
    search_list = []
    if _AESTHETICS_OK:
        for p in aesthetics.get_font_paths():
            # 支持绝对路径和相对于 PROJECT_ROOT 的路径
            if os.path.isabs(p):
                search_list.append(p)
            else:
                search_list.append(os.path.join(PROJECT_ROOT, p))

    # 静态回退字体
    search_list.extend([
        os.path.join(PROJECT_ROOT, "storage/fonts/HarmonyOS_Sans_SC_Bold.ttf"),
        os.path.join(PROJECT_ROOT, "storage/fonts/HYWenHei-65W.ttf"),
        os.path.join(PROJECT_ROOT, "storage/fonts/NotoSansSC-Bold.ttf"),
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc",
        "SourceHanSansSC-Bold.otf",
        "SimHei.ttf",
        "arial.ttf"
    ])
    for fp in search_list:
        if os.path.exists(fp): return fp
    return "arial.ttf"

FONT_PATH = get_font_path()

def get_font(size):
    return ImageFont.truetype(FONT_PATH, size)

# ==================== 0. 信息提取工具 ====================

def simple_read_topic(file_path: str) -> list:
    """读取 gpt_log 下的 summary.json 获取 topic"""
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            return [item['response']['topic'] for item in data if 'response' in item and 'topic' in item['response']]
        elif isinstance(data, dict) and 'response' in data and 'topic' in data['response']:
             return [data['response']['topic']]
        return []
    except Exception:
        return []

def quick_read_srt(file_path: str) -> str:
    """极简读取 SRT 纯文本"""
    if not os.path.exists(file_path): return ""
    with open(file_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
        content = f.read()
    pattern = r'\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}'
    lines = [
        line.strip() for line in content.splitlines() 
        if line.strip() and not line.strip().isdigit() and not re.match(pattern, line)
    ]
    return "\n".join(lines)

def find_channel_by_fuzzy_match(excel_path: str, target_title: str, min_similarity=80):
    """根据文件夹名模糊匹配 Excel 中的频道名"""
    if not os.path.exists(excel_path):
        return None
    try:
        df = pd.read_excel(excel_path)
        best_match, best_score = None, 0
        for _, row in df.iterrows():
            current_title = str(row['title'])
            similarity = fuzz.ratio(target_title.lower(), current_title.lower())
            if similarity > best_score and similarity >= min_similarity:
                best_score, best_match = similarity, row['channel_name']
        return best_match
    except Exception:
        return None

# ==================== 1. 智能高亮逻辑 ====================

def get_random_noun_highlight(text):
    """提取标题中的核心名词实体，避开虚词"""
    # 移除 [熟肉] 等干扰
    clean_text = re.sub(r'\[.*?\]', '', text)
    if HAS_JIEBA:
        words = pseg.cut(clean_text)
        nouns = [w.word for w in words if w.flag in ['n', 'nr', 'ns', 'nt', 'nz'] and len(w.word) > 1]
        if nouns:
            return random.choice(nouns)
    STOP_WORDS = ["的", "了", "在", "是", "被", "已经", "不仅", "甚至", "而且"]
    parts = re.findall(r'[\u4e00-\u9fa5]{2,4}', clean_text)
    valid_parts = [p for p in parts if p not in STOP_WORDS]
    return random.choice(valid_parts) if valid_parts else None

# ==================== 2. 封面绘图核心 ====================

def wrap_text_styled(text, font, max_width):
    lines = []
    current_line = ""
    for char in text:
        if font.getlength(current_line + char) <= max_width:
            current_line += char
        else:
            lines.append(current_line)
            current_line = char
    lines.append(current_line)
    return lines[:TITLE_MAX_LINES]

def draw_text_line_centered(draw, line, font, x_start, y_top, box_height, highlight_word=None):
    left, top, right, bottom = font.getbbox(line)
    text_height = bottom - top
    vertical_center_offset = (box_height - text_height) // 2 - top
    draw_y = y_top + vertical_center_offset

    if not highlight_word or highlight_word not in line:
        draw.text((x_start, draw_y), line, font=font, fill=NORMAL_COLOR)
        return

    parts = line.split(highlight_word, 1)
    current_x = x_start
    draw.text((current_x, draw_y), parts[0], font=font, fill=NORMAL_COLOR)
    current_x += font.getlength(parts[0])
    draw.text((current_x, draw_y), highlight_word, font=font, fill=HIGHLIGHT_COLOR)
    current_x += font.getlength(highlight_word)
    draw.text((current_x, draw_y), parts[1], font=font, fill=NORMAL_COLOR)

def cover_making_v4(image_path, output_path, translated_text):
    try:
        if not os.path.exists(image_path) or os.path.getsize(image_path) == 0:
            print(f"⚠️ 底图不存在或为空: {image_path}")
            return
        bg = Image.open(image_path).convert('RGBA')
        bg = bg.resize((TARGET_WIDTH, TARGET_HEIGHT), Image.Resampling.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(radius=BLUR_RADIUS))
        overlay = Image.new('RGBA', (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0, OVERLAY_ALPHA))
        canvas = Image.alpha_composite(bg, overlay)
        draw = ImageDraw.Draw(canvas)

        # 1. 顶部标签
        tag_font = get_font(TAG_FONTSIZE)
        tag_w = tag_font.getlength(TAG_TEXT)
        draw.rectangle([0, TAG_Y, tag_w + 100, TAG_Y + TAG_FONTSIZE + 30], fill=ACCENT_COLOR)
        draw.text((50, TAG_Y + 12), TAG_TEXT, font=tag_font, fill="white")

        # 2. 标题处理
        title_font = get_font(TITLE_FONTSIZE)
        clean_title = re.sub(r'\[.*?\]', '', translated_text).strip()
        lines = wrap_text_styled(clean_title, title_font, TARGET_WIDTH - 200)
        
        # 智能高亮
        hl_word = get_random_noun_highlight(clean_title)

        # 计算布局
        box_h = TITLE_FONTSIZE + 45
        total_h = len(lines) * (box_h + 25)
        current_y = TARGET_HEIGHT - total_h - 150

        for line in lines:
            line_w = title_font.getlength(line)
            box_left, box_right = 60, 60 + line_w + 100
            draw.rectangle([box_left, current_y, box_right, current_y + box_h], fill=BG_BOX_COLOR)
            draw.rectangle([box_left, current_y, box_left + TITLE_BAR_W, current_y + box_h], fill=ACCENT_COLOR)
            draw_text_line_centered(draw, line, title_font, box_left + TITLE_PADDING, current_y, box_h, hl_word)
            current_y += box_h + 25

        canvas.convert('RGB').save(output_path, quality=95)
        print(f"✨ 封面已保存: {output_path}")
    except Exception as e:
        print(f"❌ 封面制作失败: {e}")

# ==================== 3. API 翻译逻辑 ====================

def translate_with_api(text_content: str) -> str:
    “””
    根据提供的视频信息（频道、原标题、字幕）生成封面标题。

    要求 LLM 只从给定内容中提炼，不得编造。
    “””
    headers = {“Authorization”: f”Bearer {API_KEY}”, “Content-Type”: “application/json”}
    system_prompt = (
        “你是一名资深主笔，负责为视频封面提炼一行简短标题。\n”
        “要求：\n”
        “- 从提供的频道名、原标题和字幕中提取最具代表性的核心观点或关键信息\n”
        “- 如有明确发言人，格式为：人物：「语录节选」\n”
        “- 无明确发言人时，直接凝练事件核心\n”
        “- 严禁超过35字，严禁使用半角引号或标点，只用中文全角标点\n”
        “- 只能提炼已提供的信息，禁止编造\n”
        “仅输出标题文本，不要其他内容。”
    )
    data = {
        “model”: API_MODEL,
        “temperature”: 0.3,
        “messages”: [
            {“role”: “system”, “content”: system_prompt},
            {“role”: “user”, “content”: text_content},
        ],
    }
    try:
        response = requests.post(f”{API_BASE_URL}/v1/chat/completions”, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        return response.json()[“choices”][0][“message”][“content”].strip()
    except Exception as e:
        print(f”⚠️ API 请求失败: {e}”)
        return None

def make_cover():
    """主入口：扫描归档目录并生成封面"""
    if not os.path.exists(OUTPUT_DIR): return
    
    excel_path = os.path.join(PROJECT_ROOT, 'storage', 'tasks', 'tasks_setting.xlsx')
    
    for folder_name in os.listdir(OUTPUT_DIR):
        folder_path = os.path.join(OUTPUT_DIR, folder_name)
        if not os.path.isdir(folder_path) or folder_name in ("done", "failed"):
            continue
            
        raw_cover = os.path.join(folder_path, "cover_raw.jpg")
        if not os.path.exists(raw_cover):
            # 尝试从视频抽一帧作为底图
            video_path = next(Path(folder_path).glob("video.*"), None)
            if video_path:
                print(f"📸 正在从视频中提取封面底图: {folder_name}")
                try:
                    subprocess.run(
                        ["ffmpeg", "-y", "-i", str(video_path), "-ss", "00:00:05", "-vframes", "1", raw_cover],
                        check=True,
                        capture_output=True,
                    )
                except subprocess.CalledProcessError as e:
                    print(f"⚠️ ffmpeg 封面提取失败: {e.stderr.decode(errors='replace').strip()}")
        
        if not os.path.exists(raw_cover): continue
        
        output_cover = os.path.join(folder_path, "cover.png")
        if os.path.exists(output_cover): continue

        # 尝试生成深度优化的标题
        # 优先查找文件夹下的翻译结果
        translated_xlsx = os.path.join(folder_path, "log/translation_results.xlsx")
        srt_path = os.path.join(folder_path, "log/trans.srt") 
        
        srt_content = quick_read_srt(srt_path)[:1000]
        channel = find_channel_by_fuzzy_match(excel_path, folder_name) or "精选"
        
        info = f"频道：{channel}\n原题：{folder_name}\n字幕：{srt_content}"
        title = translate_with_api(info) or folder_name
        
        cover_making_v4(raw_cover, output_cover, title)

if __name__ == "__main__":
    make_cover()
