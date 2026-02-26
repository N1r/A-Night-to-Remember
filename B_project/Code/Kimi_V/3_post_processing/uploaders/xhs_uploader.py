"""
xhs_uploader.py
---------------
小红书视频自动化上传模块（每日限发 1 条）。

特点：
  - 支持标题 + 描述 + 标签填写
  - 支持封面上传
  - 模拟人类交互（滚动、延迟）
  - 等待视频转码完成后再发布

统一接口：
    await run(state_mgr) -> bool
"""

import asyncio
import json
import logging
import random
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple
from playwright.async_api import async_playwright, Page, BrowserContext

from _base import (
    ARCHIVES_DIR, PROJECT_ROOT, DEBUG_DIR,
    console, human_sleep, take_screenshot, find_cover, find_video,
    create_browser_context, save_cookies, type_like_human,
    random_mouse_move, clean_tag,
    bezier_mouse_move, human_click, human_scroll, warm_up_page,
)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from shared.domain import domain

PLATFORM = "xiaohongshu"
PUBLISH_URL = "https://creator.xiaohongshu.com/publish/publish"

# 日志
LOG_DIR = PROJECT_ROOT / "output" / "publish_logs"
LOG_FILE = LOG_DIR / "xhs_upload.log"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("XHSUploader")


# ==================== 上传器类 ====================

class XHSUploader:
    """小红书单视频上传器"""

    def __init__(self, context: BrowserContext, video_path: Path):
        self.context = context
        self.video_path = video_path
        self.video_dir = video_path.parent
        self.page: Optional[Page] = None
        
        # 初始默认值
        self.cover_path = find_cover(video_path)
        self.title = self.video_path.stem[:20]
        self.desc = f"分享一个精彩视频：{self.video_path.stem}"
        self.tags = ["#新闻", "#精选"]
        self.topic_tags = ["#深度分析"]

    # ---------- 元数据加载 ----------

    def _load_metadata(self):
        """从 metadata.json 加载标题、描述、标签"""
        meta_path = self.video_dir / "metadata.json"
        if not meta_path.exists():
            logger.warning(f"元数据文件不存在: {meta_path}")
            return

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            
            # 1. 尝试平台专用设置
            xhs_meta = meta.get("platforms", {}).get("xiaohongshu", {})
            
            self.title = (
                xhs_meta.get("title") or 
                meta.get("translated_title") or 
                meta.get("title") or 
                self.video_path.stem
            ).strip()[:18]

            self.desc = xhs_meta.get("desc") or meta.get("summary") or f"分享视频：{self.video_path.stem}"
            
            # 处理标签
            tags_set = set(self.topic_tags)
            
            # 加入平台专用标签
            for t in xhs_meta.get("tags", []):
                tags_set.add(t if t.startswith("#") else f"#{t}")
            
            # 加入通用分类/话题
            category = meta.get("category")
            if category and category != "未分类":
                tags_set.add(f"#{clean_tag(category)}")
            
            topics = meta.get("topics", [])
            if isinstance(topics, list):
                for t in topics[:3]:
                    if t:
                        tags_set.add(f"#{clean_tag(t)}")
            
            # 过滤标签：长度限制（防止长句子变成标签），去重
            self.tags = [t for t in tags_set if 1 < len(t) <= 20]
            logger.info(f"元数据加载成功: {self.title} (Tags: {len(self.tags)})")
        except Exception as e:
            logger.error(f"解析元数据失败: {e}")

    # ---------- 登录校验 ----------

    async def _check_login(self) -> bool:
        """检测是否已登录"""
        try:
            # 1. 访问发布页
            logger.info(f"正在访问: {PUBLISH_URL}")
            # 使用 wait_until="networkidle" 来确保页面基本加载完成，但设置合理的超时
            try:
                await self.page.goto(PUBLISH_URL, timeout=60000, wait_until="domcontentloaded")
            except Exception as ge:
                logger.warning(f"页面加载超时或异常 (尝试继续): {ge}")

            # 2. 核心探测：增加耐心，给浏览器解析 Cookie 和跳转的时间
            logger.info("⏳ 正在探测登录状态 (Max 20s)...")
            
            # 使用循环探测，而不是立即判断
            for i in range(10):
                # A. 检查是否存在上传入口 或 已经上传成功的“重新上传”按钮 (成功标准)
                upload_input = await self.page.query_selector("input[type='file']")
                uploaded_btn = await self.page.query_selector("text=重新上传")
                
                if upload_input or uploaded_btn:
                    logger.info("✅ 检测到上传入口或就绪状态，登录有效")
                    return True
                
                # B. 检查是否出现了明显的登录拦截
                current_url = self.page.url
                # 某些按钮可能带 text="登录"
                login_btn = await self.page.query_selector('button:has-text("登录"), .login-btn')
                
                if "login" in current_url or login_btn:
                    if i > 5:
                        logger.warning(f"❌ 持续检测到登录页特征，判定失效 (URL: {current_url})")
                        return False
                    else:
                        logger.debug(f"检测到潜在登录页，等待跳转... ({i})")
                
                await asyncio.sleep(2)

            # 3. 最后的尝试：显式等待上传按钮
            try:
                await self.page.wait_for_selector("input[type='file']", timeout=5000)
                logger.info("✅ 延迟探测到上传入口")
                return True
            except Exception:
                pass

            logger.warning("⚠️ 最终无法确认登录状态，建议人工检查")
            await take_screenshot(self.page, "xhs_login_failed_final")
            return False

        except Exception as e:
            logger.error(f"登录检测异常: {e}")
            await take_screenshot(self.page, "xhs_check_error")
            return False

    # ---------- 模拟交互 ----------

    async def _simulate_interaction(self):
        """模拟随机浏览行为（贝塞尔移动 + 拟人化滚动），降低自动化特征"""
        try:
            vp = self.page.viewport_size or {"width": 1280, "height": 720}
            # 随机移动到屏幕某处
            await bezier_mouse_move(self.page,
                random.uniform(vp["width"] * 0.2, vp["width"] * 0.8),
                random.uniform(vp["height"] * 0.2, vp["height"] * 0.6))
            await asyncio.sleep(random.uniform(0.5, 1.0))
            # 向下滚
            await human_scroll(self.page, random.randint(150, 400))
            await asyncio.sleep(random.uniform(0.8, 1.5))
            # 再移动一次模拟浏览
            await bezier_mouse_move(self.page,
                random.uniform(vp["width"] * 0.2, vp["width"] * 0.8),
                random.uniform(vp["height"] * 0.3, vp["height"] * 0.7))
            await asyncio.sleep(random.uniform(0.3, 0.8))
            # 回滚一点
            await human_scroll(self.page, -random.randint(80, 180))
        except Exception:
            pass

    # ---------- 核心上传流程 ----------

    async def upload(self) -> Tuple[bool, str]:
        """执行完整上传流程"""
        try:
            self._load_metadata()
            self.page = await self.context.new_page()

            if not await self._check_login():
                return False, "未登录或登录失效，请更新 Cookie"

            await self._simulate_interaction()
            # 预热：模拟用户在页面上的自然停留
            await warm_up_page(self.page, random.uniform(1.5, 2.5))

            # 1. 上传视频
            logger.info(f"📤 正在上传视频: {self.video_path.name}")
            file_input = await self.page.wait_for_selector(
                'input[type="file"]', state="attached", timeout=30000
            )
            await file_input.set_input_files(str(self.video_path))

            # 等待上传进度完成
            logger.info("⏳ 等待视频上传进度 (监测进度条消失 or 成功标记)...")
            try:
                # 进度文本特征
                progress_texts = ["上传中", "当前速度", "剩余时间"]
                
                # 遍历探测
                for _ in range(8):
                    is_uploading = False
                    for txt in progress_texts:
                        # 检查是否有可见的文本
                        visible = await self.page.locator(f'text="{txt}"').is_visible()
                        if visible:
                            is_uploading = True
                            break
                    
                    if is_uploading:
                        logger.info("📡 捕获到上传进度条可见，正在等候消失...")
                        for wait_i in range(150):
                            still_alive = False
                            for txt in progress_texts:
                                if await self.page.locator(f'text="{txt}"').is_visible():
                                    still_alive = True
                                    break
                            if not still_alive:
                                logger.info("✅ 进度条文字已消失")
                                await human_sleep(2, 3) 
                                break
                            await asyncio.sleep(2)
                        break
                    await asyncio.sleep(1.5)

                # 兜底：寻找 "重新上传" 按钮 或 "标题输入框" (证明已进入编辑态)
                try:
                    await self.page.wait_for_selector(
                        'text=/重新上传|上传成功/, input[placeholder*="标题"]', 
                        timeout=30000
                    )
                    logger.info("✅ 视频上传确认完成")
                except Exception:
                    # 再次检查标题框是否存在，如果存在直接算成功
                    if await self.page.query_selector('input[placeholder*="标题"]'):
                        logger.info("✅ 检测到标题框，判定上传已完成")
                    else:
                        raise Exception("未能确认上传完成状态")
                        
            except Exception as e:
                logger.warning(f"⚠️ 上传状态监测过程不完整: {e}")

            try:
                await self.page.wait_for_selector(
                    'input[placeholder*="填写标题"]', timeout=60000
                )
            except Exception:
                return False, "视频上传后未能进入编辑页面"

            # 2. 填写标题
            logger.info("📝 填写标题...")
            title_input = await self.page.query_selector('input[placeholder*="填写标题"]')
            if title_input:
                await title_input.click()
                await self.page.keyboard.press("Control+A")
                await self.page.keyboard.press("Backspace")
                await self.page.keyboard.type(
                    self.title, delay=random.randint(50, 120)
                )

            # 3. 填写描述和标签
            logger.info("📝 填写描述...")
            desc_input = await self.page.query_selector(
                'div#post-textarea, .tiptap, [role="textbox"]'
            )
            if desc_input:
                await human_scroll(self.page, random.randint(80, 160))
                await human_click(self.page, desc_input)
                full_desc = f"{self.desc}\n{' '.join(self.tags)}"
                for line in full_desc.split("\n"):
                    await self.page.keyboard.type(line, delay=random.randint(20, 50))
                    await self.page.keyboard.press("Enter")

            # 4. 上传封面
            if self.cover_path:
                logger.info(f"🖼️ 正在上传封面: {self.cover_path.name}")
                try:
                    edit_btn = await self.page.query_selector(
                        "text=编辑封面, .upload-cover-btn"
                    )
                    if edit_btn:
                        await edit_btn.click()
                        await human_sleep(1.5, 2.5)
                        upload_tab = await self.page.query_selector(
                            "text=上传图片, .upload-tab"
                        )
                        if upload_tab:
                            await upload_tab.click()
                            await human_sleep(0.8, 1.5)
                        cover_input = await self.page.query_selector('input[type="file"]')
                        if cover_input:
                            await cover_input.set_input_files(str(self.cover_path))
                            await human_sleep(4, 6)
                            confirm_btn = await self.page.query_selector(
                                'button:has-text("确定"), button:has-text("完成")'
                            )
                            if confirm_btn:
                                await confirm_btn.click()
                                await human_sleep(2, 3)
                except Exception as ce:
                    logger.warning(f"封面上传流程异常(跳过): {ce}")

            # 5. 等待转码 + 发布
            logger.info("🚀 准备发布 (确认最终就绪状态)...")
            
            # 再次确认上传相关的指示器是否完全消失
            for _ in range(30):
                if not self.page: break
                upload_active = False
                for txt in ["上传中", "当前速度", "剩余时间"]:
                    if await self.page.locator(f'text="{txt}"').is_visible():
                        upload_active = True
                        break
                if not upload_active:
                    break
                logger.debug("页面仍显示上传进度，等待中...")
                await asyncio.sleep(2)

            publish_btn = await self.page.wait_for_selector(
                'button:has-text("发布")', state="visible", timeout=120000
            )

            # 最终循环检测按钮状态 (处理服务器后端转码)
            for _ in range(60):
                if not await publish_btn.is_disabled():
                    # 额外检查：有些平台按钮不处于 disabled 但点击无响应或有 Loading
                    await asyncio.sleep(2)
                    break
                await asyncio.sleep(3)
                logger.info("⏳ 视频后台转码/处理中，等待发布按钮就绪...")

            # 滚到按钮位置后拟人化点击
            await human_scroll(self.page, random.randint(100, 200))
            await asyncio.sleep(random.uniform(0.3, 0.7))
            await human_click(self.page, publish_btn)
            logger.info("⏳ 等待发布结果...")
            
            for i in range(15):
                await asyncio.sleep(2)
                current_url = self.page.url
                
                # 1. URL 变更检测 (发布成功后可能会带 published=true 参数，或者跳转回首页)
                if "published=true" in current_url:
                     logger.info(f"✅ 检测到发布成功 URL 参数: {current_url}")
                     return True, "Success"
                elif "publish/publish" not in current_url:
                     logger.info(f"✅ URL已变更，判定发布成功: {current_url}")
                     return True, "Success"
                
                # 2. 页面文本检测
                success_text = await self.page.query_selector("text=发布成功, text=已发布")
                if success_text:
                    logger.info("✅ 检测到发布成功提示")
                    return True, "Success"
                
                # 3. 模态框/Toast 检测
                if await self.page.locator(".ant-message-notice").count() > 0:
                     msg = await self.page.locator(".ant-message-notice").inner_text()
                     if "成功" in msg:
                          logger.info(f"✅ 检测到成功Toast: {msg}")
                          return True, "Success"

            logger.warning("⚠️ 发布后未检测到明确跳转或成功提示，但已点击发布")
            # 兜底：如果没报错，且页面没有明显的错误提示，姑且认为成功，或者人工复核
            error_hint = await self.page.query_selector(".ant-message-error")
            if error_hint:
                 err_msg = await error_hint.inner_text()
                 return False, f"发布失败提示: {err_msg}"

            return True, "Success (Blind)"

        except Exception as e:
            DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            if self.page:
                await take_screenshot(self.page, "ERROR_XHS", DEBUG_DIR)
            logger.error(f"流程崩溃: {e}")
            return False, f"Exception: {str(e)}"
        finally:
            if self.page:
                await self.page.close()


# ==================== 对外统一接口 ====================

async def run(state_mgr) -> bool:
    """
    小红书上传入口（每日 1 条）。

    Parameters
    ----------
    state_mgr : StateManager 实例

    Returns
    -------
    bool : 是否成功上传
    """
    console.rule("[bold red]小红书上传（每日 1 条）[/bold red]")

    # 每日额度检查
    if not state_mgr.can_upload_today(PLATFORM):
        console.print("[yellow]📅 今日小红书额度已满，跳过[/yellow]")
        return False

    # 选取目标视频（优先 output_sub.mp4）
    target = None
    for d in sorted(ARCHIVES_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if not d.is_dir() or d.name in ("done", "failed"):
            continue
        if state_mgr.is_uploaded(d.name, PLATFORM):
            continue
        vid = find_video(d)
        if vid:
            target = vid
            break
    if target is None:
        console.print("[green]✅ 小红书无待办任务[/green]")
        return False
    console.print(f"🎯 目标视频: [cyan]{target.name}[/cyan]")

    async with async_playwright() as p:
        context = await create_browser_context(
            p, PLATFORM,
            headless=False,
            viewport={"width": 1280, "height": 900},
            use_stealth=True,
            slow_mo=100,
        )

        uploader = XHSUploader(context, target)
        success, msg = await uploader.upload()

        if success:
            console.print(f"[bold green]✅ {target.parent.name} 发布成功[/bold green]")
            state_mgr.mark_uploaded(target.parent.name, PLATFORM)
            state_mgr.increment_daily_quota(PLATFORM)
        else:
            console.print(f"[bold red]❌ {target.parent.name} 发布失败: {msg}[/bold red]")

        await save_cookies(context, PLATFORM)
        await context.close()

    return success


# ==================== 独立运行入口 ====================

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from auto_publish_all import StateManager
    asyncio.run(run(StateManager()))
