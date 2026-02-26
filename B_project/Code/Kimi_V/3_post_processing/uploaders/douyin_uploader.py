"""
douyin_uploader.py
------------------
抖音视频自动化上传模块（每日限发 1 条）。

特点：
  - 视频上传期间并行填写标题/标签，不等上传完成再操作
  - 注入 stealth.min.js 反检测脚本
  - 智能标题生成（emoji 前缀 + 热门话题标签）

统一接口：
    await run(state_mgr) -> bool
"""

import asyncio
import json
import random
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright

from _base import (
    ARCHIVES_DIR, TASKS_DIR,
    console, human_sleep, take_screenshot, find_cover, find_video,
    create_browser_context, save_cookies, type_like_human,
    warm_up_page, human_click, human_scroll, bezier_mouse_move,
)

import sys
PROJECT_ROOT = Path(__file__).parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from shared.domain import domain

PLATFORM = "douyin"
PUBLISH_URL = "https://creator.douyin.com/creator-micro/content/upload"

# 从领域配置读取标签
_dy_config = domain.get_upload_config("douyin")
DOMAIN_TAGS = _dy_config.get("domain_tags", [])
POPULAR_TAGS = _dy_config.get("popular_tags", [])
KEYWORD_TRIGGERS = _dy_config.get("keyword_triggers", [])
ENGAGING_PREFIXES = ["🔥 ", "💥 ", "⚡ ", "🎯 ", "🚀 ", "💎 ", "⭐ ", "🌟 "]


# ==================== 标题生成 ====================

def _generate_title(video_path: Path) -> str:
    """智能生成抖音标题（emoji + 关键词 + 话题标签）"""
    folder_name = video_path.parent.name
    stem = video_path.stem
    prefix = random.choice(ENGAGING_PREFIXES)

    # 检查关键词触发器
    use_domain = False
    for trigger in KEYWORD_TRIGGERS:
        if any(kw in folder_name for kw in trigger.get("keywords", [])):
            use_domain = True
            break

    if use_domain and DOMAIN_TAGS:
        tags = " ".join(random.sample(DOMAIN_TAGS, min(3, len(DOMAIN_TAGS))))
    elif POPULAR_TAGS:
        tags = " ".join(random.sample(POPULAR_TAGS, min(2, len(POPULAR_TAGS))))
    else:
        tags = ""

    base_title = stem[:20]
    full = f"{prefix}{base_title} {tags}".strip()
    return full[:180] if len(full) > 180 else full


# ==================== 单视频上传 ====================

async def _upload_one(context, video_path: Path) -> tuple[bool, str]:
    """上传单个视频到抖音"""
    page = await context.new_page()
    stem = video_path.stem

    try:
        # 加载元数据
        from _base import clean_tag
        title = _generate_title(video_path)
        meta_path = video_path.parent / "metadata.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                dy_meta = meta.get("platforms", {}).get("douyin", {})
                if dy_meta.get("title"):
                    title_text = dy_meta.get("title")
                    tags_list = [f"#{clean_tag(t)}" for t in dy_meta.get("tags", []) if 1 < len(t) <= 20]
                    tags = " ".join(tags_list)
                    prefix = random.choice(ENGAGING_PREFIXES)
                    title = f"{prefix}{title_text} {tags}".strip()
                    console.log(f"✅ 使用 AI 元数据: {title_text} (Tags: {len(tags_list)})")
            except Exception as me:
                console.log(f"⚠️ 解析元数据失败: {me}")

        console.log("🌐 进入抖音创作中心...")
        await page.goto(PUBLISH_URL, timeout=60000)
        await human_sleep(1.5, 2.5)
        # 页面预热：模拟真实用户浏览行为
        await warm_up_page(page, random.uniform(2.0, 3.5))

        # 登录检测 (等待跳转，增强反检测鲁棒性)
        console.log("⏳ 正在探测登录状态 (Max 20s)...")
        login_ok = False
        for i in range(10):
            # A. 检查是否存在上传入口
            if await page.locator("input[type='file']").count() > 0:
                login_ok = True
                break
            # B. 检查是否已经上传成功的“重新上传”或已经在发布编辑页
            if "upload" in page.url or "publish" in page.url:
                login_ok = True
                break
            
            # C. 明显的登录拦截
            if "login" in page.url:
                if i > 5: # 等了 10s 还是登录页，判定失效
                    break
            await asyncio.sleep(2)
        
        if not login_ok:
            await take_screenshot(page, f"LOGIN_EXPIRED_{stem}")
            return False, "Cookie 失效 或 登录页面异常 (Timeout)"

        console.log("✅ 登录状态确认就绪")
        # 登录后再做一次轻度预热，模拟用户"环顾"页面
        await warm_up_page(page, random.uniform(1.0, 2.0))

        # Step 1: 触发上传（不等待完成）
        console.log(f"📤 触发上传: [cyan]{video_path.name}[/cyan]")
        try:
            file_input = page.locator("input[type='file']").first
            # 移动鼠标到上传区域后再触发，不直接 set_input_files
            await bezier_mouse_move(page, 640, 360)
            await asyncio.sleep(random.uniform(0.3, 0.6))
            await file_input.set_input_files(str(video_path))
        except Exception as e:
            return False, f"找不到上传入口: {e}"
        await human_sleep(1.5, 2.5)
        # 上传触发后滚一下，模拟用户查看表单
        await human_scroll(page, random.randint(150, 300))

        # Step 2: 上传进行中，同时填写标题
        console.log(f"📝 填写标题: {title}")
        try:
            title_box = page.locator(".notranslate").first
            await title_box.wait_for(state="visible", timeout=15000)
            await title_box.click()
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await type_like_human(page, title)
            await human_sleep(1.0, 2.0)
        except Exception as e:
            console.log(f"[yellow]⚠️ 标题填写失败: {e}[/yellow]")

        # Step 3: 等待上传完成
        console.log("⏳ 等待上传完成...")
        try:
            # 等待“重新上传” 或 “上传成功” 或 “更换视频”
            await page.locator('text=/重新上传|更换|上传成功/').first.wait_for(state="visible", timeout=300000)
            console.log("✅ 上传完成")
        except Exception:
            await take_screenshot(page, f"TIMEOUT_{stem}")
            return False, "上传超时(5min)"

        await human_sleep(1.0, 1.5)

        # Step 4: 发布
        console.log("🚀 提交发布...")
        try:
            pub_btn = page.get_by_role("button", name="发布", exact=True)
            await pub_btn.wait_for(state="visible", timeout=10000)

            # 额外校验：等待按钮不再禁用 (处理后端转码中)
            for _ in range(20):
                if not await pub_btn.is_disabled():
                    break
                await asyncio.sleep(2)
                console.log("[dim]等待发布按钮生效...[/dim]")

            # 先滚到按钮再拟人化点击
            await human_scroll(page, random.randint(100, 200))
            await asyncio.sleep(random.uniform(0.3, 0.6))
            await human_click(page, pub_btn)
        except Exception as e:
            await take_screenshot(page, f"NO_BTN_{stem}")
            return False, f"找不到发布按钮: {e}"

        # Step 5: 跳转校验
        try:
            await page.wait_for_url("**/manage**", timeout=20000)
            console.log("[bold green]✅ 发布成功（页面跳转确认）[/bold green]")
            return True, "Success"
        except Exception:
            await take_screenshot(page, f"NO_JUMP_{stem}")
            if await page.get_by_text("发布成功").count() > 0:
                return True, "Success(Toast确认)"
            return False, "发布后未跳转"

    except Exception as e:
        await take_screenshot(page, f"EXCEPTION_{stem}")
        return False, f"异常: {str(e)[:120]}"
    finally:
        await page.close()


# ==================== 对外统一接口 ====================

async def run(state_mgr) -> bool:
    """
    抖音上传入口（每日 1 条）。

    Parameters
    ----------
    state_mgr : StateManager 实例

    Returns
    -------
    bool : 是否成功上传
    """
    console.rule("[magenta]抖音上传（每日 1 条）[/magenta]")

    # 每日额度检查
    if not state_mgr.can_upload_today(PLATFORM):
        console.print("[yellow]📅 今日抖音额度已满，跳过[/yellow]")
        return False

    # 选取目标视频（第一个未上传的，优先 output_sub.mp4）
    pending_folders = sorted(
        [d for d in ARCHIVES_DIR.iterdir() if d.is_dir() and d.name not in ("done", "failed")],
        key=lambda x: x.stat().st_mtime, reverse=True,
    )
    target = None
    for d in pending_folders:
        if state_mgr.is_uploaded(d.name, PLATFORM):
            continue
        vid = find_video(d)
        if vid:
            target = vid
            break

    if target is None:
        console.print("[green]✅ 抖音无待办任务[/green]")
        return False

    console.print(f"🎯 目标视频: [cyan]{target.name}[/cyan]")

    # 启动浏览器
    async with async_playwright() as p:
        context = await create_browser_context(
            p, PLATFORM,
            headless=False,  # 抖音反检测严格，建议有头模式
            viewport={"width": 1920, "height": 1080},
            use_stealth=True,
        )

        success, msg = await _upload_one(context, target)

        await save_cookies(context, PLATFORM)
        await context.close()

    # 更新状态
    if success:
        console.print(f"[bold green]✅ 抖音发布成功: {target.name}[/bold green]")
        state_mgr.mark_uploaded(target.parent.name, PLATFORM)
        state_mgr.increment_daily_quota(PLATFORM)
    else:
        console.print(f"[red]❌ 抖音发布失败: {msg}[/red]")

    return success


# ==================== 独立运行入口 ====================

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from auto_publish_all import StateManager
    asyncio.run(run(StateManager()))
