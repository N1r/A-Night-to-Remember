import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime

import pandas as pd
import requests
from rapidfuzz import fuzz, process
from rich.console import Console


# ==================== 配置区 ====================
def _load_config() -> tuple[str, str, str, bool]:
    """从 configs/config.yaml 读取 API 配置，与项目其他模块保持一致"""
    try:
        import yaml
        cfg_path = Path(__file__).parent.parent.parent / "configs" / "config.yaml"
        with open(cfg_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        
        api = cfg.get("api", {})
        return (
            api.get("key", ""),
            api.get("base_url", "https://api.longcat.chat/openai"),
            api.get("model", "LongCat-Flash-Lite"),
            bool(api.get("llm_support_json", False)),
        )
    except Exception:
        return (
            os.environ.get("LONGCAT_API_KEY", ""),
            "https://api.longcat.chat/openai",
            "LongCat-Flash-Lite",
            False,
        )

API_KEY, API_BASE_URL, API_MODEL, API_SUPPORT_JSON = _load_config()

PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
READY_DIR = PROJECT_ROOT / "storage" / "ready_to_publish"
TASKS_EXCEL = PROJECT_ROOT / "storage" / "tasks" / "tasks_setting.xlsx"

console = Console()

# ==================== Excel 缓存（批量处理时避免重复 I/O）====================

_excel_cache: dict = {"mtime": None, "df": None}


def _load_excel_df():
    """懒加载并缓存 Excel DataFrame，文件变更时自动失效"""
    if not TASKS_EXCEL.exists():
        return None
    try:
        mtime = TASKS_EXCEL.stat().st_mtime
        if _excel_cache["mtime"] == mtime and _excel_cache["df"] is not None:
            return _excel_cache["df"]
        df = pd.read_excel(TASKS_EXCEL)
        _excel_cache.update({"mtime": mtime, "df": df})
        return df
    except Exception as e:
        console.log(f"[red]❌ 读取 Excel 失败: {e}[/red]")
        return None

# ==================== 工具函数 ====================

def _extract_json(text: str) -> dict:
    """从 AI 响应中提取 JSON，按优先级尝试三种方式"""
    if not text:
        return {}
    # 1. 直接解析
    try:
        return json.loads(text.strip())
    except Exception:
        pass
    # 2. 提取 {...} 块（保留换行，不做 replace）
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    # 3. 去除 markdown 代码围栏后再解析
    stripped = re.sub(r'^```(?:json)?\s*', '', text.strip(), flags=re.IGNORECASE)
    stripped = re.sub(r'\s*```$', '', stripped.strip())
    try:
        return json.loads(stripped)
    except Exception:
        console.log(f"[dim yellow]⚠️ JSON 解析彻底失败，原文节选: {text[:120]}[/dim yellow]")
        return {}


def _ask_gpt(system: str, user: str, temperature: float = 0.4) -> str:
    """
    调用 LLM API。

    temperature 默认 0.4（低创造性）：
    - 避免 LLM 自由发挥、编造内容
    - 确保输出忠实于提供的素材
    """
    headers = {
        "Content-Type": "application/json",
    }
    # 兼容 API_KEY 带/不带 Bearer 前缀的情况
    if API_KEY:
        key_str = API_KEY.strip()
        if key_str.lower().startswith("bearer "):
            headers["Authorization"] = key_str
        else:
            headers["Authorization"] = f"Bearer {key_str}"
    else:
        console.log("[yellow]⚠️ 未检测到 LONGCAT API key，Authorization 头为空[/yellow]")
    payload = {
        "model": API_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
    }
    # 如果配置支持强结构化 JSON 输出，尝试使用 response_format 以减少解析错误
    if API_SUPPORT_JSON:
        try:
            payload["response_format"] = {"type": "json_object"}
        except Exception:
            pass
    try:
        response = requests.post(
            f"{API_BASE_URL}/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30,
        )
        try:
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
        except requests.exceptions.HTTPError:
            # 显示返回的状态码与响应体，便于诊断 401/403 等认证问题
            console.log(f"[yellow]⚠️ API 请求失败 ({response.status_code}): {response.text}[/yellow]")
            return ""
    except Exception as e:
        console.log(f"[yellow]⚠️ API 请求失败: {e}[/yellow]")
        return ""


def _normalize_title(text: str) -> str:
    """清理并规范化搜索文本"""
    if not text:
        return ""
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'[^\w\s]', ' ', text)
    return re.sub(r'\s+', ' ', text).strip().lower()


def _ask_and_parse_json(system: str, user: str, example: str, temperature: float = 0.35, retries: int = 1, context: str = "") -> dict:
    """向模型请求并严格解析 JSON；失败时可短促重试一次，要求模型只返回符合示例的 JSON。"""
    # 首次尝试
    res = _ask_gpt(system, user, temperature)
    parsed = _extract_json(res)
    # 若首次响应无法解析为 JSON，立即记录以便排查（即便后续重试成功也保留初始响应）
    if not parsed:
        try:
            dbg_dir = PROJECT_ROOT / "output" / "debug"
            dbg_dir.mkdir(parents=True, exist_ok=True)
            inter_path = dbg_dir / "metadata_ai_intermediate.log"
            with open(inter_path, "a", encoding="utf-8") as lf:
                lf.write("\n---\n")
                lf.write(f"time: {datetime.now().isoformat()}\n")
                lf.write(f"context: {context}\n")
                lf.write("initial_response:\n")
                lf.write((res or "") + "\n")
        except Exception:
            pass
    if parsed:
        return parsed

    # 重试：简短强约束指令，要求仅返回严格 JSON
    responses = [res]
    for _ in range(retries):
        retry_note = (
            "请严格只返回有效的 JSON，绝对不要带解释文字或代码块，" 
            f"如果不能则返回 {example} 的同结构空值。示例：{example}"
        )
        combined = user + "\n\n" + retry_note
        res2 = _ask_gpt(system, combined, temperature)
        responses.append(res2)
        parsed = _extract_json(res2)
        if parsed:
            return parsed
    # 记录失败的原始响应以便排查
    try:
        dbg_dir = PROJECT_ROOT / "output" / "debug"
        dbg_dir.mkdir(parents=True, exist_ok=True)
        log_path = dbg_dir / "metadata_ai_failures.log"
        with open(log_path, "a", encoding="utf-8") as lf:
            lf.write("\n---\n")
            lf.write(f"time: {datetime.now().isoformat()}\n")
            lf.write(f"context: {context}\n")
            lf.write("system_prompt:\n" + system.replace('\n', '\n') + "\n")
            lf.write("user_prompt:\n" + user.replace('\n', '\n') + "\n")
            for i, r in enumerate(responses):
                lf.write(f"response_{i+1}:\n")
                lf.write((r or "") + "\n")
    except Exception:
        pass

    return {}


def _read_srt_text(srt_path: Path, max_chars: int = 3000) -> str:
    """
    读取 SRT 文件，过滤序号和时间轴，仅保留字幕文本。

    max_chars: 最多返回的字符数（保留足够多以覆盖视频核心内容）
    """
    if not srt_path.exists():
        return ""
    try:
        content = srt_path.read_text(encoding='utf-8-sig', errors='ignore')
    except OSError:
        return ""
    timestamp_pattern = re.compile(r'\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}')
    lines = [
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.strip().isdigit() and not timestamp_pattern.match(line.strip())
    ]
    return "\n".join(lines)[:max_chars]


# ==================== 运营工具 ====================

def clean_tag(text: str) -> str:
    """清理话题标签，只保留字母、数字、中文和下划线"""
    if not text:
        return ""
    return re.sub(r'[^\w\u4e00-\u9fa5]', '', text).strip()


def _build_fallback_tags(info: dict) -> list:
    """从 category/topics 字段派生兜底 tags，避免硬编码泛化词"""
    tags = []
    category = info.get("category", "")
    if category and category not in ("未分类", "International", ""):
        tags.append(clean_tag(category[:10]))
    for t in info.get("topics", [])[:2]:
        t = t.strip()
        cleaned = clean_tag(t)
        if cleaned and len(cleaned) <= 10:
            tags.append(cleaned)
    tags = [t for t in dict.fromkeys(tags) if t]  # 去重保序
    return tags[:3] if tags else ["热门信息"]


def clean_tags_in_text(text: str) -> str:
    """识别文本中的 #话题 并清理其中的非法字符，清理后为空则移除"""
    if not text:
        return ""
    def _repl(match):
        cleaned = clean_tag(match.group(1))
        return f"#{cleaned}" if cleaned else ""
    return re.sub(r'#([^\s#]+)', _repl, text)


# ==================== Excel 信息提取 ====================

def get_excel_info(folder_name: str) -> dict:
    """从 Excel 中通过模糊匹配查找信息，优先匹配中文标题列"""
    df = _load_excel_df()
    if df is None:
        return {}
    try:
        norm_folder = _normalize_title(folder_name)

        # 1. 优先匹配 'title' 列（Step 1 生成的中文标题）
        if 'title' in df.columns:
            titles = df['title'].astype(str).tolist()
            norm_titles = [_normalize_title(t) for t in titles]
            match = process.extractOne(norm_folder, norm_titles, scorer=fuzz.ratio)
            if match and match[1] > 85:
                return _parse_row(df.iloc[norm_titles.index(match[0])])

        # 2. 兜底匹配 'rawtext' 列（原始推文/标题）
        if 'rawtext' in df.columns:
            raws = df['rawtext'].astype(str).tolist()
            norm_raws = [_normalize_title(r) for r in raws]
            match = process.extractOne(norm_folder, norm_raws, scorer=fuzz.token_set_ratio)
            if match and match[1] > 80:
                return _parse_row(df.iloc[norm_raws.index(match[0])])

    except Exception as e:
        console.log(f"[red]❌ 匹配 Excel 失败: {e}[/red]")
    return {}


def _parse_row(row) -> dict:
    """解析 Excel 行数据为标准字典"""
    return {
        "title": str(row.get('title', '')),
        "summary": str(row.get('rawtext', '')),           # 原始推文/描述
        "category": str(row.get('Category', '')),
        "topics": str(row.get('AI Reason', '')).split(',') if row.get('AI Reason') else [],
        "translated_text": str(row.get('translated_text', '')),  # 推文中文翻译
        "channel": str(row.get('channel_name', '')),
        "original_link": str(row.get('Video File', '')),
        "publish_date": str(row.get('Publish Date', '')),
    }


# ==================== 内容上下文构建 ====================

def _build_content_context(title: str, info: dict, srt_text: str) -> str:
    """
    构建提供给所有平台 prompt 的统一内容上下文。

    将所有可获取的原始信息聚合，让 LLM 有足够的事实依据，
    减少因信息不足导致的自由发挥和内容捏造。
    """
    parts = []
    # if info.get("channel"):
    #     parts.append(f"【来源频道】{info['channel']}")
    # if info.get("original_link"):
    #     parts.append(f"【原始链接】{info['original_link']}")
    if title:
        parts.append(f"【中文标题】{title}")
    if info.get("summary"):
        parts.append(f"【原始推文/描述（英文）】{info['summary']}")
    if info.get("translated_text"):
        parts.append(f"【中文翻译】{info['translated_text']}")
    #if info.get("category"):
    #    parts.append(f"【内容分类】{info['category']}")
    # if info.get("topics"):
    #     topics = info['topics']
    #     topics_str = "、".join(t.strip() for t in topics if t.strip()) if isinstance(topics, list) else str(topics)
    #     if topics_str:
    #         parts.append(f"【收录理由】{topics_str}")
    if srt_text:
        parts.append(f"【全文】\n{srt_text}")

    context = "\n\n".join(parts)

    # 抗幻觉及安全合规约束：明确要求 LLM 不得编造内容，并规避敏感词
    constraint = (
        "\n\n【严格约束】以上是视频的全部已知信息。"
        "只能基于以上实际内容进行提炼和改写，严禁编造视频中未出现的事件、人物、数据或观点。"
    )
    return context + constraint


# ==================== 各平台元数据生成器（独立函数，支持并发）====================

def _gen_xhs_data(content_ctx: str, folder_name: str, info: dict, title: str) -> dict:
    """生成小红书平台元数据"""
    xhs_system = """
你是小红书优质内容创作者，擅长用简洁、专业的语言拆解视频内容，提取核心价值并引发读者共鸣。
基于所提供的视频素材，生成一条信息量充足、表达清晰的笔记文案，根据视频内容自动匹配合适的垂类风格。

严格要求（违反则视为无效输出）：
1) 仅返回合法 JSON 对象，绝对禁止 Markdown 代码块或任何解释文字。
2) JSON 结构：{"title":"标题(15-20字)","desc":"正文(150-200字)"}
3) 【标题规范】15-20字；提炼视频最核心的亮点或悬念；
   可用疑问句或数字归纳句式（如"关键3点"）；
   根据内容可含1个 Emoji；严禁凭空编造，严禁使用"震惊""内幕""真相"等低质词汇。
4) 【正文结构】
   ① 内容概述：1-2句简明说清楚这期视频的核心主旨
   ② 核心看点/干货：2-3段分点展开，用"📌""🔑"等符号辅助阅读
   ③ 升华/感想：1句总结或升华主题
   ④ 互动结尾：一句开放式问题邀请读者讨论
   ⑤ 话题标签：3-5个，格式"#话题"，1-2个宽泛的流量话题 + 2-3个精准垂类话题
5) 严禁捏造事实；所有内容须忠实于提供的素材。
6) 无法解析时，仅返回 {"error":"NO_JSON"}。
7) 注意：不要包含换行符（\n）或其他未转义字符，只返回单行紧凑的 JSON。

示例输出：
{"title":"这个设计太妙了！实用与美学的完美结合📋","desc":"最近发现了一个极其巧妙的设计理念，它将日常实用性与极简美学融合得恰到好处。\n\n📌 核心亮点：打破了传统布局的局限，让空间利用率翻倍\n🔑 细节之处：材质的选择兼顾了耐用与触感\n\n好的设计不仅解决问题，还能提升生活品质。你喜欢这个设计的哪一部分？评论区来聊～\n\n#设计美学 #实用干货 #好物分享 #生活方式 #灵感"}
"""
    xhs_example = '{"title":"🤔 标题示例","desc":"这是一个 150 字左右的示例描述... #标签1 #标签2"}'
    data = _ask_and_parse_json(xhs_system, content_ctx, xhs_example, temperature=0.35, retries=1, context=f"{folder_name} - xhs")
    if data:
        data["desc"] = clean_tags_in_text(data.get("desc", ""))
    else:
        console.log("[yellow]⚠️ XHS AI 解析失败（已记录至 output/debug），使用兜底值[/yellow]")
        data = {"title": f"🤔 {title[:18]}", "desc": f"{info.get('summary') or title}\n\n#热门资讯 #分享"}
    return data


def _gen_dy_data(content_ctx: str, folder_name: str, info: dict, title: str) -> dict:
    """生成抖音平台元数据"""
    dy_system = """
你是抖音优质短视频创作者，擅长用简明抓人的语言提炼视频精华，帮助用户快速抓住最具吸引力的看点。

严格要求：
1) 仅返回严格 JSON，禁止任何额外文字或代码块。
2) JSON 结构：{"title":"标题(15-25字)","tags":["标签1","标签2","标签3"]}，tags 3-5个。
3) 【标题规范】15-25字；直接点出视频中最具冲突感、信息量或情绪共鸣的核心；
   可用问句或数字归纳句式；根据内容灵活调整语气；
   可用"？""！"增强语气，但不过度堆叠；
   严禁废话开头（"今天我们来聊""大家好"）；严禁编造；严禁使用"内幕""真相""震惊"等低质词汇。
4) 【标签规范】前1-2个用行业/领域的大流量话题；后2-3个用精准描述视频核心实体/概念的话题。
5) 若无法生成，返回 {"error":"NO_JSON"}。
6) 注意：不要包含换行符（\n）或其他未转义字符，只返回单行紧凑的 JSON。

示例输出：
{"title":"这一刻太绝了！3个细节带你看懂背后的逻辑","tags":["看点解析","细节解读","热点事件","知识干货"]}
"""
    dy_example = '{"title":"标题示例","tags":["干货","看点","深度"]}'
    data = _ask_and_parse_json(dy_system, content_ctx, dy_example, temperature=0.3, retries=1, context=f"{folder_name} - dy")
    if data:
        data["tags"] = [clean_tag(t) for t in data.get("tags", []) if clean_tag(t)]
    else:
        console.log("[yellow]⚠️ DY AI 解析失败[/yellow]")
        data = {"title": title[:20], "tags": _build_fallback_tags(info)}
    return data


def _gen_bili_data(content_ctx: str, folder_name: str, info: dict, title: str) -> dict:
    """生成 B 站平台元数据"""
    bili_system = """
你是B站资深硬核UP主/优质内容创作者，深知B站用户偏好：信息量大、独特视角、注重内容质量、热爱在评论区深度交流。

严格要求：
1) 仅返回严格 JSON，禁止多余说明或代码块。
2) JSON 结构：{"title":"标题(30-80字)","desc":"视频简介(3-5句话)"}。
3) 【标题规范】根据情况可选[内容标记] + 核心主体 + 最强看点（用"！"或"？"收尾）。
   标记可选：【中文字幕】【硬核解析】【首发】等（视视频性质而定）；
   核心主体要简洁，看点需点出最有价值、最有趣或最具信息量的部分。80字以内。
   参考格式："【硬核解析】干货拉满！关于这项技术的3个核心误区，一次讲透！"
4) 【简介规范（4段式）】
   ① 背景介绍：一句话简明说清楚这段视频分享的具体内容是什么
   ② 制作说明：如"内容已经过精心整理编译/翻译，重点已提取"（看实际情况写）
   ③ 核心看点：点明最精彩的1-2个亮点、干货或看点
   ④ 互动引导（随机变体）：
      · "觉得视频有用的顺手点个赞支持一下！"
      · "对于这点大家怎么看？评论区见～"
      · "求个一键三连，让你的首页多些硬核干货！"
   严禁捏造事实。
5) 若无法输出有效 JSON，返回 {"error":"NO_JSON"}。
6) 注意：不要包含换行符（\n）或其他未转义字符，只返回单行紧凑的 JSON。

示例输出：
{"title":"【硬核解析】这也许是你见过最清晰的原理解析！带你重新认识这个领域","desc":"本期视频带大家深入了解该领域的最新动向，核心看点在于后半段对底层逻辑的剖析，直接点出了长期以来的认知盲区。觉得有收获的朋友点个赞支持一下！"}
"""
    bili_example = '{"title":"【硬核解析】示例标题","desc":"硬核干货解析，求一键三连支持！"}'
    data = _ask_and_parse_json(bili_system, content_ctx, bili_example, temperature=0.35, retries=1, context=f"{folder_name} - bili")
    if data:
        data["desc"] = clean_tags_in_text(data.get("desc", ""))
    else:
        console.log("[yellow]⚠️ BILI AI 解析失败[/yellow]")
        data = {
            "title": f"【双语字幕】{title}",
            "desc": f"Antigravity 字幕组出品，求个一键三连支持！\n{info.get('summary') or ''}",
        }
    return data


def _gen_ks_data(content_ctx: str, folder_name: str, info: dict, title: str) -> dict:
    """生成快手平台元数据"""
    ks_system = """
你是快手头部热点内容创作者，粉丝画像下沉大众，俗称"老铁"。
你的内容风格：极度口语化、直白接地气、情绪饱满，让人一眼就想点开、看完就想转发。

严格要求：
1) 只返回严格 JSON，禁止解释文字或代码块。
2) JSON 结构：{"title":"标题(10-18字)","tags":["标签1","标签2","标签3"]}，tags 3-5个。
3) 【标题规范】10-18字；极度口语化，就像在跟朋友唠嗑；
   可用引导式（"这事又出新花样了"）或问句式（"老铁们遇到过这情况不"）；
   善用接地气词汇："这""咱""老铁""整""绝了""太牛了""给整不会了"；
   严禁生硬文绉绉的书面语；严禁编造。
4) 【标签规范】混合全网热门分类词（1-2个，扩大曝光）+ 精准描述视频的通俗词条（2-3个，精准触达）。
   风格接地气，符合快手主流受众搜索习惯。
5) 若无法返回有效 JSON，返回 {"error":"NO_JSON"}。
6) 注意：不要包含换行符（\n）或其他未转义字符，只返回单行紧凑的 JSON。

示例输出：
{"title":"这操作真是绝了老铁们看看","tags":["生活日常","涨知识","太牛了","你敢信"]}
"""
    ks_example = '{"title":"惊讶式标题这事绝了","tags":["热点","涨知识"]}'
    data = _ask_and_parse_json(ks_system, content_ctx, ks_example, temperature=0.3, retries=1, context=f"{folder_name} - ks")
    if data:
        data["tags"] = [clean_tag(t) for t in data.get("tags", []) if clean_tag(t)]
    else:
        console.log("[yellow]⚠️ KS AI 解析失败[/yellow]")
        data = {"title": title[:18], "tags": _build_fallback_tags(info)}
    return data


def _generate_all_platforms(content_ctx: str, folder_name: str, info: dict, title: str) -> dict:
    """
    并发为 4 个平台生成元数据，总耗时约等于最慢的单个平台。

    串行时约 27s/视频 → 并发后约 10s/视频。
    """
    tasks = {
        "xiaohongshu": lambda: _gen_xhs_data(content_ctx, folder_name, info, title),
        "douyin":       lambda: _gen_dy_data(content_ctx, folder_name, info, title),
        "bilibili":     lambda: _gen_bili_data(content_ctx, folder_name, info, title),
        "kuaishou":     lambda: _gen_ks_data(content_ctx, folder_name, info, title),
    }
    results: dict = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(fn): key for key, fn in tasks.items()}
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as e:
                console.log(f"[red]❌ {key} 并发生成失败: {e}[/red]")
                results[key] = {}
    return results


# ==================== 核心逻辑 ====================

def generate_metadata_for_folder(folder: Path):
    """为单个目录生成 metadata.json"""
    meta_path = folder / "metadata.json"

    # 读取已有元数据
    existing_meta = {}
    if meta_path.exists():
        try:
            existing_meta = json.loads(meta_path.read_text(encoding='utf-8'))
        except Exception:
            pass

    # 四个平台均已有元数据时跳过（节省 API 额度）
    _target_platforms = ("douyin", "xiaohongshu", "bilibili", "kuaishou")
    if existing_meta and all(
        existing_meta.get("platforms", {}).get(p)
        for p in _target_platforms
    ):
        console.log(f"  ⏭️ [dim]元数据已完整，跳过: {folder.name}[/dim]")
        return

    # 1. 从 Excel 获取原始信息
    info = get_excel_info(folder.name)
    if info:
        console.log(f"  📎 [dim]Excel 匹配成功: {info.get('title', '')[:30]}[/dim]")

    # 2. 确定中文标题
    title = existing_meta.get("translated_title") or info.get("title") or existing_meta.get("title") or folder.name

    # 3. 读取字幕（优先 artifacts/ 目录下，兼容旧路径）
    srt_candidates = [
        folder / "artifacts" / "trans.srt",
        folder / "trans.srt",
        folder / "artifacts" / "output.srt",
    ]
    srt_text = ""
    for srt_path in srt_candidates:
        srt_text = _read_srt_text(srt_path, max_chars=3000)
        if srt_text:
            break

    # 4. 构建统一内容上下文
    content_ctx = _build_content_context(title, info, srt_text)
    console.log(f"🧠 [cyan]正在并发生成多平台运营策划: {title[:25]}...[/cyan]")

    # 5. 并发调用 4 个平台生成器（串行 ~27s → 并发 ~10s）
    platform_data = _generate_all_platforms(content_ctx, folder.name, info, title)
    xhs_data  = platform_data.get("xiaohongshu", {})
    dy_data   = platform_data.get("douyin", {})
    bili_data = platform_data.get("bilibili", {})
    ks_data   = platform_data.get("kuaishou", {})

    # 6. 构建最终元数据
    summary = info.get("summary") or info.get("translated_text") or ""
    new_meta = {
        "title": folder.name,
        "translated_title": title,
        "summary": summary,
        "category": info.get("category", "未分类"),
        "topics": info.get("topics", []),
        "channel": info.get("channel", "Unknown"),
        "original_link": info.get("original_link", ""),
        "publish_date": info.get("publish_date", ""),
        "generate_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "platforms": {
            "douyin": {
                "title": dy_data.get("title", title)[:30],
                "tags": dy_data.get("tags", ["热点"]),
            },
            "xiaohongshu": {
                "title": xhs_data.get("title", title)[:30],
                "desc": xhs_data.get("desc", f"{title}\n\n{summary}"),
                "tags": [],  # 标签已包含在 desc 中
            },
            "bilibili": {
                "title": bili_data.get("title", title)[:80],
                "desc": bili_data.get("desc", summary),
                "tags": ["干货", "分享", "热点知识"] + _build_fallback_tags(info)[:1],
            },
            "kuaishou": {
                "title": ks_data.get("title", title)[:18],
                "tags": ks_data.get("tags", ["热点"]),
            },
        },
    }

    meta_path.write_text(json.dumps(new_meta, ensure_ascii=False, indent=2), encoding="utf-8")
    console.log(f"✅ [green]元数据生成成功:[/green] {folder.name} -> {title}")


def _clear_platforms(folders):
    """清除各文件夹 metadata.json 中的 platforms 块，使生成逻辑强制重跑"""
    count = 0
    for folder in folders:
        meta_path = folder / "metadata.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if "platforms" in meta:
                meta.pop("platforms")
                meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
                count += 1
        except Exception as e:
            console.log(f"  [yellow]⚠️ 清除 {folder.name} platforms 失败: {e}[/yellow]")
    console.log(f"[cyan]🗑️ 已清除 {count} 个文件夹的 platforms 缓存[/cyan]")


def process_ready_dir(force: bool = False):
    """遍历 ready_to_publish 补全元数据

    Parameters
    ----------
    force : bool
        True 时先清除各文件夹 metadata.json 中的 platforms 块，强制重新生成
    """
    if not READY_DIR.exists():
        console.log(f"[red]❌ 目录不存在: {READY_DIR}[/red]")
        return

    folders = [f for f in READY_DIR.iterdir() if f.is_dir() and f.name not in ("done", "failed")]
    if not folders:
        console.log("[yellow]⚠️ 无待处理目录[/yellow]")
        return

    if force:
        _clear_platforms(folders)

    console.rule("[bold cyan]元数据智能化补全[/bold cyan]")
    for folder in folders:
        generate_metadata_for_folder(folder)


if __name__ == "__main__":
    import sys
    process_ready_dir(force="--force" in sys.argv or "-f" in sys.argv)