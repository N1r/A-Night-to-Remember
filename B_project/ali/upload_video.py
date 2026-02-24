import asyncio
import os
import sys
from datetime import datetime
from playwright.async_api import async_playwright, Page, expect

# --- 配置信息 ---
CONFIG = {
    "video_path": "/home/n1r/桌面/ali/output.mp4",     # 视频文件路径
    "cover_path": "/home/n1r/桌面/ali/unnamed.jpg",    # 封面图片路径
    "title": "我的精彩视频",                            # 视频标题
    "base_url": "https://c.alipay.com/page/portal/home", # 支付宝创作者中心首页
    "app_id": "2030080880492910",                      # 从历史记录中提取的 App ID
    "login_timeout": 300000,                           # 等待扫码登录的超时时间 (5分钟)
}

def log(message: str):
    """带时间戳的日志输出，方便查看执行进度。"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {message}")

async def wait_for_user_login(page: Page):
    """等待用户手动完成扫码登录过程。"""
    log("正在等待用户手动登录 (请扫描页面上的二维码)...")
    try:
        # 等待页面出现能够证明已进入后台的元素，例如“发布视频”按钮
        await page.wait_for_selector("text=发布视频", timeout=CONFIG["login_timeout"])
        log("成功：已检测到登录，正在进入后台。")
    except Exception as e:
        log(f"警告：等待登录超时或未找到后台元素: {e}")
        # 即使超时也尝试继续，因为某些重定向可能不一致

async def navigate_to_upload(page: Page):
    """导航至短视频发布页面。"""
    log("正在跳转到短视频发布页面...")
    
    # 优先尝试点击页面上的“发布视频”按钮
    publish_btn = page.locator("a:has-text('发布视频')").first
    if await publish_btn.is_visible():
        await publish_btn.click()
    else:
        # 如果按钮不可见，则直接使用 appId 拼接 URL 进行跳转
        upload_url = f"https://c.alipay.com/page/content-creation/publish/short-video?appId={CONFIG['app_id']}"
        await page.goto(upload_url)
    
    # 等待上传组件加载完成 (通过查找文件输入框来确认)
    await page.wait_for_selector("input[type='file']", timeout=30000)
    log("成功：已到达上传页面。")

async def perform_upload(page: Page):
    """处理视频文件上传和标题填写。"""
    log(f"开始上传视频文件: {CONFIG['video_path']}")
    
    # 定位专用的视频上传输入框
    video_input = page.locator("input[type='file'][accept*='video']")
    await video_input.set_input_files(CONFIG["video_path"])
    
    # 填写视频标题
    log(f"正在设置视频标题: {CONFIG['title']}")
    title_input = page.locator("input[placeholder*='标题']").first
    await title_input.fill(CONFIG["title"])

async def handle_cover_image(page: Page):
    """处理封面图上传逻辑：打开弹窗、选择文件并确认。"""
    log("正在处理封面图片...")
    
    # 点击“上传封面”触发区域
    upload_cover_trigger = page.locator("text=上传封面").first
    await upload_cover_trigger.click()
    
    # 等待对话框出现并切换到“上传封面”标签页
    cover_tab = page.locator("div[role='tab']:has-text('上传封面')")
    await expect(cover_tab).to_be_visible(timeout=10000)
    await cover_tab.click()
    
    # 定位并操作对话框内的隐藏文件输入框
    log(f"正在上传封面文件: {CONFIG['cover_path']}")
    image_input = page.locator("input[type='file'][accept*='jpg']")
    await image_input.set_input_files(CONFIG["cover_path"])
    
    # 等待图片处理/预览完成后点击“完成”按钮
    done_btn = page.locator("button:has-text('完成')")
    await expect(done_btn).to_be_enabled(timeout=20000)
    await done_btn.click()
    log("成功：封面图片已上传并应用。")

async def finalize_and_publish(page: Page):
    """提交发布并处理可能出现的画质提醒。"""
    log("正在提交发布...")
    
    publish_btn = page.locator("button:has-text('确认发布')")
    await expect(publish_btn).to_be_enabled(timeout=30000)
    await publish_btn.click()
    
    # 检测是否出现了“画质清晰度较低”的拦截弹窗
    log("正在检测是否有画质提醒弹窗...")
    continue_publish_btn = page.locator("button:has-text('继续发布')")
    try:
        # 等待 5 秒观察是否有弹窗出现
        await expect(continue_publish_btn).to_be_visible(timeout=5000)
        log("检测到画质提醒，点击“继续发布”。")
        await continue_publish_btn.click()
    except Exception:
        log("未检测到画质阻塞弹窗，继续流程。")

    # 最终状态确认
    log("正在验证发布结果内容...")
    try:
        # 查找页面是否显示“审核中”状态
        await page.wait_for_selector("text=审核中", timeout=30000)
        log("发布成功：视频已进入“审核中”状态。")
    except Exception:
        log("发布操作已执行，但未能自动验证“审核中”状态，请在后台手动确认。")

async def run_automation():
    # 检查本地文件是否存在
    if not os.path.exists(CONFIG["video_path"]):
        log(f"错误：未在路径 {CONFIG['video_path']} 找到视频文件")
        return
    if not os.path.exists(CONFIG["cover_path"]):
        log(f"错误：未在路径 {CONFIG['cover_path']} 找到封面图片")
        return

    async with async_playwright() as p:
        log("启动 Chromium 浏览器...")
        # 设置 headless=False 以便用户能够肉眼看见浏览器并进行扫码
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            log(f"正在访问：{CONFIG['base_url']}...")
            await page.goto(CONFIG["base_url"])
            
            await wait_for_user_login(page)
            await navigate_to_upload(page)
            await perform_upload(page)
            await handle_cover_image(page)
            await finalize_and_publish(page)
            
        except Exception as e:
            log(f"执行过程中发生致命错误: {e}")
        finally:
            log("执行完毕。浏览器将在 15 秒后关闭。")
            await asyncio.sleep(15)
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run_automation())
