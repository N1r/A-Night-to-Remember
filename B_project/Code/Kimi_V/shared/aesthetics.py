"""
shared/aesthetics.py
--------------------
美学配置管理器 — 全局唯一的视觉样式读取入口。

核心功能：
  1. 加载 configs/aesthetics.yaml 中的 preset 定义
  2. 通过领域配置（domain profile）中的 aesthetics_preset 字段确定当前 preset
  3. 提供简洁的 API 让各模块查询视觉参数

使用方式：
    from shared.aesthetics import aesthetics

    # 获取当前 preset 名称
    aesthetics.preset_name           # "news"

    # 查询配置值（点号分隔路径）
    aesthetics.get("subtitle.style_name")        # "bbc"
    aesthetics.get("logo.position")              # "top-right"
    aesthetics.get("cover.highlight_color")      # "#FFD700"

    # 快捷方法
    aesthetics.get_subtitle_config()             # { source: {...}, translation: {...} }
    aesthetics.get_logo_config()                 # { enabled: true, path: ..., ... }
    aesthetics.get_cover_config()                # { width: 1920, ... }
    aesthetics.get_date_config()                 # { enabled: true, ... }

切换视觉风格：
    方式 1: 在领域配置中指定
        configs/domains/politics.yaml → aesthetics_preset: news
        configs/domains/sports.yaml   → aesthetics_preset: sports

    方式 2: 在 aesthetics.yaml 中修改默认值
        default_preset: news  →  default_preset: documentary
"""

import sys
from pathlib import Path
from ruamel.yaml import YAML

# 确保路径正确
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class AestheticsProfile:
    """
    美学配置 Profile — 管理当前激活的视觉样式 preset。

    数据来源：configs/aesthetics.yaml
    Preset 选择：domain profile 中的 aesthetics_preset 字段
    """

    def __init__(self, preset_name: str = None):
        self._yaml = YAML()
        self._yaml.preserve_quotes = True

        # 加载美学配置文件
        config_path = PROJECT_ROOT / "configs" / "aesthetics.yaml"
        if not config_path.exists():
            raise FileNotFoundError(
                f"美学配置文件不存在: {config_path}\n"
                f"请创建 configs/aesthetics.yaml"
            )

        with open(config_path, "r", encoding="utf-8") as f:
            self._raw = self._yaml.load(f) or {}

        # 确定 preset 名称：参数 > domain profile > 默认值
        if preset_name:
            self._preset_name = preset_name
        else:
            # 尝试从 domain profile 读取
            try:
                from shared.domain import domain
                self._preset_name = domain.get("aesthetics_preset", None)
            except Exception:
                self._preset_name = None

            # 兜底到 aesthetics.yaml 的 default_preset
            if not self._preset_name:
                self._preset_name = self._raw.get("default_preset", "news")

        # 加载对应的 preset 数据
        presets = self._raw.get("presets", {})
        self._data = presets.get(self._preset_name, {})

        if not self._data:
            # Fallback 到第一个可用的 preset
            if presets:
                first_key = next(iter(presets))
                self._data = presets[first_key]
                self._preset_name = first_key
            else:
                self._data = {}

    # ===== 基本属性 =====

    @property
    def preset_name(self) -> str:
        """当前 preset 名称"""
        return self._preset_name

    @property
    def name(self) -> str:
        """preset 中文名称"""
        return self._data.get("name", self._preset_name)

    @property
    def description(self) -> str:
        """描述信息"""
        return self._data.get("description", "")

    # ===== 通用查询 =====

    def get(self, key: str, default=None):
        """
        用点号分隔的路径查询配置。

        Examples:
            aesthetics.get("subtitle.style_name")
            aesthetics.get("logo.enabled", True)
            aesthetics.get("cover.highlight_color", "#FFD700")
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

    def get_subtitle_config(self) -> dict:
        """获取完整的字幕样式配置"""
        return self.get("subtitle", {})

    def get_logo_config(self) -> dict:
        """获取 Logo / 水印配置"""
        return self.get("logo", {})

    def get_cover_config(self) -> dict:
        """获取封面样式配置"""
        return self.get("cover", {})

    def get_date_config(self) -> dict:
        """获取日期水印配置"""
        return self.get("date_stamp", {})

    def get_encoding_config(self) -> dict:
        """获取编码参数偏好"""
        return self.get("encoding", {})

    def is_logo_enabled(self) -> bool:
        """是否启用 Logo"""
        return self.get("logo.enabled", True)

    def is_date_enabled(self) -> bool:
        """是否启用日期水印"""
        return self.get("date_stamp.enabled", True)

    def get_font_paths(self) -> list:
        """获取字体搜索路径列表"""
        return self.get("cover.font_paths", [])

    def to_dict(self):
        """将配置转换为纯 Python 字典，移除 YAML 特有类型"""
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
        return f"AestheticsProfile(preset='{self.preset_name}', name='{self.name}')"


# ===== 全局单例 =====

_aesthetics_instance = None


def get_aesthetics(preset_name: str = None) -> AestheticsProfile:
    """
    获取当前美学配置实例（单例模式）。

    首次调用时初始化，后续调用返回同一实例。
    如需切换 preset，传入 preset_name 将创建新实例。
    """
    global _aesthetics_instance
    if _aesthetics_instance is None or preset_name is not None:
        _aesthetics_instance = AestheticsProfile(preset_name)
    return _aesthetics_instance


# 便捷别名
aesthetics = get_aesthetics()
