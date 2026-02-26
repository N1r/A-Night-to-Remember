"""
style_manager.py
----------------
字幕样式管理器 — 从 aesthetics.yaml 动态加载当前领域的字幕样式。

旧方案：硬编码 3 套 SUBTITLE_STYLES 字典
新方案：aesthetics.yaml → preset → subtitle.source / subtitle.translation

保留了静态回退表 _FALLBACK_STYLES，在 aesthetics 不可用时使用。
"""

import sys
from pathlib import Path
import pysubs2

# ===== 确保能导入 shared =====
_PROJECT_ROOT = Path(__file__).parent.parent.parent.absolute()
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


def _hex_to_ass_color(hex_color: str, alpha: int = 0) -> pysubs2.Color:
    """
    将 '#RRGGBB' 格式转为 pysubs2.Color (BGR + alpha)。
    pysubs2.Color 构造函数: Color(r, g, b, a)
    """
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    return pysubs2.Color(r, g, b, alpha)


def _build_pysubs2_style(cfg: dict) -> dict:
    """将 aesthetics.yaml 中的字幕配置转为 pysubs2 SSAStyle 兼容的参数字典。"""
    style = {
        "fontname":  cfg.get("fontname", "Arial"),
        "fontsize":  cfg.get("fontsize", 50),
        "bold":      cfg.get("bold", True),
        "alignment": cfg.get("alignment", 2),
        "marginv":   cfg.get("margin_v", 70),
        "borderstyle": cfg.get("border_style", 1),
        "outline":   cfg.get("outline", 2),
        "shadow":    cfg.get("shadow", 0),
    }

    # 颜色处理
    primary = cfg.get("primary_color", "#FFFFFF")
    secondary = cfg.get("secondary_color", "#C8C8C8")
    outline_c = cfg.get("outline_color", "#000000")
    back_alpha = cfg.get("back_color_alpha", 0)

    style["primarycolor"] = _hex_to_ass_color(primary)
    style["secondarycolor"] = _hex_to_ass_color(secondary)
    style["outlinecolor"] = _hex_to_ass_color(outline_c, back_alpha)

    # border_style 3 需要 backcolor
    if style["borderstyle"] == 3:
        style["backcolor"] = _hex_to_ass_color(outline_c, back_alpha)

    return style


def _load_from_aesthetics() -> dict | None:
    """尝试从 aesthetics 配置加载字幕样式，失败则返回 None。"""
    try:
        from shared.aesthetics import aesthetics
        sub_cfg = aesthetics.get_subtitle_config()
        if not sub_cfg or "source" not in sub_cfg:
            return None

        return {
            "source": _build_pysubs2_style(sub_cfg["source"]),
            "trans":  _build_pysubs2_style(sub_cfg["translation"]),
        }
    except Exception:
        return None


# ===== 静态回退表（aesthetics 不可用时使用） =====
_FALLBACK_STYLES = {
    "young_vibrant": {
        "source": {
            "fontname": "HarmonyOS Sans SC Bold",
            "fontsize": 52,
            "primarycolor": pysubs2.Color(255, 255, 0),
            "secondarycolor": pysubs2.Color(255, 255, 255),
            "outlinecolor": pysubs2.Color(0, 0, 0, 100),
            "borderstyle": 1, "outline": 3, "shadow": 2,
            "bold": True, "alignment": 2, "marginv": 150
        },
        "trans": {
            "fontname": "HarmonyOS Sans SC Bold",
            "fontsize": 75,
            "primarycolor": pysubs2.Color(255, 255, 255),
            "secondarycolor": pysubs2.Color(200, 200, 200),
            "outlinecolor": pysubs2.Color(255, 100, 0, 50),
            "borderstyle": 1, "outline": 4, "shadow": 0,
            "bold": True, "alignment": 2, "marginv": 50
        }
    },
    "bbc": {
        "source": {
            "fontname": "Arial",
            "fontsize": 50,
            "primarycolor": pysubs2.Color(255, 212, 0),
            "secondarycolor": pysubs2.Color(255, 255, 255),
            "outlinecolor": pysubs2.Color(0, 0, 0, 30),
            "backcolor": pysubs2.Color(0, 0, 0, 30),
            "borderstyle": 3, "outline": 4.5, "shadow": 0,
            "bold": True, "alignment": 2, "marginv": 185
        },
        "trans": {
            "fontname": "Source Han Sans SC",
            "fontsize": 82,
            "primarycolor": pysubs2.Color(255, 255, 255),
            "secondarycolor": pysubs2.Color(190, 190, 190),
            "outlinecolor": pysubs2.Color(0, 0, 0, 30),
            "backcolor": pysubs2.Color(0, 0, 0, 30),
            "borderstyle": 3, "outline": 4.5, "shadow": 0,
            "bold": True, "alignment": 2, "marginv": 70
        }
    },
    "documentary": {
        "source": {
            "fontname": "Noto Sans SC Regular",
            "fontsize": 38,
            "primarycolor": pysubs2.Color(240, 240, 240),
            "secondarycolor": pysubs2.Color(150, 150, 150),
            "outlinecolor": pysubs2.Color(0, 0, 0, 180),
            "borderstyle": 1, "outline": 1.5, "shadow": 1,
            "bold": False, "alignment": 2, "marginv": 120
        },
        "trans": {
            "fontname": "Noto Sans SC-Bold",
            "fontsize": 58,
            "primarycolor": pysubs2.Color(255, 255, 255),
            "secondarycolor": pysubs2.Color(200, 200, 200),
            "outlinecolor": pysubs2.Color(0, 0, 0, 200),
            "borderstyle": 1, "outline": 2, "shadow": 1.5,
            "bold": True, "alignment": 2, "marginv": 50
        }
    },
    "premium_orange": {
        "source": {
            "fontname": "HarmonyOS Sans SC Bold",
            "fontsize": 45,
            "primarycolor": pysubs2.Color(255, 255, 255),
            "secondarycolor": pysubs2.Color(200, 200, 200),
            "outlinecolor": pysubs2.Color(0, 0, 0, 150),
            "borderstyle": 1, "outline": 2.5, "shadow": 2,
            "bold": True, "alignment": 2, "marginv": 185
        },
        "trans": {
            "fontname": "HarmonyOS Sans SC Bold",
            "fontsize": 85,
            "primarycolor": pysubs2.Color(255, 165, 0),  # 橙色
            "secondarycolor": pysubs2.Color(200, 200, 200),
            "outlinecolor": pysubs2.Color(0, 0, 0, 150),
            "borderstyle": 1, "outline": 4.0, "shadow": 3,
            "bold": True, "alignment": 2, "marginv": 70
        }
    }
}


def get_style_config(style_name="premium_orange"):
    """
    获取字幕样式配置。

    优先级：
      1. aesthetics.yaml 中当前 preset 的 subtitle 配置（动态）
      2. _FALLBACK_STYLES 静态回退表（兜底）

    Parameters
    ----------
    style_name : str
        样式名称（仅在回退模式下生效）

    Returns
    -------
    dict : { "source": {...}, "trans": {...} }
    """
    # 优先从 aesthetics 读取
    aesthetic_style = _load_from_aesthetics()
    if aesthetic_style:
        return aesthetic_style

    # 回退到静态样式表
    return _FALLBACK_STYLES.get(style_name, _FALLBACK_STYLES["premium_orange"])
