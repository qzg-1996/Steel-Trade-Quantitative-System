# -*- coding: utf-8 -*-
"""热点消息模块：抓取财经快讯 -> 黑色系过滤 -> 分类入库 -> 导出（供AI解读）

数据源（全部免费）：
  1. 东方财富全球财经快讯（约200条/次，含标题摘要链接）
  2. 新浪财经7x24快讯（约20条/次，时效最强）
  3. 上海金属网金属快讯（行业相关度高）
过滤原则：宁缺毋滥——高置信词直接命中；条件词须与行业字共现；黑名单直接排除。
"""
import hashlib
import os
import warnings
import pandas as pd

warnings.filterwarnings("ignore")

from config import OUTPUT_DIR

# ---------------- 词库（可自行增删） ----------------
# 高置信词：出现即判定为黑色系相关
STRONG = ["螺纹钢", "热轧卷板", "热卷", "冷轧", "中厚板", "线材", "盘螺", "钢坯", "废钢",
          "铁矿石", "焦炭", "焦煤", "钢材", "钢铁", "粗钢", "钢厂", "高炉", "电炉", "铁水",
          "表观消费", "黑色系", "不锈钢", "上期所", "大商所", "郑商所",
          # 宏观直通词（金融术语，误报率极低）
          "LPR", "降准", "降息", "MLF", "逆回购", "美联储", "议息", "CPI", "PPI", "PMI",
          "社融", "M2", "专项债"]
# 条件词：须与行业字共现才算命中（防止"导弹库存"类误报）
COND = ["库存", "累库", "去库", "限产", "压减", "检修", "复产", "减产",
        "成交", "基建", "地产", "房地产", "楼市"]
INDUSTRY_CHARS = "钢铁材矿焦炭煤轧"
# 黑名单：出现即排除
BLACK = ["导弹", "弹药", "芯片", "半导体", "医药", "药房", "白酒", "养殖",
         "股价", "机器人", "票房", "体育", "足球", "世界杯"]

# 分类标签（按优先级从上到下）
CATS = {
    "产业政策": ["限产", "压减", "减产", "复产", "检修", "去产能", "环保", "粗钢", "产能", "超低排放"],
    "地产基建": ["地产", "房地产", "楼市", "基建", "专项债"],
    "宏观货币": ["LPR", "降准", "降息", "MLF", "逆回购", "美联储", "议息", "CPI", "PPI", "PMI", "社融", "M2"],
    "原料动态": ["铁矿", "焦炭", "焦煤", "废钢", "钢坯", "铁水"],
    "钢材市场": ["螺纹", "热卷", "热轧", "冷轧", "钢材", "钢铁", "钢厂", "高炉", "电炉",
                "库存", "累库", "去库", "成交", "中厚板", "线材", "盘螺", "不锈钢"],
}


def classify(text):
    """返回分类标签；不相关返回 None"""
    if any(b in text for b in BLACK):
        return None
    strong_hit = any(k in text for k in STRONG)
    cond_hit = any(k in text for k in COND) and any(w in text for w in INDUSTRY_CHARS)
    if not (strong_hit or cond_hit):
        return None
    for cat, kws in CATS.items():
        if any(k in text for k in kws):
            return cat
    return "钢材市场"


# ---------------- 影响分析（规则初判，供参考） ----------------
# 利多词：以"对成材价格影响"为基准
BULL_WORDS = ["限产", "压减", "减产", "停产", "检修", "环保督察", "超低排放", "去库",
              "降准", "降息", "宽松", "专项债", "基建", "刺激", "提振", "利多",
              "上涨", "大涨", "提价", "新高", "成交放量", "需求回暖",
              "下调存款准备金", "降低存款准备金", "LPR下调", "中标利率下调"]
# 利空词
BEAR_WORDS = ["复产", "增产", "累库", "库存攀升", "库存增加", "成交低迷", "需求疲弱",
              "加息", "缩表", "收紧", "降价", "下跌", "大跌", "新低", "利空", "亏损"]
# 影响品种词
TARGET_WORDS = {
    "螺纹/建材": ["螺纹", "线材", "盘螺", "建材", "钢筋"],
    "热卷/板材": ["热卷", "热轧", "冷轧", "中厚板", "板材"],
    "原料(铁矿/双焦)": ["铁矿", "焦炭", "焦煤", "废钢", "钢坯", "铁水"],
    "宏观/全行业": ["LPR", "降准", "降息", "美联储", "PMI", "CPI", "PPI", "社融",
                "M2", "专项债", "粗钢", "钢铁", "钢材"],
}
# 影响路径模板（按类别）
PATH_TPL = {
    "产业政策": "供应端政策 → 影响产量预期 → 作用于成材价格",
    "地产基建": "需求端政策 → 影响消费预期 → 作用于成材价格",
    "宏观货币": "流动性/利率 → 影响商品整体估值与情绪",
    "原料动态": "成本端变化 → 通过成本支撑传导至成材",
    "钢材市场": "现货供需直接信号 → 影响基差与价格节奏",
}


def impact_analysis(title, summary, category):
    """消息影响分析（规则初判）：返回 品种/方向/程度/路径

    程度分级规则：
      强 = 国家级产业政策、央行货币政策
      中 = 库存产量数据、地方/行业政策、基建地产政策
      弱 = 市场动态、企业个体新闻
    """
    text = (title or "") + "。" + (summary or "")

    target = "全行业"
    for t, kws in TARGET_WORDS.items():
        if any(k in text for k in kws):
            target = t
            break

    bull = sum(1 for w in BULL_WORDS if w in text)
    bear = sum(1 for w in BEAR_WORDS if w in text)
    if bull > bear:
        direction = "偏多"
    elif bear > bull:
        direction = "偏空"
    else:
        direction = "中性"

    if category in ("产业政策", "宏观货币"):
        level = "强"
    elif category in ("地产基建", "原料动态"):
        level = "中"
    else:
        level = "弱"
    # 数据类消息降一级（例行数据影响递减）
    if any(w in text for w in ["库存", "产量", "成交"]) and category == "钢材市场":
        level = "中"

    path = PATH_TPL.get(category, "")
    return {"品种": target, "方向": direction, "程度": level, "路径": path}


def _mk_id(source, pub_time, title):
    return hashlib.md5(f"{source}|{pub_time}|{title}".encode("utf-8")).hexdigest()


def fetch_news(conn, verbose=True):
    """抓取全部消息源，过滤后入库，返回新增条数"""
    import akshare as ak
    new_count = 0

    def save(source, df, title_col, time_col, summary_col=None, url_col=None):
        nonlocal new_count
        for _, r in df.iterrows():
            title = str(r[title_col]).strip()
            summary = str(r[summary_col]).strip() if summary_col else title
            text = title + "。" + summary
            cat = classify(text)
            if cat is None:
                continue
            pub_time = str(r[time_col])[:19]
            url = str(r[url_col]) if url_col else ""
            nid = _mk_id(source, pub_time, title)
            cur = conn.execute(
                "INSERT OR IGNORE INTO news VALUES(?,?,?,?,?,?,?,?)",
                (nid, source, title, summary, text, pub_time, cat, url))
            new_count += cur.rowcount

    # 源1：东方财富全球财经快讯
    try:
        em = ak.stock_info_global_em()
        save("东方财富", em, "标题", "发布时间", "摘要", "链接")
        if verbose:
            print(f"[消息] 东方财富快讯抓取 {len(em)} 条")
    except Exception as e:
        if verbose:
            print(f"[消息] 东方财富源失败：{e}")

    # 源2：新浪财经7x24
    try:
        sina = ak.stock_info_global_sina()
        save("新浪财经", sina, "内容", "时间")
        if verbose:
            print(f"[消息] 新浪7x24抓取 {len(sina)} 条")
    except Exception as e:
        if verbose:
            print(f"[消息] 新浪源失败：{e}")

    # 源3：上海金属网金属快讯
    try:
        shmet = ak.futures_news_shmet()
        save("上海金属网", shmet, "内容", "发布时间")
        if verbose:
            print(f"[消息] 上海金属网抓取 {len(shmet)} 条")
    except Exception as e:
        if verbose:
            print(f"[消息] 上海金属网源失败：{e}")

    conn.commit()
    if verbose:
        print(f"[消息] 过滤入库：新增 {new_count} 条黑色系相关消息")
    return new_count


def get_news(conn, days=7, category=None):
    """查询消息库"""
    sql = "SELECT source, title, summary, pub_time, category, url FROM news"
    conds, params = [], []
    if days:
        sql += " WHERE pub_time >= datetime('now', 'localtime', ?)"
        params.append(f"-{days} days")
        if category and category != "全部":
            sql += " AND category=?"
            params.append(category)
    elif category and category != "全部":
        sql += " WHERE category=?"
        params.append(category)
    sql += " ORDER BY pub_time DESC"
    return pd.read_sql(sql, conn, params=params)


def export_news_txt(conn, days=1):
    """导出最近N天消息为txt，方便粘贴给AI（Kimi）做深度解读"""
    df = get_news(conn, days=days)
    if df.empty:
        return None
    path = os.path.join(OUTPUT_DIR, f"热点消息_近{days}天.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"黑色系热点消息汇总（近{days}天，共{len(df)}条）\n")
        f.write("=" * 50 + "\n\n")
        for _, r in df.iterrows():
            f.write(f"【{r['category']}】{r['pub_time']}（{r['source']}）\n")
            f.write(f"{r['title']}\n")
            if r["summary"] and r["summary"] != r["title"]:
                f.write(f"{r['summary']}\n")
            f.write("\n")
        f.write("=" * 50 + "\n")
        f.write("请将以上内容粘贴给Kimi，请其结合当日行情做利多利空解读。\n")
    return path
