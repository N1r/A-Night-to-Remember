import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

COOKIES_PATH = Path("/home/nir/alipay_cookies.json")
TARGET_URL = "https://c.alipay.com/page/content-creation/publish/short-video?appId=2030080880492910"
LOGIN_URL = "https://auth.alipay.com/login/index.htm"


async def save_cookies_after_login():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )
        page = await context.new_page()

        print("Opening Alipay login page — please scan the QR code...")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)

        # Wait until the URL leaves the login/auth domain (user scanned + logged in)
        print("Waiting for you to scan and complete login...")
        await page.wait_for_url(
            lambda url: not any(kw in url for kw in ("login", "auth", "passport", "qrcode")),
            timeout=120_000,  # 2 minutes to scan
        )

        print("Login detected! Navigating to creator center...")
        await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_timeout(2000)

        # Collect all cookies from the context
        cookies = await context.cookies()

        # Save to JSON
        COOKIES_PATH.write_text(
            json.dumps(cookies, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"\n✅ Saved {len(cookies)} cookies to: {COOKIES_PATH}")

        # Also save Playwright storage state for direct reuse
        state_path = Path(__file__).parent / "auth_state.json"
        await context.storage_state(path=str(state_path))
        print(f"✅ Auth state saved to: {state_path}")

        input("\nPress Enter to close the browser...")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(save_cookies_after_login())
