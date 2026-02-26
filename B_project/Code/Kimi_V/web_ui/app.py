from nicegui import ui, app
import sys
import subprocess
import threading
import time
from pathlib import Path

# Setup paths
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared.domain import domain
from shared.aesthetics import aesthetics

# Constants
QR_CODE_PATH = PROJECT_ROOT / "output" / "login_qrcode.png"

@ui.page('/')
def main_page():
    # Serve static files for QR code
    app.add_static_files('/output', str(PROJECT_ROOT / 'output'))
    QR_IMG_URL = "/output/login_qrcode.png"

    with ui.header().classes('bg-blue-600 items-center'):
        ui.label(f'Kimi_V Control Panel - {domain.name}').classes('text-lg font-bold text-white')

    with ui.tabs().classes('w-full') as tabs:
        dashboard_tab = ui.tab('Dashboard')
        cookie_tab = ui.tab('Cookie Manager')

    with ui.tab_panels(tabs, value=cookie_tab).classes('w-full p-4'):
        
        # ================== Dashboard ==================
        with ui.tab_panel(dashboard_tab):
            ui.label('Configuration Overview').classes('text-xl font-bold mb-4')
            with ui.row().classes('w-full gap-4'):
                with ui.card().classes('w-1/2'):
                    ui.label('Domain Config').classes('font-bold')
                    ui.json_editor({'content': domain._data}, select_on_change=False).classes('w-full h-96')
                with ui.card().classes('w-1/2'):
                    ui.label('Aesthetics Config').classes('font-bold')
                    ui.json_editor({'content': aesthetics._data}, select_on_change=False).classes('w-full h-96')

        # ================== Cookie Manager ==================
        with ui.tab_panel(cookie_tab):
            ui.label('Cookie Acquisition').classes('text-xl font-bold mb-4')
            
            with ui.row().classes('items-center gap-4 mb-4'):
                platforms = ["douyin", "bilibili", "kuaishou", "xhs", "videohao"]
                selected_platform = ui.select(platforms, value='douyin', label='Select Platform').classes('w-48')
                
                # Control Buttons
                start_btn = ui.button('Start Login Process', on_click=lambda: start_cookie_process()).classes('bg-green-500')
                stop_btn = ui.button('Stop Process', on_click=lambda: stop_cookie_process()).classes('bg-red-500').props('disabled')

            with ui.row().classes('w-full gap-4'):
                # Log Console
                with ui.card().classes('w-1/3 h-[500px] flex flex-col'):
                    ui.label('Execution Log').classes('font-bold mb-2')
                    log_view = ui.log().classes('w-full flex-grow bg-black text-green-400 font-mono text-sm p-2 overflow-y-auto')

                # QR Code / Screenshot
                with ui.card().classes('w-2/3 h-[500px] flex flex-col items-center justify-center bg-gray-50'):
                    ui.label('Login QR Code / Screenshot').classes('font-bold mb-2')
                    
                    # Image element with reactive source binding
                    # We use a timestamp to force reload
                    qr_image = ui.image(QR_IMG_URL).classes('max-h-full object-contain').style('display: none;')
                    no_image_label = ui.label('Waiting for screenshot...').classes('text-gray-400')

            # Process Management Logic
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
                            ["python3", str(script_path), "--platform", selected_platform.value],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            bufsize=1
                        )
                        process_container["proc"] = process
                        
                        for line in process.stdout:
                            log_view.push(line.strip())
                            
                        process.wait()
                    except Exception as e:
                        log_view.push(f"Error: {e}")
                    finally:
                        process_container["proc"] = None
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

            # Image Refresh Timer
            def refresh_image():
                if QR_CODE_PATH.exists():
                    # Only show if file is modified recently (e.g. within 10 seconds) or just always show if exists?
                    # Let's always show if exists, and force reload every second
                    qr_image.style('display: block;')
                    no_image_label.style('display: none;')
                    qr_image.set_source(f"{QR_CODE_PATH}?t={time.time()}")
                else:
                    qr_image.style('display: none;')
                    no_image_label.style('display: block;')

            ui.timer(1.0, refresh_image)

ui.run(title='Kimi_V Control', port=8080, reload=False, show=False)
