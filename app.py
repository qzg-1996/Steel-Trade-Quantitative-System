# -*- coding: utf-8 -*-
"""钢贸产业量化系统 v0.2 · 网页版
启动方式：双击「启动网页版.bat」，或在命令行执行  streamlit run app.py
浏览器会自动打开 http://localhost:8501
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from db import get_conn
from config import SPOT, FUTURES
from analysis import basis_df, basis_summary, hc_rb_spread
from news import fetch_news, get_news, export_news_txt, CATS

st.set_page_config(page_title="钢贸产业量化系统", page_icon="🏗️",
                   layout="wide", initial_sidebar_state="expanded")


@st.cache_data(ttl=21600, show_spinner="正在自动更新行情数据（约10秒）…")
def auto_update_data():
    """云端/本地通用：每6小时检查并自动增量更新行情与现货。
    抓取失败自动跳过（保留已有数据），不影响页面使用。"""
    try:
        from db import get_conn as _gc
        from fetch_data import update_futures, update_spot
        c = _gc()
        try:
            update_futures(c)
            update_spot(c)
        finally:
            c.close()
    except Exception:
        pass
    return True


auto_update_data()
conn = get_conn()

# 分类标签配色
CAT_COLOR = {
    "产业政策": "#C00000", "地产基建": "#E6852D", "宏观货币": "#1F4E79",
    "原料动态": "#6A3D9A", "钢材市场": "#2E7D32",
}

# ---------------- 侧边栏 ----------------
with st.sidebar:
    st.title("🏗️ 钢贸产业量化系统")
    st.caption("v0.9 · 产业 + 期货 量化研究平台（AI增强）")
    page = st.radio("功能导航",
                    ["📊 基差看板", "📈 价差与利润", "📉 技术分析", "🔬 量化研究",
                     "📋 策略输出", "📰 热点消息", "🗄️ 数据管理"])
    st.divider()
    st.caption("数据：新浪财经 / 生意社 / 东方财富\n仅供研究参考，不构成投资建议")


# ================= 页面1：基差看板 =================
if page == "📊 基差看板":
    st.header("基差看板")
    c1, c2 = st.columns([1, 1])
    with c1:
        symbol = st.selectbox("品种", list(SPOT.keys()),
                              format_func=lambda s: SPOT[s][0])
    with c2:
        days = st.slider("展示天数（交易日）", 30, 500, 120, 10)

    df = basis_df(conn, symbol).tail(days)
    info = basis_summary(conn, symbol)

    if info:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("现货价（生意社）", f"{info['spot']:.0f} 元/吨")
        m2.metric("期货主力收盘", f"{info['futures']:.0f} 元/吨")
        m3.metric("基差（现货-期货）", f"{info['basis']:+.0f} 元/吨",
                  delta=f"近一年分位 {info['pct_1y']}%", delta_color="off")
        m4.metric("近一年基差区间", f"{info['min_1y']:+.0f} ~ {info['max_1y']:+.0f}")
        st.caption(f"数据截至 {info['date']} · 基差分位 = 当前基差在近一年中的百分位")

        # ---- 套保信号记分卡（三因子合成，规则透明） ----
        from signals import hedge_scorecard
        card = hedge_scorecard(conn, symbol)
        if card:
            bg = {"🟢 绿灯": "rgba(46,125,50,0.18)", "🟡 黄灯": "rgba(230,133,45,0.18)",
                  "🔴 红灯": "rgba(198,40,40,0.18)"}[card["icon"]]
            st.markdown(
                f"""<div style="background:{bg};border-radius:8px;
                padding:12px 18px;margin:4px 0 12px 0">
                <b style="font-size:17px">套保信号：{card['icon']} · {card['desc']}
                （总分 {card['total']:+d}）</b><br>
                <span style="font-size:13px;opacity:0.8">
                基差分位 {card['basis_pct']}%（{card['basis_score']:+d}分） ·
                月差 {card['spread']:+.0f} 元/吨（{card['spread_score']:+d}分） ·
                利润分位 {card['profit_pct']}%（{card['profit_score']:+d}分） ·
                评分规则见「量化研究」页</span></div>""",
                unsafe_allow_html=True)

    if not df.empty:
        df["ma20"] = df["close"].rolling(20).mean()
        df["ma60"] = df["close"].rolling(60).mean()
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Scatter(x=df["date"], y=df["spot_price"], name="现货（生意社）",
                                 line=dict(color="#C00000", width=2)), secondary_y=False)
        fig.add_trace(go.Scatter(x=df["date"], y=df["close"], name="期货主力",
                                 line=dict(color="#1F4E79", width=2)), secondary_y=False)
        fig.add_trace(go.Scatter(x=df["date"], y=df["ma20"], name="MA20",
                                 line=dict(color="#E6852D", width=1, dash="dot")),
                      secondary_y=False)
        fig.add_trace(go.Scatter(x=df["date"], y=df["ma60"], name="MA60",
                                 line=dict(color="#888", width=1, dash="dash")),
                      secondary_y=False)
        colors = ["#2E7D32" if b >= 0 else "#C62828" for b in df["basis"]]
        fig.add_trace(go.Bar(x=df["date"], y=df["basis"], name="基差",
                             marker_color=colors, opacity=0.45), secondary_y=True)
        fig.update_layout(title=f"{SPOT[symbol][0]}基差走势图（鼠标悬停查看数值，可缩放）",
                          hovermode="x unified", height=520,
                          legend=dict(orientation="h", y=1.12))
        fig.update_yaxes(title_text="价格（元/吨）", secondary_y=False)
        fig.update_yaxes(title_text="基差（元/吨）", secondary_y=True)
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("查看/下载明细数据"):
            show = df.sort_values("date", ascending=False)
            st.dataframe(show, use_container_width=True, height=300)
            st.download_button("下载 CSV", show.to_csv(index=False).encode("utf-8-sig"),
                               f"{SPOT[symbol][0]}基差明细.csv", "text/csv")
    else:
        st.warning("暂无数据，请先到「数据管理」页更新行情。")


# ================= 页面2：价差与利润 =================
elif page == "📈 价差与利润":
    st.header("卷螺差监控（热卷 - 螺纹 · 期货主力）")
    days2 = st.slider("展示天数（交易日）", 30, 500, 120, 10, key="spread_days")
    sp = hc_rb_spread(conn).tail(days2)

    if not sp.empty:
        latest, mean_v = sp["spread"].iloc[-1], sp["spread"].mean()
        m1, m2, m3 = st.columns(3)
        m1.metric("最新卷螺差", f"{latest:+.0f} 元/吨")
        m2.metric("区间均值", f"{mean_v:.0f} 元/吨")
        m3.metric("偏离均值", f"{latest - mean_v:+.0f} 元/吨",
                  delta="高于均值" if latest > mean_v else "低于均值", delta_color="off")

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=sp["date"], y=sp["spread"], name="卷螺差",
                                 line=dict(color="#6A3D9A", width=2),
                                 fill="tozeroy", fillcolor="rgba(106,61,154,0.12)"))
        fig.add_hline(y=mean_v, line_dash="dash", line_color="#888",
                      annotation_text=f"均值 {mean_v:.0f}")
        fig.update_layout(title="卷螺差走势图", hovermode="x unified", height=460,
                          yaxis_title="价差（元/吨）")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("暂无数据，请先到「数据管理」页更新行情。")

    st.divider()
    st.header("期限结构与月差")
    from factors import term_structure, month_spread
    base_sel = st.selectbox("品种", ["RB", "HC"], index=0,
                            format_func=lambda b: "螺纹钢" if b == "RB" else "热轧卷板",
                            key="term_base")
    latest, ts = term_structure(conn, base_sel)
    if len(ts):
        st.caption(f"数据日期 {latest} · 按持仓筛选活跃合约")
        cols = st.columns(len(ts))
        for i, r in ts.iterrows():
            cols[i].metric(r["symbol"], f"{r['close']:.0f} 元",
                           f"持仓 {r['hold'] / 10000:.0f} 万手")
        if len(ts) >= 2:
            near_far = ts["close"].iloc[0] - ts["close"].iloc[-1]
            struct = "back（近强远弱，现货偏紧）" if near_far > 0 else \
                     "contango（近弱远强，预期宽松）"
            st.caption(f"首末合约月差 {near_far:+.0f} 元/吨 —— {struct}")
        ms = month_spread(conn, base_sel).tail(days2)
        if not ms.empty:
            fig_ms = go.Figure()
            fig_ms.add_trace(go.Scatter(x=ms["date"], y=ms["spread"], name="主力月差",
                                        line=dict(color="#0B7A75", width=1.8)))
            fig_ms.add_hline(y=0, line_color="#666")
            fig_ms.update_layout(title="主力月差走势（近月-远月，跟随1/5/10月主力轮换）",
                                 hovermode="x unified", height=380, yaxis_title="元/吨")
            st.plotly_chart(fig_ms, use_container_width=True)
    else:
        st.info("合约数据未入库，请在「数据管理」更新期货行情（v0.4起自动抓取主力合约）。")

    st.divider()
    st.header("螺纹盘面毛利（螺纹 - 1.6×铁矿 - 0.5×焦炭）")
    st.caption("未扣固定加工费，用于观察利润趋势与极值——利润高位时钢厂有增产压力，低位时有减产动力")
    from factors import profit_factor
    pf = profit_factor(conn).tail(days2)
    if not pf.empty:
        m1, m2 = st.columns(2)
        m1.metric("最新盘面毛利", f"{pf['profit'].iloc[-1]:.0f} 元/吨")
        m2.metric("区间均值", f"{pf['profit'].mean():.0f} 元/吨")
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=pf["date"], y=pf["profit"], name="盘面毛利",
                                  line=dict(color="#B8860B", width=2),
                                  fill="tozeroy", fillcolor="rgba(184,134,11,0.12)"))
        fig2.add_hline(y=pf["profit"].mean(), line_dash="dash", line_color="#888",
                       annotation_text=f"均值 {pf['profit'].mean():.0f}")
        fig2.update_layout(hovermode="x unified", height=400, yaxis_title="元/吨")
        st.plotly_chart(fig2, use_container_width=True)


# ================= 页面：技术分析 =================
elif page == "📉 技术分析":
    st.header("技术分析（连续合约）")
    st.caption("基于期货日线自动计算均线 / MACD / RSI / 布林带 / ATR，全部本地计算，不依赖外部接口")
    from indicators import add_indicators, interpret_technicals

    c1, c2 = st.columns([1, 2])
    with c1:
        tech_sym = st.selectbox("品种", list(FUTURES.keys()),
                                format_func=lambda s: f"{FUTURES[s]}({s})", key="tech_sym")
    with c2:
        tech_days = st.slider("展示天数（交易日）", 60, 500, 250, 10, key="tech_days")

    ohlc = pd.read_sql("SELECT date, open, high, low, close, volume FROM futures_daily "
                       "WHERE symbol=? ORDER BY date", conn, params=(tech_sym,))
    if ohlc.empty:
        st.warning("暂无数据，请先到「数据管理」页更新行情。")
    else:
        d = add_indicators(ohlc)
        show = d.tail(tech_days)
        last = d.iloc[-1]

        # 顶部指标卡
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("最新收盘", f"{last['close']:.0f}")
        bias = (last["close"] / last["ma20"] - 1) * 100 if last["ma20"] else 0
        m2.metric("20日均线乖离", f"{bias:+.1f}%",
                  delta="偏强" if bias > 0 else "偏弱", delta_color="off")
        m3.metric("RSI(14)", f"{last['rsi14']:.0f}")
        macd_state = "多头" if last["dif"] > last["dea"] else "空头"
        m4.metric("MACD状态", macd_state,
                  delta=f"DIF {last['dif']:.1f} / DEA {last['dea']:.1f}", delta_color="off")
        m5.metric("ATR(14)", f"{last['atr14']:.0f} 元",
                  delta="日真实波幅", delta_color="off")

        # 三合一图：K线+均线+布林 / MACD / RSI
        fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                            row_heights=[0.55, 0.25, 0.2], vertical_spacing=0.03,
                            subplot_titles=("K线 · 均线 · 布林带", "MACD(12,26,9)", "RSI(14)"))
        fig.add_trace(go.Candlestick(x=show["date"], open=show["open"], high=show["high"],
                                     low=show["low"], close=show["close"], name="K线",
                                     increasing_line_color="#C00000",
                                     decreasing_line_color="#2E7D32"), row=1, col=1)
        for ma, color in (("ma5", "#E6852D"), ("ma20", "#1F4E79"), ("ma60", "#6A3D9A")):
            fig.add_trace(go.Scatter(x=show["date"], y=show[ma], name=ma.upper(),
                                     line=dict(color=color, width=1.2)), row=1, col=1)
        fig.add_trace(go.Scatter(x=show["date"], y=show["boll_up"], name="布林上轨",
                                 line=dict(color="#999", width=1, dash="dot")), row=1, col=1)
        fig.add_trace(go.Scatter(x=show["date"], y=show["boll_dn"], name="布林下轨",
                                 line=dict(color="#999", width=1, dash="dot"),
                                 fill="tonexty", fillcolor="rgba(128,128,128,0.07)"), row=1, col=1)
        colors = ["#C00000" if v >= 0 else "#2E7D32" for v in show["macd"]]
        fig.add_trace(go.Bar(x=show["date"], y=show["macd"], name="MACD柱",
                             marker_color=colors), row=2, col=1)
        fig.add_trace(go.Scatter(x=show["date"], y=show["dif"], name="DIF",
                                 line=dict(color="#E6852D", width=1.2)), row=2, col=1)
        fig.add_trace(go.Scatter(x=show["date"], y=show["dea"], name="DEA",
                                 line=dict(color="#1F4E79", width=1.2)), row=2, col=1)
        fig.add_trace(go.Scatter(x=show["date"], y=show["rsi14"], name="RSI",
                                 line=dict(color="#6A3D9A", width=1.4)), row=3, col=1)
        for yv, txt in ((80, "超买80"), (20, "超卖20")):
            fig.add_hline(y=yv, row=3, col=1, line_dash="dash", line_color="#888",
                          annotation_text=txt)
        fig.update_layout(height=760, hovermode="x unified", showlegend=True,
                          legend=dict(orientation="h", y=1.02),
                          xaxis3_rangeslider_visible=False)
        fig.update_xaxes(rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)

        # 解读
        st.subheader("🎙️ 解读")
        for icon, title, content in interpret_technicals(d, FUTURES[tech_sym]):
            st.markdown(
                f'<div style="border-left:4px solid #1F4E79;padding:10px 14px;margin:8px 0;'
                f'background:rgba(128,128,128,0.08);border-radius:0 8px 8px 0">'
                f'<b>{icon} {title}</b><br>'
                f'<span style="font-size:13.5px;opacity:0.9">{content}</span></div>',
                unsafe_allow_html=True)
        st.caption("技术指标是「市场的体温计」不是「水晶球」：它描述当前状态，不预测未来。"
                   "请与基差分位、月差结构、套保信号（见「量化研究/策略输出」页）交叉验证。")


# ================= 页面3：量化研究 =================
elif page == "🔬 量化研究":
    st.header("因子有效性检验：基差分位")
    st.caption("把「基差极端位置会均值回归」的产业经验，用2019年以来的真实数据检验一遍——"
               "每个交易日按基差分位分组，统计各组未来5/20/60日的实际表现")

    symbol_r = st.selectbox("检验品种", list(SPOT.keys()),
                            format_func=lambda s: SPOT[s][0], key="research_sym")
    from research import basis_regime_test, interpret
    with st.spinner("正在跑历史检验……"):
        result = basis_regime_test(conn, symbol_r)

    if result is None:
        st.warning("样本不足（需300个交易日以上），请先在「数据管理」补齐现货历史。")
    else:
        st.subheader("检验结论")
        for line in interpret(result["summary"]):
            st.markdown(f"- {line}")

        st.subheader("分组统计明细")
        st.dataframe(result["summary"], use_container_width=True, hide_index=True)

        st.subheader("各分组未来20日基差平均变化（元/吨）")
        sm = result["summary"]
        fig3 = go.Figure(go.Bar(
            x=sm["分组"], y=sm["20日基差变化"],
            marker_color=["#C62828" if v < 0 else "#2E7D32" for v in sm["20日基差变化"]],
            text=sm["20日基差变化"], textposition="outside"))
        fig3.add_hline(y=0, line_color="#666")
        fig3.update_layout(height=380, yaxis_title="元/吨")
        st.plotly_chart(fig3, use_container_width=True)

        with st.expander("近一年基差分位走势（看当前所处位置）"):
            curve = result["curve"].tail(250)
            fig4 = go.Figure()
            fig4.add_trace(go.Scatter(x=curve["date"], y=curve["basis_pct"],
                                      line=dict(color="#1F4E79", width=1.8), name="基差分位"))
            for y, txt in [(0.1, "极低线10%"), (0.9, "极高线90%")]:
                fig4.add_hline(y=y, line_dash="dot", line_color="#C00000",
                               annotation_text=txt)
            fig4.update_layout(height=320, yaxis_title="分位（0~1）",
                               yaxis=dict(range=[0, 1]))
            st.plotly_chart(fig4, use_container_width=True)

        st.subheader("历史相似行情复盘")
        st.caption("基差分位处于当前这种极端位置（<10%）的每个独立时段，后来实际怎么走——"
                   "案例级证据，含失败案例，不挑拣")
        from research import similar_episodes
        ep = similar_episodes(conn, symbol_r)
        if not ep.empty:
            st.dataframe(ep, use_container_width=True, hide_index=True)
            win = (ep["+20日基差"].dropna() > 0).mean()
            st.caption(f"以上案例中，20日后基差走扩比例 {win * 100:.0f}%")

        st.subheader("信号灯历史成绩单（回测）")
        st.caption("把当前信号灯规则放到历史中重跑：各信号亮起后，期货实际表现")
        from backtest import signal_report, nav_backtest
        with st.spinner("回测计算中……"):
            st.dataframe(signal_report(conn, symbol_r), use_container_width=True,
                         hide_index=True)
            nav_df, nav_stats = nav_backtest(conn, symbol_r)
        cols = st.columns(len(nav_stats))
        for c, (k, v) in zip(cols, nav_stats.items()):
            c.metric(k, v)
        fig_nav = go.Figure()
        fig_nav.add_trace(go.Scatter(x=nav_df["date"], y=nav_df["nav"],
                                     name="信号净值（绿灯卖保/其余空仓）",
                                     line=dict(color="#C00000", width=1.8)))
        fig_nav.add_trace(go.Scatter(x=nav_df["date"], y=nav_df["bench"],
                                     name="同期买入持有",
                                     line=dict(color="#999", width=1.4)))
        fig_nav.update_layout(hovermode="x unified", height=380, yaxis_title="净值")
        st.plotly_chart(fig_nav, use_container_width=True)
        st.warning("回测诚实声明：基于主力连续合约（换月噪声已按±8%阈值剔除），"
                   "未计手续费滑点，信号次日建仓无前视。样本期2021年起为单边熊市："
                   "绿灯卖保被强力验证（60日下跌概率95%）；红灯为防御信号不做多——"
                   "历史检验证明熊市中「期货便宜」不构成做多理由。历史不代表未来。")

        st.subheader("套保信号跟踪记录")
        st.caption("每次打开基差看板时，当日信号自动记录于此——积累样本后用于信号胜率复盘，"
                   "胜率不行就改规则，这是量化的自我进化")
        from signals import signal_history
        hist = signal_history(conn)
        if not hist.empty:
            st.dataframe(hist, use_container_width=True, hide_index=True)
        else:
            st.caption("暂无记录。")

        st.info("方法论：基差=生意社现货-期货主力收盘；分位=基差在过去252个交易日中的相对位置；"
                "未来变化基于真实历史数据前推计算，无未来函数。历史规律不代表未来表现。")


# ================= 页面4：策略输出 =================
elif page == "📋 策略输出":
    st.header("策略建议输出")
    st.caption("规则全透明：每条策略的依据均引用「量化研究」页的真实检验数据，"
               "可追溯、可质疑、可修正")

    from strategy import build_strategy
    try:
        from report import generate_weekly_report
        _report_ok = True
    except ModuleNotFoundError:
        _report_ok = False

    sym_s = st.selectbox("品种", list(SPOT.keys()),
                         format_func=lambda s: SPOT[s][0], key="strategy_sym")

    # ---- 解读：连贯的市场分析文字 ----
    from strategy import market_brief
    brief = market_brief(conn, sym_s)
    if brief:
        st.markdown(
            f"""<div style="background:rgba(31,78,121,0.12);
            border-left:4px solid #1F4E79;border-radius:6px;
            padding:14px 18px;margin-bottom:16px">
            <b style="font-size:15px">🎙️ 解读</b>
            <div style="font-size:14px;line-height:1.8;margin-top:6px;
            white-space:pre-wrap">{brief}</div></div>""",
            unsafe_allow_html=True)

    strategies = build_strategy(conn, sym_s)

    LINE_COLOR = {"套期保值": "#1F4E79", "基差交易": "#6A3D9A"}
    for s in strategies:
        lc = LINE_COLOR.get(s["线"], "#666")
        st.markdown(
            f"""<div style="border:1px solid rgba(128,128,128,0.35);
            border-left:5px solid {lc};border-radius:6px;padding:14px 18px;
            margin-bottom:14px;background:rgba(128,128,128,0.08)">
            <span style="background:{lc};color:#fff;font-size:12px;
            padding:2px 10px;border-radius:10px">{s['线']}</span>
            <b style="font-size:16px;margin-left:8px">{s['策略']}</b>
            <span style="font-size:13px;opacity:0.6;margin-left:6px">（{s['强度']}）</span>
            <hr style="margin:8px 0;border:none;
            border-top:1px dashed rgba(128,128,128,0.35)">
            <b>依据</b>：{s['依据']}<br>
            <b>建议参数</b>：{s['建议参数']}<br>
            <b>失效条件</b>：{s['失效条件']}<br>
            <b style="color:#EF5350">风险提示</b>：{s['风险提示']}
            </div>""", unsafe_allow_html=True)
    if not strategies:
        st.info("当前无策略输出。")

    st.divider()
    st.subheader("交易测算器")
    st.caption("交易判断的最后一公里：把方向和依据，换算成具体的盈亏数字")
    from analysis import basis_summary
    cur = basis_summary(conn, sym_s)
    tab1, tab2 = st.tabs(["基差交易测算", "套保测算"])
    with tab1:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            entry = st.number_input("入场基差（元/吨）",
                                    value=float(cur["basis"]) if cur else 0.0, step=5.0)
        with c2:
            target = st.number_input("目标基差（元/吨）", value=50.0, step=5.0)
        with c3:
            stop = st.number_input("止损基差（元/吨）",
                                   value=float(cur["basis"]) - 50 if cur else -50.0, step=5.0)
        with c4:
            size = st.number_input("规模（吨）", value=1000, step=100)
        profit = (target - entry) * size
        loss = (entry - stop) * size
        rr = profit / loss if loss > 0 else 0
        m1, m2, m3 = st.columns(3)
        m1.metric("预期盈利", f"{profit / 10000:.1f} 万元")
        m2.metric("最大亏损", f"{loss / 10000:.1f} 万元")
        m3.metric("盈亏比", f"{rr:.1f} : 1",
                  delta="值得做" if rr >= 2 else ("勉强" if rr >= 1 else "不划算"),
                  delta_color="normal" if rr >= 2 else "off")
        st.caption("参考：当前基差分位对应的历史20日平均变化，见上方策略卡「依据」")
    with tab2:
        c1, c2, c3 = st.columns(3)
        with c1:
            inv_t = st.number_input("库存敞口（吨）", value=5000, step=500)
        with c2:
            fut_p = st.number_input("当前期货价（元/吨）",
                                    value=float(cur["futures"]) if cur else 3100.0, step=10.0)
        with c3:
            ratio = st.slider("拟套保比例（%）", 0, 100, 60)
        lots = inv_t * ratio / 100 / 10
        margin = lots * 10 * fut_p * 0.10
        lock = (fut_p - 15) if cur else fut_p
        m1, m2, m3 = st.columns(3)
        m1.metric("套保手数", f"{lots:.0f} 手（{inv_t * ratio / 100:.0f} 吨）")
        m2.metric("保证金占用（约10%）", f"{margin / 10000:.1f} 万元")
        m3.metric("当前基差下锁定售价≈", f"{fut_p + (cur['basis'] if cur else 0):.0f} 元/吨")
        st.caption("注：锁定售价=期货价+基差（基差为负即期货升水时，卖保实际售价高于当前现货价）")

    st.divider()
    st.subheader("周度策略报告")
    st.caption("页面直接阅读，或一键导出Word审阅上报")
    if not _report_ok:
        st.warning("Word导出组件未安装：双击 setup_and_run.bat 自动安装，"
                   "或在cmd执行 pip install python-docx 后重启网页（页面预览不受影响）")
    try:
        from report import build_weekly_markdown
        with st.expander("📖 本周策略报告（点击展开全文）", expanded=True):
            st.markdown(build_weekly_markdown(conn))
    except Exception as e:
        st.info(f"预览生成失败：{e}")
    if _report_ok and st.button("📄 生成并下载 Word 版", use_container_width=True):
        with st.spinner("生成中……"):
            rpath = generate_weekly_report(conn)
        with open(rpath, "rb") as f:
            st.download_button("⬇️ 下载 Word 报告", f,
                               file_name=rpath.split("/")[-1],
                               mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                               use_container_width=True)
        st.success("已生成，点击上方按钮下载")

    st.divider()
    st.subheader("月差结构检验（2021年以来）")
    st.caption("月差同样存在均值回归：深contango多修复、深back多收敛——月差因子的数据依据")
    from research import spread_regime_test
    st.dataframe(spread_regime_test(conn, sym_s), use_container_width=True, hide_index=True)


# ================= 页面5：热点消息 =================
elif page == "📰 热点消息":
    st.header("黑色系热点消息")

    # ---- AI 每日解读 ----
    from ai_analysis import is_ready as _ai_ready, daily_interpret
    if not _ai_ready():
        st.info("🤖 AI自动解读：请先到「🗄️ 数据管理」页底部配置 Kimi API Key "
                "（platform.moonshot.cn 免费申请），配置后此处一键生成每日消息解读。")
    else:
        a1, a2 = st.columns([1, 3])
        with a1:
            gen_ai = st.button("🤖 生成今日AI解读", use_container_width=True)
        if gen_ai:
            from analysis import basis_summary
            from factors import month_spread, profit_factor
            from signals import hedge_scorecard
            snap_parts = []
            for _s, (_n, _) in SPOT.items():
                _i = basis_summary(conn, _s)
                _c = hedge_scorecard(conn, _s, persist=False)
                if _i and _c:
                    snap_parts.append(
                        f"{_n}: 现货{_i['spot']:.0f} 期货{_i['futures']:.0f} "
                        f"基差{_i['basis']:+.0f}(近一年{_c['basis_pct']}%分位) "
                        f"信号{_c['icon']}(总分{_c['total']:+d})")
            _ms = month_spread(conn, "RB")
            _pf = profit_factor(conn)
            snap_parts.append(f"螺纹主力月差{_ms['spread'].iloc[-1]:+.0f}元/吨; "
                              f"盘面毛利{_pf['profit'].iloc[-1]:.0f}元/吨(未扣加工费)")
            today_news = get_news(conn, days=1, category=None).to_dict("records")
            with st.spinner("AI分析中（约10-20秒）……"):
                try:
                    result = daily_interpret("\n".join(snap_parts), today_news)
                    st.session_state["ai_result"] = result
                except Exception as e:
                    st.error(f"AI调用失败：{e}")
        if st.session_state.get("ai_result"):
            st.markdown(
                f"""<div style="background:rgba(106,61,154,0.10);
                border-left:4px solid #6A3D9A;border-radius:6px;
                padding:14px 18px;margin-bottom:12px">
                <b>🤖 AI每日解读</b><div style="font-size:14px;line-height:1.8;
                margin-top:6px;white-space:pre-wrap">{st.session_state['ai_result']}</div>
                </div>""", unsafe_allow_html=True)

    # ---- 顶部紧凑工具行 ----
    t1, t2, t3, t4 = st.columns([1.2, 1, 1, 1.2])
    with t1:
        if st.button("🔄 抓取最新消息", use_container_width=True):
            with st.spinner("抓取过滤中……"):
                n = fetch_news(conn, verbose=False)
            st.toast(f"新增 {n} 条相关消息")
    with t2:
        q_days = st.selectbox("时间", [1, 3, 7, 30], index=2,
                              format_func=lambda d: f"近{d}天", label_visibility="collapsed")
    with t3:
        q_cat = st.selectbox("分类", ["全部"] + list(CATS.keys()),
                             label_visibility="collapsed")
    with t4:
        if st.button("📄 导出（给AI解读）", use_container_width=True):
            path = export_news_txt(conn, days=q_days)
            st.toast("已导出到 output 文件夹" if path else "所选范围无消息")

    news = get_news(conn, days=q_days, category=q_cat)
    st.caption(f"共 {len(news)} 条 · 红=偏多 绿=偏空 灰=中性（规则初判） · "
               f"来源：东财/新浪/上海金属网")
    if news.empty:
        st.info("暂无消息，点「抓取最新消息」试试。")
    else:
        import html as _html
        from news import impact_analysis
        DIR_COLOR = {"偏多": "#C62828", "偏空": "#2E7D32", "中性": "#888888"}
        LEVEL_COLOR = {"强": "#B71C1C", "中": "#E6852D", "弱": "#999999"}

        def badge(txt, bg):
            return (f'<span style="background:{bg};color:#fff;font-size:11px;'
                    f'padding:1px 8px;border-radius:8px;margin-left:6px">{txt}</span>')

        # ---- 按日期分组展示 ----
        news = news.copy()
        news["day"] = news["pub_time"].str[:10]
        for day, group in news.groupby("day", sort=False):
            st.subheader(f"📅 {day}", divider=False)
            for _, r in group.iterrows():
                imp = impact_analysis(r["title"], r["summary"], r["category"])
                color = CAT_COLOR.get(r["category"], "#666")
                title_e = _html.escape(str(r["title"])).replace("\n", " ").replace("\r", " ")
                summ_e = _html.escape(str(r["summary"])).replace("\n", " ").replace("\r", " ")
                # 无独立摘要时不留空行（空行会截断HTML块导致尾部代码外露）
                summary_html = (f'<div style="font-size:13px;opacity:0.85;'
                                f'margin:4px 0">{summ_e}</div>'
                                if r["summary"] and r["summary"] != r["title"] else "")
                card_html = (
                    f'<div style="border-left:4px solid {color};padding:8px 14px;'
                    f'margin-bottom:10px;background:rgba(128,128,128,0.08);border-radius:4px">'
                    f'<span style="font-size:12px;opacity:0.6">{r["pub_time"][11:16]} · {r["source"]}</span>'
                    + badge(r["category"], color) + badge(imp["品种"], "#1F4E79")
                    + badge(imp["方向"], DIR_COLOR[imp["方向"]])
                    + badge("影响" + imp["程度"], LEVEL_COLOR[imp["程度"]])
                    + f'<div style="font-weight:bold;font-size:15px;margin-top:4px">{title_e}</div>'
                    + summary_html
                    + f'<div style="font-size:12px;opacity:0.55">📍 {imp["路径"]}</div>'
                    + "</div>")
                st.markdown(card_html, unsafe_allow_html=True)
                if r["url"]:
                    with st.expander("查看原文"):
                        st.markdown(f"[{r['url']}]({r['url']})")

    st.divider()
    st.info("💡 深度解读：点「导出」后打开 output 文件夹的txt，全文粘给 Kimi，"
            "我结合当日基差、月差、信号为你做利多利空分析。")


# ================= 页面4：数据管理 =================
elif page == "🗄️ 数据管理":
    st.header("数据管理")

    st.subheader("行情数据")
    if st.button("🔄 更新期货行情（5个品种，约10秒）"):
        from fetch_data import update_futures
        with st.spinner("更新中……"):
            update_futures(conn)
        st.success("期货行情已更新")
    if st.button("🔄 更新现货数据（增量补齐，按天限速抓取）"):
        from fetch_data import update_spot
        with st.spinner("更新中，首次补齐历史约需数分钟……"):
            update_spot(conn)
        st.success("现货数据已更新")

    st.subheader("数据覆盖情况")
    rows = []
    for sym, name in FUTURES.items():
        d = pd.read_sql("SELECT MIN(date) a, MAX(date) b, COUNT(*) c FROM futures_daily WHERE symbol=?",
                        conn, params=(sym,))
        rows.append({"品种": f"{name}({sym})", "起始": d["a"][0], "最新": d["b"][0], "条数": d["c"][0]})
    for sym, (name, _) in SPOT.items():
        d = pd.read_sql("SELECT MIN(date) a, MAX(date) b, COUNT(*) c FROM spot_daily WHERE symbol=?",
                        conn, params=(sym,))
        rows.append({"品种": f"{name}现货({sym})", "起始": d["a"][0], "最新": d["b"][0], "条数": d["c"][0]})
    d = pd.read_sql("SELECT COUNT(*) c FROM news", conn)
    rows.append({"品种": "热点消息", "起始": "-", "最新": "-", "条数": d["c"][0]})
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
    st.caption("数据库文件：data/steel_quant.db（SQLite，可直接备份拷贝）")

    st.divider()
    st.subheader("Mysteel 周度数据手工录入")
    st.caption("每周从Mysteel库存频道抄几个关键数（1分钟），系统自动累积库存历史，"
               "后续接入库存因子和库存走势图")
    with st.form("inv_form"):
        c1, c2, c3 = st.columns(3)
        with c1:
            inv_name = st.selectbox("指标", ["螺纹社会库存(万吨)", "螺纹钢厂库存(万吨)",
                                            "热卷社会库存(万吨)", "日均铁水产量(万吨)",
                                            "电炉产能利用率(%)"])
        with c2:
            inv_date = st.date_input("数据日期")
        with c3:
            inv_value = st.number_input("数值", step=0.01, format="%.2f")
        if st.form_submit_button("保存", use_container_width=True):
            conn.execute("INSERT OR REPLACE INTO inventory VALUES(?,?,?,?)",
                         (inv_name, inv_date.isoformat(), float(inv_value), "Mysteel手工录入"))
            conn.commit()
            st.success(f"已保存：{inv_name} {inv_date} = {inv_value}")
    inv = pd.read_sql("SELECT * FROM inventory ORDER BY date DESC LIMIT 10", conn)
    if not inv.empty:
        st.dataframe(inv, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("外部数据批量导入（Excel / CSV）")
    st.caption("把 Kimi 从 Wind 取好的数据（或任何 Excel）一次性导入，与手工录入共用同一张库存/产业数据表。"
               "文件需包含三列：指标、日期、数值（备注列可选）。可向 Kimi 索取《外部数据导入模板.xlsx》。")
    up_file = st.file_uploader("选择文件", type=["xlsx", "xls", "csv"], key="ext_upload")
    if up_file is not None:
        try:
            if up_file.name.lower().endswith(".csv"):
                imp = pd.read_csv(up_file)
            else:
                imp = pd.read_excel(up_file)
            col_map = {}
            for c in imp.columns:
                cs = str(c).strip()
                if cs in ("指标", "名称", "指标名称", "name"): col_map[c] = "name"
                elif cs in ("日期", "数据日期", "时间", "date"): col_map[c] = "date"
                elif cs in ("数值", "值", "value"): col_map[c] = "value"
                elif cs in ("备注", "来源", "note"): col_map[c] = "note"
            imp = imp.rename(columns=col_map)
            if {"name", "date", "value"} <= set(imp.columns):
                imp["date"] = pd.to_datetime(imp["date"]).dt.strftime("%Y-%m-%d")
                if "note" not in imp.columns:
                    imp["note"] = "外部导入"
                st.dataframe(imp.head(10), use_container_width=True, hide_index=True)
                st.caption(f"共 {len(imp)} 行，确认无误后点下方按钮入库（同指标同日期自动覆盖）")
                if st.button("📥 确认导入", use_container_width=True, key="ext_import_btn"):
                    n = 0
                    for _, r in imp.iterrows():
                        conn.execute("INSERT OR REPLACE INTO inventory VALUES(?,?,?,?)",
                                     (str(r["name"]), str(r["date"]), float(r["value"]), str(r["note"])))
                        n += 1
                    conn.commit()
                    st.success(f"已导入 {n} 行")
            else:
                st.error("未识别到「指标/日期/数值」三列，请检查表头（支持中文或 name/date/value）")
        except Exception as e:
            st.error(f"文件读取失败：{e}")

    # 产业数据走势图
    names = pd.read_sql("SELECT DISTINCT name FROM inventory ORDER BY name", conn)["name"].tolist()
    if names:
        st.subheader("产业数据走势")
        pick = st.selectbox("选择指标", names, key="inv_chart_pick")
        h = pd.read_sql("SELECT date, value FROM inventory WHERE name=? ORDER BY date",
                        conn, params=(pick,))
        if len(h) >= 2:
            latest_v, prev_v = h["value"].iloc[-1], h["value"].iloc[-2]
            chg = latest_v - prev_v
            mm1, mm2, mm3 = st.columns(3)
            mm1.metric("最新值", f"{latest_v:.2f}", f"{chg:+.2f}")
            mm2.metric("数据期数", f"{len(h)} 期")
            mm3.metric("区间", f"{h['date'].iloc[0]} ~ {h['date'].iloc[-1]}")
            fig_inv = go.Figure()
            fig_inv.add_trace(go.Scatter(x=h["date"], y=h["value"], name=pick,
                                         mode="lines+markers",
                                         line=dict(color="#0B7A75", width=2)))
            fig_inv.update_layout(hovermode="x unified", height=360, title=pick)
            st.plotly_chart(fig_inv, use_container_width=True)
            if len(h) >= 8:
                st.caption("💡 数据攒到8期以上后，这些曲线就可以升级成「库存因子」进入信号记分卡——"
                           "到时候叫 Kimi 帮你接入。")
        else:
            st.caption("该指标数据不足2期，继续累积。")

    st.divider()
    st.subheader("AI 分析配置（Kimi API）")
    st.caption("配置后「热点消息」页可一键生成AI每日解读。Key只保存在本地 ai_config.json，"
               "已在 .gitignore 中排除，不会上传GitHub。云端部署请在 Streamlit Cloud 后台 "
               "Settings → Secrets 添加 KIMI_API_KEY。")
    from ai_analysis import load_config, save_config, is_ready
    _cfg = load_config()
    st.caption(f"当前状态：{'✅ 已配置' if is_ready() else '❌ 未配置'}")
    key_input = st.text_input("Kimi API Key", type="password",
                              placeholder="sk-...（platform.moonshot.cn → API Key管理 申请）")
    if st.button("保存Key", use_container_width=True):
        if key_input.strip():
            save_config(key_input)
            st.success("已保存，回「热点消息」页生成AI解读试试")
        else:
            st.warning("请输入Key")
