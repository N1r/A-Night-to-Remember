# -*- coding: utf-8 -*-
"""
platform_manager.py - 平台管理器 v1.0
====================================

提供平台配置的动态管理和验证功能。

功能特性：
---------
1. 加载平台配置
2. 验证平台配置完整性
3. 生成平台选择器选项
4. 获取平台脚本路径
5. 运行平台测试

使用示例：
---------
```python
from web_ui.platforms.platform_manager import PlatformManager

manager = PlatformManager()

# 获取所有平台
platforms = manager.get_all_platforms()

# 验证某个平台配置
is_valid = manager.validate_platform("douyin")

# 获取平台脚本路径
script_path = manager.get_cli_script_path("douyin")

# 运行平台测试
result = manager.test_platform("douyin")
```

运行方式：
    .venv_webui/bin/python web_ui/platforms/platform_manager.py

"""

import sys
import os
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
CLI_TOOLS_DIR = PROJECT_ROOT / "1_pre_processing" / "cli_tools"
PLATFORMS_DIR = PROJECT_ROOT / "web_ui" / "platforms"

console = Console()


@dataclass
class PlatformInfo:
    """平台信息数据类"""
    key: str
    name: str
    icon: str
    color: str
    gradient: str
    url: Optional[str] = None
    logged_in_selectors: List[str] = field(default_factory=list)
    login_text: str = "扫码登录"
    cli_script: Optional[str] = None
    is_valid: bool = True
    error_message: Optional[str] = None


class PlatformManager:
    """平台管理器 - 负责加载、验证和管理所有平台配置"""
    
    def __init__(self):
        self.platforms: Dict[str, PlatformInfo] = {}
        self.config = self._load_config()
        self._load_platforms()
    
    def _load_config(self) -> Dict[str, Any]:
        """从配置文件加载平台配置"""
        config_path = PLATFORMS_DIR / "__init__.py"
        if not config_path.exists():
            console.print(f"[red]❌ 配置文件不存在: {config_path}[/red]")
            return {}
        
        # 简单解析配置文件
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 基础解析（实际项目中建议用更安全的方式）
            config = self._parse_config(content)
            return config
        except Exception as e:
            console.print(f"[red]❌ 解析配置文件失败: {e}[/red]")
            return {}
    
    def _parse_config(self, content: str) -> Dict[str, Any]:
        """解析配置文件内容"""
        config = {
            "BASE_PLATFORMS": {},
            "PLATFORM_CONFIG": {},
            "PREDEFINED_PLATFORMS": {}
        }
        
        # 简单解析逻辑（实际项目可用 ast 模块更安全）
        # 这里为了简单直接使用 exec（仅用于加载配置）
        local_vars = {}
        try:
            # 移除一些危险的导入
            safe_imports = {
                'Dict': Dict,
                'Any': Any,
                'List': List,
                'Optional': Optional,
                'Path': Path
            }
            # 更安全的配置解析
            import re
            
            # 提取 BASE_PLATFORMS 的内容
            base_match = re.search(r'BASE_PLATFORMS:\s*Dict\[.*?\]\s*=\s*\{(.*?)\}', content, re.DOTALL)
            if base_match:
                base_content = base_match.group(1)
                # 解析每个平台
                platform_pattern = r'"(\w+)":\s*\{(.*?)\}'
                for match in re.finditer(platform_pattern, base_content):
                    p_key = match.group(1)
                    p_content = match.group(2)
                    
                    # 提取字段
                    p_config = {}
                    for field_match in re.finditer(r'"(\w+)":\s*"([^"]+)"', p_content):
                        p_config[field_match.group(1)] = field_match.group(2)
                    
                    config["BASE_PLATFORMS"][p_key] = p_config
            
            # 提取 PLATFORM_CONFIG 的内容
            platform_match = re.search(r'PLATFORM_CONFIG:\s*Dict\[.*?\]\s*=\s*\{(.*?)\}', content, re.DOTALL)
            if platform_match:
                platform_content = platform_match.group(1)
                platform_pattern = r'"(\w+)":\s*\{(.*?)\}'
                for match in re.finditer(platform_pattern, platform_content):
                    p_key = match.group(1)
                    p_content = match.group(2)
                    
                    p_config = {}
                    for field_match in re.finditer(r'"(\w+)":\s*"([^"]+)"', p_content):
                        p_config[field_match.group(1)] = field_match.group(2)
                    
                    # 处理列表
                    list_match = re.search(r'"logged_in_selectors":\s*\[(.*?)\]', p_content)
                    if list_match:
                        items = re.findall(r'"([^"]+)"', list_match.group(1))
                        p_config["logged_in_selectors"] = items
                    
                    config["PLATFORM_CONFIG"][p_key] = p_config
            
            # 使用 ast 安全解析剩余部分
            import ast
            
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            if target.id == "BASE_PLATFORMS" and isinstance(node.value, ast.Dict):
                                base_configs = {}
                                for i, key_node in enumerate(node.value.keys):
                                    if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                                        value_node = node.value.values[i]
                                        if isinstance(value_node, ast.Dict):
                                            cfg = {}
                                            for kv in value_node.keys:
                                                if isinstance(kv, ast.Constant) and isinstance(kv.value, str):
                                                    idx = value_node.keys.index(kv)
                                                    val = value_node.values[idx]
                                                    if isinstance(val, ast.Constant):
                                                        cfg[kv.value] = val.value
                                                    elif isinstance(val, ast.List):
                                                        cfg[kv.value] = [e.value for e in val.elts if isinstance(e, ast.Constant)]
                                                base_configs[key_node.value] = cfg
                                            config["BASE_PLATFORMS"] = base_configs
                            
                            elif target.id == "PLATFORM_CONFIG" and isinstance(node.value, ast.Dict):
                                platform_configs = {}
                                for i, key_node in enumerate(node.value.keys):
                                    if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                                        value_node = node.value.values[i]
                                        if isinstance(value_node, ast.Dict):
                                            cfg = {}
                                            for kv in value_node.keys:
                                                if isinstance(kv, ast.Constant) and isinstance(kv.value, str):
                                                    idx = value_node.keys.index(kv)
                                                    val = value_node.values[idx]
                                                    if isinstance(val, ast.Constant):
                                                        cfg[kv.value] = val.value
                                                    elif isinstance(val, ast.List):
                                                        cfg[kv.value] = [e.value for e in val.elts if isinstance(e, ast.Constant)]
                                                platform_configs[key_node.value] = cfg
                                            config["PLATFORM_CONFIG"] = platform_configs
        except Exception as e:
            console.print(f"[yellow]⚠️  解析配置时出现警告: {e}[/yellow]")
        
        return config
    
    def _load_platforms(self):
        """加载所有平台信息"""
        base_configs = self.config.get("BASE_PLATFORMS", {})
        platform_configs = self.config.get("PLATFORM_CONFIG", {})
        
        for key, base_config in base_configs.items():
            platform_info = self._create_platform_info(key, base_config, platform_configs.get(key, {}))
            self.platforms[key] = platform_info
    
    def _create_platform_info(
        self, 
        key: str, 
        base_config: Dict[str, Any], 
        specific_config: Dict[str, Any]
    ) -> PlatformInfo:
        """创建平台信息对象"""
        # 合并基础配置和特定配置
        merged_config = {
            **base_config,
            **specific_config
        }
        
        # 验证必要字段
        required_fields = ["name", "icon", "color", "gradient"]
        missing_fields = [f for f in required_fields if f not in merged_config]
        
        is_valid = len(missing_fields) == 0
        
        return PlatformInfo(
            key=key,
            name=merged_config.get("name", key),
            icon=merged_config.get("icon", " Plattform"),
            color=merged_config.get("color", "#888888"),
            gradient=merged_config.get("gradient", "from-gray-400 to-gray-600"),
            url=merged_config.get("url"),
            logged_in_selectors=merged_config.get("logged_in_selectors", []),
            login_text=merged_config.get("login_text", "扫码登录"),
            cli_script=merged_config.get("cli_script"),
            is_valid=is_valid,
            error_message=f"缺少必要字段: {', '.join(missing_fields)}" if missing_fields else None
        )
    
    def get_all_platforms(self) -> Dict[str, PlatformInfo]:
        """获取所有平台"""
        return self.platforms
    
    def get_platform_names(self) -> Dict[str, str]:
        """获取平台名称映射 {key: name}"""
        return {
            key: platform.name 
            for key, platform in self.platforms.items()
        }
    
    def get_platform_options(self) -> List[Dict[str, Any]]:
        """获取平台选项（用于UI Select）"""
        return [
            {
                "value": idx,
                "label": f"{platform.icon} {platform.name}"
            }
            for idx, platform in enumerate(self.platforms.values())
        ]
    
    def get_platform_by_key(self, key: str) -> Optional[PlatformInfo]:
        """根据key获取平台信息"""
        return self.platforms.get(key)
    
    def validate_platform(self, key: str) -> bool:
        """验证平台配置是否完整"""
        platform = self.platforms.get(key)
        if not platform:
            return False
        return platform.is_valid
    
    def get_cli_script_path(self, key: str) -> Optional[Path]:
        """获取平台的CLI脚本路径"""
        platform = self.platforms.get(key)
        if not platform or not platform.cli_script:
            return None
        
        script_path = CLI_TOOLS_DIR / platform.cli_script
        if script_path.exists():
            return script_path
        return None
    
    def test_platform(self, key: str, timeout: int = 30) -> Dict[str, Any]:
        """测试平台配置是否有效"""
        platform = self.platforms.get(key)
        if not platform:
            return {"success": False, "error": f"平台 {key} 不存在"}
        
        if not platform.is_valid:
            return {"success": False, "error": platform.error_message}
        
        script_path = self.get_cli_script_path(key)
        if not script_path:
            return {"success": False, "error": f"未找到CLI脚本"}
        
        # 运行测试
        try:
            result = subprocess.run(
                ["python", str(script_path), "--test"],
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if result.returncode == 0:
                return {
                    "success": True,
                    "output": result.stdout,
                    "error": result.stderr
                }
            else:
                return {
                    "success": False,
                    "output": result.stdout,
                    "error": result.stderr
                }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "测试超时"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def print_platform_status(self):
        """打印平台状态表格"""
        table = Table(
            title="📋 平台配置状态",
            box=box.ROUNDED,
            show_lines=True
        )
        
        table.add_column("平台", style="cyan")
        table.add_column("状态", style="green")
        table.add_column("URL", style="yellow")
        table.add_column("脚本", style="magenta")
        
        for key, platform in self.platforms.items():
            status = "✅" if platform.is_valid else "❌"
            url = platform.url or "N/A"
            script = platform.cli_script or "N/A"
            
            table.add_row(
                f"{platform.icon} {platform.name}",
                status,
                url,
                script
            )
        
        console.print(table)
    
    def print_available_platforms(self):
        """打印可用平台列表"""
        console.print("\n")
        table = Table(title="📢 可用平台列表", box=box.ROUNDED)
        table.add_column("平台", style="cyan")
        table.add_column("键名", style="magenta")
        table.add_column("颜色", style="green")
        table.add_column("URL", style="yellow")
        
        for key, platform in self.platforms.items():
            table.add_row(
                f"{platform.icon} {platform.name}",
                key,
                platform.color,
                platform.url or "N/A"
            )
        
        console.print(table)


def main():
    """主函数 - 命令行接口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="平台管理器")
    parser.add_argument("--list", action="store_true", help="列出所有平台")
    parser.add_argument("--status", action="store_true", help="显示平台状态")
    parser.add_argument("--test", type=str, help="测试指定平台")
    parser.add_argument("--validate", type=str, help="验证指定平台")
    parser.add_argument("--json", action="store_true", help="以JSON格式输出")
    
    args = parser.parse_args()
    
    manager = PlatformManager()
    
    if args.list:
        manager.print_available_platforms()
    
    elif args.status:
        manager.print_platform_status()
    
    elif args.test:
        result = manager.test_platform(args.test)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            if result["success"]:
                console.print(f"[green]✅ 平台 {args.test} 测试通过[/green]")
            else:
                console.print(f"[red]❌ 平台 {args.test} 测试失败: {result.get('error', '未知错误')}[/red]")
    
    elif args.validate:
        is_valid = manager.validate_platform(args.validate)
        if args.json:
            print(json.dumps({"platform": args.validate, "valid": is_valid}, indent=2))
        else:
            status = "✅ 有效" if is_valid else "❌ 无效"
            console.print(f"平台 [bold]{args.validate}[/bold]: {status}")
    
    else:
        manager.print_platform_status()
        manager.print_available_platforms()


if __name__ == "__main__":
    main()
