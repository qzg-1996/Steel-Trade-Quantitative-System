# -*- coding: utf-8 -*-
"""策略引擎：把因子状态翻译成可执行的策略建议

策略分两条线（定位不同，不可混淆）：
  A. 套期保值策略（服务现货经营）：卖保/买保/维持，给比例区间和合约选择
  B. 基差交易策略（投机属性）：正套/反套观察窗口，给入场依据和失效条件

每条策略 = 方向 + 依据（引用因子检验的历史数据）+ 建议参数 + 失效条件 + 风险。
规则全透明：依据中的胜率和均值全部来自 research.py 的真实检验结果。
"""
from signals import hedge_scorecard
from factors import momentum
from research import basis_regime_test

BASE_HEDGE_RATIO = 50  # 基准套保比例（%），可按公司制度调整


def _test_stats(conn, symbol):
    """从因子检验结果中提取各组统计（按当前分位所在组引用，口径一致）"""
    r = basis_regime_test(conn, symbol)
    if r is None:
        return None
    s = r["summary"].set_index("分组")

    def row(g):
        return {"n": int(s.loc[g, "样本数"]),
                "win20": s.loc[g, "20日走强胜率"],
                "chg20": s.loc[g, "20日基差变化"],
                "fut60": s.loc[g, "60日期货收益"]}

    return {"极低 (<10%)": row("极低 (<10%)"), "偏低 (10-30%)": row("偏低 (10-30%)"),
            "偏高 (70-90%)": row("偏高 (70-90%)"), "极高 (>90%)": row("极高 (>90%)")}


def _group_of(bp):
    """分位(0-100)所属检验组"""
    if bp < 10:
        return "极低 (<10%)"
    if bp < 30:
        return "偏低 (10-30%)"
    if bp < 70:
        return None
    if bp < 90:
        return "偏高 (70-90%)"
    return "极高 (>90%)"


def market_brief(conn, symbol="RB"):
    """解读：把因子状态串联成连贯的市场分析文字（模板+真实数据组装）"""
    card = hedge_scorecard(conn, symbol, persist=False)
    if card is None:
        return ""
    from analysis import basis_summary
    from factors import month_spread
    info = basis_summary(conn, symbol)
    name = "螺纹" if symbol == "RB" else "热卷"
    mom20 = momentum(conn, "RB0" if symbol == "RB" else "HC0", 20)["mom20"].iloc[-1]

    # 结构定性
    struct = ("期货升水现货、远月升水近月的「双升水」结构，期货定价了较强的远期乐观预期"
              if card["spread"] < 0 and info["basis"] < 0 else
              "现货升水期货的back结构，现货端相对偏紧"
              if info["basis"] > 0 and card["spread"] > 0 else
              "期现与月间结构方向不一的过渡状态")
    # 趋势配合
    trend = ("近20日动量 %+0.1f%%，趋势与信号方向形成共振" % mom20 if
             (card["total"] >= 2 and mom20 < 0) or (card["total"] <= -2 and mom20 > 0)
             else "近20日动量 %+0.1f%%，趋势与信号存在分歧，注意节奏" % mom20)
    # 利润解读
    profit_note = ("盘面利润处于近一年 %d%% 分位，钢厂增产压力不大，现货深跌空间受限"
                   % card["profit_pct"] if card["profit_pct"] < 40 else
                   "盘面利润处于近一年 %d%% 分位，利润偏高刺激供应，警惕产量压力"
                   % card["profit_pct"] if card["profit_pct"] > 80 else
                   "盘面利润处于近一年 %d%% 分位的中性区" % card["profit_pct"])

    brief = (
        f"【市场结构】{name}现货 {info['spot']:.0f}、期货 {info['futures']:.0f}，"
        f"基差 {info['basis']:+.0f} 元/吨（近一年 {card['basis_pct']}% 分位），"
        f"月差 {card['spread']:+.0f} 元/吨。当前为{struct}。{profit_note}。\n\n"
        f"【信号解读】三因子合成 {card['total']:+d} 分（{card['icon']} {card['desc']}）。"
        f"历史检验显示：基差分位处于当前区间时，后续20-60日基差均值回归特征显著"
        f"（详见量化研究页分组数据）。{trend}。\n\n"
        f"【操作要点】{'、'.join(_action_points(card))}。"
    )
    return brief


def _action_points(card):
    """根据信号生成操作要点短句"""
    pts = []
    if card["total"] >= 2:
        pts.append("卖出套保持积极态度，比例60-80%、优选远月合约")
        pts.append("正套交易者可分批建仓，单批不超计划1/3")
        pts.append("跟踪基差分位变化，回升至50%上方即收缩动作")
    elif card["total"] <= -2:
        pts.append("不宜追保，卖保比例压至基准以下")
        pts.append("有采购锁价需求可把握买保窗口")
    else:
        pts.append("维持基准套保比例，不主动调整")
        pts.append("等待基差分位进入极端区再行动")
    return pts


def build_strategy(conn, symbol="RB"):
    """生成当日策略建议卡列表"""
    card = hedge_scorecard(conn, symbol)
    if card is None:
        return []
    stats = _test_stats(conn, symbol)
    fut_sym = "RB0" if symbol == "RB" else "HC0"
    mom20 = momentum(conn, fut_sym, 20)["mom20"].iloc[-1]

    name = "螺纹钢" if symbol == "RB" else "热轧卷板"
    strategies = []

    # ---------- A. 套期保值策略 ----------
    grp = _group_of(card["basis_pct"])
    gs = stats.get(grp) if (stats and grp) else None
    if card["total"] >= 2:
        ratio = "70-80%" if card["total"] >= 3 else "60-70%"
        ev = (f"基差分位 {card['basis_pct']}% 处于历史低位区（期货升水现货）。"
              + (f"历史检验（{grp}组）：2019年以来共{gs['n']}次，20日后基差走强胜率"
                 f"{gs['win20']}、平均变化{gs['chg20']:+.0f}元/吨；"
                 f"低位区回归主要靠期货下跌实现（60日期货均值{gs['fut60']}）。" if gs else "")
              + (f"月差contango {card['spread']:+.0f}元/吨，卖远月价格更优。"
                 if card["spread"] < 0 else ""))
        strategies.append({
            "线": "套期保值", "策略": f"{name}卖出套保", "强度": "积极",
            "依据": ev,
            "建议参数": f"套保比例可提至 {ratio}（基准{BASE_HEDGE_RATIO}%）；"
                       f"合约优选远月（contango结构下升水更高），分批建仓",
            "失效条件": "基差分位回升至50%以上，或月差转为back结构",
            "风险提示": "若强刺激政策出台，期货升水可能继续走阔，"
                       "套保端将承担基差进一步走弱的浮亏",
        })
    elif card["total"] <= -2:
        ev = (f"基差分位 {card['basis_pct']}% 处于历史高位区（期货深贴水）。"
              + (f"历史检验（{grp}组）：共{gs['n']}次，20日后基差平均"
                 f"{gs['chg20']:+.0f}元/吨，高位区回归主要靠期货上涨实现"
                 f"（60日期货均值{gs['fut60']}）。" if gs else ""))
        strategies.append({
            "线": "套期保值", "策略": f"{name}降低卖保/考虑买保", "强度": "谨慎",
            "依据": ev,
            "建议参数": f"卖出套保比例降至 {BASE_HEDGE_RATIO}% 以下；"
                       f"有采购锁价需求的，此位置是买入套保的有利窗口",
            "失效条件": "基差分位回落至50%以下",
            "风险提示": "深度back可能由现货坍塌驱动，买保需先确认现货端无崩价风险",
        })
    else:
        strategies.append({
            "线": "套期保值", "策略": f"{name}维持基准套保", "强度": "中性",
            "依据": f"基差分位 {card['basis_pct']}%、月差 {card['spread']:+.0f}元/吨、"
                   f"利润分位 {card['profit_pct']}%，三因子合成{card['total']:+d}分，"
                   f"无显著方向性优势。",
            "建议参数": f"维持基准套保比例 {BASE_HEDGE_RATIO}%，不加仓不减仓",
            "失效条件": "信号灯转绿或转红",
            "风险提示": "中性区策略价值低，频繁调整反而增加交易成本",
        })

    # ---------- B. 基差交易策略（投机属性，独立评估） ----------
    low_s = stats.get("极低 (<10%)") if stats else None
    high_s = stats.get("极高 (>90%)") if stats else None
    if card["basis_pct"] <= 10 and low_s:
        strategies.append({
            "线": "基差交易", "策略": "正套观察窗口（买现货/卖期货）", "强度": "观察",
            "依据": f"基差分位仅 {card['basis_pct']}%，历史检验（极低组{low_s['n']}次）："
                   f"20日后基差走强胜率{low_s['win20']}、平均走扩{low_s['chg20']:+.0f}元/吨。"
                   f"近20日动量 {mom20:+.1f}%。",
            "建议参数": "分三批建仓，首批不超过计划仓位的1/3；"
                       "持有周期参考20-60个交易日",
            "失效条件": "基差分位回升至30%以上（止盈/减半），"
                       "或基差继续走弱超50元/吨（止损）",
            "风险提示": "正套需占用现货资金与库容，测算好资金成本；"
                       "极端行情下基差低位可再创新低",
        })
    elif card["basis_pct"] >= 90 and high_s:
        strategies.append({
            "线": "基差交易", "策略": "反套观察窗口（卖现货/买期货）", "强度": "观察",
            "依据": f"基差分位高达 {card['basis_pct']}%，历史检验（极高组{high_s['n']}次）："
                   f"20日后基差平均{high_s['chg20']:+.0f}元/吨。",
            "建议参数": "适合有现货库存可抛的主体；纯期货端买期货替代需评估保证金",
            "失效条件": "基差分位回落至70%以下",
            "风险提示": "反套在现货紧张格局下风险大，需密切跟踪库存与成交",
        })
    return strategies
