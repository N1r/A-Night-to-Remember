"""
3_xhs.py
--------
小红书视频自动化发布模块 - 深度重构版 2.0
"""

import asyncio
import json
import random
import sys
import os
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple, List
from playwright.async_api import async_playwright, Page, BrowserContext, ElementHandle
from rich.console import Console
from rich.panel import Panel

# ==================== 配置中心 ====================
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
STORAGE_DIR = PROJECT_ROOT / "storage"
ARCHIVES_DIR = PROJECT_ROOT / "archives"
COOKIES_FILE = STORAGE_DIR / "cookies" / "xiaohongshu_cookie.json"
USER_DATA_DIR = STORAGE_DIR / "browser_data" / "xhs_profile"
STEALTH_JS_PATH = PROJECT_ROOT / "3_post_processing" / "media" / "common" / "stealth.min.js"
DEBUG_DIR = PROJECT_ROOT / "output" / "debug_xhs"

# 统一视频源路径（与抖音上传器保持一致）
VIDEO_SOURCE = ARCHIVES_DIR

console = Console()

# 配置日志
LOG_FILE = PROJECT_ROOT / "output" / "xhs_upload.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("XHSUploader")

# ==================== 工具函数 ====================

async def human_delay(min_ms=800, max_ms=2000):
    """模拟人类随机延迟"""
    await asyncio.sleep(random.uniform(min_ms, max_ms) / 1000.0)

async def safe_click(page: Page, selector: str, timeout: int = 10000) -> bool:
    """带重试和检查的点击"""
    try:
        element = await page.wait_for_selector(selector, state="visible", timeout=timeout)
        if element:
            await element.click()
            return True
    except Exception as e:
        logger.debug(f"点击失败 {selector}: {str(e)}")
    return False

# ==================== 核心逻辑 ====================

class XHSUploader:
    def __init__(self, context: BrowserContext, video_path: Path):
        self.context = context
        self.video_path = video_path
        self.video_dir = video_path.parent
        self.metadata_path = self.video_dir / "metadata.json"
        self.page: Optional[Page] = None
        
        # 初始元数据（默认值）
        self.title = self.video_path.stem[:20]
        self.desc = f"分享一个精彩视频：{self.video_path.stem}"
        self.tags = ["#新闻", "#精选"]
        self.cover_path = self._find_cover()

    def _find_cover(self) -> Optional[Path]:
        """寻找封面文件，支持多种匹配规则"""
        for ext in ['.jpg', '.png', '.jpeg', '.webp']:
            cover = self.video_path.with_suffix(ext)
            if cover.exists():
                return cover
        for name in ["cover_raw.jpg", "cover.jpg", "cover.png"]:
            fb = self.video_dir / name
            if fb.exists():
                return fb
        return None

    def _load_metadata(self):
        """解析并优化元数据"""
        if not self.metadata_path.exists():
            logger.warning(f"元数据文件不存在: {self.metadata_path}")
            return

        try:
            meta = json.loads(self.metadata_path.read_text(encoding='utf-8'))
            raw_title = meta.get('translated_title') or meta.get('title') or self.video_path.stem
            self.title = raw_title.strip()[:20]
            summary = meta.get('summary', '')
            self.desc = f"{raw_title}\n\n{summary}\n\n关注我看更多深度分析。"
            tags_set = set(["#深度分析", "#国际局势"])
            category = meta.get('category')
            if category:
                tags_set.add(f"#{category}")
            topics = meta.get('topics', [])
            if isinstance(topics, list):
                for t in topics[:3]:
                    if t: tags_set.add(f"#{t.replace(' ', '')}")
            self.tags = list(tags_set)
            logger.info(f"元数据加载成功: {self.title}")
        except Exception as e:
            logger.error(f"解析元数据失败: {str(e)}")

    async def _handle_login(self) -> bool:
        """改进的登录验证"""
        try:
            await self.page.goto("https://creator.xiaohongshu.com/publish/publish", timeout=60000)
            await human_delay(3000, 5000)
            
            # 检查多种登录状态
            login_indicators = [
                "login" in self.page.url,
                await self.page.query_selector("text=登录"),
                await self.page.query_selector("button:has-text('登录')"),
                await self.page.query_selector("[placeholder*='手机号']"),
                await self.page.query_selector("[placeholder*='密码']")
            ]
            
            if any(login_indicators):
                logger.warning("检测到登录页面，尝试自动登录...")
                return await self._auto_login()
            
            # 检查是否成功进入发布页面
            publish_indicators = [
                await self.page.query_selector('input[type="file"]'),
                await self.page.query_selector('input[placeholder*="填写标题"]'),
                "publish" in self.page.url
            ]
            
            return any(publish_indicators)
            
        except Exception as e:
            logger.error(f"登录验证失败: {e}")
            return False
    
    async def _auto_login(self):
        """自动登录功能"""
        try:
            # 尝试使用保存的cookies
            if self.cookies_file.exists():
                cookies = json.loads(self.cookies_file.read_text())
                for cookie in cookies:
                    await self.page.context.add_cookies([cookie])
                await self.page.reload()
                await human_delay(2000, 3000)
                
            # 如果仍然需要登录，显示提示信息
            if "login" in self.page.url:
                logger.error("需要手动登录小红书，请运行 get_cookies.py 更新登录信息")
                return False
                
            return True
        except Exception as e:
            logger.error(f"自动登录失败: {e}")
            return False

    async def _simulate_interaction(self):
        """模拟随机交互"""
        try:
            await self.page.mouse.wheel(0, random.randint(200, 500))
            await asyncio.sleep(1)
            await self.page.mouse.wheel(0, -200)
        except:
            pass

    async def upload(self) -> Tuple[bool, str]:
        """执行完整上传流程"""
        try:
            self._load_metadata()
            self.page = await self.context.new_page()
            
            if STEALTH_JS_PATH.exists():
                await self.page.add_init_script(path=STEALTH_JS_PATH)
            
            if not await self._handle_login():
                return False, "未登录或登录失效，请运行 get_cookies.py 更新"

            await self._simulate_interaction()

            # --- 1. 上传视频 ---
            logger.info(f"📤 正在上传视频: {self.video_path.name}")
            file_input = await self.page.wait_for_selector('input[type="file"]', state="attached", timeout=30000)
            await file_input.set_input_files(str(self.video_path))
            
            try:
                await self.page.wait_for_selector('input[placeholder*="填写标题"]', timeout=60000)
            except:
                return False, "视频上传后未能进入编辑页面"

            # --- 2. 填写标题 ---
            logger.info("📝 填写标题...")
            title_input = await self.page.query_selector('input[placeholder*="填写标题"]')
            if title_input:
                await title_input.click()
                await self.page.keyboard.press("Control+A")
                await self.page.keyboard.press("Backspace")
                await self.page.keyboard.type(self.title, delay=random.randint(50, 120))
            
            # --- 3. 填写描述和标签 ---
            logger.info("📝 填写描述...")
            desc_input = await self.page.query_selector('div#post-textarea, .tiptap, [role="textbox"]')
            if desc_input:
                await desc_input.click()
                full_desc = f"{self.desc}\n{' '.join(self.tags)}"
                lines = full_desc.split('\n')
                for line in lines:
                    await self.page.keyboard.type(line, delay=random.randint(20, 50))
                    await self.page.keyboard.press("Enter")
            
            # --- 4. 上传封面 ---
            if self.cover_path:
                logger.info(f"🖼️  正在上传自定义封面: {self.cover_path.name}")
                try:
                    edit_btn = await self.page.query_selector('text=编辑封面, .upload-cover-btn')
                    if edit_btn:
                        await edit_btn.click()
                        await human_delay(1500, 2500)
                        upload_tab = await self.page.query_selector('text=上传图片, .upload-tab')
                        if upload_tab:
                            await upload_tab.click()
                            await human_delay(800, 1500)
                        cover_input = await self.page.query_selector('input[type="file"]')
                        if cover_input:
                            await cover_input.set_input_files(str(self.cover_path))
                            await human_delay(4000, 6000)
                            confirm_btn = await self.page.query_selector('button:has-text("确定"), button:has-text("完成")')
                            if confirm_btn:
                                await confirm_btn.click()
                                await human_delay(2000, 3000)
                except Exception as ce:
                    logger.warning(f"封面上传流程异常 (跳过): {ce}")

            # --- 5. 发布 ---
            logger.info("🚀 准备发布...")
            publish_btn = await self.page.wait_for_selector('button:has-text("发布")', state="visible", timeout=120000)
            
            for _ in range(30):
                if not await publish_btn.is_disabled():
                    break
                await asyncio.sleep(2)
                logger.debug("等待视频转码中...")

            if "--test-one" in sys.argv:
                console.print("[bold yellow]🧪 [TEST MODE] 暂停发布，请检查浏览器。按回车继续...[/bold yellow]")
                await asyncio.to_thread(input, "")

            await publish_btn.click()
            await asyncio.sleep(10)
            if "publish" not in self.page.url or await self.page.query_selector("text=发布成功, text=已发布"):
                logger.info("✅ 发布指令已确认")
                return True, "Success"
            else:
                if await self.page.query_selector("text=发布成功"):
                    return True, "Success"
                return False, f"发布后状态不明 (URL: {self.page.url})"

        except Exception as e:
            ts = datetime.now().strftime("%H%M%S")
            DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            shot_path = DEBUG_DIR / f"ERROR_XHS_{ts}.png"
            if self.page:
                await self.page.screenshot(path=str(shot_path))
            logger.error(f"流程崩溃: {str(e)} | 截图: {shot_path}")
            return False, f"Exception: {str(e)}"
        finally:
            if self.page:
                await self.page.close()

async def run_xhs(state_mgr=None) -> bool:
    console.rule("[bold red]小红书自动化发布 3.1[/bold red]")
    
    targets = []
    if state_mgr:
        all_dirs = [d for d in ARCHIVES_DIR.iterdir() if d.is_dir()]
        for d in all_dirs:
            if not state_mgr.is_uploaded(d.name, "xiaohongshu"):
                vids = list(d.glob("*.mp4"))
                if vids: targets.append(vids[0])
    else:
        search_dir = PROJECT_ROOT / "storage" / "ready_to_publish"
        all_vids = sorted(search_dir.rglob("*.mp4"))
        if all_vids: targets = [all_vids[0]]

    if not targets:
        console.print("[green]✨ 没有待处理的小红书任务。[/green]")
        return True

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

        if COOKIES_FILE.exists():
            try:
                cookies = json.loads(COOKIES_FILE.read_text(encoding='utf-8'))
                await context.add_cookies(cookies.get("cookies", cookies) if isinstance(cookies, dict) else cookies)
            except Exception as e:
                logger.warning(f"Cookie 载入异常: {e}")

        final_ok = True
        for target in targets:
            uploader = XHSUploader(context, target)
            success, msg = await uploader.upload()
            if success:
                console.print(f"[bold green]✅ {target.parent.name} 发布成功[/bold green]")
                if state_mgr: state_mgr.mark_uploaded(target.parent.name, "xiaohongshu")
            else:
                console.print(f"[bold red]❌ {target.parent.name} 发布失败: {msg}[/bold red]")
                final_ok = False
            if len(targets) > 1:
                await asyncio.sleep(random.randint(15, 30))

        await context.close()
        return final_ok

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_xhs())
