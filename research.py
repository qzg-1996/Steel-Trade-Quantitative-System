# -*- coding: utf-8 -*-
"""量化研究模块：因子有效性检验

核心问题：基差分位处于极端位置时，未来基差/价格会怎么走？
方法：把2019年以来每个交易日按基差分位分组，统计各组未来N日的实际表现。
这是把"基差低位会回归"这类产业经验，变成有数据依据的判断。
"""
import pandas as pd

from factors import basis_factor

# 分组边界（非均匀，业务导向：极端组看回归，中间组看趋势）
GROUPS = [
    ("极低 (<10%)", 0.0, 0.10),
    ("偏低 (10-30%)", 0.10, 0.30),
    ("中性 (30-70%)", 0.30, 0.70),
    ("偏高 (70-90%)", 0.70, 0.90),
    ("极高 (>90%)", 0.90, 1.01),
]
FORWARD_DAYS = [5, 20, 60]


def basis_regime_test(conn, spot_symbol):
    """基差分位分组检验

    返回 dict:
      summary: 每组 样本数/未来N日基差变化均值/胜率/期货收益
      curve:   完整因子序列（画图用）
    """
    df = basis_factor(conn, spot_symbol).dropna(subset=["basis_pct"]).copy()
    if len(df) < 300:
        return None

    for n in FORWARD_DAYS:
        df[f"basis_chg_{n}"] = df["basis"].shift(-n) - df["basis"]          # 未来基差变化
        df[f"fut_ret_{n}"] = df["close"].shift(-n) / df["close"] - 1        # 未来期货收益

    rows = []
    for label, lo, hi in GROUPS:
        g = df[(df["basis_pct"] >= lo) & (df["basis_pct"] < hi)]
        row = {"分组": label, "样本数": len(g)}
        for n in FORWARD_DAYS:
            chg = g[f"basis_chg_{n}"].dropna()
            ret = g[f"fut_ret_{n}"].dropna()
            row[f"{n}日基差变化"] = round(chg.mean(), 1) if len(chg) else None
            row[f"{n}日走强胜率"] = f"{(chg > 0).mean() * 100:.0f}%" if len(chg) else "-"
            row[f"{n}日期货收益"] = f"{ret.mean() * 100:+.1f}%" if len(ret) else "-"
        rows.append(row)
    return {"summary": pd.DataFrame(rows), "curve": df}


SPREAD_GROUPS = [
    ("深contango (<-50)", -9999, -50),
    ("浅contango (-50~0)", -50, 0),
    ("浅back (0~50)", 0, 50),
    ("深back (>50)", 50, 9999),
]


def spread_regime_test(conn, base="RB"):
    """月差结构分组检验：不同月差状态下，未来月差如何演化"""
    from factors import month_spread
    df = month_spread(conn, base).dropna().copy()
    if len(df) < 200:
        return None
    for n in FORWARD_DAYS:
        df[f"chg_{n}"] = df["spread"].shift(-n) - df["spread"]
    rows = []
    for label, lo, hi in SPREAD_GROUPS:
        g = df[(df["spread"] >= lo) & (df["spread"] < hi)]
        row = {"分组": label, "样本数": len(g)}
        for n in FORWARD_DAYS:
            chg = g[f"chg_{n}"].dropna()
            row[f"{n}日月差变化"] = round(chg.mean(), 1) if len(chg) else None
            row[f"{n}日走扩胜率"] = f"{(chg > 0).mean() * 100:.0f}%" if len(chg) else "-"
        rows.append(row)
    return pd.DataFrame(rows)


def similar_episodes(conn, spot_symbol, pct_threshold=0.10, min_gap=20, topn=10):
    """历史相似行情复盘：找出基差分位曾处极端区的每个独立时段，
    列出每次后来的实际走势——案例级证据，比统计数字更直观。

    pct_threshold: 分位阈值（<0.10 为极端低位）
    min_gap: 两个时段间隔不足N个交易日则合并（同一波行情不重复计数）
    """
    df = basis_factor(conn, spot_symbol).dropna(subset=["basis_pct"]).reset_index(drop=True)
    if len(df) < 300:
        return pd.DataFrame()

    extreme = df["basis_pct"] < pct_threshold
    # 识别独立时段：极端日与前一个极端日间隔>min_gap天，视为新时段起点
    starts = []
    last_idx = -min_gap - 1
    for i, e in enumerate(extreme):
        if e and i - last_idx > min_gap:
            starts.append(i)
            last_idx = i
        elif e:
            last_idx = i

    rows = []
    for i in starts[-topn * 2:]:
        r = df.iloc[i]
        row = {"日期": r["date"].strftime("%Y-%m-%d"),
               "当时基差": round(r["basis"], 0),
               "当时期货": round(r["close"], 0),
               "当时分位": f"{r['basis_pct'] * 100:.0f}%"}
        for n in (20, 60):
            j = i + n
            if j < len(df):
                row[f"+{n}日基差"] = round(df.iloc[j]["basis"] - r["basis"], 0)
                row[f"+{n}日期货"] = f"{(df.iloc[j]['close'] / r['close'] - 1) * 100:+.1f}%"
            else:
                row[f"+{n}日基差"] = None
                row[f"+{n}日期货"] = "未到期"
        rows.append(row)
    out = pd.DataFrame(rows)
    return out.sort_values("日期", ascending=False).head(topn)


def interpret(summary):
    """根据检验结果自动生成中文结论（模板化，不臆造）"""
    if summary is None or summary.empty:
        return ["样本不足，无法得出结论。"]
    s = summary.set_index("分组")
    out = []
    low, high = s.loc["极低 (<10%)"], s.loc["极高 (>90%)"]
    if low["样本数"] >= 20 and low["20日基差变化"] is not None:
        win = low["20日走强胜率"]
        chg = low["20日基差变化"]
        verdict = "支持" if chg > 0 else "不支持"
        out.append(
            f"「低位回归」检验：基差分位低于10%共出现{int(low['样本数'])}次，"
            f"之后20日基差平均变化{chg:+.1f}元/吨，走强胜率{win}——数据{verdict}"
            f"「基差低位均值回归」的经验假设。")
    if high["样本数"] >= 20 and high["20日基差变化"] is not None:
        out.append(
            f"「高位回落」检验：基差分位高于90%共出现{int(high['样本数'])}次，"
            f"之后20日基差平均变化{high['20日基差变化']:+.1f}元/吨，"
            f"走弱概率{100 - int(high['20日走强胜率'].rstrip('%'))}%。")
    mid_chg = s.loc["中性 (30-70%)", "20日基差变化"]
    if mid_chg is not None and abs(mid_chg) < abs(low.get("20日基差变化") or 0):
        out.append("中性区分位（30-70%）的基差变化明显小于极端组，"
                   "说明分位信号在极端位置才有预测力——这符合均值回归逻辑。")
    out.append("注意：以上为历史统计规律，样本期2019年至今，不构成未来收益保证。")
    return out
