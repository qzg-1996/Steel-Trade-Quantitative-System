# -*- coding: utf-8 -*-
"""全局配置：品种、路径、参数"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
DB_PATH = os.path.join(DATA_DIR, "steel_quant.db")
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 期货品种：新浪连续合约代码 -> 中文名
FUTURES = {
    "RB0": "螺纹钢",
    "HC0": "热轧卷板",
    "I0": "铁矿石",
    "J0": "焦炭",
    "JM0": "焦煤",
}

# 现货品种（生意社）：现货代码 -> (中文名, 对应期货连续合约)
SPOT = {
    "RB": ("螺纹钢", "RB0"),
    "HC": ("热轧卷板", "HC0"),
}

# 现货数据起始日（生意社按交易日逐日抓取，首次运行从此日期补齐）
SPOT_START_DATE = "2019-01-01"

# 请求间隔（秒），防止被数据源限流
REQUEST_INTERVAL = (0.5, 1.0)

# 图表默认展示最近多少个交易日
CHART_DAYS = 120
