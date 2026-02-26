import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

COOKIES_PATH = Path("/home/nir/alipay_cookies.json")
TARGET_URL = "https://c.alipay.com/page/content-creation/publish/short-video?appId=2030080880492910"


def load_cookies(path: Path) -> list[dict]:
    """Load cookies from JSON and clean up fields Playwright doesn't accept."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    cleaned = []
    for c in raw:
        cookie = {
            "name": c["name"],
            "value": c["value"],
            "domain": c["domain"],
            "path": c.get("path", "/"),
            "httpOnly": c.get("httpOnly", False),
            "secure": c.get("secure", False),
        }
        # Playwright rejects expires=-1; omit it for session cookies
        if c.get("expires", -1) != -1:
            cookie["expires"] = c["expires"]
        # sameSite must be "Strict" | "Lax" | "None"
        same_site = c.get("sameSite", "Lax")
        if same_site in ("Strict", "Lax", "None"):
            cookie["sameSite"] = same_site
        cleaned.append(cookie)
    return cleaned


async def login_with_cookies():
    print(f"Loading cookies from: {COOKIES_PATH}")
    cookies = load_cookies(COOKIES_PATH)
    print(f"Loaded {len(cookies)} cookies")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )

        # Inject cookies before navigating
        await context.add_cookies(cookies)
        print("Cookies injected.")

        page = await context.new_page()

        print(f"Navigating to: {TARGET_URL}")
        await page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30_000)

        # Give JS a moment to redirect if session is invalid
        await page.wait_for_timeout(3000)

        current_url = page.url
        title = await page.title()
        print(f"Title : {title}")
        print(f"URL   : {current_url}")

        # Simple heuristic: if we ended up on a login page the session expired
        if any(kw in current_url for kw in ("login", "auth", "passport", "qrcode")):
            print("\n❌ Login FAILED — cookies are expired. Please refresh them.")
        else:
            print("\n✅ Login SUCCEEDED — cookies are valid!")
            # Optionally save authenticated storage state for re-use
            state_path = Path(__file__).parent / "auth_state.json"
            await context.storage_state(path=str(state_path))
            print(f"Auth state saved to: {state_path}")

        input("\nPress Enter to close the browser...")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(login_with_cookies())
