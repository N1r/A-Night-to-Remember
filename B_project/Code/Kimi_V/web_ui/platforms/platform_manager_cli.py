#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
platform_manager_cli.py - 平台管理器 CLI 工具
============================================

命令行工具，用于管理平台配置。

使用方法：
    python web_ui/platforms/platform_manager_cli.py [选项]

选项：
    --list        列出所有平台
    --status      显示平台状态
    --test <key>  测试指定平台
    --json        以JSON格式输出

运行方式：
    .venv_webui/bin/python web_ui/platforms/platform_manager_cli.py

"""

import sys
import os
import json
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()


def load_platforms_config():
    """加载平台配置"""
    try:
        from web_ui.platforms import (
            get_all_platforms,
            get_platform_names,
            BASE_PLATFORMS,
            PLATFORM_CONFIG
        )
        return {
            "all_platforms": get_all_platforms(),
            "platform_names": get_platform_names(),
            "base": BASE_PLATFORMS,
            "specific": PLATFORM_CONFIG
        }
    except Exception as e:
        console.print(f"[red]❌ 加载配置失败: {e}[/red]")
        return None


def print_platform_status(platforms_data):
    """打印平台状态"""
    if not platforms_data:
        return
    
    table = Table(
        title="📋 平台配置状态",
        box=box.ROUNDED,
        show_lines=True
    )
    
    table.add_column("平台", style="cyan")
    table.add_column("键名", style="magenta")
    table.add_column("颜色", style="green")
    table.add_column("URL", style="yellow")
    table.add_column("状态", style="green")
    
    all_platforms = platforms_data["all_platforms"]
    specific_config = platforms_data.get("specific", {})
    
    for key, platform in all_platforms.items():
        name = platform.get("name", key)
        icon = platform.get("icon", " Plattform")
        color = platform.get("color", "#888888")
        url = platform.get("url", "N/A")
        cli_script = specific_config.get(key, {}).get("cli_script", "N/A")
        
        # 检查必要字段
        required_fields = ["name", "icon", "color", "gradient"]
        has_all_fields = all(f in platform for f in required_fields)
        status = "✅" if has_all_fields else "❌"
        
        table.add_row(
            f"{icon} {name}",
            key,
            color,
            url,
            status
        )
    
    console.print(table)


def print_available_platforms(platforms_data):
    """打印可用平台列表"""
    if not platforms_data:
        return
    
    table = Table(
        title="📢 可用平台列表",
        box=box.ROUNDED
    )
    
    table.add_column("平台", style="cyan")
    table.add_column("键名", style="magenta")
    table.add_column("颜色", style="green")
    table.add_column("URL", style="yellow")
    
    all_platforms = platforms_data["all_platforms"]
    
    for key, platform in all_platforms.items():
        name = platform.get("name", key)
        icon = platform.get("icon", " Plattform")
        color = platform.get("color", "#888888")
        url = platform.get("url", "N/A")
        
        table.add_row(
            f"{icon} {name}",
            key,
            color,
            url
        )
    
    console.print(table)


def test_platform(platforms_data, key):
    """测试指定平台"""
    if not platforms_data:
        return False
    
    all_platforms = platforms_data["all_platforms"]
    
    if key not in all_platforms:
        console.print(f"[red]❌ 平台 '{key}' 不存在[/red]")
        return False
    
    platform = all_platforms[key]
    
    # 检查必要字段
    required_fields = ["name", "icon", "color", "gradient"]
    missing_fields = [f for f in required_fields if f not in platform]
    
    if missing_fields:
        console.print(f"[red]❌ 平台 '{key}' 配置不完整[/red]")
        console.print(f"   缺少字段: {', '.join(missing_fields)}")
        return False
    
    console.print(f"[green]✅ 平台 '{key}' 配置有效[/green]")
    console.print(f"   名称: {platform.get('name')}")
    console.print(f"   URL: {platform.get('url', 'N/A')}")
    console.print(f"   图标: {platform.get('icon')}")
    console.print(f"   颜色: {platform.get('color')}")
    
    return True


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="平台管理器 - 管理 Cookie WebUI 平台配置"
    )
    parser.add_argument(
        "--list", 
        action="store_true", 
        help="列出所有可用平台"
    )
    parser.add_argument(
        "--status", 
        action="store_true", 
        help="显示平台配置状态"
    )
    parser.add_argument(
        "--test", 
        type=str, 
        metavar="KEY",
        help="测试指定平台配置"
    )
    parser.add_argument(
        "--json", 
        action="store_true", 
        help="以JSON格式输出"
    )
    
    args = parser.parse_args()
    
    # 加载配置
    platforms_data = load_platforms_config()
    
    if not platforms_data:
        sys.exit(1)
    
    if args.json:
        # JSON 输出格式
        output = {
            "platforms": {
                key: {
                    "name": p.get("name"),
                    "icon": p.get("icon"),
                    "color": p.get("color"),
                    "url": p.get("url")
                }
                for key, p in platforms_data["all_platforms"].items()
            }
        }
        print(json.dumps(output, indent=2, ensure_ascii=False))
    
    elif args.test:
        success = test_platform(platforms_data, args.test)
        sys.exit(0 if success else 1)
    
    elif args.list:
        print_available_platforms(platforms_data)
    
    elif args.status:
        print_platform_status(platforms_data)
        print_available_platforms(platforms_data)
    
    else:
        # 默认显示状态
        print_platform_status(platforms_data)
        print_available_platforms(platforms_data)


if __name__ == "__main__":
    main()
