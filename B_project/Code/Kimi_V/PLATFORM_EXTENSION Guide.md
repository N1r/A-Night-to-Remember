# 📋 平台扩展指南

本指南介绍如何为 Cookie 管理 WebUI 添加新平台支持。

## 🏗️ 架构概览

```
web_ui/
└── platforms/
    ├── __init__.py          # 导出所有平台功能
    ├── platforms_config.py  # ← 主配置文件（修改这个）
    └── platform_manager.py  # 平台管理器（命令行工具）
```

## 🚀 添加新平台

### 方法 1：修改配置文件（推荐）

直接编辑 `web_ui/platforms/platforms_config.py`：

#### 步骤 1：添加基础配置

在 `BASE_PLATFORMS` 字典中添加平台基础属性：

```python
BASE_PLATFORMS: Dict[str, Dict[str, Any]] = {
    # ... 现有平台 ...
    "youku": {  # ← 平台键（英文，小写，下划线）
        "name": "优酷",  # ← 显示名称
        "icon": "📹",    # ← Emoji 图标
        "color": "#00AEE1",  # ← 品牌色（十六进制）
        "gradient": "from-blue-400 to-cyan-500",  # ← 渐变主题
    },
}
```

#### 步骤 2：添加平台特定配置

在 `PLATFORM_CONFIG` 字典中添加平台特定配置：

```python
PLATFORM_CONFIG: Dict[str, Dict[str, Any]] = {
    # ... 现有平台配置 ...
    "youku": {
        "url": "https://mgj.iqiyi.com/",  # ← 登录页面URL
        "login_text": "扫码登录",
        "logged_in_selectors": [  # ← 登录检测选择器
            ".user-info",
            ".avatar",
            "text=个人中心"
        ],
        "cli_script": "bk_get_cookies.py",  # ← CLI脚本（可选）
    },
}
```

#### 步骤 3：重启 WebUI

```bash
pkill -f simple_cookie
.venv_webui/bin/python simple_cookie_manager.py
```

### 方法 2：完整扩展（高级）

如果需要自定义登录逻辑，可以创建专用脚本：

#### 步骤 1：创建 CLI 脚本

在 `1_pre_processing/cli_tools/` 创建新脚本：

```python
# 1_pre_processing/cli_tools/get_youku.py
import asyncio
from playwright.async_api import async_playwright

PLATFORM_NAME = "youku"
URL = "https://mgj.iqiyi.com/"
QR_CODE_PATH = Path(__file__).parent.parent.parent / "output" / "login_qrcode.png"

async def login():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        await page.goto(URL)
        
        # 等待二维码出现
        await page.wait_for_selector(".qrcode-img")
        
        # 截图二维码
        await page.screenshot(path=str(QR_CODE_PATH), full_page=True)
        
        # 等待登录完成
        await page.wait_for_selector(".user-info")
        
        # 保存 Cookie
        cookies = await page.context.cookies()
        # ... 保存逻辑 ...
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(login())
```

#### 步骤 2：配置平台脚本

```python
PLATFORM_CONFIG: Dict[str, Dict[str, Any]] = {
    "youku": {
        "url": "https://mgj.iqiyi.com/",
        "cli_script": "get_youku.py",  # ← 使用自定义脚本
        # ...
    },
}
```

## 📝 预定义平台模板

以下是其他平台的配置模板，可取消注释添加：

```python
PREDEFINED_PLATFORMS: Dict[str, Dict[str, Any]] = {
    # 优酷
    "youku": {
        "name": "优酷",
        "icon": "📹",
        "color": "#00AEE1",
        "gradient": "from-blue-400 to-cyan-500",
        "url": "https://mgj.iqiyi.com/",
        "logged_in_selectors": [".user-info"],
        "cli_script": "get_youku.py",
    },
    
    # 芒果TV
    "mangotv": {
        "name": "芒果TV",
        "icon": "Tv",
        "color": "#F64C4C",
        "gradient": "from-red-500 to-orange-500",
        "url": "https://www.mgtv.com/",
        "logged_in_selectors": [".user-info"],
        "cli_script": "get_mangotv.py",
    },
    
    # YouTube
    "youtube": {
        "name": "YouTube",
        "icon": "▶️",
        "color": "#FF0000",
        "gradient": "from-red-600 to-red-800",
        "url": "https://studio.youtube.com",
        "logged_in_selectors": ["ytcp-weblna-profile-button"],
        "cli_script": "get_youtube.py",
    },
    
    # 微博
    "weibo": {
        "name": "微博",
        "icon": "🐦",
        "color": "#E6162D",
        "gradient": "from-red-600 to-orange-600",
        "url": "https://weibo.com",
        "logged_in_selectors": [".avatar_link"],
        "cli_script": "get_weibo.py",
    },
    
    # 知乎
    "zhihu": {
        "name": "知乎",
        "icon": "🤔",
        "color": "#0084FF",
        "gradient": "from-blue-500 to-indigo-600",
        "url": "https://zhuanlan.zhihu.com",
        "logged_in_selectors": [".UserAvatar.middleware-avatar"],
        "cli_script": "get_zhihu.py",
    },
    
    # Bilibili直播
    "bilibili_live": {
        "name": "B站直播",
        "icon": "📺",
        "color": "#00A1D6",
        "gradient": "from-blue-400 to-cyan-500",
        "url": "https://live.bilibili.com",
        "logged_in_selectors": [".user-info"],
        "cli_script": "bk_get_cookies.py",  # 可共用已有脚本
    },
    
    # 小红书企业号
    "xhs_business": {
        "name": "小红书企业",
        "icon": "🏢",
        "color": "#FF2442",
        "gradient": "from-red-500 to-pink-500",
        "url": "https://open.xiaohongshu.com",
        "logged_in_selectors": [".user-info"],
        "cli_script": "get_xhs_business.py",
    },
    
    # 抖音企业号
    "douyin_business": {
        "name": "抖音企业",
        "icon": "🏪",
        "color": "#FE2C55",
        "gradient": "from-pink-500 to-red-500",
        "url": "https:// equality.douyin.com/",
        "logged_in_selectors": [".user-info"],
        "cli_script": "get_douyin_business.py",
    },
}
```

## 🔍 验证平台配置

添加平台后，使用管理器验证：

```bash
# 列出所有平台
.venv_webui/bin/python web_ui/platforms/platform_manager.py --list

# 显示平台状态
.venv_webui/bin/python web_ui/platforms/platform_manager.py --status

# 测试平台
.venv_webui/bin/python web_ui/platforms/platform_manager.py --test douyin

# 验证配置
.venv_webui/bin/python web_ui/platforms/platform_manager.py --validate douyin
```

## 🎨 CSS 渐变配色方案

以下是一些常用的 Tailwind CSS 渐变组合：

```python
# 红色系
"gradient": "from-red-500 to-pink-500"
"gradient": "from-red-600 to-orange-600"

# 蓝色系
"gradient": "from-blue-400 to-cyan-500"
"gradient": "from-blue-500 to-indigo-600"

# 绿色系
"gradient": "from-green-500 to-emerald-600"
"gradient": "from-emerald-400 to-teal-500"

# 橙色系
"gradient": "from-orange-400 to-amber-500"
"gradient": "from-orange-500 to-red-500"

# 紫色系
"gradient": "from-purple-500 to-pink-500"
"gradient": "from-indigo-500 to-purple-500"

# 黑色系
"gradient": "from-gray-700 to-gray-900"
"gradient": "from-black to-gray-800"
```

## 📌 注意事项

1. **平台键命名**：使用小写字母和下划线（如 `youku`, `bilibili_live`）
2. **图标选择**：使用常见 Emoji（✅ 推荐）
3. **URL 地址**：使用创作者后台或登录页面
4. **选择器测试**：确保 CSS 选择器在实际页面中存在
5. **CLI 脚本**：可选，不配置则使用默认脚本
6. **重启服务**：修改配置后需重启 WebUI

## 🆘 常见问题

### Q1: 添加平台后不显示？
**A:** 检查 `PLATFORMS` 是否正确导入，重启 WebUI

### Q2: 二维码无法生成？
**A:** 检查平台 URL 是否正确，选择器是否匹配

### Q3: 登录验证失败？
**A:** 更新 `logged_in_selectors`，确保选择器在页面中存在

### Q4: 如何调试？
**A:** 使用平台管理器测试：

```bash
python web_ui/platforms/platform_manager.py --test youku --json
```

## 📖 相关文件

- `web_ui/platforms/platforms_config.py` - 平台配置
- `web_ui/platforms/platform_manager.py` - 平台管理器
- `web_ui/tabs/cookies.py` - Cookie 管理 UI
- `1_pre_processing/cli_tools/bk_get_cookies.py` - CLI 登录脚本

---

**最后更新**: 2026-02-27
