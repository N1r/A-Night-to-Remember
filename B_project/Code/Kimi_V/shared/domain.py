"""
shared/domain.py
----------------
领域配置管理器 — 全局唯一的领域配置读取入口。

核心功能：
  1. 根据 config.yaml 中的 `domain` 字段，自动加载对应的领域 profile
  2. 提供简洁的 API 让各模块查询领域特定配置
  3. 支持嵌套键查询（如 "upload.bilibili.tid"）

使用方式：
    from shared.domain import domain

    # 获取当前领域名称
    domain.name          # "政治新闻"
    domain.key           # "politics"

    # 查询嵌套配置
    domain.get("scrapers.youtube.channels")
    domain.get("upload.bilibili.tid")
    domain.get("upload.douyin.domain_tags")
    domain.get("screening.categories")

    # 获取上传标签（合并 base_tags + 平台标签）
    domain.get_tags("douyin")
    domain.get_tags("bilibili")

切换领域：
    只需修改 configs/config.yaml 中的 domain 字段:
        domain: politics  →  domain: sports
"""

import os
import sys
from pathlib import Path
from ruamel.yaml import YAML

# 确保路径正确
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class DomainProfile:
    """
    领域配置 Profile — 代表一个完整的内容领域。

    数据来源：configs/domains/<domain_key>.yaml
    激活方式：config.yaml 中的 `domain` 字段
    """

    def __init__(self, domain_key: str = None):
        self._yaml = YAML()
        self._yaml.preserve_quotes = True

        # 读取主配置以确定当前 domain
        config_path = PROJECT_ROOT / "configs" / "config.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            main_config = self._yaml.load(f)

        self._domain_key = domain_key or main_config.get("domain", "politics")

        # 加载领域 profile
        profile_path = PROJECT_ROOT / "configs" / "domains" / f"{self._domain_key}.yaml"
        if not profile_path.exists():
            # Fallback: 尝试加载 politics
            fallback = PROJECT_ROOT / "configs" / "domains" / "politics.yaml"
            if fallback.exists():
                profile_path = fallback
                self._domain_key = "politics"
            else:
                raise FileNotFoundError(
                    f"领域配置文件不存在: {profile_path}\n"
                    f"请从模板创建: cp configs/domains/_template.yaml "
                    f"configs/domains/{self._domain_key}.yaml"
                )

        with open(profile_path, "r", encoding="utf-8") as f:
            self._data = self._yaml.load(f) or {}

    # ===== 基本属性 =====

    @property
    def key(self) -> str:
        """领域标识符（如 politics, sports）"""
        return self._domain_key

    @property
    def name(self) -> str:
        """领域中文名称"""
        return self._data.get("name", self._domain_key)

    @property
    def icon(self) -> str:
        """领域 emoji 图标"""
        return self._data.get("icon", "🎯")

    # ===== 通用查询 =====

    def get(self, key: str, default=None):
        """
        用点号分隔的路径查询配置。

        Examples:
            domain.get("scrapers.youtube.channels")
            domain.get("upload.bilibili.tid", 0)
            domain.get("screening.categories", [])
        """
        keys = key.split(".")
        value = self._data
        try:
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default
            return value
        except Exception:
            return default

    # ===== 快捷方法 =====

    def get_tags(self, platform: str) -> list:
        """
        获取指定平台的完整标签列表（base_tags + 平台特定标签合并）。

        Parameters
        ----------
        platform : str
            平台名称：douyin, bilibili, xiaohongshu, tencent, kuaishou

        Returns
        -------
        list : 标签列表
        """
        base = self.get("upload.base_tags", [])
        platform_tags = self.get(f"upload.{platform}.default_tags", [])
        domain_tags = self.get(f"upload.{platform}.domain_tags", [])

        # 合并去重（保持顺序）
        seen = set()
        result = []
        for tag in (base + domain_tags + platform_tags):
            if tag not in seen:
                result.append(tag)
                seen.add(tag)
        return result

    def get_scraper_config(self, platform: str) -> dict:
        """获取指定采集平台的配置"""
        return self.get(f"scrapers.{platform}", {})

    def get_upload_config(self, platform: str) -> dict:
        """获取指定上传平台的配置"""
        return self.get(f"upload.{platform}", {})

    def get_screening_prompt(self) -> tuple:
        """生成 AI 筛选的 prompt context，返回 (categories, context)"""
        categories = self.get("screening.categories", ["Other"])
        context = self.get("screening.prompt_context", "content for Chinese social media")
        return categories, context

    def get_translation_prompts(self) -> dict:
        """获取翻译相关的 prompt 配置"""
        return self.get("prompts", {})

    def get_terms_path(self) -> Path | None:
        """获取当前领域的术语表绝对路径"""
        filename = self.get("custom_terms_file", "custom_terms.xlsx")
        path = PROJECT_ROOT / "configs" / filename
        return path if path.exists() else None

    def to_dict(self):
        """将配置转换为纯 Python 字典，移除 YAML 特有类型"""
        def convert(data):
            if isinstance(data, dict):
                return {k: convert(v) for k, v in data.items()}
            elif isinstance(data, list):
                return [convert(v) for v in data]
            elif hasattr(data, 'anchor'): # Handle ruamel.yaml types
                 return data.value if hasattr(data, 'value') else str(data)
            elif 'ruamel.yaml.scalarfloat.ScalarFloat' in str(type(data)):
                 return float(data)
            else:
                return data
        
        # ruamel.yaml load returns a CommentedMap which behaves like a dict but might have issues
        # with some JSON serializers if they check types strictly. 
        # However, the error 'ScalarFloat' suggests we have float-like objects that aren't float.
        # Let's try a simpler approach first: recursive conversion.
        import json
        
        # The most robust way to ensure JSON serializability is to dump and load
        # This handles CommentedMap, ScalarFloat, etc. automatically if we use a custom encoder or just str
        # But ruamel objects usually serialize fine with standard json.dump if we are careful.
        # The issue is likely `ui.json_editor` using a specific serializer.
        
        # Let's implement a safe recursive converter
        from ruamel.yaml.scalarfloat import ScalarFloat
        
        def safe_convert(obj):
            if isinstance(obj, ScalarFloat):
                return float(obj)
            if isinstance(obj, dict):
                return {k: safe_convert(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [safe_convert(v) for v in obj]
            return obj
            
        return safe_convert(self._data)


    def __repr__(self):
        return f"DomainProfile(key='{self.key}', name='{self.name}')"


# ===== 全局单例 =====

_domain_instance = None


def get_domain(domain_key: str = None) -> DomainProfile:
    """
    获取当前领域配置实例（单例模式）。

    首次调用时初始化，后续调用返回同一实例。
    如需切换领域，传入 domain_key 将创建新实例。
    """
    global _domain_instance
    if _domain_instance is None or domain_key is not None:
        _domain_instance = DomainProfile(domain_key)
    return _domain_instance


# 便捷别名
domain = get_domain()
