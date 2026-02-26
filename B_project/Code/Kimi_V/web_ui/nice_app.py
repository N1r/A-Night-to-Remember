from nicegui import ui, app
import sys
from pathlib import Path

# Setup paths
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Import Tabs
from web_ui.tabs.dashboard import dashboard_tab
from web_ui.tabs.tasks import tasks_tab
from web_ui.tabs.config import config_tab
from web_ui.tabs.workflow import workflow_tab
from web_ui.tabs.cookies import cookie_tab
from shared.domain import domain

@ui.page('/')
def main_page():
    # Serve static files for QR code
    app.add_static_files('/output', str(PROJECT_ROOT / 'output'))

    # Header
    with ui.header().classes('bg-blue-600 items-center h-16'):
        with ui.row().classes('items-center gap-2'):
            ui.icon('movie_filter').classes('text-2xl text-white')
            ui.label(f'VideoLingo Control Panel - {domain.name}').classes('text-lg font-bold text-white')
        
        ui.space()
        ui.button(icon='refresh', on_click=lambda: ui.open('/')).props('flat round color=white')

    # Main Content with Tabs
    with ui.column().classes('w-full h-[calc(100vh-64px)] p-4'):
        with ui.tabs().classes('w-full bg-gray-100 rounded-t-lg') as tabs:
            dashboard = ui.tab('Dashboard', icon='dashboard')
            tasks = ui.tab('Tasks', icon='list')
            config = ui.tab('Config', icon='settings')
            workflow = ui.tab('Workflow', icon='play_circle')
            cookies = ui.tab('Cookies', icon='cookie')

        with ui.tab_panels(tabs, value=dashboard).classes('w-full h-full bg-white rounded-b-lg border p-4'):
            
            with ui.tab_panel(dashboard):
                dashboard_tab()
            
            with ui.tab_panel(tasks):
                tasks_tab()
                
            with ui.tab_panel(config):
                config_tab()
                
            with ui.tab_panel(workflow):
                workflow_tab()
                
            with ui.tab_panel(cookies):
                cookie_tab()

# Run the app
if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title='VideoLingo Pro', port=8080, reload=False, show=False)
