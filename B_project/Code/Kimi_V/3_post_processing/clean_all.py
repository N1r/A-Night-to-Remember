import shutil
from pathlib import Path
import sys
import os

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

from shared.paths import OUTPUT_DIR, READY_DIR, DEBUG_DIR, LOG_DIR

def clean_all():
    print("🧹 [Cleaning] Starting system cleanup...")
    
    # 1. Clean output folder
    if OUTPUT_DIR.exists():
        print(f"   - Cleaning output directory: {OUTPUT_DIR}")
        for item in OUTPUT_DIR.iterdir():
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            except Exception as e:
                print(f"     ⚠️ Failed to delete {item}: {e}")

    # 2. Clean ready_to_publish folder (partially or fully)
    # We might want to keep "done" folder, but usually clean means clean.
    # Let's preserve 'done' and 'failed' if they exist.
    if READY_DIR.exists():
        print(f"   - Cleaning ready_to_publish directory: {READY_DIR}")
        for item in READY_DIR.iterdir():
            if item.name in ["done", "failed"]:
                continue
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            except Exception as e:
                print(f"     ⚠️ Failed to delete {item}: {e}")

    # 3. Clean publish_logs inside output
    publish_logs = OUTPUT_DIR / "publish_logs"
    if publish_logs.exists():
        print(f"   - Cleaning publish logs: {publish_logs}")
        shutil.rmtree(publish_logs)

    # 4. Ensure essential subdirs exist again (though shared.paths does this)
    for d in [OUTPUT_DIR, DEBUG_DIR, LOG_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    print("✅ [Cleaning] System cleanup finished.")

if __name__ == "__main__":
    clean_all()
