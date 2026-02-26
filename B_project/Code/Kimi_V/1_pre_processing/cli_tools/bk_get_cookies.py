import asyncio
import json
import os
import sys
import platform
import shutil
import time
import argparse
from pathlib import Path

# 第三方库
from playwright.async_api import async_playwright
try:
    from pyvirtualdisplay import Display
    HAS_XVFB = True
except ImportError:
    HAS_XVFB = False

from rich.console import Console
from rich.panel import Panel
from rich.theme import Theme

# ==================== 配置区 ====================
console = Console(theme=Theme({"info": "cyan", "warning": "yellow", "error": "bold red", "success": "bold green"}))

SCRIPT_DIR = Path(__file__).parent
COOKIES_DIR = SCRIPT_DIR.parent.parent / "storage" / "cookies" # Use global storage
BROWSER_DATA_DIR = SCRIPT_DIR.parent.parent / "storage" / "browser_data"
QR_CODE_PATH = SCRIPT_DIR.parent.parent / "output" / "login_qrcode.png"

COOKIES_DIR.mkdir(parents=True, exist_ok=True)
BROWSER_DATA_DIR.mkdir(parents=True, exist_ok=True)
QR_CODE_PATH.parent.mkdir(parents=True, exist_ok=True)

USE_XVFB = True if platform.system() == "Linux" and not os.environ.get("DISPLAY") else False
HEADLESS = False 

# 平台配置字典
PLATFORM_CONFIG = {
    "douyin": {
        "name": "抖音",
        "url": "https://creator.douyin.com/creator-micro/home",
        "logged_in_selectors": [".avatar-container", ".header-right", "text=发布视频", "text=内容管理"],
        "login_text": "扫码登录"
    },
    "bilibili": {
        "name": "B站",
        "url": "https://member.bilibili.com/platform/home",
        "logged_in_selectors": [".avatar-container", ".header-avatar-wrap", "text=投稿", "text=内容管理"],
        "login_text": "扫码登录" # B站也有扫码登录，选择器可能不同，需实测
    },
    "kuaishou": {
        "name": "快手",
        "url": "https://cp.kuaishou.com/article/publish/video",
        "logged_in_selectors": [".avatar-wrapper", "text=发布作品"],
        "login_text": "扫码登录"
    },
    "xhs": {
        "name": "小红书",
        "url": "https://creator.xiaohongshu.com/publish/publish",
        "logged_in_selectors": [".avatar", "text=发布笔记"],
        "login_text": "扫码登录"
    },
    "videohao": {
        "name": "视频号",
        "url": "https://channels.weixin.qq.com/platform/post/create",
        "logged_in_selectors": [".finder-avatar", "text=发表视频"],
        "login_text": "扫码登录"
    }
}

# ==================== 辅助函数 ====================

async def inject_stealth(context):
    await context.add_init_script("""
        Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
        const getParameter = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(parameter) {
            if (parameter === 37445) { return 'Google Inc. (NVIDIA)'; }
            if (parameter === 37446) { return 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1050 Ti Direct3D11 vs_5_0 ps_5_0, or similar)'; }
            return getParameter(parameter);
        };
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh'] });
    """)

def get_chrome_path():
    if platform.system() == "Linux":
        for p in ["/usr/bin/google-chrome-stable", "/usr/bin/google-chrome", "/bin/google-chrome-stable"]:
            if os.path.exists(p): return p
        return shutil.which("google-chrome-stable")
    elif platform.system() == "Windows":
        return r"C:\Program Files\Google\Chrome\Application\chrome.exe"
    return None

# ==================== 主逻辑 ====================

async def main():
    parser = argparse.ArgumentParser(description="Cookie Getter")
    parser.add_argument("--platform", type=str, default="douyin", help="Target platform (douyin, bilibili, etc.)")
    args = parser.parse_args()
    
    platform_key = args.platform
    if platform_key not in PLATFORM_CONFIG:
        console.print(f"[error]不支持的平台: {platform_key}. 支持: {list(PLATFORM_CONFIG.keys())}[/error]")
        return

    cfg = PLATFORM_CONFIG[platform_key]
    cookie_file = COOKIES_DIR / f"{platform_key}_cookies.json"
    user_data_dir = BROWSER_DATA_DIR / f"{platform_key}_profile"

    display = None
    if USE_XVFB and HAS_XVFB:
        console.print("[info]🖥️ 启动虚拟显示器 (Xvfb)...[/info]")
        display = Display(visible=0, size=(1920, 1080))
        display.start()

    try:
        console.clear()
        console.print(Panel.fit(f"[bold white]🍪 {cfg['name']} Cookie 获取工具[/bold white]", style="blue"))

        async with async_playwright() as p:
            user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            launch_args = [
                "--no-sandbox", "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled", 
                "--disable-infobars", "--window-size=1920,1080", "--start-maximized",
                "--disable-dev-shm-usage", "--no-zygote"
            ]

            console.print(f"[dim]📂 加载环境: {user_data_dir.name}[/dim]")
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                executable_path=get_chrome_path(),
                headless=HEADLESS, 
                viewport={"width": 1920, "height": 1080},
                user_agent=user_agent,
                args=launch_args
            )
            
            await inject_stealth(context)
            page = await context.new_page()

            console.print(f"[info]🔗 正在访问 {cfg['name']} 登录页...[/info]")
            try:
                await page.goto(cfg['url'], timeout=60000)
            except Exception as e:
                console.print(f"[error]❌ 页面加载出错: {e}[/error]")
                return

            await asyncio.sleep(5)

            # --- 循环检测登录状态 ---
            start_time = time.time()
            console.print("[info]🔍 等待登录... (请扫描二维码或在浏览器中登录)[/info]")
            
            last_qr_time = 0
            
            while True:
                if time.time() - start_time > 300: # 5分钟超时
                    console.print("[error]❌ 操作超时[/error]")
                    break

                # 检查登录成功标志
                is_logged_in = False
                for selector in cfg['logged_in_selectors']:
                    if await page.locator(selector).count() > 0:
                        is_logged_in = True
                        break
                
                if is_logged_in:
                    console.print("\n[success]🎉 验证成功！检测到登录态！[/success]")
                    break

                # 尝试截图二维码 (每5秒一次)
                if time.time() - last_qr_time > 5:
                    try:
                        # 简单粗暴全屏截图，由用户自己找二维码
                        await page.screenshot(path=QR_CODE_PATH, full_page=True)
                        last_qr_time = time.time()
                        console.print(f"[dim]📸 截图已更新: {QR_CODE_PATH.name}[/dim]")
                    except:
                        pass
                
                console.print(".", end="")
                sys.stdout.flush()
                await asyncio.sleep(2)

            # 保存 Cookie
            if is_logged_in:
                await asyncio.sleep(3) 
                cookies = await context.cookies()
                with open(cookie_file, 'w', encoding='utf-8') as f:
                    json.dump(cookies, f, indent=2)
                
                console.print(f"[success]💾 Cookie 已保存至: {cookie_file}[/success]")
            
            await context.close()

    except Exception as e:
        console.print(f"[error]发生异常: {e}[/error]")
    finally:
        if display:
            display.stop()
            console.print("[dim]🖥️ 虚拟显示器已关闭[/dim]")

if __name__ == "__main__":
    asyncio.run(main())