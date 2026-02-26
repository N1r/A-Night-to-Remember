"""
get_cookies.py
--------------
交互式 Cookie 获取工具。

支持平台：
  1 - 抖音创作者平台
  2 - 小红书创作者平台
  3 - 腾讯视频（视频号/企鹅号）
  4 - B 站（bilibili）
  5 - 全部平台（依次获取）

Cookie 统一保存到：storage/cookies/

运行方式：
    /home/ADing/miniconda3/envs/videolingo/bin/python apps/cli/get_cookies.py
"""

import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright

# ==================== 路径配置 ====================
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
COOKIES_DIR  = PROJECT_ROOT / "storage" / "cookies"
PROFILES_DIR = PROJECT_ROOT / "storage" / "browser_data" / "cookie_profiles"

COOKIES_DIR.mkdir(parents=True, exist_ok=True)
PROFILES_DIR.mkdir(parents=True, exist_ok=True)

# ==================== 平台定义 ====================
PLATFORMS = {
    "1": {
        "name":        "抖音创作者平台",
        "key":         "douyin",
        "url":         "https://creator.douyin.com/",
        "cookie_file": COOKIES_DIR / "douyin_cookies.json",
        "viewport":    {"width": 1920, "height": 1080},
    },
    "2": {
        "name":        "小红书创作者平台",
        "key":         "xiaohongshu",
        "url":         "https://creator.xiaohongshu.com/",
        "cookie_file": COOKIES_DIR / "xiaohongshu_cookie.json",
        "viewport":    {"width": 1400, "height": 900},
    },
    "3": {
        "name":        "腾讯视频（视频号）",
        "key":         "tencent",
        "url":         "https://shizi.qq.com/",
        "cookie_file": COOKIES_DIR / "tencent_cookies.json",
        "viewport":    {"width": 1920, "height": 1080},
    },
    "4": {
        "name":        "B 站（bilibili）",
        "key":         "bilibili",
        "url":         "https://www.bilibili.com/",
        "cookie_file": COOKIES_DIR / "bili_cookies.json",
        "viewport":    {"width": 1920, "height": 1080},
    },
}

# ==================== 核心逻辑 ====================

async def get_cookie_for_platform(choice: str) -> bool:
    """打开浏览器，等待用户手动登录，然后保存 Cookie"""
    platform = PLATFORMS[choice]
    name        = platform["name"]
    key         = platform["key"]
    url         = platform["url"]
    cookie_file = platform["cookie_file"]
    viewport    = platform["viewport"]
    profile_dir = PROFILES_DIR / key

    profile_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*55}")
    print(f"  🌐  {name}")
    print(f"{'='*55}")
    print(f"  目标网址  : {url}")
    print(f"  Cookie 路径: {cookie_file}")
    print(f"{'='*55}")
    print("\n  ➡️  浏览器即将打开，请在浏览器中完成登录。")
    print("  ➡️  登录完成后，回到此终端按 [Enter] 保存 Cookie。\n")

    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=False,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                    f"--window-size={viewport['width']},{viewport['height']}",
                    "--lang=zh-CN",
                ],
                viewport=viewport,
            )

            # 反检测
            await context.add_init_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
            )

            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(url, timeout=60000)

            # 等待用户登录
            input("  ✅ 登录完成后按 [Enter] 保存 Cookie...")

            await asyncio.sleep(1)
            cookies = await context.cookies()
            await context.close()

        # 保存为数组格式（Playwright 标准格式）
        cookie_file.write_text(
            json.dumps(cookies, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        print(f"\n  ✅ Cookie 保存成功！共 {len(cookies)} 条")
        print(f"  📁 路径: {cookie_file}\n")
        return True

    except Exception as e:
        print(f"\n  ❌ 获取 Cookie 失败: {e}\n")
        return False


# ==================== 主菜单 ====================

def print_menu():
    print("\n" + "="*55)
    print("  🍪  平台 Cookie 获取工具")
    print("="*55)
    for k, v in PLATFORMS.items():
        cookie_exists = "✅" if v["cookie_file"].exists() else "⬜"
        print(f"  {k} - {cookie_exists} {v['name']}")
    print(f"  5 - 🔄 全部平台（依次获取）")
    print(f"  0 - 退出")
    print("="*55)


async def main():
    while True:
        print_menu()
        try:
            choice = input("\n  请选择平台 [0-5]: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n  👋 已退出\n")
            break

        if choice == "0":
            print("\n  👋 已退出\n")
            break
        elif choice in PLATFORMS:
            await get_cookie_for_platform(choice)
        elif choice == "5":
            print("\n  🔄 依次获取所有平台 Cookie...\n")
            for k in PLATFORMS:
                ok = await get_cookie_for_platform(k)
                if not ok:
                    print(f"  ⚠️  {PLATFORMS[k]['name']} 获取失败，继续下一个...")
                cont = input("\n  继续下一个平台？[Enter 继续 / q 退出]: ").strip().lower()
                if cont == "q":
                    break
        else:
            print("  ❌ 无效选项，请重新输入")


if __name__ == "__main__":
    asyncio.run(main())
