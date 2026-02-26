from nicegui import ui
from shared.domain import domain
from shared.aesthetics import aesthetics

def dashboard_tab():
    with ui.column().classes('w-full h-full'):
        ui.markdown("## Configuration Overview")
        
        with ui.row().classes('w-full gap-4'):
            with ui.card().classes('w-1/2'):
                ui.label('Domain Config').classes('font-bold')
                ui.json_editor({'content': domain.to_dict()}).classes('w-full h-96')
            
            with ui.card().classes('w-1/2'):
                ui.label('Aesthetics Config').classes('font-bold')
                ui.json_editor({'content': aesthetics.to_dict()}).classes('w-full h-96')
