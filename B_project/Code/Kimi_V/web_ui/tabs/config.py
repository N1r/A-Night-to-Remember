from nicegui import ui
import yaml
from .utils import get_project_root

CONFIG_PATH = get_project_root() / "configs" / "config.yaml"

def config_tab():
    with ui.column().classes('w-full h-full'):
        ui.markdown("## Configuration Editor")
        
        editor = ui.codemirror('', language='yaml').classes('w-full h-96 border rounded')
        
        def load_config():
            if CONFIG_PATH.exists():
                with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                    content = f.read()
                    editor.value = content
            else:
                ui.notify("Config file not found!", type='negative')

        def save_config():
            try:
                # Validate YAML format
                yaml.safe_load(editor.value)
                with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                    f.write(editor.value)
                ui.notify("Configuration saved successfully!", type='positive')
            except yaml.YAMLError as e:
                ui.notify(f"Invalid YAML format: {e}", type='negative')
            except Exception as e:
                ui.notify(f"Error saving config: {e}", type='negative')

        with ui.row().classes('w-full gap-4'):
            ui.button('Load Config', on_click=load_config).classes('bg-blue-500 text-white')
            ui.button('Save Config', on_click=save_config).classes('bg-green-500 text-white')
        
        # Load initially
        load_config()
