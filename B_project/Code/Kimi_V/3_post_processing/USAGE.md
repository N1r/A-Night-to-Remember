# 3_post_processing — 使用指南

多平台视频自动发布系统。将处理好的视频从 `storage/ready_to_publish/` 自动发布至抖音、小红书、快手、B站、腾讯视频。

---

## 目录结构

```
3_post_processing/
├── auto_publish_all.py       # 主控入口（一键启动全平台）
├── get_all_cookies.py        # Cookie 获取助手（首次运行必须）
├── publish_status.py         # 发布状态管理（publish_history.json）
├── workflow_3_post.py        # 工作流集成接口（供上游调用）
├── media/
│   └── metadata_generator.py # AI 驱动的多平台内容策划
└── uploaders/
    ├── _base.py              # 公共基础库（浏览器控制/反检测）
    ├── douyin_uploader.py    # 抖音（每日 ≤3 条）
    ├── xhs_uploader.py       # 小红书（每日 ≤3 条）
    ├── ks_uploader.py        # 快手（每日 ≤3 条）
    ├── bili_uploader.py      # B站（调用 biliup CLI）
    └── tencent_uploader.py   # 腾讯视频（全量无限制）
```

---

## 前置要求

### 1. 安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. B站需要额外安装 biliup

```bash
uv install biliup
# 或下载二进制版本：https://github.com/biliup/biliup
```

### 3. 配置环境变量

在项目根目录或 shell 配置文件中设置：

```bash
# AI 元数据生成 API Key（LongCat API，兼容 OpenAI 格式）
export LONGCAT_API_KEY="your_key_here"

# 浏览器模式（可选）
# 设置为 1 使用无头模式（服务器/CI 环境），默认 0（有界面）
export HEADLESS=0
```

---

## 快速开始

### Step 1：获取平台登录 Cookie（首次运行 & Cookie 过期时）

```bash
cd /path/to/project
python 3_post_processing/get_all_cookies.py
```

- 脚本会依次弹出抖音、小红书、快手、腾讯视频的浏览器窗口
- 在浏览器中手动扫码/账密登录
- 登录成功后脚本自动保存 Cookie 到 `storage/cookies/`，无需重复操作
- B站使用 biliup 管理账号，需单独运行 `biliup login`

只获取特定平台：

```bash
python 3_post_processing/get_all_cookies.py douyin
```

### Step 2：准备视频

将待发布视频放入 `storage/ready_to_publish/<文件夹名>/`：

```
storage/ready_to_publish/
└── 20240120_某某新闻/
    ├── output_sub.mp4      # 主视频（优先使用）
    ├── cover.jpg           # 封面（可选，支持 .jpg/.png/.webp）
    ├── trans.srt           # 字幕文件（可选，用于 AI 内容策划）
    └── metadata.json       # 元数据（可选，不存在会自动生成）
```

### Step 3：运行发布

```bash
# 全平台发布（默认：抖音 + 小红书 + 快手 + B站）
python 3_post_processing/auto_publish_all.py

# 测试模式（只处理最新一个视频）
python 3_post_processing/auto_publish_all.py --test-one

# 指定平台
python 3_post_processing/auto_publish_all.py --platforms=douyin,bilibili

# 指定浏览器模式
python 3_post_processing/auto_publish_all.py --headless
python 3_post_processing/auto_publish_all.py --no-headless
```

---

## AI 内容策划（metadata_generator.py）

发布前会自动为每个视频调用 AI 生成各平台专属文案，结果保存到 `metadata.json`。

### 触发条件

- `storage/ready_to_publish/<视频目录>/metadata.json` 不存在，**或**
- 文件存在但缺少某平台的 `platforms.<platform>` 字段

### 各平台生成策略

| 平台 | 策略 | 字段 |
|------|------|------|
| 小红书 | 第一人称真实分享，有故事感，自然使用 Emoji | `title` + `desc`（含话题标签） |
| 抖音 | 让人好奇的角度，避开模板套路 | `title` + `tags` |
| 快手 | 直白接地气，说清楚视频讲什么 | `title` + `tags` |
| B站 | 双语字幕风，说明来源和值得看的理由 | `title` + `desc` |

### 手动生成元数据

```bash
python 3_post_processing/media/metadata_generator.py
```

### 自定义 Excel 信息源

将 `storage/tasks/tasks_setting.xlsx` 按以下列格式填写，脚本会通过模糊匹配自动关联：

| 列名 | 说明 |
|------|------|
| `title` | 中文标题 |
| `rawtext` | 原始文本/推文 |
| `translated_text` | 翻译后文本 |
| `Category` | 分类 |
| `channel_name` | 来源频道 |

---

## 发布状态管理

### 查看发布历史

```
storage/tasks/publish_history.json
```

每个视频目录名对应一条记录：

```json
{
  "20240120_某某新闻": {
    "douyin": true,
    "xiaohongshu": false,
    "bilibili": true,
    "kuaishou": false,
    "tencent": false
  }
}
```

### 每日配额

每日每平台最多发布 3 条（腾讯无限制），记录在：

```
storage/tasks/daily_quota.json
```

超过 7 天的旧配额记录会自动清理。

### 全平台完成后自动归档

当一个视频目录的所有目标平台（抖音/小红书/快手/B站）均标记为 `true` 时，该目录自动移入：

```
storage/ready_to_publish/done/
```

---

## 各平台特殊说明

### 抖音

- 使用有界面模式（反检测严格）
- 在上传期间并行填写标题，不等上传完成
- Cookie 位于 `storage/cookies/douyin_cookies.json`

### 小红书

- 支持封面上传（`cover.jpg`）
- 描述框使用多选择器策略，兼容页面改版
- Cookie 位于 `storage/cookies/xiaohongshu_cookies.json`

### 快手

- 从 `metadata.json` 加载标题/标签
- 等待转码完成后再发布
- Cookie 位于 `storage/cookies/kuaishou_cookies.json`

### B站

- **不使用 Playwright**，调用 `biliup` CLI 工具
- 账号管理通过 `biliup login` 完成
- 默认定时发布（次日 8:00 起，每 45 分钟错峰）
- YAML 配置生成到 `storage/tasks/biliup_upload.yaml`

### 腾讯视频

- 全量上传（不限每日条数）
- 自动处理封面裁剪弹窗
- Cookie 位于 `storage/cookies/tencent_cookies.json`

---

## 反检测说明

所有 Playwright 上传器均内置以下反检测机制：

- 每个平台绑定固定的真实 Chrome UA（防指纹关联）
- 注入 stealth JS（隐藏 `navigator.webdriver` 等自动化特征）
- Bezier 曲线鼠标轨迹（`bezier_mouse_move`）
- 拟人化点击（随机偏移点击位置）
- 多步分段滚动（带水平漂移）
- 上传前后的页面预热（`warm_up_page`，模拟真实浏览行为）
- 打字速度随机化（支持突发输入和"思考"停顿）

---

## 常见问题

**Q：Cookie 过期怎么办？**

重新运行 `python 3_post_processing/get_all_cookies.py` 获取新 Cookie。

**Q：想重新发布某个已标记为成功的视频？**

编辑 `storage/tasks/publish_history.json`，将对应平台字段改为 `false`。

**Q：视频上传超时（5分钟）？**

检查网络连接。也可减少视频文件大小或在网络较好时重试。

**Q：如何单独测试某个上传器？**

```bash
cd 3_post_processing/uploaders
python douyin_uploader.py --test-one
python xhs_uploader.py --test-one
```

**Q：AI 元数据生成失败怎么办？**

检查 `LONGCAT_API_KEY` 是否正确设置。API 失败时会使用内置的备用文案，不影响发布。

**Q：B站 biliup 提示未登录？**

```bash
biliup login
# 按提示扫码登录，凭证保存在 ~/.config/biliup/ 下
```
