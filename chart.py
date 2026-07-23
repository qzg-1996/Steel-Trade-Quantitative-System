# -*- coding: utf-8 -*-
"""图表：基差走势图（现货+期货双线+基差柱状）、卷螺差走势图"""
import os
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from config import OUTPUT_DIR, CHART_DAYS, SPOT
from analysis import basis_df, hc_rb_spread

plt.rcParams["axes.unicode_minus"] = False  # 负号正常显示


def set_chinese_font():
    """自动选择系统里已有的中文字体（Windows 优先微软雅黑）"""
    from matplotlib import font_manager
    installed = {f.name for f in font_manager.fontManager.ttflist}
    for f in ["Microsoft YaHei", "SimHei", "PingFang SC",
              "WenQuanYi Zen Hei", "Noto Sans CJK SC"]:
        if f in installed:
            matplotlib.rcParams["font.family"] = f
            return


def plot_basis(conn, spot_symbol, days=CHART_DAYS):
    """基差走势图：左轴现货+期货价格线，右轴基差柱状（绿正红负）"""
    name, _ = SPOT[spot_symbol]
    df = basis_df(conn, spot_symbol).tail(days)
    if df.empty:
        print(f"[图表] {name} 暂无数据，跳过")
        return None

    fig, ax1 = plt.subplots(figsize=(14, 7), dpi=110)
    ax1.plot(df["date"], df["spot_price"], color="#C00000", lw=1.8,
             label=f"{name}现货（生意社）")
    ax1.plot(df["date"], df["close"], color="#1F4E79", lw=1.8,
             label=f"{name}期货主力")
    ax1.set_ylabel("价格（元/吨）", fontsize=12)
    ax1.legend(loc="upper left", fontsize=11)
    ax1.grid(alpha=0.25)

    ax2 = ax1.twinx()
    colors = ["#2E7D32" if b >= 0 else "#C62828" for b in df["basis"]]
    ax2.bar(df["date"], df["basis"], color=colors, alpha=0.45, width=0.8,
            label="基差（现货-期货）")
    ax2.axhline(0, color="#666", lw=0.8, ls="--")
    ax2.set_ylabel("基差（元/吨）", fontsize=12)
    ax2.legend(loc="upper right", fontsize=11)

    ax1.xaxis.set_major_formatter(mdates.DateFormatter("%y-%m-%d"))
    ax1.set_title(f"{name}基差走势图（近{len(df)}个交易日）", fontsize=15, pad=12)
    fig.tight_layout()
    path = os.path.join(OUTPUT_DIR, f"{name}基差走势图.png")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"[图表] 已生成 {path}")
    return path


def plot_hc_rb_spread(conn, days=CHART_DAYS):
    """卷螺差走势图：热卷-螺纹 期货价差"""
    df = hc_rb_spread(conn).tail(days)
    if df.empty:
        print("[图表] 卷螺差暂无数据，跳过")
        return None

    fig, ax = plt.subplots(figsize=(14, 5.5), dpi=110)
    ax.plot(df["date"], df["spread"], color="#6A3D9A", lw=1.6)
    ax.fill_between(df["date"], df["spread"], 0, alpha=0.15, color="#6A3D9A")
    mean_v = df["spread"].mean()
    ax.axhline(mean_v, color="#888", ls="--", lw=1,
               label=f"区间均值 {mean_v:.0f}")
    ax.set_title(f"卷螺差走势图（热卷-螺纹，期货主力，近{len(df)}个交易日）",
                 fontsize=15, pad=12)
    ax.set_ylabel("价差（元/吨）", fontsize=12)
    ax.legend(fontsize=11)
    ax.grid(alpha=0.25)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%y-%m-%d"))
    fig.tight_layout()
    path = os.path.join(OUTPUT_DIR, "卷螺差走势图.png")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"[图表] 已生成 {path}")
    return path
