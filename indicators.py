# -*- coding: utf-8 -*-
"""技术分析指标：MA / MACD / RSI / 布林带 / ATR + 规则化文字解读
输入：futures_daily 的日线 DataFrame（含 open/high/low/close/volume，按日期升序）
"""
import pandas as pd
import numpy as np


def add_indicators(df):
    """在日线 DataFrame 上追加技术指标列（不修改原表，返回副本）。"""
    d = df.copy().sort_values("date").reset_index(drop=True)
    close = d["close"]

    # 均线
    for n in (5, 10, 20, 60):
        d[f"ma{n}"] = close.rolling(n).mean()

    # MACD（12,26,9）
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    d["dif"] = ema12 - ema26
    d["dea"] = d["dif"].ewm(span=9, adjust=False).mean()
    d["macd"] = 2 * (d["dif"] - d["dea"])

    # RSI（14）
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    d["rsi14"] = 100 - 100 / (1 + rs)

    # 布林带（20, 2）
    mid = close.rolling(20).mean()
    std = close.rolling(20).std()
    d["boll_mid"] = mid
    d["boll_up"] = mid + 2 * std
    d["boll_dn"] = mid - 2 * std

    # ATR（14）
    tr = pd.concat([
        d["high"] - d["low"],
        (d["high"] - close.shift(1)).abs(),
        (d["low"] - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    d["atr14"] = tr.rolling(14).mean()

    return d


def interpret_technicals(d, name="该品种"):
    """规则化文字解读：返回 [(图标, 标题, 内容), ...]，供页面直接渲染。"""
    if len(d) < 60:
        return [("⚠️", "数据不足", "至少需要60个交易日数据才能输出完整解读，请先更新行情。")]

    last = d.iloc[-1]
    prev = d.iloc[-2]
    close = last["close"]
    out = []

    # 1. 均线结构
    ma5, ma20, ma60 = last["ma5"], last["ma20"], last["ma60"]
    if close > ma20 > ma60:
        out.append(("📈", "均线结构：多头排列",
                    f"{name}收盘价（{close:.0f}）站上20日与60日均线，且20日线在60日线上方，"
                    f"中期趋势偏强。20日线（{ma20:.0f}）是第一支撑，60日线（{ma60:.0f}）是趋势生命线，"
                    f"跌破60日线则多头结构被破坏。"))
    elif close < ma20 < ma60:
        out.append(("📉", "均线结构：空头排列",
                    f"{name}收盘价（{close:.0f}）位于20日与60日均线下方，且20日线在60日线下方，"
                    f"中期趋势偏弱。反弹到20日线（{ma20:.0f}）附近容易遇压，"
                    f"重新站上60日线（{ma60:.0f}）之前不宜轻言见底。"))
    else:
        out.append(("↔️", "均线结构：纠缠震荡",
                    f"{name}均线交织（收盘{close:.0f} / 20日{ma20:.0f} / 60日{ma60:.0f}），"
                    f"无明确趋势，市场处于震荡市。震荡市中追涨杀跌容易被反复打脸，"
                    f"以区间思路对待，等均线走出方向再加仓位。"))

    # 2. MACD
    dif, dea = last["dif"], last["dea"]
    if prev["dif"] <= prev["dea"] and dif > dea:
        out.append(("✨", "MACD：刚刚金叉",
                    f"DIF（{dif:.1f}）刚刚上穿DEA（{dea:.1f}），短期动能由空转多。"
                    f"金叉出现在零轴{'上方，强度更高' if dif > 0 else '下方，属于弱势反弹信号，需量能和均线配合确认'}。"))
    elif prev["dif"] >= prev["dea"] and dif < dea:
        out.append(("💥", "MACD：刚刚死叉",
                    f"DIF（{dif:.1f}）刚刚下穿DEA（{dea:.1f}），短期动能由多转空。"
                    f"死叉出现在零轴{'下方，下跌动能较强，注意风险' if dif < 0 else '上方，多为上涨途中的回调信号'}。"))
    else:
        state = "多头动能占优" if dif > dea else "空头动能占优"
        out.append(("📊", f"MACD：{state}",
                    f"DIF（{dif:.1f}）{'>' if dif > dea else '<'}DEA（{dea:.1f}），"
                    f"柱体{'红' if last['macd'] > 0 else '绿'}色，"
                    f"{'且在零轴上方，趋势偏强' if dif > 0 else '位于零轴下方，整体仍偏弱'}。"))

    # 3. RSI
    rsi = last["rsi14"]
    if rsi >= 80:
        out.append(("🔥", f"RSI：{rsi:.0f}，超买区",
                    "短线涨速过快，追涨风险大。注意：强趋势中RSI可以长期停留在超买区，"
                    "超买不等于马上跌，应等RSI回落下穿80再考虑减仓。"))
    elif rsi <= 20:
        out.append(("🧊", f"RSI：{rsi:.0f}，超卖区",
                    "短线跌速过快，存在技术性反弹需求。同样注意：弱势中超卖可以更超卖，"
                    "不要仅凭超卖抄底，等RSI重新上穿20更稳。"))
    elif rsi >= 55:
        out.append(("💪", f"RSI：{rsi:.0f}，偏强区", "买方力量占优，尚未到超买，短期仍有上行空间。"))
    elif rsi <= 45:
        out.append(("😟", f"RSI：{rsi:.0f}，偏弱区", "卖方力量占优，尚未到超卖，短期仍有下行压力。"))
    else:
        out.append(("⚖️", f"RSI：{rsi:.0f}，中性区", "多空力量均衡，方向不明，等待外力打破平衡。"))

    # 4. 布林带位置
    up, dn, mid = last["boll_up"], last["boll_dn"], last["boll_mid"]
    width_pct = (up - dn) / mid * 100 if mid else 0
    if close >= up:
        pos = f"价格（{close:.0f}）触及或突破上轨（{up:.0f}），短线强势但偏离过大，追高谨慎"
    elif close <= dn:
        pos = f"价格（{close:.0f}）触及或跌破下轨（{dn:.0f}），短线超跌，继续杀跌需谨慎"
    elif close > mid:
        pos = f"价格（{close:.0f}）运行在中轨（{mid:.0f}）上方，偏强运行"
    else:
        pos = f"价格（{close:.0f}）运行在中轨（{mid:.0f}）下方，偏弱运行"
    squeeze = "带宽明显收窄，往往预示一波大行情在酝酿，注意突破方向。" if width_pct < 8 else ""
    out.append(("🎯", "布林带：" + ("收口" if squeeze else "常态"), pos + "。" + squeeze))

    # 5. 波动率（ATR），用于止损参考
    atr = last["atr14"]
    out.append(("🛡️", "波动与止损参考",
                f"ATR(14)={atr:.0f} 元/吨，即日均真实波幅。短线止损可设在入场价±1.5~2倍ATR"
                f"（约{atr * 1.5:.0f}~{atr * 2:.0f}元），仓位上每手对应{atr * 10:.0f}元左右的日波动风险，"
                f"据此倒推可承受的持仓手数。"))
    return out
