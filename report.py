# -*- coding: utf-8 -*-
"""周度策略报告生成（Word）：
期现回顾 + 因子信号 + 策略建议 + 热点消息，一键导出docx，审阅后即可上报。
"""
import datetime
import os

import pandas as pd
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

from config import OUTPUT_DIR, SPOT
from analysis import basis_df, hc_rb_spread
from factors import month_spread, profit_factor
from signals import hedge_scorecard, signal_history
from strategy import build_strategy
from news import get_news


def _chg(series, n):
    return series.iloc[-1] - series.iloc[-1 - n] if len(series) > n else None


def build_weekly_markdown(conn):
    """周度策略报告（markdown版）：页面直接阅读用，与Word版同源"""
    today = datetime.date.today()
    L = [f"# 钢材市场周度策略报告", f"**报告日期：{today.isoformat()}**", ""]

    L.append("## 一、本周市场回顾")
    L.append("| 品种 | 现货价 | 周变动 | 期货价 | 周变动 | 基差(分位) |")
    L.append("|---|---|---|---|---|---|")
    for sym, (name, _) in SPOT.items():
        df = basis_df(conn, sym)
        if df.empty:
            continue
        card = hedge_scorecard(conn, sym, persist=False)
        c1 = _chg(df["spot_price"], 5)
        c2 = _chg(df["close"], 5)
        L.append(f"| {name} | {df['spot_price'].iloc[-1]:.0f} | "
                 f"{c1:+.0f} | {df['close'].iloc[-1]:.0f} | {c2:+.0f} | "
                 f"{df['basis'].iloc[-1]:+.0f}（{card['basis_pct']}%） |" if c1 is not None
                 else f"| {name} | {df['spot_price'].iloc[-1]:.0f} | - | "
                      f"{df['close'].iloc[-1]:.0f} | - | - |")
    sp = hc_rb_spread(conn)
    ms = month_spread(conn, "RB")
    pf = profit_factor(conn)
    L.append(f"\n卷螺差 **{sp['spread'].iloc[-1]:+.0f}** 元/吨 · "
             f"螺纹主力月差 **{ms['spread'].iloc[-1]:+.0f}** 元/吨"
             f"（{'contango' if ms['spread'].iloc[-1] < 0 else 'back'}） · "
             f"盘面毛利 **{pf['profit'].iloc[-1]:.0f}** 元/吨（未扣加工费）\n")

    L.append("## 二、因子状态与套保信号")
    for sym, (name, _) in SPOT.items():
        card = hedge_scorecard(conn, sym, persist=False)
        if card:
            L.append(f"- **{name}**：{card['icon']} {card['desc']}（总分{card['total']:+d}）"
                     f"——基差分位{card['basis_pct']}%、月差{card['spread']:+.0f}元、"
                     f"利润分位{card['profit_pct']}%")
    L.append("")

    L.append("## 三、策略建议")
    n = 0
    for sym in SPOT:
        for s in build_strategy(conn, sym):
            n += 1
            L.append(f"### 策略{n}：{s['策略']}（{s['线']}·{s['强度']}）")
            L.append(f"**依据**：{s['依据']}")
            L.append(f"**建议参数**：{s['建议参数']}")
            L.append(f"**失效条件**：{s['失效条件']}")
            L.append(f"**风险提示**：{s['风险提示']}")
            L.append("")

    L.append("## 四、本周热点消息（经黑色系过滤）")
    news = get_news(conn, days=7)
    if news.empty:
        L.append("本周无黑色系相关重大消息。")
    else:
        from news import impact_analysis
        for _, r in news.head(10).iterrows():
            imp = impact_analysis(r["title"], r["summary"], r["category"])
            L.append(f"- [{r['category']}/{imp['方向']}/{imp['程度']}] "
                     f"{r['pub_time'][:10]}　{r['title']}")
    L.append("")
    L.append("## 五、说明与风险提示")
    L.append("本报告由量化系统基于公开数据自动生成，策略依据为2019年以来历史统计检验，"
             "历史规律不代表未来表现。策略建议供内部决策参考，实际执行须结合公司库存敞口、"
             "资金状况与审批流程。")
    return "\n".join(L)


def generate_weekly_report(conn):
    """生成周度策略报告，返回文件路径"""
    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Microsoft YaHei"
    style.font.size = Pt(10.5)

    today = datetime.date.today()
    title = doc.add_heading("钢材市场周度策略报告", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub = doc.add_paragraph(f"报告日期：{today.isoformat()}　　编制：钢贸产业量化系统 v0.5")
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # ---------- 一、本周市场回顾 ----------
    doc.add_heading("一、本周市场回顾", level=1)
    table = doc.add_table(rows=1, cols=6)
    table.style = "Light Grid Accent 1"
    hdr = table.rows[0].cells
    for i, h in enumerate(["品种", "现货价", "周变动", "期货价", "周变动", "基差(分位)"]):
        hdr[i].text = h
    from signals import hedge_scorecard as _sc  # 避免重复落库提示
    for sym, (name, _) in SPOT.items():
        df = basis_df(conn, sym)
        if df.empty:
            continue
        card = hedge_scorecard(conn, sym, persist=False)
        row = table.add_row().cells
        row[0].text = name
        row[1].text = f"{df['spot_price'].iloc[-1]:.0f}"
        c1 = _chg(df["spot_price"], 5)
        row[2].text = f"{c1:+.0f}" if c1 is not None else "-"
        row[3].text = f"{df['close'].iloc[-1]:.0f}"
        c2 = _chg(df["close"], 5)
        row[4].text = f"{c2:+.0f}" if c2 is not None else "-"
        row[5].text = f"{df['basis'].iloc[-1]:+.0f}（{card['basis_pct']}%）" if card else "-"

    sp = hc_rb_spread(conn)
    ms = month_spread(conn, "RB")
    pf = profit_factor(conn)
    p = doc.add_paragraph()
    p.add_run(
        f"卷螺差（热卷-螺纹）最新 {sp['spread'].iloc[-1]:+.0f} 元/吨；"
        f"螺纹主力月差 {ms['spread'].iloc[-1]:+.0f} 元/吨"
        f"（{'contango' if ms['spread'].iloc[-1] < 0 else 'back'}结构）；"
        f"螺纹盘面毛利 {pf['profit'].iloc[-1]:.0f} 元/吨（未扣加工费）。")

    # ---------- 二、因子与信号 ----------
    doc.add_heading("二、因子状态与套保信号", level=1)
    for sym, (name, _) in SPOT.items():
        card = hedge_scorecard(conn, sym, persist=False)
        if card:
            doc.add_paragraph(
                f"{name}：{card['icon']} {card['desc']}（总分{card['total']:+d}）——"
                f"基差分位{card['basis_pct']}%（{card['basis_score']:+d}分）、"
                f"月差{card['spread']:+.0f}元/吨（{card['spread_score']:+d}分）、"
                f"利润分位{card['profit_pct']}%（{card['profit_score']:+d}分）。",
                style="List Bullet")

    # ---------- 三、策略建议 ----------
    doc.add_heading("三、策略建议", level=1)
    n_strategy = 0
    for sym, (name, _) in SPOT.items():
        for s in build_strategy(conn, sym):
            n_strategy += 1
            h = doc.add_heading(f"策略{n_strategy}：{s['策略']}（{s['线']} · {s['强度']}）",
                                level=2)
            doc.add_paragraph(f"【依据】{s['依据']}")
            doc.add_paragraph(f"【建议参数】{s['建议参数']}")
            doc.add_paragraph(f"【失效条件】{s['失效条件']}")
            doc.add_paragraph(f"【风险提示】{s['风险提示']}")

    # ---------- 四、本周热点消息 ----------
    doc.add_heading("四、本周热点消息（经黑色系过滤）", level=1)
    news = get_news(conn, days=7)
    if news.empty:
        doc.add_paragraph("本周无黑色系相关重大消息。")
    else:
        from news import impact_analysis
        for _, r in news.head(10).iterrows():
            imp = impact_analysis(r["title"], r["summary"], r["category"])
            doc.add_paragraph(
                f"[{r['category']}/{imp['方向']}/{imp['程度']}] "
                f"{r['pub_time'][:10]}　{r['title']}",
                style="List Bullet")

    # ---------- 五、声明 ----------
    doc.add_heading("五、说明与风险提示", level=1)
    doc.add_paragraph(
        "本报告由量化系统基于公开数据自动生成，策略依据为2019年以来历史统计检验"
        "（基差分位低位组20日走强胜率75%等），历史规律不代表未来表现。"
        "策略建议供内部决策参考，实际执行须结合公司库存敞口、资金状况与审批流程。")

    path = os.path.join(OUTPUT_DIR, f"钢材市场周度策略报告_{today.isoformat()}.docx")
    doc.save(path)
    return path
