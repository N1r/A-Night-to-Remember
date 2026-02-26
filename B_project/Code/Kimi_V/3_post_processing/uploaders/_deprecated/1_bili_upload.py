import os
import shutil
import json
import random
import yaml
import requests
import pandas as pd
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from tqdm import tqdm
from fuzzywuzzy import fuzz  # 保持原代码的 fuzzywuzzy，也可以换成 rapidfuzz
from deep_translator import GoogleTranslator

# 配置 Gemini API
# 建议直接在代码里定义或从环境变量读取
GEMINI_API_KEY = "AIzaSyCYRSZcU_7B0EmZkr1p5Z9LrdiPC4A5xbw" 
# 尝试导入 jieba 进行智能名词识别
try:
    import jieba
    import jieba.posseg as pseg
    HAS_JIEBA = True
except ImportError:
    HAS_JIEBA = False
    print("🚩 提示：未安装 jieba，将使用基础随机逻辑。建议运行 'pip install jieba'")

# ==================== 全局常量与配置 ====================
# 获取项目根目录
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'storage', 'ready_to_publish')
COVER_SUFFIX = '.jpg'
NEW_COVER_SUFFIX = '.jpg' # 已经由 file_movie_topic 整理好

TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080
TAG = ['每日英语新闻', '英语新闻', '英语学习', '川普', '马斯克', '咨询直通车', '社会观察局', '热点深度观察']

# #API 配置
# API_KEY = 'sk-2hQb4lo4JuCdWWCflcN41jddIIQzhtSi78Qeb7vWOM40XSkJ'
# API_BASE_URL = 'https://api.302.ai'
# API_MODEL = 'Doubao-Seed-2.0-lite'


API_KEY = 'ak_1lt5CC7fR0YP9l47On12532E7b78k'
API_BASE_URL = 'https://api.longcat.chat/openai'
#API_MODEL = 'LongCat-Flash-Thinking'
API_MODEL = 'LongCat-Flash-Chat'
#API_MODEL = 'LongCat-Flash-Lite'



# 视觉规范
HIGHLIGHT_COLOR = "#FFD700"  # 品牌金黄
NORMAL_COLOR = "#FFFFFF"     # 纯白
BG_BOX_COLOR = (0, 0, 0, 230) # 黑色半透明背景块
RED_ACCENT = "#E21918"       # 标志性新闻红

# 自动选择字体
def get_font_path():
    possible_fonts = [
        "/root/VideoLingo/batch/Fonts/HYWenHei-65W.ttf",
        "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc",
        "SourceHanSansSC-Bold.otf",
        "SimHei.ttf",
        "arial.ttf"
    ]
    for fp in possible_fonts:
        if os.path.exists(fp): return fp
    return "arial.ttf"

FONT_PATH = get_font_path()
print(f"【系统】使用字体: {FONT_PATH}")

# ==================== 0. 新增：信息提取工具 (来自代码2) ====================

def simple_read_topic(file_path: str) -> list:
    """读取 gpt_log 下的 summary.json 获取 topic"""
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # 兼容列表或字典结构
        if isinstance(data, list):
            return [item['response']['topic'] for item in data if 'response' in item and 'topic' in item['response']]
        elif isinstance(data, dict) and 'response' in data and 'topic' in data['response']:
             return [data['response']['topic']]
        return []
    except Exception as e:
        print(f"⚠️ 读取 Topic 失败: {e}")
        return []

def quick_read_srt(file_path: str) -> str:
    """极简读取 SRT 纯文本"""
    with open(file_path, 'r', encoding='utf-8-sig', errors='ignore') as f:
        content = f.read()
    
    # 匹配时间轴的正则
    pattern = r'\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}'
    
    # 一行搞定：过滤空行、数字行、时间行
    lines = [
        line.strip() for line in content.splitlines() 
        if line.strip() and not line.strip().isdigit() and not re.match(pattern, line)
    ]
    
    return "\n".join(lines)
def find_channel_by_fuzzy_match(excel_path: str, target_title: str, min_similarity=80):
    """根据文件夹名模糊匹配 Excel 中的频道名"""
    if not os.path.exists(excel_path):
        print(f"⚠️ 未找到 {excel_path}，跳过频道匹配")
        return None
    try:
        df = pd.read_excel(excel_path)
        if 'title' not in df.columns or 'channel_name' not in df.columns:
            print("⚠️ Excel 缺少 'title' 或 'channel_name' 列")
            return None
        
        best_match, best_score = None, 0
        for _, row in df.iterrows():
            current_title = str(row['title'])
            # 使用 fuzzywuzzy 的 ratio
            similarity = fuzz.ratio(target_title.lower(), current_title.lower())
            if similarity > best_score and similarity >= min_similarity:
                best_score, best_match = similarity, row['channel_name']
        
        if best_match:
            # print(f"✅ 频道匹配成功（{best_score}%）：'{best_match}'")
            return best_match
        else:
            return None
    except Exception as e:
        print(f"❌ 频道匹配出错: {e}")
        return None

# ==================== 1. 智能高亮逻辑 (避开虚词) ====================

def get_random_noun_highlight(text):
    """提取标题中的核心名词实体，避开虚词"""
    # 移除 [频道名] 干扰
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

# ==================== 2. 封面绘图核心 (精准对齐) ====================

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
    return lines[:2] 

def draw_text_line_centered(draw, line, font, x_start, y_top, box_height, highlight_word):
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


def cover_making(image_path, output_path, translated_text, logo_path='figure.png'):
    # 假设定义的全局变量，如果没有请在函数内定义
    TARGET_WIDTH = 1920
    TARGET_HEIGHT = 1080
    try:
        # 1. 处理背景图
        bg = Image.open(image_path).convert('RGBA')
        bg = bg.resize((TARGET_WIDTH, TARGET_HEIGHT), Image.Resampling.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(radius=2))
        
        # 2. 蒙层叠加
        overlay = Image.new('RGBA', (TARGET_WIDTH, TARGET_HEIGHT), (0, 0, 0, 60))
        canvas = Image.alpha_composite(bg, overlay)
        
        # 3. --- 新增：自适应缩放并嵌入 Logo ---
        if logo_path:
            logo = Image.open(logo_path).convert('RGBA')
            orig_w, orig_h = logo.size
            
            # 设定 Logo 占据背景宽度的比例 (例如 20%)
            logo_target_width = int(TARGET_WIDTH * 0.2)
            # 计算等比例缩放后的高度
            logo_target_height = int(orig_h * (logo_target_width / orig_w))
            
            # 执行 Resize
            logo = logo.resize((logo_target_width, logo_target_height), Image.Resampling.LANCZOS)
            
            # 设置边距 (Margin)
            margin = 40
            # 粘贴到左上角，(x, y) = (margin, margin)
            # 最后的 logo 参数作为 mask 必不可少，否则透明部分会黑框
            canvas.paste(logo, (margin, margin), logo)

        # 4. 保存结果
        # 注意：JPEG 不支持透明度，所以保存前转为 RGB
        canvas.convert('RGB').save(output_path, quality=95)
        print(f"✅ 成功生成带 Logo 封面: {output_path}")

    except Exception as e:
        print(f"❌ 封面失败 {image_path}: {e}")


# ==================== 3. API 翻译逻辑 (已增强) ====================

def translate_with_api(text_content: str) -> str:
    """
    接收包含 频道名、原标题、Topic 的综合字符串进行处理
    """
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    prompt = """
# Role

你是一名深耕“今日头条”、“腾讯新闻”、“参考消息”等资讯平台的资深政经主笔。你的目标受众是b站中国中年男性群体，关注大国博弈、地缘政治与宏观经济。
你的核心能力是：从琐碎的外媒原声中，提取**最具冲击力的核心观点**，并以“一语定乾坤”的风格重塑标题。
你的核心特质是：立场坚定，视野宏阔。 你能从纷繁复杂的外媒信息中，一眼洞穿其叙事陷阱，并以符合中国国家利益、维护多极化秩序的视角进行重写。

# Input Data
* 原标题：{folder_name}
* 讨论主题：{topic_list}
* 字幕内容：{srt_list}

# Construction Rules (硬核政经爆款法则)

1. **结构化呈现（核心红线）：**
* **固定格式： “一句核心语录” 关键人物，事件的简短定性描述。**
* 语录必须摘自字幕，代表其核心立场或最震撼的细节。
* 严禁空洞，标题中必须包含具体的“实体名词”（如法案名、国家、特定数据）。

3. **视觉与符号约束：**
* **严禁使用半角符号**（如 : , " " ），必须使用全角符号（如 ： ， “” ）。
* 全文严禁超过35字。
* 仅输出标题一行，不要任何解释。
Workflow
过滤与提取： 从字幕中剔除修饰性废话，锁定那句最具“对抗性”或“承认失败”的核心原话。

意图校准： 分析该人物说话的真实意图——是恐吓、是甩锅、还是战略退缩？

重组定调： 按照公式装配。确保“金句”抓眼，“定性”扎心。

最终审校： 检查符号是否全角，语气是否像一位资深政经观察员在进行内部分析。

Examples
✅ 贝森特：“20％关税是重塑贸易霸权的核心底牌” 执意推动激进扩张。
✅ 舒默：“芯片法案的每一分钱都必须服务于遏制战略” 暴露美式科技霸权底色。
✅ 普京：“乌克兰入约即意味着全球战略平衡的终结” 严厉警告地缘安全最后红线。
✅ 马斯克：“政府补贴若脱离效率将沦为政客的数字游戏” 深度拆解美产业政策困局。

# Workflow
1. **扫视提取：** 从字幕中锁定那句最能代表人物立场、最狠、或者包含关键数据的“核心原话”。
2. **身份锁定：** 提取关键人物及与其相关的核心动作/事件。
3. 结构装配： 严格按照 人物：“语录” 描述 的公式进行组装。
4. 立场校准： 检查措辞是否符合中国读者的政经审美与立场取向，确保文字老辣、专业。

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
        print(f"API Error: {e}")
        return None

# ==================== 4. 业务处理逻辑 (整合了 Topic 和 Channel) ====================

def generate_titles(video_paths: list) -> tuple:
    titles, translated_texts = [], []
    
    print(f"🔍 开始生成标题，共 {len(video_paths)} 个视频...")
    
    for video_path in video_paths:
        folder_path = os.path.dirname(video_path)
        folder_name = os.path.basename(folder_path)
        
        # --- 整合逻辑开始 ---
        # 1. 获取 Topic
        json_path = os.path.join(folder_path, 'gpt_log', 'summary.json')
        topic_list = simple_read_topic(json_path)
        srt_path = os.path.join(folder_path, 'trans.srt')
        srt_list = quick_read_srt(srt_path)
        #print(srt_list)
        # 2. 获取 Channel Name
        channel_name = find_channel_by_fuzzy_match('tasks_setting.xlsx', folder_name) or "精选新闻"
        
        # 3. 构造发送给 API 的内容
        #prompt_content = f"频道名为：{channel_name}\n原标题为:{folder_name}\n内容主题为:{topic_list}完整字幕: {srt_list}"
        prompt_content = f"频道名为：{channel_name}\n原标题为:{folder_name}\n内容主题为:{topic_list}完整字幕: {srt_list}"

        # print(f"  > 处理: {folder_name} | 频道: {channel_name}")
        # --- 整合逻辑结束 ---

        translated = None
        max_retries = 3

        # --- 1. API 重试循环 ---
        for i in range(max_retries):
            try:
                # 尝试调用 API
                translated = translate_with_api(prompt_content)
                # 如果拿到了结果，直接跳出重试循环
                if translated:
                    print(f"  ✅ API 第 {i+1} 次调用成功")
                    break
            except Exception as e:
                print(f"  ⚠️ 第 {i+1} 次尝试失败: {e}")
            
            if i < max_retries - 1:
                import time
                time.sleep(2)

        # --- 2. 确定 raw_translated_title (无论 API 是否成功) ---
        # 初始保底：先定为文件夹名
        raw_translated_title = folder_name 

        if translated:
            # API 成功了，使用 API 的结果
            raw_translated_title = translated
        else:
            # API 彻底失败，启用 Google 翻译兜底
            print("  ⚠️ API 所有尝试均失败，尝试 Google 翻译...")
            try:
                translated_res = GoogleTranslator(source='auto', target='zh-CN').translate(folder_name)
                raw_translated_title = translated_res
                print(f"  ✅ Google 翻译兜底成功: {raw_translated_title}")
            except Exception as ge:
                print(f"  ❌ Google 翻译也失败了: {ge}，使用原始文件夹名")
                # 此时 raw_translated_title 依然是初始的 folder_name

        # --- 3. 最终结果清洗与保存 ---
        # 把最终确定的标题存入列表
        translated_texts.append(raw_translated_title)

        # 清洗标题（去掉所有括号及其内容，如 [AI] 等）
        # 这里使用 raw_translated_title 而不是 translated，防止 None 报错
        clean_t = re.sub(r'[\[【].*?[\]】]', '', raw_translated_title).strip()
        
        # 组装 B 站标题，确保不超过长度限制
        final_title = f"[熟肉]{clean_t}"
        titles.append(final_title[:80]) # B 站标题上限通常是 80 字符        
        print(f" ✅ 生成标题: {final_title}")

    return titles, translated_texts

# ==================== 配置：文案与标签 (嘲讽/吃瓜风格) ====================

# 简介模板库（随机抽取，保持新鲜感，避免查重）
DESC_TEMPLATES = [
    "【日常围观】带大家看看对面又在整什么新活。美国那点两党扯皮的破事儿，全在视频里了。本意是练口语，结果看着看着发现比电视剧还精彩。逻辑自理，看戏随意。 🏳️ 叠个甲：素材全搬自外媒，纯属语言学习和学术批判，别问，问就是为了学习。 📺 觉得有意思就随手给个三连，随缘更新，懂的都懂。",
    "⚡️ 随便聊聊：美式政坛的大戏排期与大型双标现场。 说是高阶双语素材，其实就是带大家拆解一下那套话术陷阱，看权力的游戏怎么玩崩社会共识的。 💡 蹲个点：看他们怎么把逻辑玩出花来。 🤝 互动：大家评论区理智吃瓜，要是觉得这波分析还算走心，点个赞支持下，毕竟剪辑也挺费头发的。",
    "🇺🇸 时代小本本：这帮美国政要又在演哪一出？ 翻了点美媒的犀利吐槽和辩论原声，字幕已经精校过了，方便大家看清那帮人嘴里的弯弯绕。 🎯 核心看点：日常互黑 | 政策画饼 | 媒体大型翻车现场 💬 交流：评论区大神多，欢迎在线开课。感谢各位捧场，下期见（如果我不鸽的话）。"
]

# 补充标签（高热度关键词）
EXTRA_TAGS = "特朗普,美国大选,共和党,民主党,美式笑话,双语字幕,听力,国际时事,吃瓜"

# ==================== 核心逻辑：YAML 生成 ====================

def split_and_create_yaml(videos, covers, titles, dtimes, paid_ratio=0.1):
    """
    将视频列表随机划分为免费/付费内容，并生成对应的上传 YAML 配置文件
    """
    total = len(videos)
    indices = list(range(total))
    random.shuffle(indices) # 打乱顺序
    
    # 计算分割点
    split_point = int(total * (1 - paid_ratio))
    
    # --- 内部函数：写入 YAML ---
    def write_yaml(sub_v, sub_c, sub_t, sub_dt, filename, is_paid):
        streamers = {}
        
        for i, (v, c, t, dt) in enumerate(zip(sub_v, sub_c, sub_t, sub_dt)):
            # 1. 随机选择简介模板
            base_desc = random.choice(DESC_TEMPLATES)
            
            # 2. 组合最终简介 (将标题放在第一行，利于 SEO 和用户快速预览)
            final_desc = f"► 本期看点：{t}\n\n{base_desc}"
            
            # 3. 处理标签 (合并 Global TAG 和 EXTRA_TAGS)
            # 正确合并列表 TAG 和字符串 EXTRA_TAGS
            tag_list = TAG if isinstance(TAG, list) else [TAG]
            combined_tags = tag_list + EXTRA_TAGS.split(",")
            
            # 去重、去空、限制数量 (B站限制标签数，通常取前12个)
            final_tag_list = list(set([x.strip() for x in combined_tags if x.strip()]))
            final_tag = ",".join(final_tag_list[:12])

            # 4. 构造单个视频的配置项
            entry = {
                "copyright": 1,           # 1=自制 (翻译二创通常投自制)
                "source": None,           # 自制无需 source
                "tid": 208,               # 分区ID (208=资讯-环球/时政，请根据需要调整)
                "cover": c, 
                "title": t,
                "desc": final_desc,
                "tag": final_tag,
                "dtime": dt,              # 定时发布时间戳
                "open-elec": 1,           # 开启充电
            }
            
            # 如果是付费内容，添加付费字段
            if is_paid:
                entry.update({
                    "charging_pay": 1, 
                    "upower_level_id": "1212996740244948080" # 🔴 请确认这是您的充电计划 ID
                })
                
            streamers[v] = entry

        # 5. 写入文件
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                # allow_unicode=True 保证中文正常显示，sort_keys=False 保持字段顺序
                yaml.dump({"submit": "App", "streamers": streamers}, f, allow_unicode=True, sort_keys=False)
            print(f"📄 已生成配置文件: {filename} (包含 {len(sub_v)} 个视频)")
        except Exception as e:
            print(f"❌ 写入 YAML 失败 ({filename}): {e}")

    # --- 执行分割与写入 ---
    
    # 划分索引
    f_idx = indices[:split_point] # 免费部分索引
    p_idx = indices[split_point:] # 付费部分索引
    
    # 生成免费内容的 YAML
    write_yaml(
        [videos[i] for i in f_idx], 
        [covers[i] for i in f_idx], 
        [titles[i] for i in f_idx], 
        [dtimes[i] for i in f_idx], 
        str(Path(PROJECT_ROOT) / 'free_content.yaml'),
        False
    )
    
    # 生成付费内容的 YAML (如果有的话)
    if p_idx:
        write_yaml(
            [videos[i] for i in p_idx], 
            [covers[i] for i in p_idx], 
            [titles[i] for i in p_idx], 
            [dtimes[i] for i in p_idx], 
            'paid_content.yaml', 
            True
        )
# ==================== 5. 主程序 ====================

def main():
    """
    扫描 storage/ready_to_publish 下的子文件夹，
    每个子文件夹名即为已翻译的标题，内含 {title}.mp4 和 {title}.jpg。
    生成 free_content.yaml 供 biliup 使用。
    """
    from pathlib import Path
    import sys

    ready_dir = Path(OUTPUT_DIR)
    if not ready_dir.exists():
        print(f"❌ 目录不存在: {ready_dir}")
        return

    # 扫描子文件夹，找到包含 .mp4 的有效视频文件夹
    video_entries = []  # [(video_path, cover_path, folder_name)]
    for folder in sorted(ready_dir.iterdir()):
        if not folder.is_dir():
            continue
        # 跳过 done / failed 归档文件夹
        if folder.name in ("done", "failed"):
            continue
        
        # 找 .mp4（文件名与文件夹名相同）
        mp4_files = list(folder.glob("*.mp4"))
        if not mp4_files:
            continue
        video_path = mp4_files[0]

        # 找封面 .jpg
        jpg_files = list(folder.glob("*.jpg"))
        cover_path = str(jpg_files[0]) if jpg_files else ""

        video_entries.append((str(video_path), cover_path, folder.name))

    if not video_entries:
        print(f"❌ 在 {ready_dir} 下未发现任何视频文件夹")
        return

    print(f"📂 发现 {len(video_entries)} 个视频，开始生成 B站 YAML 配置...")

    videos   = [e[0] for e in video_entries]
    covers   = [e[1] for e in video_entries]
    # 文件夹名已经是翻译好的中文标题，直接加前缀
    titles   = [f"[熟肉]{e[2]}" for e in video_entries]  # 修复：B站标题上限 80 字

    # 定时发布时间：明天 8:00 起，每隔 45 分钟一个
    start_time = (
        datetime.now(timezone(timedelta(hours=8)))
        .replace(hour=8, minute=0, second=0, microsecond=0)
        + timedelta(days=1)
    )
    dtimes = [
        int((start_time + timedelta(minutes=45 * i)).timestamp())
        for i in range(len(videos))
    ]

    # 打印预览
    print("\n📋 上传预览：")
    for i, (v, c, t, dt) in enumerate(zip(videos, covers, titles, dtimes)):
        sched = datetime.fromtimestamp(dt).strftime("%m-%d %H:%M")
        print(f"  [{i+1}] {t[:40]}...")
        print(f"       视频: {v}")
        print(f"       封面: {c or '(无)'}")
        print(f"       定时: {sched}")

    # 生成 YAML（全部作为免费内容）
    split_and_create_yaml(videos, covers, titles, dtimes, paid_ratio=0.0)

    # ==================== 自动上传到 B 站 ====================
    yaml_path    = Path(PROJECT_ROOT) / "free_content.yaml"
    cookies_path = Path(PROJECT_ROOT) / "storage" / "cookies" / "bili_cookies.json"

    print(f"\n✨ YAML 已生成: {yaml_path}")

    # 自动探测 biliup 可执行文件路径
    import shutil
    biliup_bin = shutil.which("biliup") or os.path.expanduser("~/.local/bin/biliup")

    if not os.path.isfile(biliup_bin):
        print(f"❌ 未找到 biliup 可执行文件（已查找: {biliup_bin}）")
        print(f"   请手动运行: biliup upload -c {yaml_path} -u {cookies_path}")
        return

    if not cookies_path.exists():
        print(f"❌ 未找到 B 站 Cookies 文件: {cookies_path}")
        return

    cmd = [biliup_bin, "-u", str(cookies_path), "upload", "-c", str(yaml_path)]
    print(f"\n🚀 开始上传到 B 站...")
    print(f"   命令: {' '.join(cmd)}\n")

    import subprocess
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))

    if result.returncode == 0:
        print("\n✅ B 站上传完成！")
    else:
        print(f"\n❌ biliup 退出码: {result.returncode}，请检查上方日志。")

if __name__ == "__main__":
    main()
