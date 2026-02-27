# -*- coding: utf-8 -*-
"""
platforms.py - 平台配置管理 v1.0
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

运行方式：
    .venv_webui/bin/python -m web_ui.platforms

"""

from web_ui.platforms.platforms_config import (
    get_all_platforms,
    get_platform_names,
    get_platform_options,
    get_platform_by_key,
    print_available_platforms,
    BASE_PLATFORMS,
    PLATFORM_CONFIG,
    PREDEFINED_PLATFORMS,
    PROJECT_ROOT
)

__all__ = [
    'get_all_platforms',
    'get_platform_names',
    'get_platform_options',
    'get_platform_by_key',
    'print_available_platforms',
    'BASE_PLATFORMS',
    'PLATFORM_CONFIG',
    'PREDEFINED_PLATFORMS',
    'PROJECT_ROOT'
]
