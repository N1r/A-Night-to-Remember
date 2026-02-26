import os
import sys
import gc
import pandas as pd
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
import time

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.absolute()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

# These must be imported after sys.path is set
from modules.common.utils_batch.settings_check import check_settings
from modules.common.utils_batch.video_processor import process_video
from core.utils.config_utils import load_key, update_key

console = Console()

SETTINGS_FILE = str(PROJECT_ROOT / 'storage' / 'tasks' / 'tasks_setting.xlsx')

def record_and_update_config(source_language, target_language):
    original_source_lang = load_key('whisper.language')
    original_target_lang = load_key('target_language')
    
    if source_language and not pd.isna(source_language):
        update_key('whisper.language', source_language)
    if target_language and not pd.isna(target_language):
        update_key('target_language', target_language)
    
    return original_source_lang, original_target_lang

def process_batch():
    if not check_settings():
        console.print("[bold red]Settings check failed, please check your task list and input files.[/bold red]")
        return False

    df = pd.read_excel(SETTINGS_FILE)
    processed = 0

    for index, row in df.iterrows():
        status_val = row.get('Status')
        if pd.isna(status_val) or str(status_val).strip() == "" or "Error" in str(status_val):
            total_tasks = len(df)
            video_file = str(row['Video File'])
            
            console.print(Panel(f"Now processing task: {video_file}\nTask {index + 1}/{total_tasks}", 
                             title="[bold blue]Current Task", expand=False))
            
            source_language = row.get('Source Language')
            target_language = row.get('Target Language')
            
            original_source_lang, original_target_lang = record_and_update_config(source_language, target_language)
            
            try:
                dubbing = 0 if pd.isna(row.get('Dubbing')) else int(row['Dubbing'])
                status, error_step, error_message = process_video(video_file, dubbing, False)
                status_msg = "Done" if status else f"Error: {error_step} - {error_message}"
            except Exception as e:
                status_msg = f"Error: Unhandled exception - {str(e)}"
                console.print(f"[bold red]Error processing {video_file}: {status_msg}")
            finally:
                update_key('whisper.language', original_source_lang)
                update_key('target_language', original_target_lang)

                df.at[index, 'Status'] = status_msg
                df.to_excel(SETTINGS_FILE, index=False)
                
                gc.collect()
                time.sleep(1)
                processed += 1
                # Optional safety break for testing
                # if processed >= 3:
                #    break
        else:
            console.print(f"Skipping task: {row['Video File']} - Status: {status_val}")

    console.print(Panel("All available tasks processed!\nResults are in the `output/processed` folder!", 
                       title="[bold green]Batch Processing Complete", expand=False))
    return True

if __name__ == "__main__":
    process_batch()
