"""
ks_uploader.py
--------------
快手视频自动化上传模块。

快手创作者平台: https://cp.kuaishou.com/article/publish/video

特点：
  - 多选择器策略定位描述框（兼容页面改版）
  - 等待转码完成后再发布
  - 从 metadata.json 加载标题/标签

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
    create_browser_context, save_cookies,
    warm_up_page, human_click, human_scroll, bezier_mouse_move,
)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from shared.domain import domain

PLATFORM = "kuaishou"
PUBLISH_URL = "https://cp.kuaishou.com/article/publish/video"

# 日志
LOG_DIR = PROJECT_ROOT / "output" / "publish_logs"
LOG_FILE = LOG_DIR / "ks_upload.log"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("KSUploader")


# ==================== 上传器类 ====================

class KSUploader:
    """快手单视频上传器"""

    def __init__(self, context: BrowserContext, video_path: Path):
        self.context = context
        self.video_path = video_path
        self.video_dir = video_path.parent
        self.page: Optional[Page] = None

        # 默认元数据（从 domain profile 读取）
        _ks_config = domain.get_upload_config("kuaishou")
        self.title = self.video_path.stem
        self.desc = f"分享视频：{self.video_path.stem}"
        self.tags = _ks_config.get("default_tags", ["#新闻", "#精选"])

    # ---------- 元数据加载 ----------

    def _load_metadata(self):
        """从 metadata.json 加载标题、描述、标签"""
        meta_path = self.video_dir / "metadata.json"
        if not meta_path.exists():
            logger.warning(f"元数据文件不存在: {meta_path}")
            return

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            
            # 尝试平台专用设置
            ks_meta = meta.get("platforms", {}).get("kuaishou", {})
            
            self.title = (
                ks_meta.get("title") or 
                meta.get("translated_title") or 
                meta.get("title") or 
                self.video_path.stem
            )
            
            self.desc = ks_meta.get("desc") or meta.get("summary") or f"分享视频：{self.video_path.stem}"

            tags_set = set(self.tags)
            
            # 增加详情标签
            from _base import clean_tag
            for t in ks_meta.get("tags", []):
                tags_set.add(f"#{clean_tag(t)}")

            category = meta.get("category")
            if category and category != "未分类":
                tags_set.add(f"#{clean_tag(category)}")
            
            # 过滤标签：长度限制（防止长句子变成标签）
            self.tags = [t for t in tags_set if 1 < len(t) <= 20]
            logger.info(f"元数据加载成功: {self.title} (Tags: {len(self.tags)})")
        except Exception as e:
            logger.error(f"解析元数据失败: {e}")

    # ---------- 定位描述框 ----------

    async def _find_desc_input(self):
        """多策略定位描述框，兼容快手页面改版"""
        selectors = [
            'div[data-placeholder*="作品描述"]',
            'div[contenteditable="true"]',
            'textarea[placeholder*="作品描述"]',
            ".ql-editor",
            "#work-description-edit",
            ".desc-input",
        ]

        for selector in selectors:
            try:
                el = await self.page.wait_for_selector(
                    selector, state="visible", timeout=3000
                )
                if el:
                    logger.info(f"📍 找到描述框: {selector}")
                    return el
            except Exception:
                continue

        # 兜底：通过"作品描述"标签的坐标偏移定位
        logger.info("🔍 尝试通过坐标定位描述框...")
        try:
            desc_label = await self.page.wait_for_selector(
                "text=作品描述", timeout=5000
            )
            if desc_label:
                bbox = await desc_label.bounding_box()
                if bbox:
                    await self.page.mouse.click(
                        bbox["x"] + bbox["width"] + 100,
                        bbox["y"] + 40,
                    )
                    logger.info("📍 通过坐标定位到描述框")
                    return True  # 标记已点击
        except Exception:
            pass

        return None

    # ---------- 定位发布按钮 ----------

    async def _find_publish_button(self):
        """多策略定位发布按钮"""
        logger.info("🔍 尝试定位发布按钮...")

        # 1. 强制 JS 滚动到底部
        await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await human_sleep(1, 2)

        # 2. 精确查找 "发布" 文本元素
        try:
            # 查找所有文本完全为 "发布" 的可见元素
            candidates = await self.page.get_by_text("发布", exact=True).all()
            visible_candidates = []
            for c in candidates:
                if await c.is_visible():
                    visible_candidates.append(c)

            if visible_candidates:
                # 通常底部的按钮是最后一个
                target = visible_candidates[-1]
                logger.info("📍 定位到 '发布' 文本元素")
                await target.scroll_into_view_if_needed()
                return target
        except Exception as e:
            logger.warning(f"精确查找 '发布' 失败: {e}")

        # 3. 兜底：Playwright 模糊查找
        try:
            return await self.page.wait_for_selector(
                'button:has-text("发布"), div[role="button"]:has-text("发布")',
                state="visible", 
                timeout=3000
            )
        except Exception:
            return None

    # ---------- 核心上传流程 ----------

    async def upload(self) -> Tuple[bool, str]:
        """执行完整上传流程"""
        try:
            self._load_metadata()
            self.page = await self.context.new_page()

            # 访问快手发布页
            logger.info("🌐 访问快手创作者平台发布页...")
            await self.page.goto(PUBLISH_URL, timeout=60000)
            await asyncio.sleep(3)
            # 页面预热：模拟真实用户浏览行为
            await warm_up_page(self.page, random.uniform(2.5, 4.0))

            # 登录检测 (耐心探测)
            logger.info("⏳ 正在探测登录状态 (Max 20s)...")
            login_ok = False
            for i in range(10):
                # A. 检查是否存在上传入口 或 已成功上传状态
                upload_input = await self.page.query_selector("input[type='file']")
                uploaded_btn = await self.page.query_selector("text=重新上传")
                if upload_input or uploaded_btn:
                    login_ok = True
                    break
                
                # B. 检查明显的登录页
                if "passport" in self.page.url or "login" in self.page.url:
                    if i > 5:
                        break
                await asyncio.sleep(2)

            if not login_ok:
                return False, f"未登录或登录失效 (URL: {self.page.url})"
            
            logger.info("✅ 登录状态确认就绪")

            # Step 1: 上传视频
            logger.info(f"📤 正在上传视频: {self.video_path.name}")
            file_input = await self.page.wait_for_selector(
                'input[type="file"]', state="attached", timeout=30000
            )
            await file_input.set_input_files(str(self.video_path))

            # 等待上传完成
            logger.info("⏳ 等待视频上传完成...")
            try:
                await self.page.wait_for_selector("text=重新上传", timeout=300000)
                logger.info("✅ 视频上传完成")
            except Exception:
                await take_screenshot(self.page, "UPLOAD_TIMEOUT_KS", DEBUG_DIR)
                return False, "视频上传超时(5min)"

            await human_sleep(2, 3)
            # 滚动到表单区域，模拟用户查看内容
            await human_scroll(self.page, random.randint(200, 350))
            await asyncio.sleep(random.uniform(0.5, 1.0))

            # Step 2: 填写作品描述
            logger.info("📝 填写作品描述...")
            desc_input = await self._find_desc_input()

            if not desc_input:
                await take_screenshot(self.page, "NO_DESC_INPUT_KS", DEBUG_DIR)
                return False, "无法定位作品描述输入框"

            # 如果返回的是 element 而非 True 标记，需要先拟人化点击
            if desc_input is not True:
                await human_click(self.page, desc_input)

            await human_sleep(0.5, 1)
            await self.page.keyboard.press("Control+A")
            await self.page.keyboard.press("Backspace")
            await human_sleep(0.3, 0.5)

            full_text = f"{self.title} {' '.join(self.tags)}"
            if len(full_text) > 500:
                full_text = full_text[:500]
            await self.page.keyboard.type(full_text, delay=random.randint(30, 60))
            logger.info(f"📝 描述已填写: {full_text[:50]}...")

            await human_sleep(1, 2)

            # Step 3: 测试模式断点
            if "--test-one" in sys.argv:
                await take_screenshot(self.page, "BEFORE_PUBLISH_KS", DEBUG_DIR)
                console.print(
                    "[bold yellow]🧪 [TEST] 暂停发布，按回车继续...[/bold yellow]"
                )
                await asyncio.to_thread(input, "")

            # Step 4: 发布
            logger.info("🚀 准备发布...")
            publish_btn = await self._find_publish_button()

            if not publish_btn:
                await take_screenshot(self.page, "NO_PUBLISH_BTN_KS", DEBUG_DIR)
                return False, "找不到发布按钮"

            # 等待按钮可用
            for _ in range(15):
                if not await publish_btn.is_disabled():
                    break
                await asyncio.sleep(2)
                logger.debug("等待发布按钮可用...")

            # 滚到按钮附近后拟人化点击
            await human_scroll(self.page, random.randint(80, 150))
            await asyncio.sleep(random.uniform(0.3, 0.7))
            await human_click(self.page, publish_btn)
            logger.info("🚀 已点击发布按钮")
            await asyncio.sleep(8)

            # Step 5: 校验结果
            current_url = self.page.url
            if ("publish" not in current_url) or ("manage" in current_url) or ("published=true" in current_url):
                logger.info("✅ 发布成功（页面已跳转）")
                return True, "Success"

            for text in ["发布成功", "已发布", "作品已发布"]:
                if await self.page.query_selector(f"text={text}"):
                    logger.info(f"✅ 发布成功（检测到: {text}）")
                    return True, "Success"

            await take_screenshot(self.page, "POST_PUBLISH_KS", DEBUG_DIR)
            return False, f"发布后状态不明 (URL: {current_url})"

        except Exception as e:
            if self.page:
                await take_screenshot(self.page, "ERROR_KS", DEBUG_DIR)
            logger.error(f"流程异常: {e}")
            return False, f"Exception: {str(e)}"
        finally:
            if self.page:
                await self.page.close()


# ==================== 对外统一接口 ====================

async def run(state_mgr) -> bool:
    """
    快手上传入口。

    Parameters
    ----------
    state_mgr : StateManager 实例

    Returns
    -------
    bool : 是否成功上传
    """
    console.rule("[bold yellow]快手上传[/bold yellow]")

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
        console.print("[green]✅ 快手无待办任务[/green]")
        return False
    console.print(f"🎯 目标视频: [cyan]{target.parent.name}[/cyan]")

    async with async_playwright() as p:
        context = await create_browser_context(
            p, PLATFORM,
            headless=None,   # 由全局 HEADLESS_MODE / env HEADLESS= 控制
            viewport={"width": 1280, "height": 900},
            use_stealth=True,
        )

        uploader = KSUploader(context, target)
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
