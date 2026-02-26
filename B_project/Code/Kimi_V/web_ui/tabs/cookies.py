from nicegui import ui
import subprocess
import threading
import time
import sys
from .utils import get_project_root

PROJECT_ROOT = get_project_root()
QR_CODE_PATH = PROJECT_ROOT / "output" / "login_qrcode.png"

def cookie_tab():
    with ui.column().classes('w-full h-full'):
        ui.markdown("## Cookie Manager")
        
        with ui.row().classes('items-center gap-4 mb-4'):
            platforms = ["douyin", "bilibili", "kuaishou", "xhs", "videohao"]
            selected_platform = ui.select(platforms, value='douyin', label='Select Platform').classes('w-48')
            
            start_btn = ui.button('Start Login Process').classes('bg-green-500 text-white')
            stop_btn = ui.button('Stop Process').classes('bg-red-500 text-white').props('disabled')

        with ui.row().classes('w-full gap-4'):
            with ui.card().classes('w-1/3 h-[500px] flex flex-col'):
                ui.label('Execution Log').classes('font-bold mb-2')
                log_view = ui.log().classes('w-full flex-grow bg-black text-green-400 font-mono text-sm p-2 overflow-y-auto')

            with ui.card().classes('w-2/3 h-[500px] flex flex-col items-center justify-center bg-gray-50'):
                ui.label('Login QR Code / Screenshot').classes('font-bold mb-2')
                qr_image = ui.image('/output/login_qrcode.png').classes('max-h-full object-contain').style('display: none;')
                no_image_label = ui.label('Waiting for screenshot...').classes('text-gray-400')

        process_container = {"proc": None}

        def start_cookie_process():
            if process_container["proc"]:
                ui.notify('Process already running!', type='warning')
                return

            start_btn.disable()
            stop_btn.enable()
            log_view.clear()
            log_view.push(f"Starting cookie acquisition for: {selected_platform.value}")

            script_path = PROJECT_ROOT / "1_pre_processing" / "cli_tools" / "bk_get_cookies.py"
            
            def run_thread():
                try:
                    process = subprocess.Popen(
                        [sys.executable, str(script_path), "--platform", selected_platform.value],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                        cwd=PROJECT_ROOT
                    )
                    process_container["proc"] = process
                    
                    for line in process.stdout:
                        log_view.push(line.strip())
                        
                    process.wait()
                except Exception as e:
                    log_view.push(f"Error: {e}")
                finally:
                    process_container["proc"] = None
                    # Update UI in main thread via ui.run_javascript or callback? 
                    # NiceGUI handles this automatically mostly, but let's be safe.
                    # Since we are in a thread, direct UI updates might work if context is preserved, 
                    # but usually better to use ui.timer or something.
                    # For simplicity, we just update the buttons state on next interaction or timer check.
                    # But to be responsive, we can just update the element properties.
                    start_btn.enable()
                    stop_btn.disable()
                    log_view.push("Process finished.")

            threading.Thread(target=run_thread, daemon=True).start()

        def stop_cookie_process():
            if process_container["proc"]:
                process_container["proc"].terminate()
                process_container["proc"] = None
                log_view.push("Process terminated by user.")
                start_btn.enable()
                stop_btn.disable()

        start_btn.on_click(start_cookie_process)
        stop_btn.on_click(stop_cookie_process)

        def refresh_image():
            if QR_CODE_PATH.exists():
                qr_image.style('display: block;')
                no_image_label.style('display: none;')
                qr_image.set_source(f"/output/login_qrcode.png?t={time.time()}")
            else:
                qr_image.style('display: none;')
                no_image_label.style('display: block;')

        ui.timer(1.0, refresh_image)
