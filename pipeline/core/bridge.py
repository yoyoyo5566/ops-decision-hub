"""把「賣多少」接到「送多少」。

兩份商品清單來自不同來源、編碼不同（SKU_002 起司 / SKU007 起司片 200g），
自動字串比對會找到 8 組疑似同物，其中一組是誤配（牛奶 vs 牛奶咖啡）。
這裡只採用人工確認過的 7 組，且僅 4 組同時具備銷售歷史與庫存紀錄，
能真正貫通「預測 → 缺口 → 補貨 → 配送」。其餘一律不接。

門市分配權重取自各門市的實際配送量，不是新生成的客戶歸屬映射：
好市多與 Cama 咖啡的需求量差 95 倍，那是資料裡真實存在的業態結構，
用隨機映射推導會把它抹平。
"""
from __future__ import annotations

import difflib

import pandas as pd

# 人工確認過的商品對照（牛奶 → 牛奶咖啡 已剔除）
CONFIRMED = {
    "起司": "起司片 200g",
    "米": "包裝米 5kg",
    "醬油": "醬油 1L",
    "礦泉水": "礦泉水 500ml",
    "麵包": "麵包 600g",
    "餅乾": "餅乾 200g",
    "巧克力": "巧克力 100g",
}
REJECTED = {"牛奶": "牛奶咖啡 500ml"}


def candidate_matches(retail_names, fresh_names, cutoff=0.55):
    """自動比對的原始結果，含誤配，用於呈現主資料落差。"""
    out = []
    for a in retail_names:
        for b in fresh_names:
            if a in b or b in a or difflib.SequenceMatcher(None, a, b).ratio() > cutoff:
                out.append(dict(零售主檔=a, 生鮮主檔=b,
                                相似度=round(difflib.SequenceMatcher(None, a, b).ratio(), 2),
                                人工判定="採用" if CONFIRMED.get(a) == b else "誤配，剔除"))
    return pd.DataFrame(out)


def linked_products(forecast_tbl: pd.DataFrame, inventory_tbl: pd.DataFrame):
    """同時有預測與庫存的商品，這是兩條線唯一能對接的部分。"""
    inv = inventory_tbl.set_index("sku_name")
    rows = []
    for retail, fresh in CONFIRMED.items():
        f = forecast_tbl[forecast_tbl.sku_name == retail]
        if f.empty or fresh not in inv.index:
            continue
        f = f.iloc[0]
        i = inv.loc[fresh]
        need = float(f["下月預測"])
        gap = max(0.0, need - float(i.current_qty))
        rows.append(dict(
            商品=retail, 庫存品名=fresh, 溫層=i.temp_zone,
            下月預測=need, 區間下限=float(f["區間下限"]), 預測方法=f["採用"],
            目前庫存=int(i.current_qty), 安全存量=int(i.safe_stock),
            前置期天=int(i.lead_time_days),
            補貨缺口=round(gap, 0),
            涵蓋天數=round(float(i.current_qty) / (need / 30), 1) if need > 0 else None,
        ))
    return pd.DataFrame(rows).sort_values("補貨缺口", ascending=False).reset_index(drop=True)


def allocate_to_stores(linked: pd.DataFrame, stores: pd.DataFrame):
    """依各門市實際配送量占比，把全公司缺口攤到門市。"""
    s = stores[stores.store_id != "DEPOT"].copy()
    s["share"] = s.demand_kg / s.demand_kg.sum()
    rows = []
    for _, p in linked.iterrows():
        for _, st in s.iterrows():
            if p["溫層"] != st.temp_zone:      # 溫層不符的門市不配該商品
                continue
            q = p["補貨缺口"] * st.share
            if q < 1:
                continue
            rows.append(dict(store_id=st.store_id, store_name=st.store_name,
                             temp_zone=st.temp_zone, 商品=p["商品"],
                             配送量占比=round(st.share, 4),
                             分配補貨量=round(q, 0)))
    return pd.DataFrame(rows)


def bottleneck(linked: pd.DataFrame, stores: pd.DataFrame, vehicles: pd.DataFrame):
    """把補貨缺口按溫層彙總，對照該溫層的車隊容量。"""
    out = []
    for z in ("冷藏", "常溫"):
        cap = int(vehicles.query("temp_zone==@z").capacity_kg.sum())
        dem = int(stores.query("temp_zone==@z").demand_kg.sum())
        gap = float(linked.query("溫層==@z").補貨缺口.sum())
        out.append(dict(溫層=z, 車隊容量kg=cap, 今日配送需求kg=dem,
                        產能使用率=round(dem / cap * 100, 1),
                        剩餘容量kg=cap - dem,
                        待補貨件數=int(gap)))
    return pd.DataFrame(out)
