#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
add_platform.py - 快速添加平台脚本
================================

使用方法：
    python web_ui/platforms/add_platform.py [平台键] [平台名称] [图标] [颜色]

示例：
    python web_ui/platforms/add_platform.py youku 优酷 📹 #00AEE1

或者交互式添加：
    python web_ui/platforms/add_platform.py

"""

import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
CONFIG_FILE = PROJECT_ROOT / "web_ui" / "platforms" / "platforms_config.py"

def read_config():
    """读取配置文件"""
    with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
        return f.read()

def write_config(content):
    """写入配置文件"""
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        f.write(content)

def add_platform_to_section(content, section_name, platform_key, platform_data):
    """在配置文件中添加平台到指定段落"""
    import re
    
    # 构建平台条目
    icon = platform_data.get("icon", " Plattform")
    color = platform_data.get("color", "#888888")
    gradient = platform_data.get("gradient", "from-gray-400 to-gray-600")
    
    platform_entry = f'''    "{platform_key}": {{
        "name": "{platform_data.get("name", platform_key)}",
        "icon": "{icon}",
        "color": "{color}",
        "gradient": "{gradient}",
    }},
'''
    
    # 查找段落
    pattern = rf'({section_name}:\s*Dict\[.*?\]\s*=\s*\{{)(.*?)(\n\}})'
    match = re.search(pattern, content, re.DOTALL)
    
    if match:
        # 插入到段落末尾，但在最后一个条目之后
        section_content = match.group(2)
        
        # 检查平台是否已存在
        if f'"{platform_key}":' in section_content:
            print(f"❌ 平台 '{platform_key}' 已存在")
            return content
        
        # 在末尾插入（在最后一个 }; 之前）
        lines = section_content.rstrip().split('\n')
        
        # 找到最后一个有效的平台条目
        insert_pos = len(lines)
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip() and not lines[i].strip().startswith('#'):
                insert_pos = i + 1
                break
        
        lines.insert(insert_pos, platform_entry.rstrip())
        
        # 重建段落
        new_section = '\n'.join(lines)
        new_content = content[:match.start(2)] + new_section + content[match.end(2):]
        
        return new_content
    else:
        print(f"⚠️  未找到段落: {section_name}")
        return content

def add_platform(platform_key, name, icon, color, gradient=None):
    """添加平台到配置"""
    
    if gradient is None:
        # 根据颜色生成默认渐变
        if "red" in color.lower():
            gradient = "from-red-500 to-pink-500"
        elif "blue" in color.lower():
            gradient = "from-blue-400 to-cyan-500"
        elif "green" in color.lower():
            gradient = "from-green-500 to-emerald-600"
        elif "orange" in color.lower():
            gradient = "from-orange-400 to-amber-500"
        else:
            gradient = "from-gray-400 to-gray-600"
    
    content = read_config()
    
    # 检查平台是否已存在
    if f'"{platform_key}":' in content:
        print(f"❌ 平台 '{platform_key}' 已存在")
        return False
    
    # 构建平台数据
    platform_data = {
        "name": name,
        "icon": icon,
        "color": color,
        "gradient": gradient
    }
    
    # 添加到 BASE_PLATFORMS
    content = add_platform_to_section(content, "BASE_PLATFORMS", platform_key, platform_data)
    
    # 添加到 PLATFORM_CONFIG（仅基础配置，不包含URL等）
    platform_config_entry = f'''    "{platform_key}": {{
        "url": "https://",
        "login_text": "扫码登录",
        "logged_in_selectors": [
            ".user-info"
        ],
        "cli_script": "bk_get_cookies.py",
    }},
'''
    
    # 查找 PLATFORM_CONFIG 并插入
    import re
    pattern = rf'(PLATFORM_CONFIG:\s*Dict\[.*?\]\s*=\s*\{{)(.*?)(\n\}})'
    match = re.search(pattern, content, re.DOTALL)
    
    if match:
        section_content = match.group(2)
        if f'"{platform_key}":' not in section_content:
            lines = section_content.rstrip().split('\n')
            insert_pos = len(lines)
            for i in range(len(lines) - 1, -1, -1):
                if lines[i].strip() and not lines[i].strip().startswith('#'):
                    insert_pos = i + 1
                    break
            lines.insert(insert_pos, platform_config_entry.rstrip())
            new_section = '\n'.join(lines)
            content = content[:match.start(2)] + new_section + content[match.end(2):]
    
    # 添加到 PREDEFINED_PLATFORMS（注释状态）
    predefined_entry = f'''    # {name}
    "{platform_key}": {{
        "name": "{name}",
        "icon": "{icon}",
        "color": "{color}",
        "gradient": "{gradient}",
    }},
'''
    
    pattern = rf'(PREDEFINED_PLATFORMS:\s*Dict\[.*?\]\s*=\s*\{{)(.*?)(\n\}})'
    match = re.search(pattern, content, re.DOTALL)
    
    if match:
        section_content = match.group(2)
        lines = section_content.rstrip().split('\n')
        insert_pos = len(lines)
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].strip() and not lines[i].strip().startswith('#'):
                insert_pos = i + 1
                break
        lines.insert(insert_pos, predefined_entry.rstrip())
        new_section = '\n'.join(lines)
        content = content[:match.start(2)] + new_section + content[match.end(2):]
    
    # 写入文件
    write_config(content)
    
    print(f"✅ 成功添加平台 '{platform_key}'")
    print(f"   名称: {name}")
    print(f"   图标: {icon}")
    print(f"   颜色: {color}")
    print(f"   渐变: {gradient}")
    print()
    print("📝 下一步：")
    print(f"   1. 编辑 {CONFIG_FILE}")
    print(f"   2. 为平台配置 URL 和登录检测选择器")
    print(f"   3. 如果需要，配置 cli_script")
    print(f"   4. 重启 WebUI")
    
    return True

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="快速添加平台到配置"
    )
    parser.add_argument("key", nargs="?", help="平台键（英文，小写）")
    parser.add_argument("name", nargs="?", help="平台名称")
    parser.add_argument("icon", nargs="?", help="平台图标（Emoji）")
    parser.add_argument("color", nargs="?", help="品牌色（十六进制）")
    parser.add_argument("--gradient", help="CSS渐变（可选）")
    
    args = parser.parse_args()
    
    # 交互式输入
    if not all([args.key, args.name, args.icon, args.color]):
        print("=== 快速添加平台 ===")
        print()
        args.key = input("平台键（如：youku, bilibili）: ").strip()
        args.name = input("平台名称（如：优酷, B站）: ").strip()
        args.icon = input("平台图标（Emoji，如：📹, 📺）: ").strip()
        args.color = input("品牌色（十六进制，如：#00AEE1）: ").strip()
        args.gradient = input("CSS渐变（可选，直接回车使用默认）: ").strip() or None
    
    # 验证输入
    if not args.key or not args.name or not args.icon or not args.color:
        print("❌ 缺少必要参数")
        parser.print_help()
        sys.exit(1)
    
    # 转换颜色格式
    if not args.color.startswith("#"):
        args.color = "#" + args.color
    
    # 添加平台
    success = add_platform(args.key, args.name, args.icon, args.color, args.gradient)
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
