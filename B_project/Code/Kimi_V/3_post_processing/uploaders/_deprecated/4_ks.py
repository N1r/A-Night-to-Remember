"""
4_ks.py
--------
快手视频自动化发布模块

快手创作者平台: https://cp.kuaishou.com/article/publish/video
"""

import asyncio
import json
import random
import sys
import os
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple
from playwright.async_api import async_playwright, Page, BrowserContext
from rich.console import Console

# ==================== 配置中心 ====================
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
STORAGE_DIR = PROJECT_ROOT / "storage"
ARCHIVES_DIR = PROJECT_ROOT / "archives"
COOKIES_FILE = STORAGE_DIR / "cookies" / "kuaishou_cookie.json"
USER_DATA_DIR = STORAGE_DIR / "browser_data" / "ks_profile"
STEALTH_JS_PATH = PROJECT_ROOT / "3_post_processing" / "media" / "common" / "stealth.min.js"
DEBUG_DIR = PROJECT_ROOT / "output" / "debug_ks"

console = Console()

# 配置日志
LOG_FILE = PROJECT_ROOT / "output" / "ks_upload.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("KSUploader")

# ==================== 工具函数 ====================

async def human_delay(min_ms=800, max_ms=2000):
    await asyncio.sleep(random.uniform(min_ms, max_ms) / 1000.0)

async def take_debug_screenshot(page, prefix="DEBUG"):
    """保存调试截图"""
    ts = datetime.now().strftime("%H%M%S")
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    path = DEBUG_DIR / f"{prefix}_{ts}.png"
    try:
        await page.screenshot(path=str(path))
        logger.info(f"📸 截图已保存: {path}")
    except:
        pass
    return path

# ==================== 核心逻辑 ====================

class KSUploader:
    def __init__(self, context: BrowserContext, video_path: Path):
        self.context = context
        self.video_path = video_path
        self.video_dir = video_path.parent
        self.metadata_path = self.video_dir / "metadata.json"
        self.page: Optional[Page] = None

        self.title = self.video_path.stem
        self.desc = f"分享视频：{self.video_path.stem}"
        self.tags = ["#新闻", "#精选"]

    def _load_metadata(self):
        if not self.metadata_path.exists():
            logger.warning(f"元数据文件不存在: {self.metadata_path}")
            return
        try:
            meta = json.loads(self.metadata_path.read_text(encoding='utf-8'))
            self.title = meta.get('translated_title') or meta.get('title') or self.video_path.stem
            summary = meta.get('summary', '')
            self.desc = f"{self.title}\n{summary}"
            category = meta.get('category')
            tags_set = set(["#深度分析"])
            if category:
                tags_set.add(f"#{category}")
            self.tags = list(tags_set)
            logger.info(f"元数据加载成功: {self.title}")
        except Exception as e:
            logger.error(f"解析元数据失败: {str(e)}")

    async def upload(self) -> Tuple[bool, str]:
        try:
            self._load_metadata()
            self.page = await self.context.new_page()

            if STEALTH_JS_PATH.exists():
                await self.page.add_init_script(path=STEALTH_JS_PATH)

            # 访问快手发布页
            logger.info("🌐 访问快手创作者平台发布页...")
            await self.page.goto(
                "https://cp.kuaishou.com/article/publish/video",
                timeout=60000
            )
            await asyncio.sleep(5)

            # 检查登录状态
            if "passport" in self.page.url or "login" in self.page.url:
                return False, "未登录或登录失效，请先获取快手 Cookie"

            # ── Step 1: 上传视频 ──
            logger.info(f"📤 正在上传视频: {self.video_path.name}")
            file_input = await self.page.wait_for_selector(
                'input[type="file"]', state="attached", timeout=30000
            )
            await file_input.set_input_files(str(self.video_path))

            # 等待视频上传完成（出现"重新上传"按钮）
            logger.info("⏳ 等待视频上传完成...")
            try:
                await self.page.wait_for_selector(
                    'text=重新上传', timeout=300000
                )
                logger.info("✅ 视频上传完成")
            except Exception:
                await take_debug_screenshot(self.page, "UPLOAD_TIMEOUT")
                return False, "视频上传超时（5分钟）"

            await human_delay(2000, 3000)

            # ── Step 2: 填写作品描述 ──
            # 快手发布页的描述框 placeholder: "作品描述不会写？试试智能文案"
            logger.info("📝 填写作品描述...")

            # 尝试多种选择器定位描述框
            desc_input = None
            desc_selectors = [
                'div[data-placeholder*="作品描述"]',
                'div[contenteditable="true"]',
                'textarea[placeholder*="作品描述"]',
                '.ql-editor',
                '#work-description-edit',
                '.desc-input',
            ]

            for selector in desc_selectors:
                try:
                    el = await self.page.wait_for_selector(
                        selector, state="visible", timeout=3000
                    )
                    if el:
                        desc_input = el
                        logger.info(f"📍 找到描述框: {selector}")
                        break
                except:
                    continue

            if not desc_input:
                # 最后尝试: 通过文本内容查找
                logger.info("🔍 尝试通过页面文本定位描述框...")
                try:
                    # 点击"作品描述"旁边的输入区域
                    desc_label = await self.page.wait_for_selector(
                        'text=作品描述', timeout=5000
                    )
                    if desc_label:
                        # 找到标签后，点击其附近的编辑区域
                        bbox = await desc_label.bounding_box()
                        if bbox:
                            # 点击标签右侧的输入区域
                            await self.page.mouse.click(
                                bbox['x'] + bbox['width'] + 100,
                                bbox['y'] + 40
                            )
                            desc_input = True  # 标记为已点击
                            logger.info("📍 通过坐标定位到描述框")
                except:
                    pass

            if not desc_input:
                await take_debug_screenshot(self.page, "NO_DESC_INPUT")
                return False, "无法定位作品描述输入框"

            # 如果 desc_input 是 element（非 True 标记），点击它
            if desc_input is not True:
                await desc_input.click()

            await human_delay(500, 1000)

            # 清空并输入
            await self.page.keyboard.press("Control+A")
            await self.page.keyboard.press("Backspace")
            await human_delay(300, 500)

            full_text = f"{self.title} {' '.join(self.tags)}"
            # 限制长度
            if len(full_text) > 500:
                full_text = full_text[:500]
            await self.page.keyboard.type(full_text, delay=random.randint(30, 60))
            logger.info(f"📝 描述已填写: {full_text[:50]}...")

            await human_delay(1000, 2000)

            # ── Step 3: 点击发布 ──
            if "--test-one" in sys.argv:
                await take_debug_screenshot(self.page, "BEFORE_PUBLISH")
                console.print(
                    "[bold yellow]🧪 [TEST MODE] 暂停发布，请检查浏览器。"
                    "按回车继续...[/bold yellow]"
                )
                await asyncio.to_thread(input, "")

            logger.info("🚀 准备发布...")
            # 用 JS 找到发布按钮并滚动到可视区域
            publish_btn = None
            try:
                # 先用 JS scrollIntoView 让按钮进入视口
                await self.page.evaluate("""
                    (() => {
                        const btns = document.querySelectorAll('button');
                        for (const btn of btns) {
                            if (btn.textContent.trim() === '发布') {
                                btn.scrollIntoView({ behavior: 'smooth', block: 'center' });
                                return true;
                            }
                        }
                        return false;
                    })()
                """)
                await human_delay(1500, 2000)
                publish_btn = await self.page.wait_for_selector(
                    'button:has-text("发布")', state="visible", timeout=10000
                )
            except:
                pass

            if not publish_btn:
                # 备用：用 keyboard End 键滚动
                for _ in range(5):
                    await self.page.keyboard.press("End")
                    await human_delay(500, 800)
                try:
                    publish_btn = await self.page.wait_for_selector(
                        'button:has-text("发布")', state="visible", timeout=5000
                    )
                except:
                    pass

            if not publish_btn:
                await take_debug_screenshot(self.page, "NO_PUBLISH_BTN")
                return False, "找不到发布按钮"

            # 检查按钮是否可点击
            for _ in range(15):
                if not await publish_btn.is_disabled():
                    break
                await asyncio.sleep(2)
                logger.debug("等待发布按钮可用...")

            await publish_btn.click()
            logger.info("🚀 已点击发布按钮")

            # 等待发布结果
            await asyncio.sleep(8)

            # 检查是否有发布成功提示或页面跳转
            current_url = self.page.url
            if "publish" not in current_url or "manage" in current_url:
                logger.info("✅ 发布成功（页面已跳转）")
                return True, "Success"

            # 检查成功提示
            success_texts = ['发布成功', '已发布', '作品已发布']
            for text in success_texts:
                if await self.page.query_selector(f'text={text}'):
                    logger.info(f"✅ 发布成功（检测到: {text}）")
                    return True, "Success"

            await take_debug_screenshot(self.page, "POST_PUBLISH")
            return False, f"发布后状态不明 (URL: {current_url})"

        except Exception as e:
            await take_debug_screenshot(self.page, "ERROR_KS")
            logger.error(f"流程异常: {str(e)}")
            return False, f"Exception: {str(e)}"
        finally:
            if self.page:
                await self.page.close()


async def run_ks(state_mgr=None) -> bool:
    console.rule("[bold yellow]快手自动化发布[/bold yellow]")

    search_dir = PROJECT_ROOT / "storage" / "ready_to_publish"
    targets = sorted([
        v for v in search_dir.rglob("output_sub.mp4")
        if "TEST_VIDEO" not in str(v)
    ])
    if not targets:
        console.print("[green]✨ 没有待处理的快手任务。[/green]")
        return True

    target = targets[0]  # 每次只处理一个
    console.print(f"🎯 目标视频: [cyan]{target.parent.name}[/cyan]")

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False if "--test-one" in sys.argv else True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--lang=zh-CN",
            ],
            ignore_default_args=["--enable-automation"],
            viewport={"width": 1280, "height": 900}
        )

        # 注入 Cookie
        if COOKIES_FILE.exists():
            try:
                cookies = json.loads(COOKIES_FILE.read_text(encoding='utf-8'))
                if isinstance(cookies, dict):
                    cookies = cookies.get("cookies", cookies)
                await context.add_cookies(cookies)
                logger.info("🍪 快手 Cookie 已加载")
            except Exception as e:
                logger.warning(f"Cookie 载入异常: {e}")

        uploader = KSUploader(context, target)
        success, msg = await uploader.upload()

        if success:
            console.print(f"[bold green]✅ {target.parent.name} 发布成功[/bold green]")
            if state_mgr:
                state_mgr.mark_uploaded(target.parent.name, "kuaishou")
        else:
            console.print(f"[bold red]❌ {target.parent.name} 发布失败: {msg}[/bold red]")

        await context.close()
        return success


if __name__ == "__main__":
    asyncio.run(run_ks())
