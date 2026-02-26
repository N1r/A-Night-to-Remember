"""
_base.py
--------
所有平台上传器的公共基础模块。

提供：
  - 统一路径配置
  - 浏览器反检测启动
  - Cookie 加载/保存
  - 通用工具函数（人工延迟、截图、封面查找等）
"""

import asyncio
import json
import math
import os
import random
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

from playwright.async_api import async_playwright, BrowserContext
from rich.console import Console

# ==================== 路径配置（全局唯一定义）====================

PROJECT_ROOT  = Path(__file__).parent.parent.parent.absolute()
ARCHIVES_DIR  = PROJECT_ROOT / "storage" / "ready_to_publish"
STORAGE_DIR   = PROJECT_ROOT / "storage"
COOKIES_DIR   = STORAGE_DIR  / "cookies"
BROWSER_DIR   = STORAGE_DIR  / "browser_data"
TASKS_DIR     = STORAGE_DIR  / "tasks"
DEBUG_DIR     = PROJECT_ROOT / "output" / "debug"
LOG_DIR       = PROJECT_ROOT / "output" / "publish_logs"

HISTORY_FILE     = TASKS_DIR / "publish_history.json"
DAILY_QUOTA_FILE = TASKS_DIR / "daily_quota.json"

# stealth.min.js 路径（如果存在则注入）
STEALTH_JS = PROJECT_ROOT / "3_post_processing" / "media" / "common" / "stealth.min.js"

# 全局开关：默认 False（有头模式），可通过环境变量 HEADLESS=1 覆盖
HEADLESS_MODE = os.environ.get("HEADLESS", "").lower() in ("1", "true", "yes")

# 确保关键目录存在
for _d in [COOKIES_DIR, BROWSER_DIR, TASKS_DIR, DEBUG_DIR, LOG_DIR]:
    _d.mkdir(parents=True, exist_ok=True)

console = Console()

# ==================== 桌面环境变量（有头模式 Linux 必须）====================

if sys.platform.startswith("linux"):
    if not os.environ.get("DISPLAY"):
        os.environ["DISPLAY"] = ":0"
    _uid = os.getuid()
    if not os.environ.get("XDG_RUNTIME_DIR"):
        os.environ["XDG_RUNTIME_DIR"] = f"/run/user/{_uid}"
    if not os.environ.get("DBUS_SESSION_BUS_ADDRESS"):
        os.environ["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{_uid}/bus"

# ==================== 反检测浏览器参数 ====================

STEALTH_ARGS = [
    "--no-sandbox",
    "--disable-blink-features=AutomationControlled",
    "--disable-automation",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-infobars",
    "--disable-extensions",
    "--disable-dev-shm-usage",
    "--ignore-certificate-errors",
    "--password-store=basic",
    "--use-mock-keychain",
    "--lang=zh-CN,zh;q=0.9,en;q=0.8",
    "--disable-features=UserAgentClientHint",
    "--metrics-recording-only",
]

# 多 UA 池：每个平台使用固定但不同的 UA，避免同一平台每次切换被识别
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
]

# 每个平台绑定固定 UA，保持会话指纹一致
_PLATFORM_UA: dict = {
    "douyin":      USER_AGENTS[0],
    "xiaohongshu": USER_AGENTS[1],
    "kuaishou":    USER_AGENTS[2],
    "tencent":     USER_AGENTS[3],
    "bilibili":    USER_AGENTS[4],
}

# 内置轻量 stealth 脚本（stealth.min.js 缺失时使用）
_INLINE_STEALTH = """
// 1. 隐藏 webdriver 特征
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

// 2. 补全 chrome 对象（自动化环境缺失此对象）
if (!window.chrome) {
    window.chrome = {
        app: {isInstalled: false},
        runtime: {},
        loadTimes: function(){return {};},
        csi: function(){return {};}
    };
}

// 3. 修复 permissions API 的通知权限探测
try {
    const _orig = navigator.permissions.query.bind(navigator.permissions);
    navigator.permissions.query = (p) =>
        p.name === 'notifications'
            ? Promise.resolve({state: Notification.permission, onchange: null})
            : _orig(p);
} catch(e) {}

// 4. 补全 navigator.plugins（自动化环境通常为空）
if (navigator.plugins.length === 0) {
    const mkPlugin = (name, fn, desc) => {
        const mt = {type:'application/pdf', suffixes:'pdf', description:desc};
        const pl = {name, filename:fn, description:desc, length:1,
                    item:()=>mt, namedItem:()=>mt};
        mt.enabledPlugin = pl;
        return pl;
    };
    const arr = [
        mkPlugin('Chrome PDF Plugin','internal-pdf-viewer','Portable Document Format'),
        mkPlugin('Chrome PDF Viewer','mhjfbmdgcfjbbpaeojofohoefgiehjai',''),
        mkPlugin('Native Client','internal-nacl-plugin',''),
    ];
    Object.defineProperty(arr, '__proto__', {value: PluginArray.prototype});
    Object.defineProperty(navigator, 'plugins', {get: () => arr});
}

// 5. 修正 navigator.languages
Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN','zh','en-US','en']});
"""

# ==================== 通用工具函数 ====================

async def human_sleep(min_s: float = 1.5, max_s: float = 4.5):
    """模拟人类操作的随机等待"""
    await asyncio.sleep(random.uniform(min_s, max_s))


async def bezier_mouse_move(page, end_x: float, end_y: float):
    """
    沿三次贝塞尔曲线将鼠标移到目标坐标，模拟真实手部轨迹。

    使用 smoothstep 缓动：起末慢、中间快，并加入随机曲率偏移。
    """
    try:
        vp = page.viewport_size or {"width": 1280, "height": 720}
        start_x = random.uniform(vp["width"]  * 0.2, vp["width"]  * 0.8)
        start_y = random.uniform(vp["height"] * 0.2, vp["height"] * 0.8)

        dx, dy = end_x - start_x, end_y - start_y
        length  = max(1.0, math.hypot(dx, dy))

        # 垂直偏移决定弧度
        dev    = min(length * 0.35, 110.0)
        perp_x = -dy / length * random.uniform(dev * 0.3, dev)
        perp_y =  dx / length * random.uniform(dev * 0.3, dev)
        if random.random() < 0.5:
            perp_x, perp_y = -perp_x, -perp_y

        cp1x = start_x + dx * 0.30 + perp_x
        cp1y = start_y + dy * 0.30 + perp_y
        cp2x = start_x + dx * 0.70 + perp_x * 0.5
        cp2y = start_y + dy * 0.70 + perp_y * 0.5

        steps = min(max(int(length / 12), 12), 40)
        for i in range(1, steps + 1):
            t = i / steps
            e = t * t * (3.0 - 2.0 * t)          # smoothstep
            x = ((1-e)**3*start_x + 3*(1-e)**2*e*cp1x
                 + 3*(1-e)*e**2*cp2x + e**3*end_x)
            y = ((1-e)**3*start_y + 3*(1-e)**2*e*cp1y
                 + 3*(1-e)*e**2*cp2y + e**3*end_y)
            await page.mouse.move(x, y)
            # 速度：起末慢、中间快
            spf = 1.0 + 0.6 * abs(t - 0.5)
            await asyncio.sleep(random.uniform(0.007, 0.022) * spf)
    except Exception:
        pass


async def random_mouse_move(page):
    """随机移动鼠标到屏幕内某处（贝塞尔曲线路径）"""
    try:
        vp = page.viewport_size or {"width": 1280, "height": 720}
        tx = random.uniform(vp["width"]  * 0.1, vp["width"]  * 0.9)
        ty = random.uniform(vp["height"] * 0.1, vp["height"] * 0.9)
        await bezier_mouse_move(page, tx, ty)
    except Exception:
        pass


async def human_click(page, locator, button: str = "left"):
    """
    拟人化点击：贝塞尔曲线移到元素附近，短暂停顿后点击偏离中心的位置。
    兼容 Playwright Locator 与 ElementHandle。
    """
    try:
        box = await locator.bounding_box()
        if box and box["width"] > 0 and box["height"] > 0:
            tx = box["x"] + box["width"]  * random.uniform(0.32, 0.68)
            ty = box["y"] + box["height"] * random.uniform(0.32, 0.68)
            await bezier_mouse_move(page, tx, ty)
            await asyncio.sleep(random.uniform(0.06, 0.18))
            await page.mouse.click(tx, ty, button=button)
            return
    except Exception:
        pass
    # 兜底：直接调用 locator.click()
    try:
        await locator.click()
    except Exception:
        pass


async def human_scroll(page, delta_y: int = 300):
    """
    拟人化滚动：分多步完成，带轻微水平随机抖动。
    delta_y 正数向下，负数向上。
    """
    try:
        steps = random.randint(4, 8)
        per_step = delta_y / steps
        for _ in range(steps):
            drift_x = random.uniform(-4.0, 4.0)
            await page.mouse.wheel(drift_x, per_step * random.uniform(0.85, 1.15))
            await asyncio.sleep(random.uniform(0.04, 0.14))
    except Exception:
        pass


async def warm_up_page(page, duration_s: float = None):
    """
    页面预热：用随机滚动 + 鼠标移动模拟自然阅读行为，降低操作节奏特征。
    duration_s  总时长（秒），默认随机 2-4s。
    """
    if duration_s is None:
        duration_s = random.uniform(2.0, 4.0)
    actions = random.randint(2, 4)
    per_action = max(0.3, duration_s / actions)
    for _ in range(actions):
        r = random.random()
        try:
            if r < 0.45:
                await human_scroll(page, random.randint(80, 280))
            elif r < 0.75:
                vp = page.viewport_size
                if vp:
                    tx = random.uniform(vp["width"]  * 0.1, vp["width"]  * 0.9)
                    ty = random.uniform(vp["height"] * 0.1, vp["height"] * 0.9)
                    await bezier_mouse_move(page, tx, ty)
            # else: 纯停顿
        except Exception:
            pass
        await asyncio.sleep(random.uniform(per_action * 0.6, per_action * 1.4))


async def take_screenshot(page, prefix: str, output_dir: Path = None):
    """保存调试截图"""
    out = output_dir or DEBUG_DIR
    out.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%H%M%S")
    path = out / f"{prefix}_{ts}.png"
    try:
        await page.screenshot(path=str(path), full_page=True)
        console.print(f"[dim]📸 截图已保存: {path.name}[/dim]")
    except Exception:
        pass


def find_video(folder: Path) -> Optional[Path]:
    """
    在视频文件夹内查找目标 mp4，优先返回 output_sub.mp4（压制后成品），
    无则按修改时间降序返回第一个 mp4。
    """
    preferred = folder / "output_sub.mp4"
    if preferred.exists():
        return preferred
    mp4s = sorted(folder.glob("*.mp4"), key=lambda x: x.stat().st_mtime, reverse=True)
    return mp4s[0] if mp4s else None


def find_cover(video_path: Path) -> Optional[Path]:
    """在视频所在文件夹内查找封面图（优先同名，其次 cover.png/jpg）"""
    for ext in [".jpg", ".png", ".jpeg", ".webp"]:
        c = video_path.with_suffix(ext)
        if c.exists():
            return c
    for name in ["cover", "cover_raw"]:
        for ext in [".png", ".jpg", ".jpeg"]:
            c = video_path.parent / f"{name}{ext}"
            if c.exists():
                return c
    return None


def is_valid_cover(img_path: Path, min_w: int = 752, min_h: int = 360) -> bool:
    """检查封面图是否达到最小分辨率要求"""
    try:
        from PIL import Image
        with Image.open(img_path) as img:
            w, h = img.size
            return w >= min_w and h >= min_h
    except Exception:
        return False


def get_chrome_executable() -> Optional[str]:
    """查找系统安装的真实 Chrome，降低自动化特征"""
    if sys.platform.startswith("linux"):
        for path in [
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/opt/google/chrome/google-chrome",
        ]:
            if os.path.exists(path):
                return path
    elif sys.platform == "win32":
        chrome = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        if os.path.exists(chrome):
            return chrome
    return None


# ==================== 浏览器上下文管理 ====================

async def create_browser_context(
    playwright_instance,
    platform_name: str,
    headless: bool = None,
    viewport: dict = None,
    use_stealth: bool = True,
    slow_mo: int = 0,
) -> BrowserContext:
    """
    创建带反检测的持久化浏览器上下文。

    Parameters
    ----------
    playwright_instance : Playwright 实例
    platform_name       : 平台名称（用于 profile 和 cookie 目录隔离）
    headless            : 是否无头模式（默认使用全局 HEADLESS_MODE）
    viewport            : 视窗大小（默认 1280x720）
    use_stealth         : 是否启用 stealth.min.js（默认 True）
    slow_mo             : 操作延迟 ms（默认 0）

    Returns
    -------
    BrowserContext
    """
    if headless is None:
        headless = HEADLESS_MODE

    data_dir = BROWSER_DIR / f"{platform_name}_profile"
    data_dir.mkdir(parents=True, exist_ok=True)

    vp = viewport or {"width": 1280, "height": 720}

    # 附加随机窗口尺寸到参数中
    extra_args = STEALTH_ARGS + [
        f"--window-size={random.randint(1280, 1440)},{random.randint(800, 900)}"
    ]

    # 每个平台使用固定 UA，保持指纹会话一致性
    _ua = _PLATFORM_UA.get(platform_name, USER_AGENTS[0])

    context = await playwright_instance.chromium.launch_persistent_context(
        user_data_dir=str(data_dir),
        executable_path=get_chrome_executable(),
        headless=headless,
        args=extra_args,
        user_agent=_ua,
        viewport=vp,
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
        ignore_default_args=["--enable-automation"],
        slow_mo=slow_mo,
    )

    # 注入反检测脚本：优先使用完整版 stealth.min.js，否则用内置轻量版
    if use_stealth and STEALTH_JS.exists():
        await context.add_init_script(path=str(STEALTH_JS))
        console.log(f"[dim]🛡️ stealth.min.js 已注入 ({platform_name})[/dim]")
    else:
        await context.add_init_script(_INLINE_STEALTH)
        if not use_stealth:
            console.log(f"[dim]🛡️ 内置 stealth 脚本已注入 ({platform_name})[/dim]")

    # 加载平台 Cookie
    await load_cookies(context, platform_name)

    return context


async def load_cookies(context: BrowserContext, platform_name: str):
    """从本地文件加载 Cookie 到浏览器上下文"""
    cookie_path = COOKIES_DIR / f"{platform_name}_cookies.json"
    if not cookie_path.exists():
        # 尝试旧命名格式
        alt_names = [
            f"{platform_name}_cookie.json",
            f"tc_cookies.json" if platform_name == "tencent" else "",
        ]
        for alt in alt_names:
            if alt:
                alt_path = COOKIES_DIR / alt
                if alt_path.exists():
                    cookie_path = alt_path
                    break

    if not cookie_path.exists():
        console.log(f"[yellow]⚠️ {platform_name} Cookie 文件不存在[/yellow]")
        return

    try:
        raw = json.loads(cookie_path.read_text(encoding="utf-8"))
        cookies = raw if isinstance(raw, list) else raw.get("cookies", [])
        if cookies:
            await context.add_cookies(cookies)
            console.log(f"[dim]🍪 {platform_name} Cookie 已加载[/dim]")
    except Exception as e:
        console.log(f"[yellow]⚠️ {platform_name} Cookie 加载失败: {e}[/yellow]")


async def save_cookies(context: BrowserContext, platform_name: str):
    """将当前浏览器 Cookie 保存到本地文件"""
    cookie_path = COOKIES_DIR / f"{platform_name}_cookies.json"
    try:
        cookies = await context.cookies()
        cookie_path.write_text(
            json.dumps(cookies, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        console.log(f"[dim]🍪 {platform_name} Cookie 已保存[/dim]")
    except Exception as e:
        console.log(f"[yellow]⚠️ {platform_name} Cookie 保存失败: {e}[/yellow]")


# ==================== 模拟人工输入 ====================

async def type_like_human(page, text: str, speed: str = "normal"):
    """
    模拟人工打字，带真实节奏感。

    特性：
      - 三档速度控制（fast / normal / slow）
      - 随机"爆发模式"：连续几个字快速输入
      - 标点/空格自动延长停顿
      - 偶发思考停顿（约每 25 字触发一次）

    speed: 'fast' | 'normal' | 'slow'
    """
    speed_map = {
        "fast":   (15, 55),
        "normal": (35, 110),
        "slow":   (70, 190),
    }
    min_d, max_d = speed_map.get(speed, (35, 110))
    burst = 0  # 剩余"快速连打"字数

    for i, char in enumerate(text):
        # 爆发模式：以约 6% 概率触发，连续 3-8 字加速
        if burst > 0:
            delay = random.randint(min_d // 2, min_d)
            burst -= 1
        else:
            delay = random.randint(min_d, max_d)
            if random.random() < 0.06:
                burst = random.randint(3, 8)

        # 标点/空格/换行 停顿更长
        if char in "，。！？,.!? \n":
            delay = int(delay * random.uniform(1.5, 2.8))
        elif char in "；：;:()（）[]【】":
            delay = int(delay * random.uniform(1.2, 1.8))
        elif char in "#@":
            delay = int(delay * random.uniform(1.1, 1.5))

        # 偶发思考停顿（约每 25 个字一次）
        if i > 0 and random.random() < 0.035:
            await asyncio.sleep(random.uniform(0.4, 1.2))

        await page.keyboard.type(char, delay=delay)

    await asyncio.sleep(random.uniform(0.3, 0.7))


def clean_tag(text: str) -> str:
    """
    清理话题标签，只保留字母、数字、中文和下划线。
    符合小红书、抖音等平台对话题内特殊符号的限制。
    """
    if not text:
        return ""
    # 移除非法字符，保留中文(u4e00-u9fa5)、字母(a-zA-Z)、数字(0-9)和下划线
    # Python 3 re.sub 如果带 UNICODE 标志，\w 已包含大部分中文字符，但显式指定更安全
    cleaned = re.sub(r'[^\w\u4e00-\u9fa5]', '', text)
    return cleaned.strip()
