
import asyncio
import os
import sys
from pathlib import Path
from playwright.async_api import async_playwright
from rich.console import Console
from rich.panel import Panel

# 添加模块路径
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).parent / "uploaders"))

from uploaders._base import (
    create_browser_context, save_cookies,
    COOKIES_DIR, HEADLESS_MODE
)
from verify_cookies import VERIFY_CONFIG as PLATFORMS

console = Console()

async def get_cookie_for_platform(platform_key, config):
    console.print(f"\n[bold cyan]🚀 启动 {config['name']} ({platform_key}) 登录流程...[/bold cyan]")
    
    use_stealth = "--no-stealth" not in sys.argv

    async with async_playwright() as playwright:
        # 强制使用有头模式
        context = await create_browser_context(playwright, platform_key, headless=False, use_stealth=use_stealth)
        page = await context.new_page()
        
        try:
            console.print(f"🔗 正在打开: {config['url']}")
            await page.goto(config['url'], timeout=60000)
            
            console.print(f"[yellow]⚠️ 请在弹出的浏览器中手动完成登录...[/yellow]")
            console.print(f"   (登录成功后，脚本会自动检测并保存 Cookie)")

            # 循环检查登录状态
            max_retries = 300 # 5分钟
            for i in range(max_retries):
                # 检查 URL 或 关键元素
                if "login" not in page.url and (
                    await page.query_selector(config.get("verify_selector", "body")) 
                    or await page.evaluate("() => document.cookie.includes('session')") # 简单兜底
                ):
                    # 额外等待确保加载完成
                    console.print("[green]✅ 检测到可能的登录成功，等待 3 秒...[/green]")
                    await asyncio.sleep(3)
                    
                    # 保存 Cookie
                    await save_cookies(context, platform_key)
                    console.print(f"[bold green]🎉 {config['name']} Cookie 已保存至: {COOKIES_DIR}/{platform_key}_cookies.json[/bold green]")
                    break
                
                await asyncio.sleep(1)
                if i % 10 == 0:
                    console.print(f"⏳ 等待登录... ({i}/{max_retries})")
            else:
                console.print(f"[red]❌ {config['name']} 登录超时[/red]")

        except Exception as e:
            console.print(f"[red]❌ 发生错误: {e}[/red]")
        finally:
            await context.close()

async def main():
    console.print(Panel("🍪 全平台 Cookie 获取助手", style="bold blue"))
    
    # 获取用户选择
    options = list(PLATFORMS.keys())
    
    # 自动模式：如果没有任何参数，或者有 --all，就自动全跑（除了 B 站）
    auto_run = "--all" in sys.argv or len(sys.argv) <= 1
    
    for key in options:
        if key == "bilibili": continue # 跳过 B 站

        config = PLATFORMS[key]
        
        # 如果指定了 --select，则只跑选中的
        if "--select" in sys.argv and key not in sys.argv:
            continue
            
        if not auto_run:
            choice = console.input(f"\n是否获取 [bold]{config['name']}[/bold] 的 Cookie? (y/n/q) [default: y]: ").strip().lower()
            if choice == 'q':
                break
            if choice == 'n':
                continue
        else:
            console.print(f"\n[dim]自动选中: {config['name']}[/dim]")
            
        await get_cookie_for_platform(key, config)

    console.print("\n[bold green]✨ 所有任务结束[/bold green]")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        console.print("\n[red]🚫 用户中断[/red]")
