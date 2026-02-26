"""
3_xhs.py (修复版本)
--------
小红书视频自动化发布模块 - 深度重构版 2.0 (修复版)
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
    """安全的点击操作"""
    try:
        element = await page.wait_for_selector(selector, timeout=timeout)
        if element:
            await element.click()
            await human_delay(500, 1500)
            return True
    except Exception as e:
        logger.warning(f"点击元素失败 {selector}: {e}")
    return False

async def safe_type(page: Page, selector: str, text: str, delay_range=(50, 120)):
    """安全的输入操作"""
    try:
        element = await page.wait_for_selector(selector, timeout=10000)
        if element:
            await element.click()
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            for char in text:
                await page.keyboard.type(char, delay=random.randint(*delay_range))
                await human_delay(100, 300)
            return True
    except Exception as e:
        logger.warning(f"输入文本失败 {selector}: {e}")
    return False

# ==================== 小红书上传器类 ====================

class XHSUploader:
    def __init__(self, video_name: str):
        self.video_name = video_name
        self.video_path, self.video_dir = self._find_video()
        self.metadata_path = self.video_dir / "metadata.json"
        self.cookies_file = COOKIES_FILE
        self.debug_path = DEBUG_DIR / f"{video_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # 初始化元数据（默认值）
        self.title = self.video_path.stem[:20]
        self.desc = f"分享一个精彩视频：{self.video_path.stem}"
        self.tags = ["#新闻", "#精选"]
        self.cover_path = self._find_cover()

        # 创建调试目录
        self.debug_path.mkdir(parents=True, exist_ok=True)

    def _find_video(self):
        """查找视频文件 - 支持archives和ready_to_publish双目录"""
        # 优先查找archives目录（与抖音上传器保持一致）
        video_in_archives = VIDEO_SOURCE / self.video_name / f"{self.video_name}.mp4"
        if video_in_archives.exists():
            return video_in_archives, VIDEO_SOURCE / self.video_name

        # 回退到ready_to_publish目录
        video_in_storage = STORAGE_DIR / "ready_to_publish" / self.video_name / "output_sub.mp4"
        if video_in_storage.exists():
            return video_in_storage, STORAGE_DIR / "ready_to_publish" / self.video_name

        logger.error(f"未找到视频文件: {self.video_name}")
        return None, None

    def _find_cover(self) -> Optional[Path]:
        """寻找封面文件，支持多种匹配规则"""
        if not self.video_path:
            return None

        # 优先查找archives目录
        for ext in ['.jpg', '.png', '.jpeg', '.webp']:
            cover = self.video_path.with_suffix(ext)
            if cover.exists():
                return cover

        # 查找特定文件名
        for name in ["cover_raw.jpg", "cover.jpg", "cover.png"]:
            fb = self.video_dir / name
            if fb.exists():
                return fb

        return None

    def _parse_metadata_txt(self, txt_path):
        """解析metadata.txt文件"""
        meta = {}
        content = txt_path.read_text(encoding='utf-8')
        
        # 简单的txt解析逻辑
        lines = content.split('\n')
        for line in lines:
            if '标题:' in line:
                meta['title'] = line.split('标题:')[1].strip()
            elif '内容:' in line:
                meta['summary'] = line.split('内容:')[1].strip()
            elif '分类:' in line:
                meta['category'] = line.split('分类:')[1].strip()
        
        return meta

    def _apply_metadata(self, meta, source_dir):
        """应用元数据"""
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

    def _load_metadata(self):
        """改进的元数据加载 - 支持多个目录和文件格式"""
        # 尝试多个可能的元数据文件路径
        possible_paths = [
            # archives目录
            ARCHIVES_DIR / self.video_name / "metadata.json",
            ARCHIVES_DIR / self.video_name / "metadata.txt",
            # ready_to_publish目录
            STORAGE_DIR / "ready_to_publish" / self.video_name / "metadata.json",
        ]
        
        for meta_path in possible_paths:
            if meta_path.exists():
                try:
                    if meta_path.suffix == '.json':
                        meta = json.loads(meta_path.read_text(encoding='utf-8'))
                    else:  # .txt文件
                        meta = self._parse_metadata_txt(meta_path)
                    
                    self._apply_metadata(meta, meta_path.parent)
                    logger.info(f"成功加载元数据: {meta_path}")
                    return
                except Exception as e:
                    logger.warning(f"解析元数据文件失败 {meta_path}: {e}")
                    continue
        
        # 如果没有找到元数据文件，使用默认值
        logger.warning(f"未找到元数据文件，使用默认值: {self.video_path.stem}")
        self.title = self.video_path.stem[:20]
        self.desc = f"分享一个精彩视频：{self.video_path.stem}"
        self.tags = ["#新闻", "#精选"]

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

    async def _simulate_interaction(self):
        """模拟随机交互"""
        try:
            await self.page.mouse.wheel(0, random.randint(200, 500))
            await human_delay(1000, 2000)
            await self.page.mouse.wheel(0, -200)
        except:
            pass

    async def upload(self) -> Tuple[bool, str]:
        """执行完整上传流程"""
        try:
            if not self.video_path:
                return False, "未找到视频文件"

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
            if not await safe_type(self.page, 'input[placeholder*="填写标题"]', self.title):
                logger.warning("标题输入失败，尝试备用选择器")
                if not await safe_type(self.page, 'input[placeholder*="标题"]', self.title):
                    return False, "填写标题失败"

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
                    await human_delay(200, 500)
            else:
                logger.warning("未找到描述输入框")

            # --- 4. 上传封面 ---
            if self.cover_path:
                logger.info(f"🖼️  正在上传自定义封面: {self.cover_path.name}")
                try:
                    edit_btn = await self.page.query_selector('text=编辑封面, .upload-cover-btn')
                    if edit_btn:
                        await edit_btn.click()
                        await human_delay(1000, 2000)
                        
                        cover_input = await self.page.query_selector('input[type="file"][accept*="image"]')
                        if cover_input:
                            await cover_input.set_input_files(str(self.cover_path))
                            await human_delay(2000, 3000)
                            logger.info("封面上传成功")
                        else:
                            logger.warning("未找到封面上传输入框")
                    else:
                        logger.warning("未找到编辑封面按钮")
                except Exception as e:
                    logger.warning(f"封面上传失败: {e}")

            # --- 5. 发布 ---
            logger.info("🚀 准备发布...")
            publish_btn = await self.page.query_selector('button:has-text("发布"), button:has-text("立即发布")')
            if publish_btn:
                await publish_btn.click()
                await human_delay(3000, 5000)
                logger.info("✅ 发布成功！")
                return True, "发布成功"
            else:
                logger.warning("未找到发布按钮")
                return False, "未找到发布按钮"

        except Exception as e:
            logger.error(f"上传过程异常: {str(e)}")
            return False, f"上传失败: {str(e)}"

    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.playwright = await async_playwright().start()
        self.context = await self.playwright.chromium.launch_persistent_context(
            USER_DATA_DIR,
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--disable-extensions",
                "--disable-plugins",
                "--disable-images",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--disable-gpu",
                "--window-size=1920,1080",
                "--lang=zh-CN,zh"
            ],
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if hasattr(self, 'context'):
            await self.context.close()
        if hasattr(self, 'playwright'):
            await self.playwright.stop()

# ==================== 主函数 ====================

async def run_xhs(state_mgr=None) -> bool:
    console.rule("[bold red]小红书自动化发布 3.1 (修复版)[/bold red]")
    
    # 查找archives目录中的视频
    if not VIDEO_SOURCE.exists():
        logger.error(f"视频源目录不存在: {VIDEO_SOURCE}")
        return False

    # 过滤掉done和failed文件夹，只处理有效的视频文件夹
        all_dirs = [d for d in VIDEO_SOURCE.iterdir() if d.is_dir()]
        video_dirs = [d for d in all_dirs if d.name not in ['done', 'failed']]
        
        if not video_dirs:
            logger.info(f"archives目录中没有找到有效的视频文件夹（已过滤done/failed）")
            return False

    logger.info(f"找到 {len(video_dirs)} 个视频文件夹")

    for video_dir in video_dirs:
        video_name = video_dir.name
        logger.info(f"开始处理视频: {video_name}")

        try:
            async with XHSUploader(video_name) as uploader:
                success, message = await uploader.upload()
                if success:
                    logger.info(f"✅ {video_name} 发布成功")
                    if state_mgr:
                        state_mgr.update_status(video_name, "xiaohongshu", True)
                else:
                    logger.error(f"❌ {video_name} 发布失败: {message}")
                    if state_mgr:
                        state_mgr.update_status(video_name, "xiaohongshu", False)
        except Exception as e:
            logger.error(f"处理视频 {video_name} 时发生异常: {e}")
            if state_mgr:
                state_mgr.update_status(video_name, "xiaohongshu", False)

    return True

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_xhs())