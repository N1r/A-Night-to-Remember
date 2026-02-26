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
TAG = ['每日英语新闻, 英语新闻, 英语学习, 川普, 马斯克, 咨询直通车, 社会观察局, 热点深度观察']

# #API 配置
# API_KEY = 'sk-2hQb4lo4JuCdWWCflcN41jddIIQzhtSi78Qeb7vWOM40XSkJ'
# API_BASE_URL = 'https://api.302.ai'
# API_MODEL = 'Doubao-Seed-2.0-lite'


API_KEY = 'ak_1lt5CC7fR0YP9l47On12532E7b78k'
API_BASE_URL = 'https://api.longcat.chat/openai'
#API_MODEL = 'LongCat-Flash-Thinking'
API_MODEL = 'LongCat-Flash-Chat'
#API_MODEL = 'LongCat-Flash-Lite'

# ==================== 工具函数 ====================
def ask_gpt(system, user, model=None, temperature=0.7):
    """封装 API 请求"""
    if model is None: model = API_MODEL
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        "temperature": temperature,
        "stream": False
    }
    try:
        response = requests.post(API_BASE_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content']
    except Exception as e:
        print(f"❌ API 请求失败: {e}")
        return None

def human_sleep(min_sec=1, max_sec=3):
    """模拟人类操作延迟"""
    time.sleep(random.uniform(min_sec, max_sec))

# ==================== 视频标题翻译与生成 ====================
def translate_titles(folder_names):
    """
    智能翻译视频文件夹名（即原始英文标题）为中文标题
    返回：clean_titles, raw_translated_titles
    """
    clean_titles = []
    raw_translated_titles = []

    for folder_name in folder_names:
        print(f"\n📝 正在翻译标题: {folder_name}")
        raw_translated_title = folder_name  # 默认使用原始文件夹名

        # 尝试使用 Gemini API 翻译
        try:
            print("  🔄 尝试使用 Gemini API 翻译...")
            translated_res = ask_gpt(
                system="你是一个专业的中英翻译助手，请把输入的英文准确翻译成中文，要求简洁明了，适合做视频标题。",
                user=f"请将以下英文标题翻译成中文：{folder_name}",
                model=API_MODEL,
                temperature=0.3
            )
            if translated_res and len(translated_res) > 5:
                raw_translated_title = translated_res.strip()
                print(f"  ✅ Gemini API 翻译成功: {raw_translated_title}")
            else:
                raise Exception("API 返回内容过短或为空")

        except Exception as e:
            print(f"  ⚠️ Gemini API 翻译失败: {e}，尝试备用方案...")

            # 尝试使用 LongCat API 翻译
            try:
                print("  🔄 尝试使用 LongCat API 翻译...")
                translated_res = ask_gpt(
                    system="你是一个专业的中英翻译助手，请把输入的英文准确翻译成中文，要求简洁明了，适合做视频标题。",
                    user=f"请将以下英文标题翻译成中文：{folder_name}",
                    model=API_MODEL,
                    temperature=0.3
                )
                if translated_res and len(translated_res) > 5:
                    raw_translated_title = translated_res.strip()
                    print(f"  ✅ LongCat API 翻译成功: {raw_translated_title}")
                else:
                    raise Exception("API 返回内容过短或为空")

            except Exception as e2:
                print(f"  ⚠️ LongCat API 翻译也失败了: {e2}，尝试 OpenAI API...")

                # 尝试使用 OpenAI API 翻译
                try:
                    print("  🔄 尝试使用 OpenAI API 翻译...")
                    translated_res = ask_gpt(
                        system="你是一个专业的中英翻译助手，请把输入的英文准确翻译成中文，要求简洁明了，适合做视频标题。",
                        user=f"请将以下英文标题翻译成中文：{folder_name}",
                        model="gpt-4o-mini",
                        temperature=0.3
                    )
                    if translated_res and len(translated_res) > 5:
                        raw_translated_title = translated_res.strip()
                        print(f"  ✅ OpenAI API 翻译成功: {raw_translated_title}")
                    else:
                        raise Exception("API 返回内容过短或为空")

                except Exception as e3:
                    print(f"  ⚠️ OpenAI API 翻译也失败了: {e3}，尝试 Google 翻译...")
                    try:
                        translated_res = GoogleTranslator(source='auto', target='zh-CN').translate(folder_name)
                        raw_translated_title = translated_res
                        print(f"  ✅ Google 翻译兜底成功: {raw_translated_title}")
                    except Exception as ge:
                        print(f"  ❌ Google 翻译也失败了: {ge}，使用原始文件夹名")
                        # 此时 raw_translated_title 依然是初始的 folder_name

        # --- 最终结果清洗与保存 ---
        # 把最终确定的标题存入列表
        raw_translated_titles.append(raw_translated_title)

        # 清洗标题（去掉所有括号及其内容，如 [AI] 等）
        # 这里使用 raw_translated_title 而不是 translated，防止 None 报错
        clean_t = re.sub(r'[\[【].*?[\]】]', '', raw_translated_title).strip()

        # 组装 B 站标题，确保不超过长度限制
        final_title = f"[熟肉]{clean_t}"
        clean_titles.append(final_title[:80]) # B 站标题上限通常是 80 字符
        print(f"  ✅ 生成标题: {final_title}")

    return clean_titles, raw_translated_titles

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

    # 免费内容索引
    f_idx = indices[:split_point]
    # 付费内容索引
    p_idx = indices[split_point:]

    def write_yaml(videos, covers, titles, dtimes, filename, is_paid):
        streamers = {}
        sub_v = []

        for i, (v, c, t, dt) in enumerate(zip(videos, covers, titles, dtimes)):
            # 4. 构造单个视频的配置项
            entry = {
                "copyright": 1,           # 1=自制 (翻译二创通常投自制)
                "source": None,           # 自制无需 source
                "tid": 208,               # 分区ID (208=资讯-环球/时政，请根据需要调整)
                "cover": c,
                "title": t,
                "desc": random.choice(DESC_TEMPLATES),
                "tag": f"{','.join(TAG)}," + EXTRA_TAGS,
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
            sub_v.append(v)

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
            str(Path(PROJECT_ROOT) / 'paid_content.yaml'),
            True
        )

# ==================== 5. 主程序 ====================
def main():
    print("="*50)
    print("B站自动化上传工具 v2.0")
    print("="*50)

    # 获取 ready_to_publish 目录
    ready_dir = Path(OUTPUT_DIR)
    if not ready_dir.exists():
        print(f"❌ 目录不存在: {ready_dir}")
        return

    print(f"📂 扫描目录: {ready_dir}")

    video_entries = []
    for folder in ready_dir.iterdir():
        if not folder.is_dir():
            continue
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