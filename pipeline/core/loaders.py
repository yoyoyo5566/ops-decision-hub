"""資料載入層。

刻意維持兩條互不合併的資料線，原因見 LINEAGE 說明：
  B2B 供應鏈線  D18 門市主檔 / D19 生鮮庫存 / D17 台中配送網絡
  B2C 顧客線    D15 消費者 RFM 與交易 / D16 客訴文本

兩線的 customer_id 與 sku_id 分屬不同編碼體系，格式相近但語意不同，
唯一經過驗證的橋接是「D18 customer_name = D17 store_name」，20 家門市全數對上。
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

DATA = Path(__file__).resolve().parent.parent.parent / "raw"


def _csv(name, **kw):
    return pd.read_csv(DATA / name, **kw)


# ---------- B2B 供應鏈線 ----------
def stores_master():
    """D18 門市主檔（50 筆客戶，其中 20 筆為門市）"""
    return _csv("源_客戶主檔.csv")


def delivery_network():
    return _csv("配送網絡_台中20門市.csv")


def vehicles():
    return _csv("配送網絡_車型.csv")


def inventory():
    df = _csv("inventory.csv")
    df["last_replenish"] = pd.to_datetime(df["last_replenish"])
    return df


def trigger_rules():
    with open(DATA / "觸發規則.json", encoding="utf-8") as f:
        return json.load(f)


def mdm_rules():
    return _csv("mdm_治理規則表.csv")


def store_bridge():
    """D18 ←→ D17 的門市對照表（唯一驗證過的跨週橋接）"""
    m = stores_master()
    n = delivery_network()
    b = m.merge(n, left_on="customer_name", right_on="store_name", how="inner")
    return b[["customer_id", "customer_name", "store_id", "district_y", "region",
              "temp_zone_y", "demand_kg", "join_date"]].rename(
        columns={"district_y": "district", "temp_zone_y": "temp_zone"})


# ---------- B2C 顧客線 ----------
def customers():
    return _csv("customer_all.csv")


def transactions():
    return _csv("transactions.csv")


def sales_monthly():
    df = _csv("sales_monthly.csv")
    df["date"] = pd.to_datetime(df["date"])
    return df


def sku_catalog():
    return _csv("sku_catalog.csv")


def complaints():
    df = _csv("客訴文本_202509-202602.csv")
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["month"] = df["timestamp"].dt.to_period("M").astype(str)
    return df


LINEAGE = [
    dict(表="源_客戶主檔.csv", 來源="D18", 主鍵="customer_id C001–C050", 筆數=50,
         語意="B2B 客戶，20 家為配送門市", 線="供應鏈"),
    dict(表="配送網絡_台中20門市.csv", 來源="D17", 主鍵="store_id S01–S20 + DEPOT", 筆數=21,
         語意="台中配送節點，含經緯度、時窗、溫層", 線="供應鏈"),
    dict(表="配送網絡_距離矩陣.csv / 時間矩陣.csv", 來源="D17", 主鍵="21×21", 筆數=441,
         語意="節點間距離（km）與行駛時間（分）", 線="供應鏈"),
    dict(表="配送網絡_車型.csv", 來源="D17", 主鍵="vehicle_id V1–V3", 筆數=3,
         語意="車輛容量、油耗、固定成本、工時上限", 線="供應鏈"),
    dict(表="inventory.csv", 來源="D19", 主鍵="sku_id SKU001–SKU030（無底線）", 筆數=30,
         語意="生鮮商品庫存與安全存量", 線="供應鏈"),
    dict(表="customer_all.csv", 來源="D15", 主鍵="customer_id C0001–C1500（四位）", 筆數=1500,
         語意="個人消費者 RFM、分群、流失標籤", 線="顧客"),
    dict(表="transactions.csv", 來源="D15", 主鍵="order_id × sku_id", 筆數=13026,
         語意="消費者購物籃明細", 線="顧客"),
    dict(表="sales_monthly.csv", 來源="D15", 主鍵="sku_id SKU_001–（有底線）× 月", 筆數=360,
         語意="10 項零售商品 36 個月銷量", 線="顧客"),
    dict(表="客訴文本_202509-202602.csv", 來源="D16", 主鍵="id FB-xxxx", 筆數=200,
         語意="消費者客訴文本、情緒、痛點分類", 線="顧客"),
]

ID_CONFLICTS = [
    dict(欄位="customer_id", 體系A="D15/D16　C0001–C1500（四位數）",
         體系B="D18　C001–C050（三位數）",
         實際差異="A 是個人消費者，B 是門市與企業客戶",
         字面交集="0 筆", 處理方式="不合併。兩線各自獨立呈現"),
    dict(欄位="sku_id", 體系A="D15　SKU_001–SKU_030（有底線）",
         體系B="D19　SKU001–SKU030（無底線）",
         實際差異="A 是尿布、啤酒等零售雜貨；B 是鮮乳、優格等生鮮",
         字面交集="0 筆", 處理方式="不合併。預測與庫存分屬不同商品線"),
    dict(欄位="門市識別", 體系A="D17　store_id S01–S20",
         體系B="D18　customer_id C001–C050",
         實際差異="同一批門市的兩種編碼",
         字面交集="0 筆（但 store_name 全數對上）",
         處理方式="以名稱橋接，20/20 成功，是唯一啟用的跨週關聯"),
]
