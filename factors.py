# -*- coding: utf-8 -*-
"""因子库：把产业逻辑变成可计算的序列

因子是量化的心脏——每个因子对应一个可检验的产业假设：
  基差因子：基差偏离历史常态后会均值回归
  利润因子：盘面利润过高/过低会驱动钢厂增减产，反向作用于价格
  动量因子：价格短期存在趋势惯性
"""
import pandas as pd

from config import SPOT

ROLL_WINDOW = 252  # 滚动分位窗口：约一年交易日


def basis_factor(conn, spot_symbol, window=ROLL_WINDOW):
    """基差因子：基差值 + 滚动一年分位（0~1）

    分位 = 当前基差在过去一年中的相对位置，0.05 即近一年 5% 分位（极低）。
    """
    df = _basis_df(conn, spot_symbol)
    if df.empty:
        return df
    df["basis_pct"] = df["basis"].rolling(window).apply(
        lambda x: (x <= x.iloc[-1]).mean(), raw=False)
    return df


def _basis_df(conn, spot_symbol):
    """现货-期货合并表（内部用）"""
    _, fut_symbol = SPOT[spot_symbol]
    spot = pd.read_sql("SELECT date, spot_price FROM spot_daily WHERE symbol=?",
                       conn, params=(spot_symbol,), parse_dates=["date"])
    fut = pd.read_sql("SELECT date, close FROM futures_daily WHERE symbol=?",
                      conn, params=(fut_symbol,), parse_dates=["date"])
    df = pd.merge(spot, fut, on="date", how="inner").sort_values("date")
    df["basis"] = (df["spot_price"] - df["close"]).round(2)
    return df.reset_index(drop=True)


def futures_close(conn, fut_symbol):
    """单品种期货收盘价序列"""
    return pd.read_sql("SELECT date, close FROM futures_daily WHERE symbol=?",
                       conn, params=(fut_symbol,), parse_dates=["date"])


def profit_factor(conn):
    """螺纹盘面毛利因子 = 螺纹 - 1.6×铁矿 - 0.5×焦炭（元/吨）

    产业含义：1吨粗钢约耗1.6吨铁矿+0.5吨焦炭。
    未扣固定加工费（只影响绝对值，不影响相对高低），用于观察利润趋势与极值。
    """
    rb = futures_close(conn, "RB0").rename(columns={"close": "rb"})
    i = futures_close(conn, "I0").rename(columns={"close": "i"})
    j = futures_close(conn, "J0").rename(columns={"close": "j"})
    df = rb.merge(i, on="date").merge(j, on="date")
    df["profit"] = (df["rb"] - 1.6 * df["i"] - 0.5 * df["j"]).round(1)
    return df[["date", "profit"]]


def momentum(conn, fut_symbol, n=20):
    """动量因子：N日涨跌幅（%）"""
    df = futures_close(conn, fut_symbol)
    df[f"mom{n}"] = (df["close"].pct_change(n) * 100).round(2)
    return df


def _pair_spread(conn, near, far, start, end):
    """两个合约在指定窗口的价差序列（近月-远月）"""
    n = pd.read_sql("SELECT date, close FROM futures_daily WHERE symbol=? AND date BETWEEN ? AND ?",
                    conn, params=(near, start, end), parse_dates=["date"])
    f = pd.read_sql("SELECT date, close FROM futures_daily WHERE symbol=? AND date BETWEEN ? AND ?",
                    conn, params=(far, start, end), parse_dates=["date"])
    if len(n) < 5 or len(f) < 5:
        return None
    m = pd.merge(n, f, on="date", suffixes=("_n", "_f"))
    m["spread"] = (m["close_n"] - m["close_f"]).round(1)
    return m[["date", "spread"]]


def month_spread(conn, base="RB"):
    """主力月差因子（近月-远月），跟随螺纹/热卷主力1/5/10月轮换规律：
      1-3月看 当年05合约-当年10合约；4-9月看 当年10合约-次年01合约；
      10-12月看 次年01合约-次年05合约。
    正值=back（近强远弱，现货紧），负值=contango（近弱远强，预期宽松）。
    """
    rows = []
    for y in range(2021, 2028):
        yy, ny = y % 100, (y + 1) % 100
        segs = [(f"{y}-01-01", f"{y}-03-31", f"{base}{yy:02d}05", f"{base}{yy:02d}10"),
                (f"{y}-04-01", f"{y}-09-30", f"{base}{yy:02d}10", f"{base}{ny:02d}01"),
                (f"{y}-10-01", f"{y}-12-31", f"{base}{ny:02d}01", f"{base}{ny:02d}05")]
        for start, end, near, far in segs:
            df = _pair_spread(conn, near, far, start, end)
            if df is not None:
                rows.append(df)
    if not rows:
        return pd.DataFrame(columns=["date", "spread"])
    out = pd.concat(rows).drop_duplicates("date").sort_values("date")
    return out.reset_index(drop=True)


def term_structure(conn, base="RB", topn=4):
    """当前期限结构：最新交易日各活跃合约收盘价、持仓、月差"""
    latest = pd.read_sql(
        "SELECT MAX(date) d FROM futures_daily WHERE symbol=?", conn,
        params=(f"{base}0",))["d"][0]
    df = pd.read_sql(
        "SELECT symbol, close, hold, volume FROM futures_daily "
        "WHERE date=? AND symbol LIKE ? AND symbol != ?",
        conn, params=(latest, f"{base}%", f"{base}0"))
    df = df[df["symbol"].str.len() == 6].sort_values("symbol")
    df = df[df["hold"] > 1000].head(topn)  # 剔除不活跃合约
    return latest, df.reset_index(drop=True)
