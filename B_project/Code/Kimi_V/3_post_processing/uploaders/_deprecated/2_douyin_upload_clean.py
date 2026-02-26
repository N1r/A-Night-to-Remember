"""
2_douyin_upload_clean.py
------------------------
抖音视频上传模块（每日限发 1 条）。

改进：
  - 视频上传期间并行填写标题/标签，不等上传完成再操作
  - 注入完整 stealth.min.js 反检测脚本
  - 更完善的浏览器反自动化参数

可独立运行：
    python modules/uploaders/2_douyin_upload_clean.py

也可被 auto_publish_all.py 调用：
    from modules.uploaders.2_douyin_upload_clean import run_douyin
    await run_douyin(videos, state_mgr)
"""

import asyncio
import json
import random
import sys
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright

from rich.console import Console
from rich.panel import Panel

# ==================== 桌面环境变量（有头模式必须）====================
import os as _os
if not _os.environ.get("DISPLAY"):
    _os.environ["DISPLAY"] = ":0"
_uid = _os.getuid()
if not _os.environ.get("XDG_RUNTIME_DIR"):
    _os.environ["XDG_RUNTIME_DIR"] = f"/run/user/{_uid}"
if not _os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
    _os.environ["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{_uid}/bus"
_xauth = f"/var/run/lightdm/root/{_os.environ.get('DISPLAY', ':0')}"
if _os.path.exists(_xauth) and not _os.environ.get("XAUTHORITY"):
    _os.environ["XAUTHORITY"] = _xauth

# ==================== 路径配置 ====================
PROJECT_ROOT  = Path(__file__).parent.parent.parent.absolute()
ARCHIVES_FOLDER  = PROJECT_ROOT / "archives"
VIDEO_FOLDER  = ARCHIVES_FOLDER  # 使用archives目录
COOKIES_FILE  = PROJECT_ROOT / "storage" / "cookies" / "douyin_cookies.json"
USER_DATA_DIR = PROJECT_ROOT / "storage" / "browser_data" / "douyin_profile"
DEBUG_DIR     = PROJECT_ROOT / "output"  / "debug_douyin"
STATUS_FILE   = PROJECT_ROOT / "storage" / "tasks" / ".douyin_daily_lock.json"
STEALTH_JS    = PROJECT_ROOT / "modules" / "common" / "stealth.min.js"

DONE_DIR   = VIDEO_FOLDER / "done"
FAILED_DIR = VIDEO_FOLDER / "failed"

for _p in [VIDEO_FOLDER, COOKIES_FILE.parent, USER_DATA_DIR, DEBUG_DIR, DONE_DIR, FAILED_DIR]:
    _p.mkdir(parents=True, exist_ok=True)

# 欧美政治高权重话题标签
POLITICS_TAGS = ["#欧美政治", "#国际新闻", "#美国政治", "#时政热点", "#深度分析",
                 "#国际局势", "#硬核观点", "#时事评论"]

# 热门标签
POPULAR_TAGS = ["#国际", "#时事", "#政治", "#新闻", "#热点", "#分析",
                "#观点", "#评论", "#深度", "#国际政治", "#美国", "#欧洲"]

# 吸引人的标题前缀
ENGAGING_PREFIXES = ["🔥 ", "💥 ", "⚡ ", "🎯 ", "🚀 ", "💎 ", "⭐ ", "🌟 "]

console = Console()

# ==================== 反检测浏览器参数 ====================
STEALTH_ARGS = [
    "--no-sandbox",
    "--disable-blink-features=AutomationControlled",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-infobars",
    "--disable-extensions",
    "--disable-dev-shm-usage",
    "--disable-web-security",
    "--disable-features=IsolateOrigins,site-per-process",
    "--lang=zh-CN",
    "--window-size=1920,1080",
    # 随机化 User-Agent 相关
    "--disable-features=UserAgentClientHint",
]

# ==================== 工具函数 ====================

async def _screenshot(page, name_prefix: str):
    ts = datetime.now().strftime("%H%M%S")
    path = DEBUG_DIR / f"{name_prefix}_{ts}.png"
    try:
        await page.screenshot(path=str(path), full_page=True)
        console.print(f"[dim]📸 截图: {path.name}[/dim]")
    except Exception:
        pass

# ==================== 智能标题生成函数 ====================
def generate_douyin_title(video_path: Path, metadata=None):
    """
    智能生成抖音标题
    """
    import random
    
    # 获取视频文件夹名作为基础
    folder_name = video_path.parent.name
    stem = video_path.stem
    
    # 吸引人的前缀
    prefix = random.choice(ENGAGING_PREFIXES)
    
    # 智能标签选择
    if "政治" in folder_name or "美国" in folder_name:
        selected_tags = " ".join(random.sample(POLITICS_TAGS, 3))
    else:
        selected_tags = " ".join(random.sample(POPULAR_TAGS, 2))
    
    # 构建完整标题，控制长度
    base_title = stem[:20]  # 限制基础标题长度
    full_title = f"{prefix}{base_title} {selected_tags}"
    
    # 确保标题不超过抖音限制（通常200字符）
    if len(full_title) > 180:
        full_title = full_title[:177] + "..."
    
    return full_title

async def _human_sleep(min_s=0.8, max_s=2.0, context=None):
    """拟人化等待函数"""
    # 根据上下文调整等待时间
    if context == "thinking":  # 思考时间
        await asyncio.sleep(random.uniform(min_s * 1.5, max_s * 2.0))
    elif context == "loading":  # 加载时间
        await asyncio.sleep(random.uniform(min_s * 2, max_s * 3))
    elif context == "error_recovery":  # 错误恢复时间
        await asyncio.sleep(random.uniform(1.0, 2.5))
    else:
        await asyncio.sleep(random.uniform(min_s, max_s))

async def _type_text(page, text: str):
    """模拟人工打字 - 拟人化版本"""
    for i, char in enumerate(text):
        # 随机打字速度，模拟真实用户
        delay = random.randint(30, 120)
        
        # 添加更多停顿，模拟思考
        if char in [" ", "，", "。", "！", "？"]:
            delay = random.randint(50, 150)
        
        # 话题标签后增加思考时间
        if char == "#":
            delay = random.randint(80, 200)
            await asyncio.sleep(0.3)   # 话题联想等待
        
        # 随机错误和修正（模拟真实输入）
        if random.random() < 0.05:  # 5%概率出错
            await page.keyboard.press("Backspace")
            await asyncio.sleep(0.2)
            await page.keyboard.type(char, delay=delay)
        else:
            await page.keyboard.type(char, delay=delay)
        
        # 段落间增加更长停顿
        if char in ["。", "！"] and i < len(text) - 1:
            await asyncio.sleep(random.uniform(0.8, 1.5))

# ==================== 核心上传逻辑 ====================

async def _upload_one(context, video_path: Path) -> tuple[bool, str]:
    """
    上传单个视频到抖音。
    关键改进：触发文件上传后立即开始填写标题/标签，
    不等上传进度条完成，节省约 30-60 秒。
    """
    page = await context.new_page()
    stem = video_path.stem

    try:
        console.log("🌐 进入抖音创作中心...")
        await page.goto(
            "https://creator.douyin.com/creator-micro/content/upload",
            timeout=60000
        )
        await _human_sleep(1.5, 2.5)

        # 登录检测
        if "login" in page.url or await page.get_by_text("扫码登录").count() > 0:
            await _screenshot(page, f"LOGIN_EXPIRED_{stem}")
            return False, "Cookie 失效，需要重新登录"

        # ── Step 1: 触发上传（不等待完成）──
        console.log(f"📤 触发上传: [cyan]{video_path.name}[/cyan]")
        try:
            file_input = page.locator("input[type='file']").first
            await file_input.set_input_files(str(video_path))
        except Exception as e:
            return False, f"找不到上传入口: {e}"

        await _human_sleep(1.5, 2.5)  # 等待页面切换到编辑态

        # ── Step 2: 上传进行中，同时填写标题 ──
        console.log("📝 填写标题（上传同步进行中）...")
        try:
            title_box = page.locator(".notranslate").first
            await title_box.wait_for(state="visible", timeout=15000)
            await title_box.click()
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")

            # 使用智能标题生成
            full_title_text = generate_douyin_title(video_path)
            await _type_text(page, full_title_text)
            await _human_sleep(1.0, 2.0)  # 更长的思考时间
        except Exception as e:
            console.log(f"[yellow]⚠️ 标题填写失败: {e}，继续等待上传[/yellow]")

        # ── Step 3: 等待上传完成（此时标题已填好）──
        console.log("⏳ 等待上传完成...")
        try:
            await page.get_by_text("重新上传").wait_for(state="visible", timeout=300000)
            console.log("✅ 上传完成")
        except Exception:
            await _screenshot(page, f"UPLOAD_TIMEOUT_{stem}")
            return False, "上传超时（5min）"

        await _human_sleep(1.0, 1.5)

        # ── Step 4: 发布 ──
        console.log("🚀 提交发布...")
        try:
            pub_btn = page.get_by_role("button", name="发布", exact=True)
            await pub_btn.wait_for(state="visible", timeout=10000)
            await pub_btn.click()
        except Exception as e:
            await _screenshot(page, f"NO_BTN_{stem}")
            return False, f"找不到发布按钮: {e}"

        # ── Step 5: 跳转校验 ──
        try:
            await page.wait_for_url("**/content/manage**", timeout=30000)
            console.log("[bold green]✅ 发布成功（页面跳转确认）[/bold green]")
            return True, "Success"
        except Exception:
            await _screenshot(page, f"NO_JUMP_{stem}")
            if await page.get_by_text("发布成功").count() > 0:
                return True, "Success(Toast确认)"
            return False, "发布后未跳转，请查看截图"

    except Exception as e:
        await _screenshot(page, f"EXCEPTION_{stem}")
        return False, f"异常: {str(e)[:120]}"
    finally:
        await page.close()

# ==================== 对外接口 ====================

async def run_douyin(videos: list[Path], state_mgr=None) -> bool:
    """
    从 videos 列表中选取第一个未上传的视频发布到抖音。

    Parameters
    ----------
    videos    : ready_to_publish 下所有 .mp4 文件的 Path 列表
    state_mgr : StateManager 实例（可选）

    Returns
    -------
    bool : 是否成功上传
    """
    console.rule("[magenta]抖音上传（每日 1 条）[/magenta]")

    # ── 每日额度检查 ──
    today = datetime.now().strftime("%Y-%m-%d")
    if state_mgr is not None:
        if not state_mgr.can_upload_today("douyin"):
            console.print("[yellow]📅 今日抖音额度已满，跳过[/yellow]")
            return False
    else:
        if STATUS_FILE.exists():
            try:
                lock = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
                if lock.get("last_success_date") == today:
                    console.print(f"[yellow]📅 今日 ({today}) 抖音任务已完成，跳过[/yellow]")
                    return False
            except Exception:
                pass

    # ── 选取目标视频 ──
    if state_mgr is not None:
        target = next(
            (v for v in videos if not state_mgr.is_uploaded(v.parent.name, "douyin")),
            None
        )
    else:
        all_vids = sorted(VIDEO_FOLDER.rglob("*.mp4"))
        target = next(
            (v for v in all_vids if v.parent.name not in ("done", "failed")),
            None
        )

    if target is None:
        console.print("[green]✅ 抖音无待办任务[/green]")
        return False

    console.print(f"🎯 目标视频: [cyan]{target.name}[/cyan]")

    # ── 启动浏览器（带完整反检测）──
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            args=STEALTH_ARGS,
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            color_scheme="light",
        )

        # 注入 stealth.min.js（完整反检测）
        if STEALTH_JS.exists():
            await context.add_init_script(path=str(STEALTH_JS))
            console.log("[dim]🛡️ stealth.min.js 已注入[/dim]")
        else:
            # 降级：基础 webdriver 隐藏
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

        # 注入 Cookie
        if COOKIES_FILE.exists():
            try:
                raw = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
                cookies = raw if isinstance(raw, list) else raw.get("cookies", [])
                await context.add_cookies(cookies)
                console.log("[dim]🍪 抖音 Cookie 已加载[/dim]")
            except Exception as e:
                console.log(f"[yellow]⚠️ Cookie 加载失败: {e}[/yellow]")

        success, msg = await _upload_one(context, target)

        # 保存最新 Cookie
        try:
            fresh = await context.cookies()
            COOKIES_FILE.write_text(
                json.dumps(fresh, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )
        except Exception:
            pass

        await context.close()

    # ── 更新状态 ──
    if success:
        console.print(f"[bold green]✅ 抖音发布成功: {target.name}[/bold green]")
        if state_mgr is not None:
            state_mgr.mark_uploaded(target.parent.name, "douyin")
            state_mgr.increment_daily_quota("douyin")
        else:
            STATUS_FILE.write_text(
                json.dumps({"last_success_date": today}),
                encoding="utf-8"
            )
    else:
        console.print(f"[red]❌ 抖音发布失败: {msg}[/red]")

    return success

# ==================== 独立运行入口 ====================

if __name__ == "__main__":
    asyncio.run(run_douyin([], state_mgr=None))