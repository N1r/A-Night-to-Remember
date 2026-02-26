"""
verify_cookies.py
-----------------
无头浏览器 Cookie 有效性验证。

在正式发布前，快速检测各平台登录态是否仍然有效。
每个平台独立启动临时无头 Chromium，互不干扰发布用的持久化 Profile。
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, Tuple

from playwright.async_api import async_playwright
from rich.console import Console
from rich.table import Table

PROJECT_ROOT = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).parent / "uploaders"))

from uploaders._base import (
    COOKIES_DIR,
    STEALTH_ARGS,
    _INLINE_STEALTH,
    _PLATFORM_UA,
    USER_AGENTS,
)

console = Console()

# ==================== 各平台验证配置 ====================

_LOGIN_TEXTS_COMMON = [
    "扫码登录", "手机号登录", "账号登录", "二维码", "扫一扫",
    "立即登录", "请先登录", "马上登录", "登录后",
]

VERIFY_CONFIG: Dict[str, dict] = {
    "douyin": {
        "name": "抖音",
        "url": "https://creator.douyin.com/creator-micro/content/upload",
        "login_keywords": ["login", "passport"],
        "verify_selector": "text=发布作品",
        "page_login_texts": _LOGIN_TEXTS_COMMON + ["一键登录", "抖音登录"],
    },
    "xiaohongshu": {
        "name": "小红书",
        "url": "https://creator.xiaohongshu.com/publish/publish",
        "login_keywords": ["login", "signin"],
        "verify_selector": "text=发布笔记",
        "page_login_texts": _LOGIN_TEXTS_COMMON + ["小红书登录", "手机验证码"],
    },
    "kuaishou": {
        "name": "快手",
        "url": "https://cp.kuaishou.com/article/publish/video",
        "login_keywords": ["login", "passport"],
        "verify_selector": "text=发布作品",
        "page_login_texts": _LOGIN_TEXTS_COMMON + ["快手账号登录", "短信验证码登录"],
    },
    "tencent": {
        "name": "腾讯视频",
        "url": "https://om.qq.com/userAuth/index",
        "login_keywords": ["login"],
        "verify_selector": "text=首页",
        "page_login_texts": _LOGIN_TEXTS_COMMON + ["微信登录", "QQ登录"],
    },
}

# 最多同时验证的平台数（避免一次性启动太多无头浏览器）
_SEMAPHORE = asyncio.Semaphore(2)


async def _verify_one(
    playwright_instance,
    platform_key: str,
    config: dict,
    timeout: int = 25000,
) -> Tuple[bool, str]:
    """
    验证单个平台的 Cookie 是否有效（使用临时无头浏览器）。

    使用独立的非持久化 browser.launch()，不会影响发布用的 persistent_context。

    Returns
    -------
    (is_valid: bool, reason: str)
    """
    # 1. 检查 Cookie 文件
    cookie_path = COOKIES_DIR / f"{platform_key}_cookies.json"
    if not cookie_path.exists():
        return False, "Cookie 文件不存在"

    try:
        raw = json.loads(cookie_path.read_text(encoding="utf-8"))
        cookies = raw if isinstance(raw, list) else raw.get("cookies", [])
        if not cookies:
            return False, "Cookie 文件为空"
    except Exception as e:
        return False, f"读取失败: {e}"

    # 2. 启动临时无头浏览器
    browser = None
    context = None
    async with _SEMAPHORE:
        try:
            browser = await playwright_instance.chromium.launch(
                headless=True,
                args=STEALTH_ARGS,
            )
            context = await browser.new_context(
                user_agent=_PLATFORM_UA.get(platform_key, USER_AGENTS[0]),
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
            )
            await context.add_init_script(_INLINE_STEALTH)
            await context.add_cookies(cookies)

            page = await context.new_page()

            # 3. 访问平台创作者页面
            try:
                await page.goto(
                    config["url"],
                    timeout=timeout,
                    wait_until="domcontentloaded",
                )
            except Exception as e:
                return False, f"页面加载超时: {e}"

            await asyncio.sleep(3)  # 等待跳转稳定

            current_url = page.url.lower()

            # 4. 判断是否被重定向到登录页（URL 关键词）
            for keyword in config.get("login_keywords", ["login"]):
                if keyword in current_url:
                    return False, f"已跳转登录页 ({page.url[:55]}...)"

            # 4b. 检查页面可见文本中的中文登录提示（QR 码弹窗等不改变 URL 的情况）
            body_text = ""
            try:
                body_text = await page.inner_text("body", timeout=3000)
            except Exception:
                pass
            for phrase in config.get("page_login_texts", []):
                if phrase in body_text:
                    return False, f"页面含登录提示: 「{phrase}」"

            # 5. 检查登录成功的关键元素
            try:
                element = await page.wait_for_selector(
                    config["verify_selector"],
                    timeout=8000,
                    state="attached",
                )
                if element:
                    return True, "登录态有效"
            except Exception:
                pass

            # 6. 兜底：URL 未含登录关键词则视为有效
            return True, "URL 未重定向（兜底通过）"

        except Exception as e:
            return False, f"验证异常: {e}"
        finally:
            if context:
                try:
                    await context.close()
                except Exception:
                    pass
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass


async def verify_all_cookies(
    platforms: list = None,
) -> Dict[str, Tuple[bool, str]]:
    """
    并发验证各平台 Cookie 有效性（无头模式）。

    Parameters
    ----------
    platforms : 要验证的平台列表，默认全部平台

    Returns
    -------
    dict: {platform_key: (is_valid, reason)}
    """
    if platforms is None:
        platforms = list(VERIFY_CONFIG.keys())

    console.print("\n[bold cyan]🔍 Cookie 验证中（无头浏览器）...[/bold cyan]")

    async with async_playwright() as playwright:
        tasks = [
            _verify_one(playwright, key, VERIFY_CONFIG[key])
            for key in platforms
            if key in VERIFY_CONFIG
        ]
        task_results = await asyncio.gather(*tasks, return_exceptions=True)

    results: Dict[str, Tuple[bool, str]] = {}
    valid_keys = [k for k in platforms if k in VERIFY_CONFIG]
    for key, result in zip(valid_keys, task_results):
        if isinstance(result, Exception):
            results[key] = (False, f"内部异常: {result}")
        else:
            results[key] = result

    return results


def print_verification_results(results: Dict[str, Tuple[bool, str]]) -> bool:
    """
    打印验证结果表格。

    Returns
    -------
    bool: 是否所有平台均有效
    """
    table = Table(
        title="Cookie 验证结果",
        show_header=True,
        header_style="bold magenta",
        show_lines=True,
    )
    table.add_column("平台", style="cyan", width=12)
    table.add_column("状态", width=12)
    table.add_column("详情", style="dim")

    all_valid = True
    for platform_key, (is_valid, reason) in results.items():
        name = VERIFY_CONFIG.get(platform_key, {}).get("name", platform_key)
        if is_valid:
            status = "[bold green]✅ 有效[/bold green]"
        else:
            status = "[bold red]❌ 失效[/bold red]"
            all_valid = False
        table.add_row(name, status, reason)

    console.print(table)
    return all_valid


# ==================== 独立运行入口 ====================

if __name__ == "__main__":
    async def _main():
        results = await verify_all_cookies()
        all_valid = print_verification_results(results)
        if not all_valid:
            invalid = [
                VERIFY_CONFIG[k]["name"]
                for k, (v, _) in results.items()
                if not v
            ]
            console.print(
                f"\n[yellow]⚠️  失效平台: {', '.join(invalid)}"
                f"\n   请运行 python get_all_cookies.py 重新登录[/yellow]"
            )
        else:
            console.print("\n[bold green]✅ 所有平台 Cookie 均有效！[/bold green]")

    asyncio.run(_main())
