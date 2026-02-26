# 🎨 领域 × 美学配置系统 — 使用与维护指南

> **更新日期**：2026-02-19  
> **适用范围**：Kimi_V 视频翻译管线全流程

---

## 目录

1. [设计理念](#1-设计理念)
2. [架构总览](#2-架构总览)
3. [配置文件清单](#3-配置文件清单)
4. [快速上手：切换领域与风格](#4-快速上手切换领域与风格)
5. [领域配置协议](#5-领域配置协议)
6. [美学配置协议](#6-美学配置协议)
7. [Python API 参考](#7-python-api-参考)
8. [数据流与模块对接关系](#8-数据流与模块对接关系)
9. [弃用清单与迁移说明](#9-弃用清单与迁移说明)
10. [已知限制与改进方向](#10-已知限制与改进方向)

---

## 1. 设计理念

**核心目标**：让"内容领域"和"视觉风格"完全解耦并可独立配置。

| 维度 | 旧方案 | 新方案 |
|------|--------|--------|
| 领域切换 | 修改 5+ 模块的硬编码标签/prompt | 改 `config.yaml` 的 1 个字段 |
| 视觉风格 | 散落在 3-4 个 Python 文件中 | 集中在 `aesthetics.yaml` 一个文件 |
| 新增领域 | 全代码审查 + 修改 | 复制 `_template.yaml` + 填写 |
| 新增风格 | 修改 `style_manager.py` | 在 `aesthetics.yaml` 中新增 preset |

---

## 2. 架构总览

```
┌─────────────────────────────────────────────────────────┐
│                   configs/config.yaml                    │
│                   domain: politics                       │
└──────────────────────┬──────────────────────────────────┘
                       ▼
┌──────────────────────────────────────────────────────────┐
│              configs/domains/politics.yaml                │
│  ┌─ name: "政治新闻"                                      │
│  ├─ aesthetics_preset: "news"  ◄── 指定视觉风格            │
│  ├─ scrapers: { youtube, twitter, ... }                   │
│  ├─ screening: { categories, prompt_context }             │
│  ├─ prompts: { summary, translation }                     │
│  └─ upload: { base_tags, douyin, bilibili, ... }          │
└──────────────┬───────────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────────┐
│              configs/aesthetics.yaml                      │
│  presets:                                                 │
│   ├─ news:                                                │
│   │   ├─ subtitle:   { source, translation }              │
│   │   ├─ logo:       { enabled, path, scale_* }           │
│   │   ├─ date_stamp: { enabled, color, duration }         │
│   │   ├─ cover:      { colors, tag_text, fonts }          │
│   │   └─ encoding:   { crf, preset }                     │
│   ├─ sports: { ... }                                      │
│   └─ documentary: { ... }                                 │
└──────────────────────────────────────────────────────────┘
```

**Python 层：**

```
shared/domain.py      →  DomainProfile (单例)  →  domain.get("upload.douyin.domain_tags")
shared/aesthetics.py  →  AestheticsProfile (单例) →  aesthetics.get("cover.highlight_color")
```

---

## 3. 配置文件清单

| 文件 | 用途 | 修改频率 |
|------|------|----------|
| `configs/config.yaml` | 全局配置入口，设置当前领域 (`domain: xxx`) | 按需 |
| `configs/domains/<key>.yaml` | 领域 profile（采集源、prompt、标签、美学 preset） | 新增领域时 |
| `configs/domains/_template.yaml` | 新领域模板 | 不修改 |
| `configs/aesthetics.yaml` | 美学 preset 定义（字幕、Logo、封面、编码） | 调视觉时 |

---

## 4. 快速上手：切换领域与风格

### 4.1 切换整个领域（含视觉风格）

```yaml
# configs/config.yaml — 只改一行
domain: politics    # → 新闻风格
domain: sports      # → 运动风格
```

领域 profile 中的 `aesthetics_preset` 会自动切换全部视觉元素。

### 4.2 仅切换视觉风格（不换领域）

```yaml
# configs/domains/politics.yaml — 只改一行
aesthetics_preset: "news"         # 当前
aesthetics_preset: "documentary"  # 换成纪录片风格
```

### 4.3 创建全新领域

1. 复制 `configs/domains/_template.yaml` → `configs/domains/finance.yaml`
2. 填写配置（采集源、标签、prompt 等）
3. 设置 `aesthetics_preset: "news"` 或创建新 preset
4. 在 `config.yaml` 设置 `domain: finance`
5. 运行 — 无需修改任何 Python 代码

### 4.4 创建全新美学 preset

在 `configs/aesthetics.yaml` 的 `presets:` 下新增：

```yaml
presets:
  my_custom_style:
    name: "自定义风格"
    description: "..."

    subtitle:
      style_name: "bbc"
      source:
        fontname: "Arial"
        fontsize: 50
        primary_color: "#FFD400"
        # ... (参考 news preset 填写完整)
      translation:
        # ...

    logo:
      enabled: true
      path: "core/logo.png"
      # ...

    date_stamp:
      enabled: true
      # ...

    cover:
      width: 1920
      height: 1080
      highlight_color: "#FFD700"
      accent_color: "#E21918"
      tag_text: " 🌐 MY BRAND • 标签 "
      # ...

    encoding:
      crf: 26
      preset: "fast"
```

然后在领域配置中引用：`aesthetics_preset: "my_custom_style"`

---

## 5. 领域配置协议

每个 `configs/domains/<key>.yaml` 须包含以下字段：

```yaml
# === 必填 ===
name: "领域中文名"
key: your_domain_key        # 须与文件名一致
icon: "🎯"
aesthetics_preset: "news"   # 引用 aesthetics.yaml 中的 preset

# === 采集源 ===
scrapers:
  youtube:
    channels: {}
    fetch_limit: 5
    filters: { min_duration, max_duration, blacklist_keywords }
  twitter:
    accounts: []
  bluesky:
    targets: []

# === AI 筛选 ===
screening:
  categories: ["Category1", "Other"]
  prompt_context: "..."

# === 翻译 prompt ===
prompts:
  summary:
    role: "..."
    task: "..."
  translation:
    style: "..."

# === 术语表 ===
custom_terms_file: "custom_terms.xlsx"

# === 上传标签 ===
upload:
  base_tags: ["#标签"]
  douyin: { domain_tags, popular_tags, keyword_triggers }
  bilibili: { tid, title_prefix, base_tags, extra_tags, description_template }
  xiaohongshu: { default_tags, topic_tags }
  tencent: { default_tags }
  kuaishou: { default_tags }
```

---

## 6. 美学配置协议

每个 preset 包含 **5 大视觉维度**，覆盖管线中所有视觉环节：

| 维度 | 字段路径 | 影响模块 |
|------|---------|---------|
| **字幕** | `subtitle.source.*`, `subtitle.translation.*` | `style_manager.py` → `_6_gen_sub.py` |
| **Logo** | `logo.enabled`, `logo.path`, `logo.scale_*` | `_7_1_ass_into_vid.py` |
| **日期水印** | `date_stamp.enabled`, `date_stamp.color`, `date_stamp.duration` | `_7_1_ass_into_vid.py` |
| **封面** | `cover.highlight_color`, `cover.tag_text`, `cover.font_paths` | `new_cover_making.py` |
| **编码** | `encoding.crf`, `encoding.preset` | `_7_1_ass_into_vid.py` |

### 字幕参数详解

| 字段 | 类型 | 说明 |
|------|------|------|
| `fontname` | str | 字体名称（须系统已安装） |
| `fontsize` | int | 基准字号（竖屏会自动 ×1.5） |
| `primary_color` | str | 主色 `#RRGGBB` |
| `outline_color` | str | 描边色 `#RRGGBB` |
| `outline` | float | 描边粗细 |
| `shadow` | float | 阴影深度 |
| `bold` | bool | 是否粗体 |
| `alignment` | int | ASS 对齐码（2=底部居中，7=左上） |
| `margin_v` | int | 垂直边距（像素） |
| `border_style` | int | 1=描边, 3=背景框 |
| `back_color_alpha` | int | 背景色透明度 (0-255) |

### 封面参数详解

| 字段 | 类型 | 说明 |
|------|------|------|
| `highlight_color` | str | 标题高亮词颜色 |
| `normal_color` | str | 普通标题文字颜色 |
| `accent_color` | str | 标签条背景色 + 左侧竖条色 |
| `bg_box_color` | list | 标题背景块 RGBA `[R,G,B,A]` |
| `blur_radius` | int | 底图高斯模糊半径 |
| `overlay_alpha` | int | 全局遮罩透明度 |
| `tag_text` | str | 顶部标签文字 |
| `tag_fontsize` | int | 标签字号 |
| `title_fontsize` | int | 标题字号 |
| `title_max_lines` | int | 标题最大行数 |
| `title_bar_width` | int | 左侧竖条宽度 |
| `font_paths` | list | 字体搜索路径（按优先级） |

---

## 7. Python API 参考

### 7.1 领域管理器 `shared.domain`

```python
from shared.domain import domain

# 基本属性
domain.name                    # "政治新闻"
domain.key                     # "politics"
domain.icon                    # "🏛️"

# 通用查询
domain.get("scrapers.youtube.channels")
domain.get("upload.bilibili.tid")
domain.get("screening.categories")

# 快捷方法
domain.get_tags("douyin")                # 合并 base_tags + platform tags
domain.get_upload_config("bilibili")     # 完整上传配置字典
domain.get_screening_prompt()            # (prompt_text, categories)
domain.get_translation_prompts()         # { summary: {role, task}, translation: {style} }
```

### 7.2 美学管理器 `shared.aesthetics`

```python
from shared.aesthetics import aesthetics

# 基本属性
aesthetics.preset_name         # "news"
aesthetics.name                # "新闻资讯"

# 通用查询
aesthetics.get("subtitle.style_name")         # "bbc"
aesthetics.get("logo.position")               # "top-right"
aesthetics.get("cover.highlight_color")       # "#FFD700"
aesthetics.get("encoding.crf")                # 26

# 快捷方法
aesthetics.get_subtitle_config()   # { style_name, source: {...}, translation: {...} }
aesthetics.get_logo_config()       # { enabled, path, scale_*, ... }
aesthetics.get_cover_config()      # { width, height, colors, ... }
aesthetics.get_date_config()       # { enabled, fontname, color, ... }
aesthetics.get_encoding_config()   # { crf, preset, pixel_format }

# 布尔检查
aesthetics.is_logo_enabled()       # True
aesthetics.is_date_enabled()       # True

# 字体路径
aesthetics.get_font_paths()        # ["storage/fonts/...", ...]
```

### 7.3 切换 preset（运行时）

```python
from shared.aesthetics import get_aesthetics

# 强制切换到指定 preset
aesthetics = get_aesthetics("documentary")
```

---

## 8. 数据流与模块对接关系

```
                    ┌─────────────────────┐
                    │   config.yaml       │
                    │   domain: politics  │
                    └─────────┬───────────┘
                              ▼
                    ┌─────────────────────┐
                    │ domains/politics.yaml│
                    │ aesthetics_preset:  │
                    │   "news"            │
                    └───┬─────────┬───────┘
                        │         │
           ┌────────────┘         └──────────────┐
           ▼                                      ▼
  ┌─────────────────┐                   ┌──────────────────┐
  │ shared/domain.py│                   │shared/aesthetics │
  │ (DomainProfile) │                   │(AestheticsProfile│
  └──┬──┬──┬──┬─────┘                   └──┬──┬──┬──┬──────┘
     │  │  │  │                             │  │  │  │
     │  │  │  └─ uploaders (tags)           │  │  │  └─ _7_1_ass_into_vid.py
     │  │  │    ├ douyin_uploader.py         │  │  │    (logo, date, encoding)
     │  │  │    ├ bili_uploader.py           │  │  │
     │  │  │    ├ xhs_uploader.py           │  │  └──── style_manager.py
     │  │  │    └ ks_uploader.py            │  │        (subtitle styles)
     │  │  │                                │  │            ↓
     │  │  └── workflow_1_pre.py            │  │        _6_gen_sub.py
     │  │      (screening prompt)           │  │        (ASS generation)
     │  │                                   │  │
     │  └──── _4_1_summarize.py             │  └──── new_cover_making.py
     │        (translation prompts)         │         (cover colors, fonts)
     │                                      │
     └────── domain_manager.py              └──── [future modules]
             (桥接层·已弃用)
```

---

## 9. 弃用清单与迁移说明

### 已弃用文件

| 文件 | 状态 | 替代方案 |
|------|------|---------|
| `2_mid_processing/core/domain_manager.py` | **桥接层** — 保留兼容 | `shared.domain` |
| `1_pre_processing/scrapers/_deprecated/` | 旧采集器 | 使用新版采集器 |
| `3_post_processing/uploaders/_deprecated/` | 旧上传器 | 使用新版上传器 |

### 弃用的硬编码变量

| 原变量 | 所在文件 | 替代配置路径 |
|--------|---------|-------------|
| `POLITICS_TAGS` | `_deprecated/2_douyin_upload_clean.py` | `domain.get_tags("douyin")` |
| `POPULAR_TAGS` (硬编码) | `_deprecated/2_douyin_upload_clean.py` | `domain.get("upload.douyin.popular_tags")` |
| `POLITICS_ACCOUNTS` | `_deprecated/fetch_videos_X.py` | `domain.get("scrapers.twitter.accounts")` |
| `RED_ACCENT` | `_deprecated/1_bili_upload.py` | `aesthetics.get("cover.accent_color")` |
| `TAG = '每日英语新闻...'` | 已在 `new_cover_making.py` 移除 | `aesthetics.get("cover.tag_text")` |
| `LOGO_PATH = "core/logo.png"` | `_7_1_ass_into_vid.py` | `aesthetics.get("logo.path")` |
| `subtitle_style` in `config.yaml` | 仍保留做回退 | `aesthetics.get("subtitle.style_name")` |

### 迁移指南：旧代码 → 新 API

```python
# ❌ 旧写法
from core.domain_manager import get_prompts_for_domain
prompts = get_prompts_for_domain()

# ✅ 新写法
from shared.domain import domain
prompts = domain.get_translation_prompts()

# ❌ 旧写法
style_name = load_key("subtitle_style") or "bbc"
style_config = get_style_config(style_name)

# ✅ 新写法
style_config = get_style_config()  # 内部自动从 aesthetics 读取

# ❌ 旧写法
HIGHLIGHT_COLOR = "#FFD700"
RED_ACCENT = "#E21918"

# ✅ 新写法
HIGHLIGHT_COLOR = aesthetics.get("cover.highlight_color", "#FFD700")
ACCENT_COLOR    = aesthetics.get("cover.accent_color", "#E21918")
```

---

## 10. 已知限制与改进方向

### 当前限制

| 限制 | 详情 |
|------|------|
| **静态分析器误报** | Pyre2 无法识别运行时 `sys.path.insert()` 导致的跨目录导入，所有 `"Could not find import"` 均为假阳性 |
| **单例不可热重载** | `domain` 和 `aesthetics` 在进程生命周期内不可变；切换需重启进程或调用 `get_aesthetics("new_preset")` |
| **字体依赖系统安装** | 字幕字体须在系统中已安装，未找到时 pysubs2 会静默回退到默认字体 |
| **Logo 路径相对关系** | Logo path 相对于 `2_mid_processing/` 目录，不是项目根目录 |

### 改进方向

#### 🔴 高优先级

1. **`domain_manager.py` 完全退役**
   - 将 `prompts.py` 和 `_4_1_summarize.py` 中的 `from core.domain_manager import ...` 替换为 `from shared.domain import domain`
   - 然后将 `domain_manager.py` 移入 `_deprecated/` 目录

2. **`domains.yaml` 旧文件清理**
   - `configs/domains.yaml`（单文件领域 prompt 定义）已被 `configs/domains/<key>.yaml` 取代
   - 确认没有其他模块引用后，移入 `_deprecated/`

3. **`workflow_1_pre.py` AI 筛选 prompt**
   - 硬编码的 `categories = ["International|Politics|Tech|Life|Other"]` 应改为 `domain.get("screening.categories")`

#### 🟡 中优先级

4. **封面字体自动下载**
   - 当 `font_paths` 中的字体不存在时，自动从 Google Fonts 或预配置 URL 下载

5. **美学 preset 继承机制**
   - 支持 preset 继承（如 `sports` 继承 `news` 的编码配置，只覆盖封面和字幕）
   - YAML 语法：`_extends: news`

6. **多 Logo 支持**
   - 不同领域可能需要不同的 Logo 文件
   - 当前 `logo.path` 支持配置，但实际 Logo 文件需要手动放置

7. **预览工具**
   - 新建一个 CLI 命令 `python -m shared.aesthetics preview`，生成各 preset 的样例封面用于快速对比

#### 🟢 低优先级

8. **运行时验证**
   - 在 `AestheticsProfile.__init__` 中添加 schema 验证，确保所有必填字段都存在
   - 使用 Pydantic 或 jsonschema

9. **更多 preset**
   - `entertainment` — 娱乐风格（彩色渐变 + 活泼字体）
   - `tech` — 科技风格（冷色调 + 等宽字体）
   - `finance` — 财经风格（深蓝 + 严肃感）

10. **自动化测试**
    - 为 `shared.domain` 和 `shared.aesthetics` 编写 pytest 单元测试
    - 覆盖：正常加载、缺失文件、错误 preset 名称、嵌套查询边界

---

## 附录：三套 preset 视觉预览

| 参数 | 📰 news | ⚽ sports | 🎬 documentary |
|------|---------|-----------|-----------------|
| 字幕原文色 | 黄 #FFD400 | 黄 #FFFF00 | 灰白 #F0F0F0 |
| 字幕中文色 | 白 #FFFFFF | 白 #FFFFFF | 白 #FFFFFF |
| 字幕边框 | 背景框 | 描边 | 描边 |
| 封面高亮 | 金 #FFD700 | 红 #FF4444 | 米 #E8D5B7 |
| 封面强调 | 红 #E21918 | 蓝 #00AAFF | 深金 #8B6914 |
| 封面标签 | 🌐 GLOBAL NEWS | ⚡ SPORTS LIVE | 🎬 DOCUMENTARY |
| Logo | ✅ 启用 12% | ✅ 启用 10% | ❌ 关闭 |
| 日期水印 | ✅ 橙色 10秒 | ❌ 关闭 | ❌ 关闭 |
| 编码 CRF | 26 | 24 | 28 |
| 模糊度 | 2 | 1 | 4 |
