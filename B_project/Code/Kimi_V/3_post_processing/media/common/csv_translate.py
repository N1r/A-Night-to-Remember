import pandas as pd
import requests
import json
import time
import re
import os
from tqdm import tqdm
from colorama import init, Fore, Style

# ==================== 0. 初始化 ====================
init(autoreset=True)

# ==================== 1. 配置区 ====================
API_KEY = 'ak_1lt5CC7fR0YP9l47On12532E7b78k'
API_BASE_URL = 'https://api.longcat.chat/openai'
API_MODEL = 'LongCat-Flash-Lite'
FILE_PATH = 'batch/tasks_setting.xlsx'

# ==================== 2. 核心清理逻辑 ====================
def super_clean_text(text):
    """清理 URL、社交媒体推广、特定博主信息、@提及、#标签"""
    if not isinstance(text, str): return ""
    
    # 进一步拓展的删除整行推广内容
    garbage_patterns = [
        # 1. 频道会员与赞助
        r'^.*(Become a Member|Join this channel|Support the channel|Patreon|PayPal|Donation).*$',
        r'^\s*(加入会员|成为会员|赞助本频道|支持作者).*$',

        # 2. 社交媒体全家桶 (新增 Brian Tyler Cohen 相关及更多平台)
        r'^(Instagram|Facebook|FB|Reddit|Discord|Threads|Bluesky|Substack|Twitter|X|Telegram|TG|TikTok|WhatsApp|Twitch|Spotify|Apple Podcasts)[:：\s]?.*$',
        r'^.*(Follow me on|Follow us|Connect with us|For more from).*$',
        r'^.*(Brian Tyler Cohen|布莱恩·泰勒·科恩).*$',
        r'^.*(Straight-news).*$',

        # 3. 订阅与导流 (新增书籍、通讯订阅)
        r'^\s*[\U00010000-\U0010ffff]?\s*(订阅|点击订阅|欢迎订阅|获取|关注|Subscribe|订购).*$',
        r'^.*(Newsletter|NYT bestselling book|畅销书|通讯订阅).*$',

        # 4. 商业合作与联系方式
        r'^.*(Business inquiries|Contact me|合作邀约|商务合作).*$',
        r'^.*(Get my book|My merch|周边商品).*$',

        # 5. 常见结尾废话
        r'^(更多内容请见|更多资讯|了解更多|Read more|Related videos).*$',
        r'^.*(All rights reserved|版权所有).*$'
    ]   
    
    for pattern in garbage_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.MULTILINE)

    # B. 删除所有 URL (含括号内及断头链接)
    text = re.sub(r'https?://\S+|www\.\S+|https?:/\s?$', '', text)
    
    # C. 删除 @提及 和 #标签
    text = re.sub(r'@[\w\.-]+', '', text)
    text = re.sub(r'#\S+', '', text)

    # D. 格式修正
    text = text.replace('()', '').replace('（）', '')
    text = re.sub(r'\n\s*\n', '\n', text) 
    return re.sub(r'\s+', ' ', text).strip()

# ==================== 3. 翻译逻辑 ====================
def translate_batch_20(text_dict: dict) -> dict:
    """批量翻译，追求地道中文表达"""
    if not text_dict: return {}
    
    headers = {
        "Content-Type": "application/json",
    }
    if API_KEY:
        k = API_KEY.strip()
        if k.lower().startswith("bearer "):
            headers["Authorization"] = k
        else:
            headers["Authorization"] = f"Bearer {k}"
    else:
        print("⚠️ 未检测到 LONGCAT API key，Authorization 头为空")
    
    prompt = f"""
    # Role
    你是一位资深国际新闻编辑，擅长将外语内容地道地转化为符合中文母语逻辑的短评。

    # Task
    将 JSON 中的 Value 翻译成中文。保持 Key 不变，仅返回 JSON 对象。

    # Principles
    1. **信达雅**：拒绝生硬直译，根据中文习惯调整语序和遣词造句。
    2. **专业度**：使用正式、地道的新闻用语，避免口水话。
    3. **简洁性**：在保留原意基础上，表达要干练有力度。

    # Data
    {json.dumps(text_dict, ensure_ascii=False)}
    """
    
    data = {
        "model": API_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "temperature": 0.3,
        "max_tokens": 4096
    }

    try:
        response = requests.post(f"{API_BASE_URL}/v1/chat/completions", headers=headers, json=data, timeout=60)
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"].strip()
        
        # 提取 JSON 内容
        start, end = content.find("{"), content.rfind("}")
        if start != -1 and end != -1:
            content = content[start : end + 1]
        return json.loads(content)
    except Exception as e:
        # 失败返回特殊标记，以便后续剔除
        return {k: "FAIL_TO_TRANSLATE" for k in text_dict.keys()}

# ==================== 4. 主程序 ====================

def main():
    if not os.path.exists(FILE_PATH):
        print(f"{Fore.RED}❌ 找不到任务文件: {FILE_PATH}")
        return

    # 读取原始数据
    try:
        df = pd.read_excel(FILE_PATH)
    except Exception as e:
        print(f"{Fore.RED}❌ 读取 Excel 失败: {e}")
        return

    initial_count = len(df)

    # 1. 初始化翻译列（如果不存在则创建）
    if 'translated_text' not in df.columns:
        df['translated_text'] = ""
    
    # 2. 预处理：清洗文本，但不对 df 进行剔除操作
    print(f"{Fore.CYAN}🧹 正在清洗文本噪音 (URL/Tags/推广)...")
    df['rawtext'] = df['rawtext'].apply(super_clean_text)
    
    # 填充空值，确保后续逻辑正常
    df['translated_text'] = df['translated_text'].fillna("").astype(str)

    # 3. 识别待翻译行 (断点续传逻辑)
    # 只处理：翻译为空、或之前标记为失败的行
    mask = (df['translated_text'].str.strip() == "") | (df['translated_text'] == "FAIL_TO_TRANSLATE")
    indices_to_translate = df[mask].index.tolist()
    
    if not indices_to_translate:
        print(f"{Fore.GREEN}✅ 所有行均已完成翻译，无需重复操作。")
        return

    # 4. 执行批量翻译
    batch_size = 20
    print(f"{Fore.MAGENTA}🚀 启动 LongCat 批量翻译 | 待处理: {len(indices_to_translate)} / {initial_count} 行")

    with tqdm(total=len(indices_to_translate), desc="翻译进度", unit="行") as pbar:
        for i in range(0, len(indices_to_translate), batch_size):
            current_batch = indices_to_translate[i : i + batch_size]
            
            # 构造本次载荷
            payload = {}
            for idx in current_batch:
                text = str(df.at[idx, 'rawtext']).strip()
                if text:
                    payload[str(idx)] = text
                else:
                    # 如果清洗后文本变空了，我们记录为跳过，而不是删除整行
                    df.at[idx, 'translated_text'] = "empty"

            # 调用接口
            if payload:
                results = translate_batch_20(payload)
                for idx_str, trans in results.items():
                    idx_int = int(idx_str)
                    # 无论成功失败，都只操作 'translated_text' 单元格
                    # 如果接口返回 FAIL_TO_TRANSLATE，也会写入单元格以便下次重试
                    df.at[idx_int, 'translated_text'] = trans
            
            pbar.update(len(current_batch))
            # 适当限速，保护 API
            time.sleep(0.3)

    # 5. 保存并覆盖原文件 (不再执行任何 df.drop 或过滤)
    try:
        # 使用原文件名覆盖保存，保留所有行和原始列
        df.to_excel(FILE_PATH, index=False)
        
        success_count = len(df[df['translated_text'].str.strip() != ""])
        print(f"\n{Fore.GREEN}✨ 处理完成！")
        print(f"{Fore.WHITE}📊 表格总行数: {initial_count} (已全部保留)")
        print(f"{Fore.CYAN}✅ 已翻译成功行数: {success_count}")
        print(f"📂 文件已更新: {FILE_PATH}")
    except PermissionError:
        print(f"{Fore.RED}❌ 覆盖失败！请先关闭 Excel 文件: {FILE_PATH} 后再运行脚本。")
    except Exception as e:
        print(f"{Fore.RED}❌ 保存过程出错: {e}")

if __name__ == "__main__":
    main()