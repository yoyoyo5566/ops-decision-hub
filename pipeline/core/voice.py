"""客訴聲音分析（D16）：痛點分佈、情緒趨勢、與顧客價值的交叉。"""
from __future__ import annotations

import pandas as pd

NEG = {"負", "強烈負"}
SEV = {"強烈負": 3, "負": 2, "中性": 1, "正": 0}


def enrich(cx: pd.DataFrame):
    d = cx.copy()
    d["is_negative"] = d.sentiment.isin(NEG)
    d["severity"] = d.sentiment.map(SEV)
    return d


def pain_summary(d: pd.DataFrame):
    g = d.groupby("pain_category").agg(
        件數=("id", "count"),
        負面件數=("is_negative", "sum"),
        嚴重度總分=("severity", "sum"),
        涉及顧客數=("customer_id", "nunique"),
    ).reset_index()
    g["負面率"] = (g.負面件數 / g.件數 * 100).round(1)
    return g.sort_values("嚴重度總分", ascending=False).reset_index(drop=True)


def monthly_trend(d: pd.DataFrame):
    g = d.groupby(["month", "pain_category"]).size().reset_index(name="件數")
    return g


def channel_mix(d: pd.DataFrame):
    g = d.groupby(["channel", "sentiment"]).size().reset_index(name="件數")
    return g


def join_customer_value(d: pd.DataFrame, customers: pd.DataFrame):
    """客訴顧客與 RFM 的交叉。兩者同屬 D15/D16 顧客線，ID 體系一致，可安全合併。"""
    agg = d.groupby("customer_id").agg(
        客訴件數=("id", "count"),
        負面件數=("is_negative", "sum"),
        嚴重度=("severity", "sum"),
        主要痛點=("pain_category", lambda s: s.mode().iloc[0]),
    ).reset_index()
    m = agg.merge(customers, on="customer_id", how="left")
    return m.sort_values("嚴重度", ascending=False).reset_index(drop=True)
