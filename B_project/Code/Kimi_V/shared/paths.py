"""
shared/paths.py
---------------
全局路径定义 — 整个项目唯一的路径真相来源。

其他模块一律从这里导入路径，禁止各自定义 PROJECT_ROOT。

使用方式：
    from shared.paths import PROJECT_ROOT, STORAGE_DIR, ARCHIVES_DIR
"""

from pathlib import Path

# ==================== 项目根目录 ====================
# Kimi_V/ 的绝对路径（通过本文件位置向上一级推导）
PROJECT_ROOT = Path(__file__).parent.parent.absolute()

# ==================== 一级目录 ====================
CONFIGS_DIR = PROJECT_ROOT / "configs"
STORAGE_DIR = PROJECT_ROOT / "storage"
OUTPUT_DIR  = PROJECT_ROOT / "output"

# ==================== 存储子目录 ====================
COOKIES_DIR     = STORAGE_DIR / "cookies"
BROWSER_DATA    = STORAGE_DIR / "browser_data"
TASKS_DIR       = STORAGE_DIR / "tasks"
READY_DIR       = STORAGE_DIR / "ready_to_publish"
ARCHIVES_DIR    = PROJECT_ROOT / "archives"

# ==================== 存储文件 ====================
TASKS_EXCEL     = TASKS_DIR / "tasks_setting.xlsx"
VISITED_LOG     = TASKS_DIR / "visited_videos.json"
PUBLISH_HISTORY = TASKS_DIR / "publish_history.json"
DAILY_QUOTA     = TASKS_DIR / "daily_quota.json"
CONFIG_YAML     = CONFIGS_DIR / "config.yaml"

# ==================== 处理阶段目录 ====================
PRE_PROCESSING  = PROJECT_ROOT / "1_pre_processing"
MID_PROCESSING  = PROJECT_ROOT / "2_mid_processing"
POST_PROCESSING = PROJECT_ROOT / "3_post_processing"

# ==================== 媒体资源 ====================
STEALTH_JS      = POST_PROCESSING / "media" / "common" / "stealth.min.js"
LOG_DIR         = OUTPUT_DIR / "debug_screenshots"
DEBUG_DIR       = OUTPUT_DIR / "debug"

# ==================== 确保关键目录存在 ====================
for d in [COOKIES_DIR, BROWSER_DATA, TASKS_DIR, READY_DIR, ARCHIVES_DIR,
          OUTPUT_DIR, LOG_DIR, DEBUG_DIR]:
    d.mkdir(parents=True, exist_ok=True)
