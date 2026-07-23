# -*- coding: utf-8 -*-
"""SQLite 数据库：建表与连接（无需安装数据库软件，数据存在 data 文件夹）"""
import sqlite3
from config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    # 期货日线：开高低收、成交量、持仓量、结算价
    conn.execute("""CREATE TABLE IF NOT EXISTS futures_daily(
        symbol TEXT NOT NULL, date TEXT NOT NULL,
        open REAL, high REAL, low REAL, close REAL,
        volume REAL, hold REAL, settle REAL,
        PRIMARY KEY(symbol, date))""")
    # 现货日线：生意社现货价、主力合约、主力合约价、基差
    conn.execute("""CREATE TABLE IF NOT EXISTS spot_daily(
        symbol TEXT NOT NULL, date TEXT NOT NULL,
        spot_price REAL, dominant_contract TEXT,
        dominant_price REAL, dom_basis REAL,
        PRIMARY KEY(symbol, date))""")
    # 库存表（二期使用：社会库存/钢厂库存，可从 Excel 手工导入）
    conn.execute("""CREATE TABLE IF NOT EXISTS inventory(
        name TEXT NOT NULL, date TEXT NOT NULL, value REAL,
        note TEXT, PRIMARY KEY(name, date))""")
    # 热点消息表：黑色系相关财经快讯
    conn.execute("""CREATE TABLE IF NOT EXISTS news(
        id TEXT PRIMARY KEY, source TEXT, title TEXT, summary TEXT,
        content TEXT, pub_time TEXT, category TEXT, url TEXT)""")
    # 套保信号记录表：每日记分卡落库，用于胜率复盘
    conn.execute("""CREATE TABLE IF NOT EXISTS signals(
        date TEXT NOT NULL, symbol TEXT NOT NULL,
        basis_pct REAL, basis_score INTEGER,
        spread REAL, spread_score INTEGER,
        profit_pct REAL, profit_score INTEGER,
        total INTEGER, level TEXT,
        PRIMARY KEY(date, symbol))""")
    conn.commit()
    return conn
