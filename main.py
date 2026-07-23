# -*- coding: utf-8 -*-
"""钢贸产业量化系统 v0.1 —— 一键运行入口

用法：
    方式一（推荐小白）：双击「一键更新并出图.bat」
    方式二：在本文件夹打开命令行，执行  python main.py

功能：更新行情 -> 计算基差 -> 生成图表 -> 打印今日摘要
"""
import datetime

from config import SPOT
from db import get_conn
from fetch_data import update_futures, update_spot
from analysis import basis_summary, hc_rb_spread
from chart import set_chinese_font, plot_basis, plot_hc_rb_spread


def main():
    print("=" * 60)
    print("   钢贸产业量化系统 v0.1   |   " + datetime.date.today().isoformat())
    print("=" * 60)
    conn = get_conn()

    print("\n【1/3】更新期货行情（螺纹/热卷/铁矿/焦炭/焦煤）……")
    update_futures(conn)

    print("\n【2/3】更新钢材现货（首次运行需补齐历史，请耐心等候）……")
    update_spot(conn)

    print("\n【3/3】生成图表……")
    set_chinese_font()
    plot_basis(conn, "RB")
    plot_basis(conn, "HC")
    plot_hc_rb_spread(conn)

    print("\n" + "=" * 60)
    print("【今日基差摘要】")
    for s, (name, _) in SPOT.items():
        info = basis_summary(conn, s)
        if info:
            print(f"  {name}（{info['date']}）")
            print(f"    现货 {info['spot']:.0f}  |  期货 {info['futures']:.0f}  |  "
                  f"基差 {info['basis']:+.0f} 元/吨")
            print(f"    基差近一年分位 {info['pct_1y']}%  |  "
                  f"近一年区间 {info['min_1y']:+.0f} ~ {info['max_1y']:+.0f}")
    spread = hc_rb_spread(conn)
    if not spread.empty:
        print(f"  卷螺差（热卷-螺纹期货）最新 {spread['spread'].iloc[-1]:+.0f} 元/吨")
    print("=" * 60)
    print("\n完成！图表已保存在 output 文件夹。")
    conn.close()


if __name__ == "__main__":
    main()
    input("\n按回车键退出……")  # 双击运行时防止窗口闪退
