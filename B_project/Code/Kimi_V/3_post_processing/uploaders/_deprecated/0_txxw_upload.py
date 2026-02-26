import asyncio
import json
import random
import platform
import os
import shutil
from pathlib import Path
from playwright.async_api import async_playwright

# ==================== Rich 美化库 ====================
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeRemainingColumn
from rich.table import Table
from rich.panel import Panel

# ==================== 配置区 ====================
console = Console()
print = console.print 

import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from modules.common.browser_utils import get_chrome_path

# ==================== 配置区 ====================
console = Console()
print = console.print 

# 自动检测系统
SYSTEM = platform.system()

# 路径配置 - 使用绝对路径
FOLDER_PATH = PROJECT_ROOT / "output" / "ready_to_publish"
COVER_FOLDER_PATH = PROJECT_ROOT / "output" / "ready_to_publish"
COOKIES_FILE = PROJECT_ROOT / "storage" / "cookies" / "tc_cookies.json"       
USER_DATA_DIR = PROJECT_ROOT / "storage" / "browser_data" / "tencent_profile"         

# 成功/失败归档
DONE_DIR = FOLDER_PATH / "done"
FAILED_DIR = FOLDER_PATH / "failed"
DONE_DIR.mkdir(parents=True, exist_ok=True)
FAILED_DIR.mkdir(parents=True, exist_ok=True)
USER_DATA_DIR.mkdir(parents=True, exist_ok=True) 

# 服务器模式强制无头
HEADLESS_MODE = True

# 封面最小分辨率
MIN_COVER_WIDTH = 752
MIN_COVER_HEIGHT = 360

# 任务统计
TASK_RESULTS = []

# ==================== 工具函数 ====================

async def human_sleep(min_seconds=1, max_seconds=3):
    """模拟人类操作的随机等待"""
    t = random.uniform(min_seconds, max_seconds)
    await asyncio.sleep(t)

async def refresh_cookies(context):
    """同步刷新 Cookie 到本地文件"""
    try:
        cookies = await context.cookies()
        COOKIES_FILE.write_text(json.dumps(cookies, indent=2))
    except Exception as e:
        console.print(f"[red]⚠️ Cookie 刷新失败: {e}[/red]")

def is_valid_image(img_path):
    try:
        from PIL import Image
        with Image.open(img_path) as img:
            w, h = img.size
            return w >= MIN_COVER_WIDTH and h >= MIN_COVER_HEIGHT
    except:
        return False

def find_cover_for_video(video_path, cover_folder):
    # 优先在视频所在子目录下寻找同名封面
    for ext in [".png", ".jpg", ".jpeg"]:
        cover_path = video_path.parent / f"{video_path.stem}{ext}"
        if cover_path.exists() and is_valid_image(cover_path):
            return cover_path
    return None

def move_finished_file(video_path, cover_path, target_dir):
    try:
        # 移动整个子文件夹或至少保持结构
        video_folder_name = video_path.parent.name
        dest_folder = target_dir / video_folder_name
        dest_folder.mkdir(parents=True, exist_ok=True)
        
        shutil.move(str(video_path), dest_folder / video_path.name)
        if cover_path and cover_path.exists():
            shutil.move(str(cover_path), dest_folder / cover_path.name)
    except Exception as e:
        console.print(f"[red]❌ 文件移动失败: {e}[/red]")

# ==================== 核心上传逻辑 ====================

async def upload_cover_logic(page, cover_path):
    """上传封面"""
    try:
        upload_btn = page.get_by_role("img", name="plus")
        await upload_btn.wait_for(state="visible", timeout=10000)
        await upload_btn.click()
        
        input_el = page.locator("span.ant-upload input[type='file']")
        await input_el.wait_for(state="attached", timeout=10000)
        await input_el.set_input_files(str(cover_path))
        return True
    except Exception as e:
        console.print(f"[red]❌ 上传封面失败: {e}[/red]")
        return False

async def process_cover_crop_logic(page):
    """裁剪逻辑"""
    try:
        await page.get_by_role("dialog", name="裁剪封面").locator("img").click()
        await human_sleep(0.5, 1)
        try:
            await page.get_by_text("封面未裁剪").first.click()
            await page.get_by_text("封面未裁剪").click()
        except:
            pass 
        await human_sleep(0.5, 1)
        await page.get_by_role("button", name="完 成").click()
        return True
    except:
        return False

async def upload_single_video(context, video_path, cover_path):
    """单视频处理流程"""
    page = await context.new_page()
    video_stem = video_path.stem

    try:
        # 1. 进入页面
        await page.goto("https://shizi.qq.com/creation/video")
        if "login" in page.url:
            return False, "登录失效"

        # 2. 上传视频
        await page.get_by_role("button", name="本地上传").wait_for(state="visible", timeout=20000)
        console.log(f"📤 正在上传: [cyan]{video_path.name}[/cyan]")
        video_input = page.locator("input[type='file'][accept^='video']")
        await video_input.set_input_files(str(video_path))

        # 等待视频流传输完成
        try:
            await page.locator("text=视频上传成功").wait_for(state="visible", timeout=300000)
            console.log("✅ 视频流传输完毕")
        except:
            # 传输超时截
            try:
                await page.screenshot(path=shot_path, full_page=True, timeout=10000)
            except Exception as e:
                print(f"截图失败，跳过继续执行: {e}")
            #await page.screenshot(path=FAILED_DIR / f"timeout_{video_stem}.png", full_page=True)
            #return False, "视频上传超时"
        
        await human_sleep(1, 2)

        # 3. 封面处理
        if cover_path:
            console.log(f"🖼️  处理封面: [cyan]{cover_path.name}[/cyan]")
            if await upload_cover_logic(page, cover_path):
                await process_cover_crop_logic(page)
            await human_sleep(1, 2)

        # --- 4. 填写摘要 (自动复用文件名) ---
        try:
            # 企鹅号摘要框通常是 textarea 或 contenteditable
            # 优先通过 placeholder 定位，如果没有则通过文本框角色
            summary_text = video_stem  # 使用视频文件名（不含后缀）作为摘要
            console.log(f"📝 正在填写摘要: {summary_text[:20]}...")
            summary_input = page.get_by_placeholder("填写摘要可以快速传递核心信息")
            await summary_input.fill(summary_text)
            await human_sleep(0.5, 1)
        except Exception as e:
            console.log(f"[yellow]⚠️ 摘要填写失败: {e}[/yellow]")
        try:
            console.log("🧧 正在尝试勾选活动：春节创作不打烊")
            
            # 1. 先确保该活动卡片在视野内
            activity_card = page.get_by_text("春节创作不打烊")
            
            if await activity_card.is_visible(timeout=5000):
                # 2. 点击该活动。注意：有些 UI 需要点击卡片本身，有些是点击复选框
                # 这里使用 force=True 应对可能存在的透明遮罩
                await activity_card.click(force=True)
                console.log("✅ 已成功选择活动：春节创作不打烊")
                await human_sleep(0.5, 1)
            else:
                console.log("[yellow]⚠️ 未在页面上找到 '春节创作不打烊' 活动，可能活动已过期或账号无权限[/yellow]")
                
        except Exception as e:
            console.log(f"[yellow]⚠️ 勾选活动时出错: {str(e)[:50]}[/yellow]")
        # 5. 发布设置 (包含新增的自主声明和自荐选项)
        try:
            # --- 自主声明部分 ---
            # 点击 "声明原创" (保持原逻辑)
            try:
                await page.get_by_text("声明原创").click(timeout=3000)
                await page.get_by_text("该视频非AI生成").click(timeout=3000)
            except:
                pass
            # --- 自主声明部分 ---
            # 1. 优先尝试勾选 "取材网络，谨慎甄别"
            try:
                console.log("📝 正在勾选: 取材网络，谨慎甄别")
                # 使用 force=True 应对某些由于布局重叠导致的点击拦截
                await page.get_by_text("取材网络，谨慎甄别").click(timeout=4000)
            except Exception as e:
                console.log("[yellow]⚠️ 无法勾选'取材网络'，正在尝试勾选'暂无声明'...[/yellow]")
                try:
                    # 如果第一个失败，保底勾选 "暂无声明"
                    await page.get_by_text("暂无声明").click(timeout=3000)
                    console.log("✅ 已勾选: 暂无声明")
                except:
                    console.log("[red]❌ 暂无声明也无法勾选，跳过自主声明阶段[/red]")

        except Exception as e:
            console.log(f"[yellow]⚠️ 附加选项勾选过程中出现微小异常: {str(e)[:30]}[/yellow]")
        # 5. 发布与校验
        console.log("🚀 提交发布...")
        await page.get_by_role("button", name="发 布").click()



# 使用更精准的选择器，并增加尝试次数或监听

        try:
            modal_title_text = "素材来源信息"
            source_option_text = "引用自站外媒体"
            confirm_btn_name = "确 定"
            # 1. 使用 wait_for_selector 或 expect 替代 is_visible 的简单判断
            # 这样可以确保元素真正进入可交互状态
            modal = page.get_by_text(modal_title_text)
            # 缩短等待时间，如果 3秒内没出现，大概率是没弹
            await modal.wait_for(state="visible", timeout=3000)
            console.log(f"⚠️ 检测到【{modal_title_text}】，正在处理...")
            # 2. 定位“引用自站外媒体”并点击
            # 使用 label 或 text，并添加 force=True 确保即使被微小遮挡也能点击
            source_checkbox = page.get_by_text(source_option_text)
            await source_checkbox.click(force=True)
            # 验证是否选中（可选，增加稳健性）
            if not await source_checkbox.is_checked(): 
                await source_checkbox.check()
            await human_sleep(0.5, 0.8)

            # 3. 点击“确定”按钮
            # 使用 get_by_role 配合精确名称，防止误点背景其他的“确定”
            confirm_btn = page.get_by_role("button", name=confirm_btn_name)
            await confirm_btn.click()
            console.log("✅ 弹窗已确认")
            # 4. 关键：等待弹窗消失，确保后续操作不会被残余遮罩层拦截
            await modal.wait_for(state="hidden", timeout=5000)
            
        except Exception as e:
            # 只有在确实需要处理报错时才记录，否则静默跳过
            console.log(f"ℹ️ 未检测到弹窗或已自动跳过: {str(e)}")

        console.log("🚀 再次提交发布...")
        await page.get_by_role("button", name="发 布").click()
        await human_sleep(1, 2)
        if await page.get_by_role("button", name="确定发布").is_visible():
            await page.get_by_role("button", name="确定发布").click()
        
        # 严格验证是否跳转
        console.log("⏳ 等待跳转校验...")
        try:
            await page.wait_for_url("**/content/article-manage**", timeout=25000)
            console.log("[bold green]✅ 发布成功 (已跳转)[/bold green]")
            await refresh_cookies(context)
            return True, "发布成功"
        except:
            # 发布后没跳转，可能是卡了或者有报错弹窗，截图
            shot_path = FAILED_DIR / f"fail_no_jump_{video_stem}.png"
            await page.screenshot(path=shot_path, full_page=True)
            return False, f"发布后未跳转(截图已保存)"

    except Exception as e:
        # 任何程序层面的崩溃，保存现场
        shot_path = FAILED_DIR / f"error_exception_{video_stem}.png"
        await page.screenshot(path=shot_path, full_page=True)
        console.log(f"[bold red]❌ 脚本异常: {str(e)[:50]}[/bold red]")
        return False, f"异常: {str(e)[:30]}"

    finally:
        await page.close()

# ==================== 浏览器启动 ====================

async def start_persistent_browser(p):
    console.print(f"[dim]📂 加载数据目录: {USER_DATA_DIR}[/dim]")
    
    args = [
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-blink-features=AutomationControlled",
    ]
    
    context = await p.chromium.launch_persistent_context(
        user_data_dir=USER_DATA_DIR,
        headless=HEADLESS_MODE,
        args=args,
        viewport={"width": 1920, "height": 1080},
    )
    
    await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    if COOKIES_FILE.exists():
        try:
            json_cookies = json.loads(COOKIES_FILE.read_text())
            await context.add_cookies(json_cookies)
            console.print("[green]🍪 已合并本地 Cookies 文件[/green]")
        except Exception as e:
            console.print(f"[yellow]⚠️ Cookie 注入失败: {e}[/yellow]")
    
    return context

# ==================== 主程序 ====================

async def main():
    console.clear()
    console.print(Panel.fit("[bold white]🐧 企鹅号 自动化上传[/bold white]", style="blue"))

    videos = list(FOLDER_PATH.glob("*.mp4"))
    if not videos:
        console.print("[bold red]❌ 目录下没有待处理的 .mp4 文件[/bold red]")
        return

    async with async_playwright() as p:
        context = await start_persistent_browser(p)
        
        # 预检
        test_page = await context.new_page()
        try:
            await test_page.goto("https://shizi.qq.com/creation/video", timeout=30000)
            if "login" in test_page.url:
                console.print("[bold red]⛔ 登录失效，请手动登录一次或更新 Cookies[/bold red]")
                await context.close()
                return
        except Exception as e:
            console.print(f"[red]❌ 初始化访问失败: {e}[/red]")
            await context.close()
            return
        finally:
            await test_page.close()

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeRemainingColumn(),
            console=console
        ) as progress:
            
            task_id = progress.add_task("批量上传中...", total=len(videos))

            for video_path in videos:
                progress.update(task_id, description=f"正在处理: {video_path.name}")
                
                cover_path = find_cover_for_video(video_path, COVER_FOLDER_PATH)
                success, msg = await upload_single_video(context, video_path, cover_path)
                
                if success:
                    move_finished_file(video_path, cover_path, DONE_DIR)
                    TASK_RESULTS.append({"name": video_path.name, "status": "成功"})
                else:
                    move_finished_file(video_path, cover_path, FAILED_DIR)
                    TASK_RESULTS.append({"name": video_path.name, "status": "失败", "reason": msg})
                
                progress.advance(task_id)
                if video_path != videos[-1]:
                    await human_sleep(5, 8)

        await context.close()

    # 结果统计
    table = Table(title="任务执行报告")
    table.add_column("视频名称", style="cyan")
    table.add_column("状态", style="bold")
    table.add_column("备注", style="dim")

    for res in TASK_RESULTS:
        status_str = f"[green]成功[/green]" if res["status"] == "成功" else f"[red]失败[/red]"
        table.add_row(res["name"], status_str, res.get("reason", "-"))
    
    console.print(table)

if __name__ == "__main__":
    asyncio.run(main())
