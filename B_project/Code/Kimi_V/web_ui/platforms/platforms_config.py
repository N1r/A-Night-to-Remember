# -*- coding: utf-8 -*-
"""
platforms.py - 平台配置管理 v2.0
================================

为 WebUI 提供可扩展的平台配置系统。

架构说明：
---------
1. 基础配置 (BASE_PLATFORMS) - 定义所有平台的基础属性
2. 平台配置 (PLATFORM_CONFIG) - 定义每个平台的特定配置
3. 动态注册 - 支持运行时添加新平台

添加新平台步骤：
-------------
1. 在 BASE_PLATFORMS 中添加平台基础配置
2. 在 PLATFORM_CONFIG 中添加平台特定配置（URL、登录检测等）
3. 如果需要自定义脚本，在 cli_tools 中创建 get_<platform>.py
4. 重启 WebUI 即可

使用示例：
---------
```python
from web_ui.platforms import platforms

# 获取所有平台
all_platforms = platforms.get_all_platforms()

# 获取平台选项（用于UI）
options = platforms.get_platform_options()

# 获取平台名称
names = platforms.get_platform_names()
```

"""

from typing import Dict, Any, List
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()


def get_all_platforms() -> Dict[str, Dict[str, Any]]:
    """获取所有平台配置（合并基础配置和平台配置）"""
    all_platforms = {}
    
    for platform_key, base_config in BASE_PLATFORMS.items():
        platform_config = {
            **base_config,
            **PLATFORM_CONFIG.get(platform_key, {})
        }
        all_platforms[platform_key] = platform_config
    
    return all_platforms


def get_platform_names() -> Dict[str, str]:
    """获取平台名称映射 {key: name}"""
    return {
        key: config["name"]
        for key, config in get_all_platforms().items()
    }


def get_platform_options() -> List[Dict[str, Any]]:
    """获取NiceGUI Select组件使用的选项列表"""
    return [
        {
            "value": idx,
            "label": f"{config['icon']} {config['name']}"
        }
        for idx, (key, config) in enumerate(get_all_platforms().items())
    ]


def get_platform_by_key(platform_key: str) -> Dict[str, Any]:
    """根据key获取平台配置"""
    return get_all_platforms().get(platform_key)


# ==================== 基础平台配置 ====================
# 这些是每个平台必须的基础属性
BASE_PLATFORMS: Dict[str, Dict[str, Any]] = {
    # 抖音
    "douyin": {
        "name": "抖音",
        "icon": "🎵",
        "color": "#FE2C55",
        "gradient": "from-pink-500 to-red-500",
    },
    # B站
    "bilibili": {
        "name": "B站",
        "icon": "📺",
        "color": "#00A1D6",
        "gradient": "from-blue-400 to-cyan-500",
    },
    # 快手
    "kuaishou": {
        "name": "快手",
        "icon": "👋",
        "color": "#FF4906",
        "gradient": "from-orange-400 to-amber-500",
    },
    # 小红书
    "xhs": {
        "name": "小红书",
        "icon": "📕",
        "color": "#FF2442",
        "gradient": "from-red-500 to-pink-500",
    },
    # 微信视频号
    "tencent": {
        "name": "视频号",
        "icon": "📹",
        "color": "#07C160",
        "gradient": "from-green-500 to-emerald-600",
    },
}

# ==================== 平台特定配置 ====================
# 这些是每个平台特有的配置（URL、登录检测选择器等）
PLATFORM_CONFIG: Dict[str, Dict[str, Any]] = {
    "douyin": {
        "url": "https://creator.douyin.com/creator-micro/home",
        "login_text": "扫码登录",
        "logged_in_selectors": [
            ".avatar-container",
            ".header-right",
            "text=发布视频",
            "text=内容管理"
        ],
        "cli_script": "bk_get_cookies.py",
    },
    "bilibili": {
        "url": "https://member.bilibili.com/platform/home",
        "login_text": "扫码登录",
        "logged_in_selectors": [
            ".avatar-container",
            ".header-avatar-wrap",
            "text=投稿",
            "text=内容管理"
        ],
        "cli_script": "bk_get_cookies.py",
    },
    "kuaishou": {
        "url": "https://cp.kuaishou.com/article/publish/video",
        "login_text": "扫码登录",
        "logged_in_selectors": [
            ".avatar-wrapper",
            "text=发布作品"
        ],
        "cli_script": "bk_get_cookies.py",
    },
    "xhs": {
        "url": "https://creator.xiaohongshu.com/publish/publish",
        "login_text": "扫码登录",
        "logged_in_selectors": [
            ".avatar",
            "text=发布笔记"
        ],
        "cli_script": "bk_get_cookies.py",
    },
    "tencent": {
        "url": "https://channels.weixin.qq.com/platform/post/create",
        "login_text": "扫码登录",
        "logged_in_selectors": [
            ".finder-avatar",
            "text=发表视频",
            ".header-right",
            "发布作品"
        ],
        "cli_script": "bk_get_cookies.py",
    },
}

# ==================== 预定义平台（可选） ====================
# 这里列出其他可能需要支持的平台供参考
# 取消注释并添加到 BASE_PLATFORMS 和 PLATFORM_CONFIG 即可启用

PREDEFINED_PLATFORMS: Dict[str, Dict[str, Any]] = {
    # 优酷
    "youku": {
        "name": "优酷",
        "icon": "📹",
        "color": "#00AEE1",
        "gradient": "from-blue-400 to-cyan-500",
    },
    
    # 芒果TV
    "mangotv": {
        "name": "芒果TV",
        "icon": "Tv",
        "color": "#F64C4C",
        "gradient": "from-red-500 to-orange-500",
    },
    
    # YouTube
    "youtube": {
        "name": "YouTube",
        "icon": "▶️",
        "color": "#FF0000",
        "gradient": "from-red-600 to-red-800",
    },
    
    # 微博
    "weibo": {
        "name": "微博",
        "icon": "🐦",
        "color": "#E6162D",
        "gradient": "from-red-600 to-orange-600",
    },
    
    # 知乎
    "zhihu": {
        "name": "知乎",
        "icon": "🤔",
        "color": "#0084FF",
        "gradient": "from-blue-500 to-indigo-600",
    },
    
    # Bilibili直播
    "bilibili_live": {
        "name": "B站直播",
        "icon": "📺",
        "color": "#00A1D6",
        "gradient": "from-blue-400 to-cyan-500",
    },
    
    # 小红书企业号
    "xhs_business": {
        "name": "小红书企业",
        "icon": "🏢",
        "color": "#FF2442",
        "gradient": "from-red-500 to-pink-500",
    },
    
    # 抖音企业号
    "douyin_business": {
        "name": "抖音企业",
        "icon": "🏪",
        "color": "#FE2C55",
        "gradient": "from-pink-500 to-red-500",
    },
    # 测试平台
}

# ==================== 辅助函数 ====================

def print_available_platforms():
    """打印可用平台列表"""
    print("\n" + "=" * 60)
    print("📢 可用平台列表")
    print("=" * 60)
    
    for key, config in get_all_platforms().items():
        name = config["name"]
        icon = config["icon"]
        color = config["color"]
        gradient = config.get("gradient", "no-gradient")
        url = config.get("url", "N/A")
        
        print(f"  {icon} {name}")
        print(f"    平台键: {key}")
        print(f"    颜色: {color}")
        print(f"    渐变: {gradient}")
        if url != "N/A":
            print(f"    URL: {url}")
        print()

if __name__ == "__main__":
    print_available_platforms()
