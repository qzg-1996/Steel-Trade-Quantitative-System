# -*- coding: utf-8 -*-
"""套保信号记分卡：多因子合成，规则全透明

三因子打分（基于v0.3因子检验结论设计）：
  因子1 基差分位：<10%→+2（期货贵，卖保好位置）；10-30%→+1；30-70%→0；
                  70-90%→-1；>90%→-2（期货便宜，不宜追保）
  因子2 月差结构：contango（近低远高）→+1（卖远月价格更有利）；
                  back（近高远低）→-1
  因子3 利润分位：>90%→+1（利润高→增产压力→价格承压）；
                  <10%→-1；其余→0
总分 -4~+4：≥+2 绿灯（卖保有利窗口）；≤-2 红灯（不宜追保）；其余黄灯观望。
每个信号自动落库 signals 表，用于事后胜率复盘——信号不行就改规则。
"""
import pandas as pd

from factors import basis_factor, month_spread, profit_factor

LEVELS = {
    "green": ("🟢 绿灯", "卖出套保有利窗口"),
    "yellow": ("🟡 黄灯", "中性观望"),
    "red": ("🔴 红灯", "不宜追保/考虑减仓"),
}


def hedge_scorecard(conn, spot_symbol="RB", persist=True):
    """计算当日套保信号记分卡并落库"""
    # 因子1：基差分位
    bdf = basis_factor(conn, spot_symbol).dropna(subset=["basis_pct"])
    if bdf.empty:
        return None
    bp = float(bdf["basis_pct"].iloc[-1])
    date = bdf["date"].iloc[-1].strftime("%Y-%m-%d")
    basis_score = 2 if bp < 0.10 else 1 if bp < 0.30 else 0 if bp < 0.70 \
        else -1 if bp < 0.90 else -2

    # 因子2：月差结构
    sp = month_spread(conn, "RB" if spot_symbol == "RB" else "HC")
    spread = float(sp["spread"].iloc[-1]) if not sp.empty else 0.0
    spread_score = 1 if spread < 0 else (-1 if spread > 0 else 0)

    # 因子3：利润分位（近一年）
    pf = profit_factor(conn)
    recent = pf["profit"].tail(252)
    pp = float((recent <= recent.iloc[-1]).mean()) if len(recent) else 0.5
    profit_score = 1 if pp > 0.90 else (-1 if pp < 0.10 else 0)

    total = basis_score + spread_score + profit_score
    key = "green" if total >= 2 else ("red" if total <= -2 else "yellow")
    icon, desc = LEVELS[key]

    card = {
        "date": date, "total": total, "icon": icon, "desc": desc,
        "basis_pct": round(bp * 100, 1), "basis_score": basis_score,
        "spread": spread, "spread_score": spread_score,
        "profit_pct": round(pp * 100, 1), "profit_score": profit_score,
    }

    if persist:
        conn.execute("""INSERT OR REPLACE INTO signals
            (date, symbol, basis_pct, basis_score, spread, spread_score,
             profit_pct, profit_score, total, level) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (date, spot_symbol, card["basis_pct"], basis_score, spread,
             spread_score, card["profit_pct"], profit_score, total, icon + " " + desc))
        conn.commit()
    return card


def signal_history(conn, limit=30):
    """信号历史记录（用于复盘）"""
    return pd.read_sql(
        "SELECT * FROM signals ORDER BY date DESC LIMIT ?", conn, params=(limit,))
