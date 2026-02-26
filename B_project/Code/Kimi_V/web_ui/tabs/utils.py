from nicegui import ui
import subprocess
import threading
import sys
from pathlib import Path

def get_project_root():
    return Path(__file__).parent.parent.parent.absolute()

def run_command(command, log_element):
    """Run a shell command and stream output to a log element."""
    def run_thread():
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=get_project_root()
            )
            for line in process.stdout:
                log_element.push(line.strip())
            process.wait()
            log_element.push(f"Process finished with code {process.returncode}")
        except Exception as e:
            log_element.push(f"Error: {str(e)}")

    threading.Thread(target=run_thread, daemon=True).start()
