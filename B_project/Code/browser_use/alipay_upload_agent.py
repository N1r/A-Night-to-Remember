import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

from browser_use import Agent, BrowserSession, Controller
from browser_use.browser.profile import BrowserProfile
from browser_use.llm.openai.chat import ChatOpenAI

# ── paths ──────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
VIDEO_PATH  = str(BASE_DIR / "video/好莱坞演员为何不敢得罪民主党？.mp4")
COVER_PATH  = str(BASE_DIR / "video/cover.png")
AUTH_STATE  = str(BASE_DIR / "auth_state.json")
HISTORY_OUT = str(BASE_DIR / "run_history.json")

# ── video metadata ─────────────────────────────────────────────────────────
meta = json.loads((BASE_DIR / "video/metadata.json").read_text(encoding="utf-8"))
VIDEO_TITLE = meta.get("translated_title", "好莱坞演员为何不敢得罪民主党？")

# Name for the 生活号 account (≤20 chars). Change if needed.
ACCOUNT_NAME = "好莱坞深度解析"

START_URL  = "https://c.alipay.com/page/life-account/index?appId=2030080880492910"
UPLOAD_URL = "https://c.alipay.com/page/content-creation/publish/short-video?appId=2030080880492910"

# ── custom controller actions ──────────────────────────────────────────────
controller = Controller()


@controller.action("inject_video_file")
async def inject_video_file(browser_session: BrowserSession, file_path: str):
    """Set the file input to the video path, fire events, wait for upload to visibly start."""
    print(f"\n[inject_video_file] START — file_path={file_path}")
    try:
        page = await browser_session.get_current_page()
        print(f"[inject_video_file] page url = {page.url}")

        # Use CDP to set files — works even in shadow DOM
        inputs = await page.query_selector_all('input[type="file"]')
        print(f"[inject_video_file] found {len(inputs)} file inputs")
        if not inputs:
            return "❌ No file input found on page."

        await inputs[0].set_input_files(file_path)
        print("[inject_video_file] set_input_files done — dispatching events")

        await page.evaluate("""
            const inp = document.querySelector('input[type=file]');
            if (inp) {
                inp.dispatchEvent(new Event('change', {bubbles: true}));
                inp.dispatchEvent(new Event('input',  {bubbles: true}));
            }
        """)

        # Poll up to 15 s for any visual sign of upload starting
        for i in range(15):
            await asyncio.sleep(1)
            bar   = await page.query_selector('[role="progressbar"]')
            body  = await page.inner_text('body')
            print(f"[inject] t={i+1}s bar={bar is not None}  body_snippet={body[:80].replace(chr(10),' ')}")
            if bar or '好莱坞' in body:
                return f"✅ Upload started! bar={bar is not None}. Now call wait_for_upload_complete."

        body = await page.inner_text('body')
        return f"⚠️ File injected but upload UI not confirmed after 15s. Body: {body[:300]}"
    except Exception as e:
        import traceback
        print(f"[inject_video_file] EXCEPTION: {traceback.format_exc()}")
        return f"❌ inject_video_file failed: {e}"


@controller.action("inject_cover_image")
async def inject_cover_image(browser_session: BrowserSession, file_path: str):
    """Inject cover image into the cover file input."""
    page = await browser_session.get_current_page()
    try:
        inputs = page.locator('input[type="file"]')
        count = await inputs.count()
        target = inputs.nth(1) if count > 1 else inputs.first
        await target.set_input_files(file_path)
        await page.evaluate("""
            const inputs = document.querySelectorAll('input[type=file]');
            const inp = inputs.length > 1 ? inputs[1] : inputs[0];
            if (inp) inp.dispatchEvent(new Event('change', {bubbles: true}));
        """)
        return f"✅ Cover injected: {file_path}"
    except Exception as e:
        return f"❌ inject_cover_image failed: {e}"


@controller.action("wait_for_upload_complete")
async def wait_for_upload_complete(browser_session: BrowserSession):
    """Poll until upload finishes: progress bar gone/100%, or video thumbnail appears."""
    page = await browser_session.get_current_page()
    for _ in range(72):   # max 6 minutes
        await asyncio.sleep(5)
        # Check Ant Design progress bar
        bar = await page.query_selector('[role="progressbar"]')
        if bar is None:
            return "✅ Upload complete — page ready for title and publish."
        val = await bar.get_attribute("aria-valuenow")
        if val == "100":
            return "✅ Upload complete (100%)."
    return "⚠️ Upload timed out after 6 min — check manually."


# ── prompt ─────────────────────────────────────────────────────────────────
PROMPT = f"""
You are a browser automation agent. Your goal is to publish a short video on 支付宝创作者中心.
You are ALREADY LOGGED IN — never try to scan a QR code.

## Steps (follow in exact order)

### 1 · Navigate to the start page
Go to: {START_URL}
Wait for the page to fully load (networkidle or 5 s).

### 2 · Handle 生活号 signup (only if redirected to signup page)
If the current URL contains "signup" or the page shows "入驻生活号":
  a. Find the "号名称" input field and type: {ACCOUNT_NAME}
  b. Find the avatar upload input (input[type=file]) and call `inject_cover_image`
     with file_path="{COVER_PATH}" to set the profile picture.
  c. Check the "同意《生活号服务协议》" checkbox.
  d. Click the "立即开通" button.
  e. Wait up to 10 s for the page to redirect away from signup.
If the page does NOT show signup (already registered), skip to step 3.

### 3 · Navigate to the video upload page
Go to: {UPLOAD_URL}
Wait until the page contains an upload area or "上传视频" heading.

### 4 · Inject the video file
- DO NOT click the upload button — it would open a native OS dialog.
- Call `inject_video_file` with file_path="{VIDEO_PATH}".
- After ✅ response, call `wait_for_upload_complete` and wait for ✅.

### 5 · Fill in the title
- The title field (标题描述) may already be auto-filled from the filename.
- Check its current value. If it already contains "{VIDEO_TITLE}", leave it.
- If it is empty or different, clear it and type exactly: {VIDEO_TITLE}

### 6 · Upload cover image (if a cover/封面 field is visible)
- Call `inject_cover_image` with file_path="{COVER_PATH}".

### 7 · Publish
- Click the "发布" or "提交" button.
- Wait for a success message ("发布成功", "审核中") or redirect.

### 8 · Confirm
- Report the final URL and any confirmation text visible on screen.
- End your reply with exactly: MISSION_COMPLETE

## Hard rules
- NEVER click anything that would open a system file picker dialog.
- If a step fails, retry once before reporting failure.
- If redirected to a login page at any point, stop and report it immediately.
"""


# ── run ────────────────────────────────────────────────────────────────────
async def run():
    llm = ChatOpenAI(
        model="LongCat-Flash-Thinking",
        base_url="https://api.longcat.chat/openai",
        api_key="ak_2Bx3q80SQ4SU5ta3pC9Do4F845y6K",
    )

    browser_profile = BrowserProfile(
        headless=False,
        is_local=True,
        storage_state=AUTH_STATE,   # start already authenticated
    )
    session = BrowserSession(browser_profile=browser_profile)

    agent = Agent(
        task=PROMPT,
        llm=llm,
        browser_session=session,
        controller=controller,
        use_thinking=True,
    )

    try:
        result = await agent.run()
        print(f"\n--- Result ---\n{result}")

        # Save run history
        history_data = {
            "run_at": datetime.now().isoformat(),
            "video": VIDEO_PATH,
            "title": VIDEO_TITLE,
            "result_text": str(result),
        }
        Path(HISTORY_OUT).write_text(
            json.dumps(history_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"History saved → {HISTORY_OUT}")

    finally:
        await session.stop()


if __name__ == "__main__":
    asyncio.run(run())
