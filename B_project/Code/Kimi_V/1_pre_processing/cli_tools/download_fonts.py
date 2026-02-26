import os
import requests
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, DownloadColumn, TransferSpeedColumn

console = Console()

# 配置项：可以轻松添加更多字体
FONTS_CONFIG = {
    "NotoSansSC-Bold.ttf": "https://github.com/googlefonts/noto-cjk/raw/main/Sans/SubsetOTF/SC/NotoSansSC-Bold.otf",
    "NotoSansSC-Regular.ttf": "https://github.com/googlefonts/noto-cjk/raw/main/Sans/SubsetOTF/SC/NotoSansSC-Regular.otf",
    "HarmonyOS_Sans_SC_Bold.ttf": "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Chinese-Simplified/NotoSansCJKsc-Bold.otf", # 备选
}

def download_font(url, dest_path):
    response = requests.get(url, stream=True)
    total_size = int(response.headers.get('content-length', 0))
    
    with Progress(
        TextColumn("[bold blue]{task.fields[filename]}", justify="right"),
        BarColumn(bar_width=40),
        "[progress.percentage]{task.percentage:>3.1f}%",
        "•",
        DownloadColumn(),
        "•",
        TransferSpeedColumn(),
    ) as progress:
        task = progress.add_task("download", total=total_size, filename=dest_path.name)
        with open(dest_path, "wb") as f:
            for data in response.iter_content(chunk_size=1024):
                size = f.write(data)
                progress.update(task, advance=size)

def main():
    # 遵循我们重构后的路径规范
    PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
    FONT_DIR = PROJECT_ROOT / "storage" / "fonts"
    FONT_DIR.mkdir(parents=True, exist_ok=True)

    console.print(f"[bold green]🚀 字体下载器启动[/bold green]")
    console.print(f"目标目录: [cyan]{FONT_DIR}[/cyan]\n")

    for name, url in FONTS_CONFIG.items():
        dest = FONT_DIR / name
        if dest.exists():
            console.print(f"⏩ [yellow]{name}[/yellow] 已存在，跳过。")
            continue
        
        try:
            console.print(f"📥 正在下载 [bold]{name}[/bold]...")
            download_font(url, dest)
            console.print(f"✅ [green]{name}[/green] 下载完成！")
        except Exception as e:
            console.print(f"❌ 下载 [red]{name}[/red] 失败: {e}")

    console.print("\n[bold green]✨ 所有字体处理完毕！[/bold green]")

if __name__ == "__main__":
    main()
