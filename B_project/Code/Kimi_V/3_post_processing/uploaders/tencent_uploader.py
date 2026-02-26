"""
tencent_uploader.py
-------------------
腾讯新闻自动化上传模块。

特点：
  - 不限每日发布数量（全量上传）
  - 支持封面上传 + 裁剪
  - 自动处理原创声明 / 素材来源弹窗

统一接口：
    await run(state_mgr) -> bool
"""

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

from _base import (
    ARCHIVES_DIR, LOG_DIR, HEADLESS_MODE,
    console, human_sleep, take_screenshot,
    find_cover, find_video, is_valid_cover,
    create_browser_context, save_cookies,
    warm_up_page, human_click, human_scroll,
)

PLATFORM = "tencent"
PUBLISH_URL = "https://shizi.qq.com/creation/video"


# ==================== 封面处理 ====================

async def _handle_cover_crop(page):
    """处理腾讯特有的封面裁剪弹窗"""
    try:
        dialog = page.get_by_role("dialog", name="裁剪封面")
        if await dialog.is_visible(timeout=5000):
            await dialog.locator("img").first.click()
            await human_sleep(0.5, 1)
            try:
                await page.get_by_text("封面未裁剪").first.click(timeout=1000)
            except Exception:
                pass
            await human_sleep(0.5, 1)
            await page.get_by_role("button", name="完 成").click()
            await dialog.wait_for(state="hidden", timeout=10000)
            return True
    except Exception:
        return False


async def _upload_cover(page, cover_path: Path):
    """上传自定义封面"""
    try:
        upload_btn = page.get_by_role("img", name="plus")
        if await upload_btn.is_visible(timeout=3000):
            await upload_btn.click()
            input_el = page.locator("span.ant-upload input[type='file']")
            await input_el.wait_for(state="attached", timeout=10000)
            await input_el.set_input_files(str(cover_path))
            await human_sleep(1, 2)
            await _handle_cover_crop(page)
            return True
    except Exception:
        pass
    return False


# ==================== 单视频上传 ====================

async def _upload_one(page, video_path: Path) -> tuple[bool, str]:
    """上传单个视频到腾讯视频号"""
    stem = video_path.stem

    try:
        import random
        # 1. 进入发布页
        await page.goto(PUBLISH_URL, timeout=60000)
        await page.wait_for_selector("button:has-text('本地上传')", timeout=20000)
        # 页面预热
        await warm_up_page(page, random.uniform(1.5, 3.0))

        # 2. 选择视频文件
        console.log(f"📤 正在上传: [cyan]{video_path.name}[/cyan]")
        await page.locator("input[type='file'][accept^='video']").set_input_files(str(video_path))

        # 3. 等待上传完成
        console.log("⏳ 等待上传...")
        try:
            await page.locator("text=视频上传成功").wait_for(timeout=300000)
            console.log("✅ 视频流传输完毕")
        except Exception:
            await take_screenshot(page, f"timeout_tencent_{stem}", LOG_DIR)
            return False, "视频上传超时(5min)"

        await human_sleep(1, 2)
        # 上传完成后滚动查看表单
        await human_scroll(page, random.randint(150, 300))
        await human_sleep(0.5, 1.0)

        # 4. 封面处理
        cover = find_cover(video_path)
        if cover and is_valid_cover(cover):
            console.log(f"🖼️ 上传封面: {cover.name}")
            await _upload_cover(page, cover)

        # 5. 填写摘要
        try:
            await page.get_by_placeholder("填写摘要可以快速传递核心信息").fill(stem)
        except Exception as e:
            console.log(f"[yellow]⚠️ 摘要填写失败: {e}[/yellow]")

        # 7. 原创声明
        try:
            await page.get_by_text("声明原创").click(timeout=1000)
            await page.get_by_text("该视频非AI生成").click(timeout=1000)
        except Exception:
            pass

        # 自主声明：优先"取材网络"，保底"暂无声明"
        try:
            await page.get_by_text("取材网络，谨慎甄别").click(timeout=2000)
        except Exception:
            try:
                await page.get_by_text("暂无声明").click(timeout=2000)
            except Exception:
                pass

        # 8. 发布
        console.log("🚀 提交发布...")
        _pub_btn = page.get_by_role("button", name="发 布")
        await human_scroll(page, random.randint(80, 150))
        await human_sleep(0.3, 0.6)
        await human_click(page, _pub_btn)

        # 9. 素材来源弹窗
        try:
            modal = page.get_by_text("素材来源信息")
            if await modal.is_visible(timeout=5000):
                await human_click(page, page.get_by_text("引用自站外媒体"))
                await human_click(page, page.get_by_role("button", name="确 定"))
                await modal.wait_for(state="hidden", timeout=5000)
                await human_sleep(1)
                await human_click(page, page.get_by_role("button", name="发 布"))
        except Exception:
            pass

        # 10. 确认发布弹窗
        try:
            confirm = page.get_by_role("button", name="确定发布")
            if await confirm.is_visible(timeout=5000):
                await confirm.click(force=True)
        except Exception:
            pass

        # 11. 跳转校验
        try:
            await page.wait_for_url("**/content/article-manage**", timeout=25000)
            console.print(f"[bold green]✅ {video_path.name} 发布成功[/bold green]")
            return True, "Success"
        except Exception:
            await take_screenshot(page, f"fail_tencent_{stem}", LOG_DIR)
            return False, "发布后未跳转"

    except Exception as e:
        await take_screenshot(page, f"error_tencent_{stem}", LOG_DIR)
        return False, f"异常: {str(e)[:120]}"


# ==================== 对外统一接口 ====================

async def run(state_mgr) -> bool:
    """
    腾讯视频号上传入口（全量上传，不限每日条数）。

    Parameters
    ----------
    state_mgr : StateManager 实例

    Returns
    -------
    bool : 是否全部成功
    """
    console.rule(f"[blue]腾讯视频上传（全量）[/blue]")

    # 筛选待上传视频（每文件夹只取 output_sub.mp4 或最新 mp4）
    pending_folders = sorted(
        [d for d in ARCHIVES_DIR.iterdir() if d.is_dir() and d.name not in ("done", "failed")],
        key=lambda x: x.stat().st_mtime, reverse=True,
    )
    pending = []
    for d in pending_folders:
        if state_mgr.is_uploaded(d.name, PLATFORM):
            continue
        vid = find_video(d)
        if vid:
            pending.append(vid)

    if not pending:
        console.print("[green]✅ 腾讯视频无待办任务[/green]")
        return False

    console.print(f"📋 待上传 {len(pending)} 个视频")

    all_ok = True
    async with async_playwright() as p:
        context = await create_browser_context(p, PLATFORM, use_stealth=False)
        page = await context.new_page()

        try:
            # 登录检测
            await page.goto(PUBLISH_URL, timeout=60000)
            if "login" in page.url or await page.get_by_text("微信登录").count() > 0:
                console.print("[yellow]⚠️ 腾讯视频未登录或 Session 过期[/yellow]")
                if HEADLESS_MODE:
                    console.print("[red]❌ 无头模式下无法手动登录[/red]")
                    return False
                await asyncio.to_thread(input, "✅ 登录成功后按 [Enter] 继续...")

            # 逐个上传
            for video in pending:
                success, msg = await _upload_one(page, video)
                if success:
                    state_mgr.mark_uploaded(video.parent.name, PLATFORM)
                    state_mgr.increment_daily_quota(PLATFORM)
                else:
                    console.print(f"[red]❌ {video.name}: {msg}[/red]")
                    all_ok = False

        finally:
            await save_cookies(context, PLATFORM)
            await context.close()

    return all_ok


# ==================== 独立运行入口 ====================

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from auto_publish_all import StateManager
    asyncio.run(run(StateManager()))
