# 📊 平台扩展框架使用指南

## 🚀 快速添加新平台

### 方法 1：使用 CLI 工具（推荐）

```bash
# 交互式添加
.venv_webui/bin/python web_ui/platforms/add_platform.py

# 命令行添加
.venv_webui/bin/python web_ui/platforms/add_platform.py \
    youku \
    "优酷" \
    📹 \
    "#00AEE1" \
    --gradient "from-blue-400 to-cyan-500"
```

### 方法 2：手动编辑配置文件

编辑 `web_ui/platforms/platforms_config.py`：

```python
# 1. 在 BASE_PLATFORMS 中添加
BASE_PLATFORMS = {
    # ... 现有平台 ...
    "youku": {
        "name": "优酷",
        "icon": "📹",
        "color": "#00AEE1",
        "gradient": "from-blue-400 to-cyan-500",
    },
}

# 2. 在 PLATFORM_CONFIG 中添加
PLATFORM_CONFIG = {
    # ... 现有配置 ...
    "youku": {
        "url": "https://mgj.iqiyi.com/",
        "login_text": "扫码登录",
        "logged_in_selectors": [".user-info"],
        "cli_script": "bk_get_cookies.py",
    },
}
```

### 方法 3：完整自定义脚本

1. 在 `1_pre_processing/cli_tools/` 创建脚本 `get_youku.py`
2. 配置 `cli_script` 指向新脚本
3. 重启 WebUI

## 📋 可用工具

### 平台管理器 CLI

```bash
# 列出所有平台
.venv_webui/bin/python web_ui/platforms/platform_manager_cli.py --list

# 显示状态
.venv_webui/bin/python web_ui/platforms/platform_manager_cli.py --status

# 测试平台
.venv_webui/bin/python web_ui/platforms/platform_manager_cli.py --test youku

# JSON 输出
.venv_webui/bin/python web_ui/platforms/platform_manager_cli.py --json
```

### 预定义平台模板

配置文件中包含以下预定义平台（已注释）：

- ✅ 抖音、B站、快手、小红书、视频号（已启用）
- ⏸️ 优酷、芒果TV、YouTube、微博、知乎（已预定义）
- ⏸️ B站直播、小红书企业、抖音企业（已预定义）

取消注释并添加到 `BASE_PLATFORMS` 和 `PLATFORM_CONFIG` 即可启用。

## 📐 平台配置说明

### 必需字段（BASE_PLATFORMS）

```python
"platform_key": {
    "name": "显示名称",        # 必需
    "icon": "Emoji图标",       # 必需
    "color": "#十六进制颜色",   # 必需
    "gradient": "CSS渐变",    # 必需
}
```

### 可选字段（PLATFORM_CONFIG）

```python
"platform_key": {
    "url": "https://登录页面URL",           # 默认: 空
    "login_text": "扫码登录",                # 默认: "扫码登录"
    "logged_in_selectors": [".选择器1"],    # 默认: []
    "cli_script": "cli脚本名.py",            # 默认: "bk_get_cookies.py"
}
```

## 🎨 渐变配色方案

推荐的 Tailwind CSS 渐变：

```python
# 红色系
"from-red-500 to-pink-500"
"from-red-600 to-orange-600"

# 蓝色系
"from-blue-400 to-cyan-500"
"from-blue-500 to-indigo-600"

# 绿色系
"from-green-500 to-emerald-600"
"from-emerald-400 to-teal-500"

# 橙色系
"from-orange-400 to-amber-500"

# 紫色系
"from-purple-500 to-pink-500"
```

## 🔄 重启 WebUI

添加平台后：

```bash
pkill -f simple_cookie
.venv_webui/bin/python simple_cookie_manager.py
```

## 📄 文件结构

```
web_ui/platforms/
├── __init__.py               # 导出平台功能
├── platforms_config.py       # ← 主配置文件
├── platform_manager.py       # 平台管理器（旧版）
├── platform_manager_cli.py   # CLI 工具（推荐）
└── add_platform.py           # 快速添加脚本
```

## 📖 完整文档

详见 `PLATFORM_EXTENSION Guide.md`（英文版）
