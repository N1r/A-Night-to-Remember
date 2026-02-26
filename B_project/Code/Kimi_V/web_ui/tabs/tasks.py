from nicegui import ui
import pandas as pd
from .utils import get_project_root

TASKS_PATH = get_project_root() / "1_pre_processing" / "storage" / "tasks" / "tasks_setting.xlsx"

def tasks_tab():
    with ui.column().classes('w-full h-full'):
        ui.markdown("## Task Management")
        
        grid = ui.aggrid({
            'columnDefs': [],
            'rowData': [],
            'rowSelection': 'multiple',
            'pagination': True,
            'paginationPageSize': 20
        }).classes('w-full h-96')

        def load_tasks():
            if TASKS_PATH.exists():
                try:
                    df = pd.read_excel(TASKS_PATH)
                    # Convert NaN to None for JSON serialization
                    df = df.where(pd.notnull(df), None)
                    
                    # Generate column definitions
                    cols = []
                    for col in df.columns:
                        cols.append({
                            'headerName': col, 
                            'field': col, 
                            'editable': True,
                            'sortable': True,
                            'filter': True,
                            'resizable': True
                        })
                    
                    grid.options['columnDefs'] = cols
                    grid.options['rowData'] = df.to_dict('records')
                    grid.update()
                    ui.notify(f"Loaded {len(df)} tasks successfully!", type='positive')
                except Exception as e:
                    ui.notify(f"Error loading tasks: {e}", type='negative')
            else:
                ui.notify("Tasks file not found!", type='warning')

        def save_tasks():
            try:
                # Get data from grid
                data = grid.options['rowData']
                if not data:
                    ui.notify("No data to save!", type='warning')
                    return
                
                df = pd.DataFrame(data)
                
                # Ensure directory exists
                TASKS_PATH.parent.mkdir(parents=True, exist_ok=True)
                
                df.to_excel(TASKS_PATH, index=False)
                ui.notify("Tasks saved successfully!", type='positive')
            except Exception as e:
                ui.notify(f"Error saving tasks: {e}", type='negative')

        def add_row():
             # Basic add row logic - adds empty row
             current_data = grid.options['rowData']
             if current_data:
                 # Copy keys from first row to ensure structure
                 new_row = {k: "" for k in current_data[0].keys()}
                 current_data.append(new_row)
                 grid.update()
             else:
                 ui.notify("Load data first before adding rows", type='warning')

        with ui.row().classes('w-full gap-4 mb-4'):
            ui.button('Reload Tasks', on_click=load_tasks).classes('bg-blue-500 text-white')
            ui.button('Save Changes', on_click=save_tasks).classes('bg-green-500 text-white')
            ui.button('Add Row', on_click=add_row).classes('bg-gray-500 text-white')

        # Load initially
        load_tasks()
