from nicegui import ui
import subprocess
import threading
import sys
from .utils import get_project_root

def workflow_tab():
    with ui.column().classes('w-full h-full'):
        ui.markdown("## Workflow Execution")
        
        log_view = ui.log().classes('w-full h-96 bg-black text-green-400 font-mono p-4 rounded-md')
        
        def run_script(script_path):
            full_path = get_project_root() / script_path
            
            def run_thread():
                try:
                    process = subprocess.Popen(
                        [sys.executable, str(full_path)],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                        cwd=get_project_root()
                    )
                    
                    for line in process.stdout:
                        log_view.push(line.strip())
                    
                    process.wait()
                    log_view.push(f"Process finished with code {process.returncode}")
                except Exception as e:
                    log_view.push(f"Error: {str(e)}")
            
            log_view.push(f"Starting script: {script_path}...")
            threading.Thread(target=run_thread, daemon=True).start()

        with ui.row().classes('w-full gap-4'):
            ui.button('Step 1: Pre-Processing (Scrape & Filter)', on_click=lambda: run_script("1_pre_processing/workflow_1_pre.py")).classes('bg-blue-500 text-white')
            ui.button('Step 2: Mid-Processing (Translate & Subtitle)', on_click=lambda: run_script("2_mid_processing/workflow_2_mid.py")).classes('bg-green-500 text-white')
            ui.button('Step 3: Post-Processing (Upload)', on_click=lambda: run_script("3_post_processing/workflow_3_post.py")).classes('bg-purple-500 text-white')
            ui.button('Clear Logs', on_click=log_view.clear).classes('bg-gray-500 text-white')

        ui.label('Note: Workflows run asynchronously. Check logs for progress.').classes('text-sm text-gray-500 mt-2')
