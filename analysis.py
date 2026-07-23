# -*- coding: utf-8 -*-
"""指标计算：基差、基差历史分位、卷螺差"""
import pandas as pd

from config import SPOT


def basis_df(conn, spot_symbol):
    """现货价 + 期货收盘价 + 基差 明细表（按日期升序）"""
    _, fut_symbol = SPOT[spot_symbol]
    spot = pd.read_sql("SELECT date, spot_price FROM spot_daily WHERE symbol=?",
                       conn, params=(spot_symbol,), parse_dates=["date"])
    fut = pd.read_sql("SELECT date, close FROM futures_daily WHERE symbol=?",
                      conn, params=(fut_symbol,), parse_dates=["date"])
    df = pd.merge(spot, fut, on="date", how="inner").sort_values("date")
    df["basis"] = (df["spot_price"] - df["close"]).round(2)
    return df


def basis_summary(conn, spot_symbol):
    """基差摘要：最新值、近一年分位、历史分位、近一年区间"""
    df = basis_df(conn, spot_symbol)
    if df.empty:
        return None
    latest = df.iloc[-1]
    one_year = df[df["date"] >= df["date"].max() - pd.Timedelta(days=365)]
    return {
        "date": latest["date"].strftime("%Y-%m-%d"),
        "spot": latest["spot_price"],
        "futures": latest["close"],
        "basis": latest["basis"],
        "pct_1y": round((one_year["basis"] <= latest["basis"]).mean() * 100, 1),
        "pct_all": round((df["basis"] <= latest["basis"]).mean() * 100, 1),
        "max_1y": one_year["basis"].max(),
        "min_1y": one_year["basis"].min(),
    }


def hc_rb_spread(conn):
    """卷螺差：热卷期货 - 螺纹期货（主力连续）"""
    hc = pd.read_sql("SELECT date, close FROM futures_daily WHERE symbol='HC0'",
                     conn, parse_dates=["date"])
    rb = pd.read_sql("SELECT date, close FROM futures_daily WHERE symbol='RB0'",
                     conn, parse_dates=["date"])
    df = pd.merge(hc, rb, on="date", suffixes=("_hc", "_rb"))
    df["spread"] = (df["close_hc"] - df["close_rb"]).round(2)
    return df
