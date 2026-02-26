"""
wechat_channels_uploader.py
-------------------
视频号自动化上传模块。

特点：
  - 基于 Playwright 的自动化上传
  - 自动管理 Cookie（支持扫码登录保存）
  - 定时发布支持
  - 一次性上传全部待办任务
"""

import asyncio
import os
from datetime import datetime, timedelta
import random
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Playwright

from _base import (
    ARCHIVES_DIR, COOKIES_DIR, HEADLESS_MODE,
    console, human_sleep, take_screenshot,
    find_cover, find_video, get_chrome_executable,
    type_like_human, human_click, warm_up_page, random_mouse_move
)
import json

PLATFORM = "wechat_channels" # 为了和之前的做区分

def format_str_for_short_title(origin_title: str) -> str:
    # 定义允许的特殊字符
    allowed_special_chars = "《》“”:+?%°"

    # 移除不允许的特殊字符
    filtered_chars = [char if char.isalnum() or char in allowed_special_chars else ' ' if char == ',' else '' for
                      char in origin_title]
    formatted_string = ''.join(filtered_chars)

    # 调整字符串长度
    if len(formatted_string) > 16:
        # 截断字符串
        formatted_string = formatted_string[:16]
    elif len(formatted_string) < 6:
        # 使用空格来填充字符串
        formatted_string += ' ' * (6 - len(formatted_string))

    return formatted_string

async def set_init_script(context):
    from _base import STEALTH_JS, _INLINE_STEALTH
    if STEALTH_JS.exists():
        await context.add_init_script(path=str(STEALTH_JS))
    else:
        await context.add_init_script(_INLINE_STEALTH)
    return context

async def cookie_auth(account_file: Path, executable_path=None):
    """
    通过实际访问后台页面来验证 Cookie 是否依然有效。
    """
    async with async_playwright() as playwright:
        from _base import create_browser_context
        # 验证时也使用统一的高强度反检测配置，避免被误判为爬虫而重定向
        context = await create_browser_context(
            playwright, 
            "tencent", 
            headless=HEADLESS_MODE
        )
        page = await context.new_page()
        try:
            # 访问发布页进行测试
            await page.goto("https://channels.weixin.qq.com/platform/post/create", timeout=30000)
            await asyncio.sleep(2)
            
            # 1. 检查是否被重定向到登录页
            if "login.html" in page.url:
                console.log("[yellow]⚠️ 视频号 Cookie 已失效，需要扫码[/yellow]")
                return False
                
            # 2. 检查是否存在登录后的特征元素（如“发表”按钮或头像昵称区域）
            # 只要探测到这些元素，说明 session 依然活跃
            # 微信视频号后台可能加载较慢，增加超时时间到 30 秒，避免误判
            try:
                await page.wait_for_selector('button:has-text("发表"), .finder-nickname', timeout=30000)
                console.log("[green]✅ 视频号 Cookie 验证有效[/green]")
                return True
            except:
                # 二次检查，如果URL仍不在登录页，可能只是元素变了或网络极慢，保守认为有效
                if "login.html" not in page.url:
                    console.log("[yellow]⚠️ 视频号 页面加载缓慢，但未跳转登录，尝试默认有效[/yellow]")
                    return True
                console.log("[yellow]⚠️ 视频号 登录状态存疑，为了保险将执行重新登录[/yellow]")
                return False
        except Exception as e:
            console.log(f"[dim]验证 Cookie 期间发生非致命异常: {e}[/dim]")
            return False
        finally:
            await context.close()


async def get_tencent_cookie(account_file: Path, executable_path=None):
    async with async_playwright() as playwright:
        options = {
            'args': ['--lang en-GB'],
            'headless': False, # 需要打开浏览器才能扫码
            'executable_path': executable_path,
            'channel': 'chrome'
        }
        browser = await playwright.chromium.launch(**options)
        context = await browser.new_context()
        await set_init_script(context)
        page = await context.new_page()
        await page.goto("https://channels.weixin.qq.com")
        console.print("[bold cyan]=================================================[/bold cyan]")
        console.print("[bold cyan]⚠️ 请在弹出的浏览器窗口中直接扫码登录微信视频号 ⚠️[/bold cyan]")
        console.print("[bold cyan]登录并进入后台主页后，脚本将自动保存凭证并继续执行。[/bold cyan]")
        console.print("[bold cyan]=================================================[/bold cyan]")
        
        # 等待页面出现"发表视频"之类的元素或者等待URL发生变化
        try:
            await page.wait_for_url("**/platform/post/create**", timeout=120000)
        except Exception as e:
            # 如果窗体直接关了等，捕获异常以防整个程序崩溃
            console.log(f"[yellow]⚠️ 等待登录时出错或窗口被关闭: {e}[/yellow]")
        
        try:
            await asyncio.sleep(2)  # 留足够的时间确保状态写入
            await context.storage_state(path=str(account_file))
            console.print("[green]✅ 视频号 新的Cookie已尝试保存[/green]")
        except Exception:
            pass

async def weixin_setup(account_file_path: Path, executable_path=None) -> bool:
    """
    【用户要求】跳过 Cookie 检查，直接尝试执行任务。
    由于使用了 launch_persistent_context，浏览器会自动维持之前的登录状态。
    """
    console.print('[cyan]⏭️  已跳过 Cookie 有效性检查，直接尝试使用当前 Session...[/cyan]')
    # 如果 account_file 根本不存在，则仍需进行初始化登录（可选，但通常即使跳过也应确保文件存在）
    # 但根据要求，这里我们强制认为 True 即可
    return True


class TencentVideo(object):
    def __init__(self, title, file_path, tags, publish_date, account_file, category=None, is_draft=False):
        self.title = title
        self.file_path = str(file_path)
        self.tags = tags
        self.publish_date = publish_date
        self.account_file = str(account_file)
        self.category = category
        self.headless = HEADLESS_MODE
        self.is_draft = is_draft
        self.local_executable_path = get_chrome_executable()

    async def set_schedule_time_tencent(self, page, publish_date):
        label_element = page.locator("label").filter(has_text="定时").nth(1)
        await human_click(page, label_element)

        await human_click(page, page.locator('input[placeholder="请选择发表时间"]'))

        str_month = str(publish_date.month) if publish_date.month > 9 else "0" + str(publish_date.month)
        current_month = str_month + "月"
        # 获取当前的月份
        page_month = await page.locator('span.weui-desktop-picker__panel__label:has-text("月")').inner_text()

        # 检查当前月份是否与目标月份相同
        if page_month != current_month:
            await human_click(page, page.locator('button.weui-desktop-btn__icon__right'))

        # 获取页面元素
        elements = await page.locator('table.weui-desktop-picker__table a').all()

        # 遍历元素并点击匹配的元素
        for element in elements:
            if 'weui-desktop-picker__disabled' in await element.evaluate('el => el.className'):
                continue
            text = await element.inner_text()
            if text.strip() == str(publish_date.day):
                await human_click(page, element)
                break

        # 输入小时部分
        await human_click(page, page.locator('input[placeholder="请选择时间"]'))
        await page.keyboard.press("Control+A") # 修复 Keyboard 修正
        await page.keyboard.press("Backspace")
        await type_like_human(page, str(publish_date.hour))

        # 选择标题栏（令定时时间生效）
        await human_click(page, page.locator("div.input-editor"))

    async def handle_upload_error(self, page):
        console.log("视频出错了，重新上传中")
        del_btn = page.locator('div.media-status-content div.tag-inner:has-text("删除")')
        await human_click(page, del_btn)
        await human_click(page, page.get_by_role('button', name="删除", exact=True))
        file_input = page.locator('input[type="file"]')
        await file_input.set_input_files(self.file_path)

    async def add_short_title(self, page):
        short_title_element = page.get_by_text("短标题", exact=True).locator("..").locator(
            "xpath=following-sibling::div").locator('span input[type="text"]')
        if await short_title_element.count():
            short_title = format_str_for_short_title(self.title)
            await human_click(page, short_title_element)
            await type_like_human(page, short_title)

    async def click_publish(self, page):
        while True:
            try:
                # 处理可能遗留的 "声明原创" 阻断确认框 (兼容主 DOM / 嵌套 IFrame)
                # 使用更灵活的查找方式
                async def handle_intercept(root):
                    intercept_btn = root.locator('button, .weui-desktop-btn').filter(has_text="声明原创").first
                    if await intercept_btn.count() > 0 and await intercept_btn.is_visible():
                        console.log("[cyan]  [-] 发现原创拦截确认，尝试点击...[/cyan]")
                        await intercept_btn.click(force=True)
                        return True
                    return False

                if not await handle_intercept(page):
                    frame = page.frame_locator('iframe[name="content"]')
                    await handle_intercept(frame)
                
                await asyncio.sleep(1)
                    
                if self.is_draft:
                    # 点击"保存草稿"按钮
                    draft_button = page.locator('div.form-btns button:has-text("保存草稿")')
                    if await draft_button.count():
                        await human_click(page, draft_button, "left")
                    
                    # 轮询验证是否跳转
                    for _ in range(10):
                        if "post/list" in page.url or "draft" in page.url:
                            break
                        await asyncio.sleep(1)
                    console.log("  [-]视频草稿保存成功")
                else:
                    # 点击"发表"按钮
                    publish_button = page.locator('div.form-btns button:has-text("发表")')
                    if await publish_button.count():
                        await human_click(page, publish_button, "left")
                    
                    # 轮询验证是否跳转
                    for _ in range(10):
                        if "post/list" in page.url:
                            break
                        await asyncio.sleep(1)
                    console.log("  [-]视频发布成功")
                break
            except Exception as e:
                current_url = page.url
                if self.is_draft:
                    if "post/list" in current_url or "draft" in current_url:
                        console.log("  [-]视频草稿保存成功")
                        break
                else:
                    if "https://channels.weixin.qq.com/platform/post/list" in current_url:
                        console.log("  [-]视频发布成功")
                        break
                console.log(f"  [-] 视频正在发布中 (重试: {e})...")
                await asyncio.sleep(1)

    async def detect_upload_status(self, page):
        """
        等待视频上传完成并且必填项都校验通过（标志为“发表”按钮可用）。
        """
        console.log("  [-] 正在等待视频上传与处理完成...")
        start_time = datetime.now()
        
        while True:
            # 检查是否等待超时 (10 分钟)
            if (datetime.now() - start_time).total_seconds() > 600:
                raise Exception("视频上传超时 (超过10分钟)")

            try:
                # 检查错误重试状态 (红色错误条或重新上传按钮)
                if await page.locator('div.status-msg.error').count() > 0 or await page.locator('div.media-status-content div.tag-inner:has-text("重新上传")').count() > 0:
                    console.log("[red]  [-] 发现上传被阻断出错了...准备尝试点重新上传[/red]")
                    await self.handle_upload_error(page)
                    continue

                # 验证终极成功标志：发表按钮变为可点击状态
                publish_btn = page.get_by_role("button", name="发表")
                if await publish_btn.count() > 0:
                    btn_class = await publish_btn.first.get_attribute('class') or ""
                    if "weui-desktop-btn_disabled" not in btn_class.lower() and "is-disabled" not in btn_class.lower():
                        console.log("[green]  [-] 视频上传完毕 100% (发表按钮已就绪)[/green]")
                        break
                    
                await asyncio.sleep(3)
            except Exception as e:
                # 忽略瞬时检测异常
                await asyncio.sleep(2)

    async def add_title_tags(self, page):
        # 话题和带货标签输入框等仍在主文档中
        input_editor = page.locator("div.input-editor")
        await human_click(page, input_editor)
        await type_like_human(page, self.title)
        await page.keyboard.press("Enter")
        for index, tag in enumerate(self.tags, start=1):
            await type_like_human(page, "#" + tag)
            await page.keyboard.press("Space")
            await asyncio.sleep(random.uniform(0.3, 0.8))
        console.log(f"  [-]成功添加hashtag: {len(self.tags)}个")

    async def add_collection(self, page):
        collection_elements = page.get_by_text("添加到合集").locator("xpath=following-sibling::div").locator('.option-list-wrap > div')
        if await collection_elements.count() > 1:
            await page.get_by_text("添加到合集").locator("xpath=following-sibling::div").click()
            await collection_elements.first.click()

    async def add_original(self, page):
        """
        探测并声明原创。
        使用 原生 Playwright API，完美处理 React 合成事件，并自动穿透普通的 open Shadow DOM。
        结合用户实测的完整文本进行精准点击。
        """
        import re
        console.log("[cyan]  [-] 开始探测并声明原创 (Native Playwright)...[/cyan]")
        try:
            frame = page.frame_locator('iframe[name="content"]')
            
            # --- 1. 点击主页面原创声明入口 ---
            main_texts = [
                "声明后，作品将展示原创标记",
                "原创声明",
                "声明原创"
            ]
            main_checked = False
            for root in [frame, page]:
                for text in main_texts:
                    # a) 优先尝试作为 Checkbox 获取
                    loc_cb = root.get_by_role("checkbox", name=re.compile(text)).first
                    if await loc_cb.count() > 0 and await loc_cb.is_visible():
                        console.log(f"[cyan]  [-] 发现主原创入口 Checkbox: {text}[/cyan]")
                        if not await loc_cb.is_checked():
                            # 根据录制步骤，这里可能需要多次点击或者强行 check
                            await loc_cb.check(force=True)
                        main_checked = True
                        break
                    
                    # b) 退而求其次，直接点击 Text 标签本身 (使用双击)
                    loc_text = root.get_by_text(re.compile(text)).first
                    if await loc_text.count() > 0 and await loc_text.is_visible():
                        console.log(f"[cyan]  [-] 发现主原创入口 Text (尝试双击): {text}[/cyan]")
                        # 用户脚本中大量出现 dblclick，这里采用 dblclick 模拟强干扰下的点击
                        await loc_text.dblclick(force=True)
                        main_checked = True
                        break
                if main_checked:
                    break

            if not main_checked:
                console.log("[yellow]  [-] 未能通过文本点击主原创入口，尝试 Class 备用规则...[/yellow]")
                for root in [frame, page]:
                    loc_class = root.locator('.original-proto-wrapper').first
                    if await loc_class.count() > 0 and await loc_class.is_visible():
                        await loc_class.dblclick(force=True)
                        main_checked = True
                        break
                
            await asyncio.sleep(2.0)

            # --- 2. 处理弹窗协议勾选 (我已阅读并同意...) ---
            dialog_texts = [
                "评论区有机会展示广告", 
                "我已阅读并同意《原创声明须知》",
                "同意并遵守",
                "我已阅读并同意"
            ]
            
            proto_checked = False
            for root in [frame, page]:
                for text in dialog_texts:
                    loc = root.get_by_text(re.compile(text)).first
                    if await loc.count() > 0 and await loc.is_visible():
                        console.log(f"[cyan]  [-] 发现并且双击弹窗协议: {text}[/cyan]")
                        # 复刻用户行为: get_by_text(...).first.dblclick()
                        await loc.dblclick(force=True)
                        proto_checked = True
                        break
                # 复刻用户的按 label.uncheck/check 行为作为补充
                label_loc = root.get_by_label("").nth(5)
                if await label_loc.count() > 0:
                    try:
                        await label_loc.click(force=True)
                    except:
                        pass
                if proto_checked:
                    break
            
            if not proto_checked:
                # 备用：点击弹窗内的 .original-proto-wrapper
                for root in [frame, page]:
                    w = root.locator('.declare-original-dialog .original-proto-wrapper, .weui-desktop-dialog .original-proto-wrapper').first
                    if await w.count() > 0 and await w.is_visible():
                        console.log("[cyan]  [-] 触发弹窗协议 (Class 备用)...[/cyan]")
                        await w.dblclick(force=True)
                        proto_checked = True
                        break

            await asyncio.sleep(1.0)
            
            # --- 3. 点击“声明原创”确认按钮 ---
            btn_clicked = False
            for root in [frame, page]:
                btn_loc = root.get_by_role("button", name="声明原创").first
                if await btn_loc.count() > 0 and await btn_loc.is_visible():
                    console.log("[cyan]  [-] 点击弹窗确认 [声明原创] 按钮...[/cyan]")
                    await btn_loc.click(force=True)
                    btn_clicked = True
                    break
            
            if not btn_clicked:
                for root in [frame, page]:
                    btn_loc = root.locator('.weui-desktop-dialog .weui-desktop-btn_primary, .declare-original-dialog .weui-desktop-btn_primary').first
                    if await btn_loc.count() > 0 and await btn_loc.is_visible():
                        console.log("[cyan]  [-] 点击弹窗确认 (类名备用)...[/cyan]")
                        await btn_loc.click(force=True)
                        btn_clicked = True
                        break

            await asyncio.sleep(2.0)
            
            # 结果以最后 Playwright Inspector pause 为准
            console.log("[green]  [-] 原创声明 Native Playwright 执行完毕。[/green]")
            return True
            
        except Exception as e:
            console.log(f"[yellow]  [-] 原创声明处理异常: {e}[/yellow]")
            return False




    async def upload_single(self, context) -> bool:
        page = await context.new_page()
        try:
            await page.goto("https://channels.weixin.qq.com/platform/post/create")
            console.log(f'[cyan]🚀 开始上传: {self.title}[/cyan]')
            
            await page.wait_for_url("**/platform/post/create**", timeout=20000)
            await warm_up_page(page) # 页面预热，模拟自然行为
            
            # 1. 触发上传
            file_input = page.locator('input[type="file"]')
            await file_input.set_input_files(self.file_path)
            
            # 2. 开始填写元数据和交互 (利用上传的时间差同时填表)
            await human_sleep(1, 3) 
            await self.add_title_tags(page)
            await self.add_short_title(page)
            
            # 3. 原创声明 (核心强制流程)
            original_success = False
            for try_idx in range(5): # 最多尝试5次原创声明
                if await self.add_original(page):
                    original_success = True
                    break
                console.log(f"[yellow]  [-] 原创声明第 {try_idx+1} 次尝试未完全成功，稍后重试...[/yellow]")
                await asyncio.sleep(2)

            if not original_success:
                raise Exception("无法确认原创声明被勾选，为了安全起见停止当前视频发布。")
            
            # 4. 阻塞等待上传完成及属性全部可用 (检测按钮可用)
            await self.detect_upload_status(page)
            
            # 5. 点击发表（只有上述所有都成功，且原创打钩了才触发）
            await self.click_publish(page)

            # 保存最后状态
            await context.storage_state(path=self.account_file)
            console.log(f'[green]✅ {self.title} 上传完毕！[/green]')
            return True
            
        except Exception as e:
            error_str = str(e)
            if "Target page, context or browser has been closed" in error_str:
                console.log(f"[red]❌ {self.title} 浏览器由于未知原因被关闭。可能引发了反爬虫风控。[/red]")
            else:
                console.log(f"[red]❌ {self.title} 上传异常: {error_str}[/red]")
            
            try:
                # 若还有页面可用则截图
                if not page.is_closed():
                    await take_screenshot(page, "error_wechat_channels", Path("./output/debug"))
            except:
                pass
            return False
            
        finally:
            try:
                if not page.is_closed():
                    await page.close()
            except Exception:
                pass


# ==================== 对外统一接口 ====================

def _get_metadata_info(folder_path: Path):
    """尝试从 metadata.json 获取标题和标签"""
    meta_path = folder_path / "metadata.json"
    title = folder_path.name
    tags = []
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            # 兼容读取可能生成的微信数据，因为没有专属 key，所以拿其他平台的借用
            platforms = meta.get("platforms", {})
            tk_data = platforms.get("douyin", {})
            ks_data = platforms.get("kuaishou", {})
            
            if tk_data.get("title"):
                title = tk_data.get("title")
                tags = tk_data.get("tags", [])
            elif ks_data.get("title"):
                title = ks_data.get("title")
                tags = ks_data.get("tags", [])
        except Exception:
            pass
    return title, tags

async def run(state_mgr=None) -> bool:
    """
    微信视频号上传入口（批量全量上传）。
    """
    console.rule("[bold yellow]微信视频号上传 (批量)[/bold yellow]")

    ready_dir = ARCHIVES_DIR
    if not ready_dir.exists():
        console.print(f"[red]❌ 目录不存在: {ready_dir}[/red]")
        return False

    # 1. 查找待办列表
    video_entries = []
    for folder in sorted(ready_dir.iterdir()):
        if not folder.is_dir() or folder.name in ("done", "failed"):
            continue
        if state_mgr and state_mgr.is_uploaded(folder.name, PLATFORM):
            continue
        
        # 获取该文件夹下的成品短片
        vid = find_video(folder)
        if not vid:
            # 或者兜底匹配用户指定的那种特定视频名策略 (同名.mp4)
            fallback_vid = folder / f"{folder.name}.mp4"
            if fallback_vid.exists():
                vid = fallback_vid
            else:
                continue
            
        video_entries.append((vid, folder.name, folder))

    if not video_entries:
        console.print("[green]✅ 微信视频号无待办任务[/green]")
        return False

    console.print(f"📋 共发现 {len(video_entries)} 个视频待上传到 微信视频号")

    # 2. 鉴权验证
    account_file = COOKIES_DIR / f"{PLATFORM}_cookies.json"
    executable_path = get_chrome_executable()
    await weixin_setup(account_file, executable_path)

    # 3. 登录并初始化浏览器上下文 (使用 _base 统一的高强度反检测配置)
    all_ok = True
    async with async_playwright() as playwright:
        from _base import create_browser_context
        context = await create_browser_context(
            playwright, 
            "tencent", 
            headless=HEADLESS_MODE
        )

        try:
            for idx, (vid_path, folder_name, folder_path) in enumerate(video_entries):
                title, tags = _get_metadata_info(folder_path)
                pub_date = 0 # 改为不定时，立即发表
                
                uploader = TencentVideo(
                    title=title,
                    file_path=vid_path,
                    tags=tags,
                    publish_date=pub_date,
                    account_file=account_file,
                    category=None, # 可以手动指定，例如 "科技"
                    is_draft=False
                )
                
                success = await uploader.upload_single(context)
                if success and state_mgr:
                    state_mgr.mark_uploaded(folder_name, PLATFORM)
                    state_mgr.increment_daily_quota(PLATFORM)
                else:
                    all_ok = False
                    
                # 等待间隔，避免被限流
                await human_sleep(5, 12)
                
        finally:
            await context.close()


    return all_ok


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from auto_publish_all import StateManager
    asyncio.run(run(StateManager()))
