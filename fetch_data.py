# -*- coding: utf-8 -*-
"""数据抓取：期货日线（新浪财经）+ 钢材现货（生意社），自动增量更新"""
import time
import random
import warnings
import pandas as pd

warnings.filterwarnings("ignore")

from config import FUTURES, SPOT, SPOT_START_DATE, REQUEST_INTERVAL


def _active_contracts():
    """当前及次年的1/5/10月主力合约代码（期限结构用）"""
    import datetime
    y = datetime.date.today().year % 100
    return [f"{s}{yy:02d}{m}" for s in ("RB", "HC")
            for yy in (y, y + 1) for m in ("01", "05", "10")]


def _save_daily(conn, sym, df):
    df["symbol"] = sym
    df["date"] = df["date"].astype(str)
    conn.executemany(
        "INSERT OR REPLACE INTO futures_daily VALUES(?,?,?,?,?,?,?,?,?)",
        df[["symbol", "date", "open", "high", "low", "close",
            "volume", "hold", "settle"]].values.tolist())
    conn.commit()


def update_futures(conn):
    """期货日线：接口返回全量历史，逐条覆盖写入（重复日期自动更新）"""
    import akshare as ak
    for sym, name in FUTURES.items():
        try:
            _save_daily(conn, sym, ak.futures_zh_daily_sina(symbol=sym))
            n = conn.execute("SELECT COUNT(*) FROM futures_daily WHERE symbol=?",
                             (sym,)).fetchone()[0]
            print(f"[期货] {name}({sym}) 共 {n} 条")
        except Exception as e:
            print(f"[期货] {name}({sym}) 更新失败：{e}")
    # v0.4 追加：活跃主力合约（期限结构/月差因子用）
    ok = 0
    for c in _active_contracts():
        try:
            _save_daily(conn, c, ak.futures_zh_daily_sina(symbol=c))
            ok += 1
        except Exception:
            pass
    print(f"[期货] 主力合约更新 {ok} 个（期限结构用）")


def _missing_spot_dates(conn):
    """已有期货行情但缺现货数据的交易日列表"""
    fut_dates = pd.read_sql(
        "SELECT DISTINCT date FROM futures_daily WHERE symbol='RB0' AND date>=?",
        conn, params=(SPOT_START_DATE,))["date"].tolist()
    have = pd.read_sql("SELECT DISTINCT date FROM spot_daily", conn)["date"].tolist()
    return sorted(set(fut_dates) - set(have))


def update_spot(conn, days_limit=None):
    """现货日线：按交易日逐日补齐，带随机延时防止被限流"""
    import akshare as ak
    missing = _missing_spot_dates(conn)
    if days_limit:
        missing = missing[-days_limit:]
    if not missing:
        print("[现货] 数据已是最新，无需更新")
        return
    print(f"[现货] 待补 {len(missing)} 个交易日，"
          f"预计约 {len(missing) * 0.8 / 60:.0f} 分钟（防限流限速抓取）……")
    ok = 0
    for i, d in enumerate(missing, 1):
        try:
            sp = ak.futures_spot_price(date=d.replace("-", ""))
            if "symbol" in sp.columns:
                for s in SPOT:
                    row = sp[sp["symbol"] == s]
                    if len(row):
                        r = row.iloc[0]
                        conn.execute(
                            "INSERT OR REPLACE INTO spot_daily VALUES(?,?,?,?,?,?)",
                            (s, d, float(r["spot_price"]), str(r["dominant_contract"]),
                             float(r["dominant_contract_price"]), float(r["dom_basis"])))
                conn.commit()
                ok += 1
        except Exception:
            pass  # 个别日期数据源缺失属正常，下次运行会自动重试
        if i % 20 == 0:
            print(f"[现货] 进度 {i}/{len(missing)}")
        time.sleep(random.uniform(*REQUEST_INTERVAL))
    print(f"[现货] 补齐完成：成功 {ok}/{len(missing)} 天，未补到的下次运行自动重试")
