# SMC 智能资金分析系统

基于 Smart Money Concepts 的单向做多策略分析工具。覆盖 A股 + 港股，一键完成数据获取、SMC分析、信号生成、图表输出。

---

## 快速开始

```bash
conda activate smc_env
pip install -r requirements.txt   # 首次使用
```

### 一键运行

```bash
# 完整流程: 获取数据 → 分析 → 生成报告 → 启动 Web
python one_click_v2.py --web

# 仅查看已有分析结果 (秒开)
python one_click_v2.py --skip-fetch --web
```

浏览器打开 `http://localhost:8080`，即可查看买入信号 Top 20 及对应的 SMC 图表。

---

## 命令参数

| 参数 | 缩写 | 说明 |
|------|------|------|
| `--a-stocks N` | `-a N` | A股数量，默认 500 |
| `--hk-stocks N` | `-k N` | 港股数量，默认 200 |
| `--force` | `-f` | 强制重新获取全部数据 |
| `--skip-fetch` | | 跳过数据获取，只分析已有数据 |
| `--no-charts` | | 不生成图表（加速分析） |
| `--web` | `-w` | 完成后启动 Web 界面 |
| `--port N` | `-p N` | Web 端口，默认 8080 |

### 常用组合

```bash
python one_click_v2.py                    # 默认: A股500 + 港股200
python one_click_v2.py -a 50 -k 20 -w    # 小样本测试 + 自动开 Web
python one_click_v2.py --skip-fetch       # 只分析，不拉数据
python one_click_v2.py --skip-fetch -w    # 直接看已有结果
python one_click_v2.py --force -w         # 全部重新获取 + 查看
```

---

## Web 界面

Web 页面从最新的 `output/reports/smc_report_*.xlsx` 读取信号强度前 20 的买入信号：

- 每张卡片显示: 代码、名称、信号强度、胜率、盈亏比、入场/止损/目标价、OB重叠度
- 点击卡片展开对应的 SMC 分析图表 (Plotly 交互式)
- 前 3 名用绿色高亮

也可以单独启动 Web（不跑分析）:

```bash
python one_click_v2.py --skip-fetch --web
# 或
python -c "from src.web.app import run_app; run_app()"
```

---

## 项目结构

```
SMC_tidy/
├── one_click_v2.py          # 入口脚本 (获取 + 分析 + Web)
├── config.yaml              # 配置文件
├── requirements.txt         # 依赖
├── src/
│   ├── core/
│   │   ├── engine.py        # 向量化 SMC 引擎
│   │   ├── signals.py       # 信号生成 (单向做多)
│   │   ├── visualizer.py    # 暗色主题 Plotly 图表
│   │   └── types.py         # 数据类型
│   ├── orchestrator.py      # 统一调度器
│   ├── config.py            # 配置管理
│   ├── data_fetch/          # akshare 数据获取
│   ├── web/app.py           # FastAPI Web 应用
│   ├── report/              # 报告生成
│   └── smc_analysis/        # 策略分析
├── data/
│   ├── raw/                 # 原始日线 CSV
│   └── processed/           # SMC 格式 CSV
└── output/
    ├── charts/              # 个股图表 HTML
    └── reports/             # Excel/HTML 报告
```

---

## 信号说明

### 评分维度 (满分 100)

| 维度 | 分值 | 说明 |
|------|------|------|
| 区域匹配 | 25 | 折价区加分 |
| 趋势匹配 | 20 | 看涨趋势加分 |
| OB 距离 | 20 | 价格接近 OB 加分 |
| OB 叠加 | 15 | 多个 OB 重叠加分 |
| FVG 一致 | 10 | 看涨 FVG 加分 |
| 结构突破 | 10 | BOS/CHoCH 确认加分 |

### 信号强度参考

| 强度 | 等级 | 建议 |
|------|------|------|
| 70+ | 强 | 重点关注 |
| 50-69 | 中 | 结合其他因素判断 |
| 40-49 | 弱 | 谨慎 |
| <40 | 无 | 等待 |

### 交易参数

- **入场价**: OB 底部
- **止损**: 入场 - ATR 缓冲
- **目标1**: 2R | **目标2**: 3R
- **胜率预估**: 35%-70%

---

## Python API

```python
from src.orchestrator import SMCOrchestrator
import pandas as pd

orch = SMCOrchestrator()
df = pd.read_csv("data/processed/000001_平安银行_daily_smc.csv")
result = orch.analyze(df, symbol="000001", name="平安银行")

sig = result.signal
print(f"强度: {sig.signal_strength}, 入场: {sig.entry_price}, 止损: {sig.stop_loss}")
```

---

## 配置 (config.yaml)

```yaml
smc_analysis:
  swing_length: 50        # 波段识别长度

data_fetch:
  start_date_days: 720    # 历史天数
  batch_delay: 0.5        # 请求间隔

chart:
  height: 900
  show_volume: true

web:
  host: "0.0.0.0"
  port: 8080
```

---

## 数据来源

A股和港股数据均通过 [akshare](https://github.com/akfamily/akshare) 免费获取。

- A股行情获取约需 2-3 分钟（全量扫描），历史数据逐只获取
- 已有数据自动跳过，不会重复下载
- `--force` 参数可强制刷新全部数据

---

*本系统仅供学习研究，不构成投资建议。*
