# -*- coding: utf-8 -*-
"""信号回测：把三因子信号灯放到历史里跑一遍，看它真实的成绩单

两部分：
  1. 分组统计：历史上每次亮绿灯/红灯之后，期货实际怎么走（和因子检验同口径）
  2. 净值模拟：绿灯做空、红灯做多、黄灯空仓的机械执行净值 vs 买入持有

诚实声明（页面同步标注）：
  - 基于主力连续合约价格，换月日收益存在跳空噪声（已按±8%阈值剔除异常日）
  - 未计手续费与滑点；信号次日才建仓（无前视偏差）
  - 回测有效 ≠ 未来有效，样本期2021年起（三因子数据交集）
"""
import numpy as np
import pandas as pd

from factors import basis_factor, month_spread, profit_factor

ROLL = 252


def _rolling_pct(s, w=ROLL):
    return s.rolling(w).apply(lambda x: (x <= x.iloc[-1]).mean(), raw=False)


def _build_frame(conn, symbol):
    base = "RB" if symbol == "RB" else "HC"
    bdf = basis_factor(conn, symbol)[["date", "basis", "close", "basis_pct"]]
    ms = month_spread(conn, base).rename(columns={"spread": "ms"})
    pf = profit_factor(conn)
    pf["profit_pct"] = _rolling_pct(pf["profit"])
    df = (bdf.merge(ms, on="date", how="left")
             .merge(pf[["date", "profit_pct"]], on="date", how="left")
             .dropna(subset=["basis_pct", "ms", "profit_pct"])
             .reset_index(drop=True))
    bs = df["basis_pct"].map(lambda p: 2 if p < .1 else 1 if p < .3 else 0 if p < .7 else -1 if p < .9 else -2)
    ss = df["ms"].map(lambda s: 1 if s < 0 else (-1 if s > 0 else 0))
    ps = df["profit_pct"].map(lambda p: 1 if p > .9 else (-1 if p < .1 else 0))
    df["score"] = bs + ss + ps
    df["signal"] = df["score"].map(lambda t: "green" if t >= 2 else ("red" if t <= -2 else "yellow"))
    return df


def signal_report(conn, symbol="RB"):
    """各信号的后续表现统计"""
    df = _build_frame(conn, symbol)
    rows = []
    labels = {"green": "🟢 绿灯（卖保窗口）", "yellow": "🟡 黄灯（观望）", "red": "🔴 红灯（不宜追保）"}
    for sig in ("green", "yellow", "red"):
        g = df[df["signal"] == sig]
        row = {"信号": labels[sig], "天数": len(g), "占比": f"{len(g) / len(df) * 100:.0f}%"}
        for n in (20, 60):
            r = (g["close"].shift(-n) / g["close"] - 1).dropna()
            if len(r):
                row[f"{n}日期货均值"] = f"{r.mean() * 100:+.2f}%"
                row[f"{n}日下跌概率"] = f"{(r < 0).mean() * 100:.0f}%"
        rows.append(row)
    return pd.DataFrame(rows)


def nav_backtest(conn, symbol="RB"):
    """净值模拟：按信号灯真实语义——绿灯卖保（空头验证）、其余空仓。

    重要：红灯是"不宜追保"的防御信号，不是做多信号。
    历史回测已证明熊市中"期货便宜"不构成做多理由（会被均线/趋势碾压），
    因此红灯不反向开仓。"""
    df = _build_frame(conn, symbol).copy()
    df["daily_ret"] = df["close"].pct_change()
    # 换月噪声剔除：日收益超±8%视为换月异常（螺纹正常日波动极少超此值）
    df.loc[df["daily_ret"].abs() > 0.08, "daily_ret"] = 0.0
    pos = df["signal"].map({"green": -1, "yellow": 0, "red": 0}).shift(1).fillna(0)
    df["strategy_ret"] = pos * df["daily_ret"]
    df["nav"] = (1 + df["strategy_ret"]).cumprod()
    df["bench"] = (1 + df["daily_ret"].fillna(0)).cumprod()

    rets = df["strategy_ret"].dropna()
    ann = (df["nav"].iloc[-1]) ** (252 / len(df)) - 1
    sharpe = rets.mean() / rets.std() * np.sqrt(252) if rets.std() > 0 else 0
    dd = (df["nav"] / df["nav"].cummax() - 1).min()
    win_days = (rets[rets != 0] > 0).mean()
    stats = {"年化收益": f"{ann * 100:+.1f}%", "夏普比率": f"{sharpe:.2f}",
             "最大回撤": f"{dd * 100:.1f}%", "持仓日胜率": f"{win_days * 100:.0f}%",
             "期末净值": f"{df['nav'].iloc[-1]:.2f}",
             "同期买入持有": f"{df['bench'].iloc[-1]:.2f}"}
    return df[["date", "nav", "bench"]], stats
