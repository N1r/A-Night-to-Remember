import os
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from pathlib import Path
import sys

# Constants
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.absolute()
SETTINGS_FILE = str(PROJECT_ROOT / 'storage' / 'tasks' / 'tasks_setting.xlsx')
INPUT_FOLDER = str(PROJECT_ROOT / 'storage' / 'input')
VALID_DUBBING_VALUES = [0, 1]

console = Console()

def check_settings():
    os.makedirs(INPUT_FOLDER, exist_ok=True)
    if not os.path.exists(SETTINGS_FILE):
        # Create an empty template if it doesn't exist
        df = pd.DataFrame(columns=[
            'Score', 'Video File', 'title', 'rawtext', 'translated_text', 
            'Publish Date', 'Replies', 'Reposts', 'viewCount', 
            'channel_name', 'duration', 'Source Language', 
            'Target Language', 'Dubbing', 'Status'
        ])
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        df.to_excel(SETTINGS_FILE, index=False)
        console.print(f"[yellow]Created template task list at {SETTINGS_FILE}[/yellow]")
        return False

    df = pd.read_excel(SETTINGS_FILE)
    if df.empty:
        console.print("[yellow]Task list is empty.[/yellow]")
        return False

    input_files = set(os.listdir(INPUT_FOLDER))
    excel_files = set(df['Video File'].tolist())
    files_not_in_excel = {f for f in input_files if f not in excel_files and not f.startswith('.')}

    all_passed = True
    local_video_tasks = 0
    url_tasks = 0

    if files_not_in_excel:
        console.print(Panel(
            "\n".join([f"- {file}" for file in files_not_in_excel]),
            title="[bold yellow]Warning: Files in input folder not mentioned in Excel sheet",
            expand=False
        ))
        # Not a fatal error, just a warning
        # all_passed = False 

    for index, row in df.iterrows():
        video_file = str(row['Video File'])
        if pd.isna(video_file) or not video_file.strip():
            continue
            
        dubbing = row['Dubbing']

        if video_file.startswith('http'):
            url_tasks += 1
        elif os.path.isfile(os.path.join(INPUT_FOLDER, video_file)):
            local_video_tasks += 1
        else:
            # Check if status is already done, if so, skip error
            if row.get('Status') == 'Done':
                continue
            console.print(Panel(f"Invalid video file or URL 「{video_file}」", title=f"[bold red]Error in row {index + 2}", expand=False))
            all_passed = False

        if not pd.isna(dubbing):
            try:
                if int(dubbing) not in VALID_DUBBING_VALUES:
                    console.print(Panel(f"Invalid dubbing value 「{dubbing}」", title=f"[bold red]Error in row {index + 2}", expand=False))
                    all_passed = False
            except ValueError:
                all_passed = False

    if all_passed and (local_video_tasks + url_tasks > 0):
        console.print(Panel(f"✅ All settings passed the check!\nDetected {local_video_tasks} local video tasks and {url_tasks} URL tasks.", title="[bold green]Success", expand=False))

    return all_passed


if __name__ == "__main__":  
    check_settings()