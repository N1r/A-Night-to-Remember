import os, sys
import platform
import subprocess
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

ascii_logo = """
__     ___     _            _     _                    
\ \   / (_) __| | ___  ___ | |   (_)_ __   __ _  ___  
 \ \ / /| |/ _` |/ _ \/ _ \| |   | | '_ \ / _` |/ _ \ 
  \ V / | | (_| |  __/ (_) | |___| | | | | (_| | (_) |
   \_/  |_|\__,_|\___|\___/|_____|_|_| |_|\__, |\___/ 
                                          |___/        
"""

def install_package(*packages):
    subprocess.check_call([sys.executable, "-m", "pip", "install", *packages])

def check_ffmpeg():
    from rich.console import Console
    from rich.panel import Panel
    console = Console()

    try:
        # Check if ffmpeg is installed
        subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
        console.print(Panel("✅ FFmpeg is already installed", style="green"))
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        system = platform.system()
        install_cmd = ""
        
        if system == "Windows":
            install_cmd = "choco install ffmpeg"
            extra_note = "Install Chocolatey first (https://chocolatey.org/)"
        elif system == "Darwin":
            install_cmd = "brew install ffmpeg"
            extra_note = "Install Homebrew first (https://brew.sh/)"
        elif system == "Linux":
            install_cmd = "apt install ffmpeg  # Ubuntu/Debian"
            extra_note = "Please install FFmpeg using your package manager manually if not found."
        
        console.print(Panel.fit(
            "❌ FFmpeg not found\n\n" +
            f"🛠️ Suggested installation:\n[bold cyan]{install_cmd}[/bold cyan]\n\n" +
            f"💡 Note:\n{extra_note}\n\n" +
            "🔄 After installing FFmpeg, please run this installer again.",
            style="red"
        ))
        return False

def main():
    install_package("requests", "rich", "ruamel.yaml", "InquirerPy", "pandas", "openpyxl")
    from rich.console import Console
    from rich.panel import Panel
    from rich.box import DOUBLE
    from InquirerPy import inquirer
    from core.utils.decorator import except_handler

    console = Console()
    
    width = max(len(line) for line in ascii_logo.splitlines()) + 4
    welcome_panel = Panel(
        ascii_logo,
        width=width,
        box=DOUBLE,
        title="[bold green]🌏[/bold green]",
        border_style="bright_blue"
    )
    console.print(welcome_panel)

    console.print(Panel.fit("🚀 Starting Lightweight Installation", style="bold magenta"))

    # Configure mirrors
    if inquirer.confirm(
        message="Do you need to auto-configure PyPI mirrors? (Recommended if you have difficulty accessing pypi.org)",
        default=True
    ).execute():
        from core.utils.pypi_autochoose import main as choose_mirror
        choose_mirror()

    @except_handler("Failed to install project requirements")
    def install_requirements():
        console.print(Panel("Installing dependencies from requirements.txt...", style="cyan"))
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])

    install_requirements()
    check_ffmpeg()
    
    # First panel with installation complete
    panel1_text = (
        "Installation completed (Lightweight Mode)" + "\n\n" +
        "Torch and heavy ML dependencies were skipped. Sudo steps were removed."
    )
    console.print(Panel(panel1_text, style="bold green"))

    # Second panel with troubleshooting tips
    panel2_text = (
        "If the application fails to start:" + "\n" +
        "1. Check your network connection" + "\n" +
        "2. Re-run the installer: [bold]python apps/cli/install.py[/bold]"
    )
    console.print(Panel(panel2_text, style="yellow"))

if __name__ == "__main__":
    main()
