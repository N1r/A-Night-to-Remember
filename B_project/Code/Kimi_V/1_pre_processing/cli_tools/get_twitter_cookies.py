import asyncio
import json
import os
import sys
import platform
import shutil
from pathlib import Path
from playwright.async_api import async_playwright
from rich.console import Console
from rich.panel import Panel

# 配置
console = Console()
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
COOKIES_DIR = PROJECT_ROOT / "1_pre_processing" / "scrapers"
COOKIES_FILE = COOKIES_DIR / "twitter_cookies.json"
USER_DATA_DIR = PROJECT_ROOT / "storage" / "browser_data" / "twitter_profile"

COOKIES_DIR.mkdir(parents=True, exist_ok=True)
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

async def main():
    console.print(Panel.fit("[bold cyan]Twitter Cookie 获取工具[/bold cyan]"))
    
    async with async_playwright() as p:
        # 尝试寻找 Chrome 路径
        executable_path = None
        if platform.system() == "Linux":
            for p_path in ["/usr/bin/google-chrome-stable", "/usr/bin/google-chrome", "/bin/google-chrome-stable"]:
                if os.path.exists(p_path):
                    executable_path = p_path
                    break
        
        console.print(f"[info]正在启动浏览器... 用户数据目录: {USER_DATA_DIR}[/info]")
        
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            executable_path=executable_path,
            headless=False,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 720}
        )

        page = context.pages[0] if context.pages else await context.new_page()
        
        console.print("[yellow]请在打开的浏览器中登录 Twitter (X)。[/yellow]")
        console.print("[yellow]登录成功并回到首页后，回到这里按 Enter 键保存 Cookie。[/yellow]")
        
        await page.goto("https://x.com/home")
        
        # 使用 asyncio.to_thread 处理同步 input 避免阻塞事件循环
        await asyncio.to_thread(input, "\n完成登录后按 Enter 键继续...")
        
        cookies = await context.cookies()
        with open(COOKIES_FILE, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, indent=2)
            
        console.print(f"[bold green]✅ Cookie 已保存至: {COOKIES_FILE}[/bold green]")
        await context.close()

if __name__ == "__main__":
    asyncio.run(main())
