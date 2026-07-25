"""決策事件。

各模組的輸出格式不同、單位不同、關心的東西也不同。主管不需要知道
某個數字來自哪一個模組，他要的是：發生什麼、多嚴重、證據是什麼、該做什麼。
所有模組在這裡統一翻譯成同一種結構，控制塔只排優先順序。

每一則事件的 evidence 都是實際計算出來的數字，沒有任何預先寫入的結論。
automation_ok 決定它能不能交給 Agent 自動處理——高影響、涉及對外承諾、
或需要人際判斷的一律轉人工，這條界線是設計的一部分，不是限制。
"""
from __future__ import annotations

import pandas as pd

SEV_ORDER = {"緊急": 0, "高": 1, "中": 2, "低": 3}


def _e(eid, domain, severity, title, evidence, action, entity="", automation_ok=False,
       source=""):
    return dict(event_id=eid, domain=domain, severity=severity, title=title,
                evidence=evidence, recommended_action=action, entity=entity,
                automation_ok=automation_ok, source=source, status="待處理")


def build(R) -> pd.DataFrame:
    ev, n = [], 0

    def nid():
        nonlocal n
        n += 1
        return f"EVT-{n:03d}"

    # ── 供應履約：補貨與產能 ──────────────────────────────
    lk = R["bridge"]["linked"]
    for _, p in lk.iterrows():
        if p["補貨缺口"] <= 0:
            continue
        tight = p["涵蓋天數"] is not None and p["涵蓋天數"] <= p["前置期天"] * 1.5
        sev = "緊急" if tight else ("高" if p["補貨缺口"] > 300 else "中")
        ev.append(_e(
            nid(), "庫存", sev, f"{p['商品']}庫存不足以支應下月需求",
            f"下月預測 {p['下月預測']:.0f} 件（{p['預測方法']}），"
            f"目前庫存 {p['目前庫存']} 件、僅夠 {p['涵蓋天數']} 天，"
            f"補貨前置期 {p['前置期天']} 天，缺口 {p['補貨缺口']:.0f} 件。",
            f"立即建立 {p['補貨缺口']:.0f} 件補貨需求並排入配送",
            entity=p["商品"], automation_ok=True, source="需求預測 × 庫存"))

    bn = R["bridge"]["bottleneck"]
    for _, z in bn.iterrows():
        if z["產能使用率"] >= 85:
            ev.append(_e(
                nid(), "配送", "緊急" if z["產能使用率"] >= 90 else "高",
                f"{z['溫層']}車隊產能逼近上限",
                f"{z['溫層']}配送需求 {z['今日配送需求kg']:,} 公斤，"
                f"車隊總容量 {z['車隊容量kg']:,} 公斤，使用率 {z['產能使用率']}%，"
                f"僅剩 {z['剩餘容量kg']} 公斤餘裕。同時有 {z['待補貨件數']} 件該溫層商品待補。",
                "評估增購或租用同溫層車輛，或與門市協商調整收貨時段",
                entity=z["溫層"], automation_ok=False, source="配送網絡 × 補貨缺口"))

    st = R["routing"]["stress"]
    fail = st[st.未能服務門市 > 0]
    if len(fail):
        f = fail.iloc[0]
        ev.append(_e(
            nid(), "配送", "高", "需求小幅成長即出現無法服務的門市",
            f"壓力測試顯示需求成長 {f['需求成長']} 時，現有車隊已有 "
            f"{f['未能服務門市']} 家門市無法排入當日路線。",
            "提前規劃車隊擴充，不要等到當天才發現送不完",
            automation_ok=False, source="路徑最佳化壓力測試"))

    nv, wf = R["routing"]["naive"]["summary"], R["routing"]["opt"]["summary"]
    if nv["violations"] + nv["early_min"] > 0:
        ev.append(_e(
            nid(), "配送", "中", "直覺排法有門市無法在可收貨時段內送達",
            f"按地理就近排序的方案：總成本 NT${nv['total_cost']:,.0f}，"
            f"{nv['violations']} 家門市遲到、累計 {nv['late_min']} 分鐘，"
            f"另有門市早到共 {nv['early_min']} 分鐘（到場時店未開門）。"
            f"最佳化後總成本 NT${wf['total_cost']:,.0f}，時窗違反歸零。",
            f"改採最佳化排程，同時省下 NT${nv['total_cost']-wf['total_cost']:,.0f}",
            automation_ok=True, source="OR-Tools CVRPTW"))

    # ── 客戶經營：流失與聲音 ─────────────────────────────
    ch = R["churn"]
    top = ch["scored"].nlargest(5, "at_risk_value")
    for _, c in top.iterrows():
        comp = R["voice"]["raw"]
        neg = comp[(comp.customer_id == c.customer_id) & (comp.is_negative)]
        sev = "緊急" if (c.churn_prob >= .8 and len(neg)) else "高"
        e = (f"流失機率 {c.churn_prob:.0%}，累積消費 NT${c.Monetary:,.0f}，"
             f"最近購買 {c.Recency:.0f} 天前，分群「{c.cluster_name}」。")
        if len(neg):
            e += f" 另有 {len(neg)} 則負面客訴，主要痛點為{neg.pain_category.mode().iloc[0]}。"
        ev.append(_e(
            nid(), "客戶", sev, f"高價值客戶 {c.customer_id} 流失風險",
            e, "由客戶經理於 24 小時內人工聯繫，不要用自動化訊息",
            entity=c.customer_id, automation_ok=False, source="流失模型 × 客訴"))

    pain = R["voice"]["pain"]
    p0 = pain.iloc[0]
    ev.append(_e(
        nid(), "顧客體驗", "高", f"{p0.pain_category}是客訴量與嚴重度雙冠",
        f"{int(p0['件數'])} 則客訴（占全部 {p0['件數']/len(R['voice']['raw'])*100:.0f}%），"
        f"負面率 {p0['負面率']}%，涉及 {int(p0['涉及顧客數'])} 位顧客。",
        "納入服務流程檢討，並與配送排程一併檢視",
        entity=p0.pain_category, automation_ok=False, source="客訴文本分析"))

    # ── 資料治理 ────────────────────────────────────────
    cand = R["bridge"]["candidates"]
    bad = cand[cand.人工判定 != "採用"]
    ev.append(_e(
        nid(), "資料治理", "中", "兩套商品編碼缺少共同主檔",
        f"銷售端與庫存端各有 30 項商品、編碼規則不同。自動比對找到 "
        f"{len(cand)} 組疑似同物，人工檢查後剔除 {len(bad)} 組誤配"
        f"（{bad.iloc[0].零售主檔} vs {bad.iloc[0].生鮮主檔}），"
        f"實際只有 {len(R['bridge']['linked'])} 項能貫通預測與庫存。",
        "建立統一 Product Master，指定權威來源系統",
        automation_ok=False, source="主資料比對"))

    df = pd.DataFrame(ev)
    df["_o"] = df.severity.map(SEV_ORDER)
    return df.sort_values(["_o", "domain"]).drop(columns="_o").reset_index(drop=True)


def summary(ev: pd.DataFrame):
    return dict(total=len(ev),
                critical=int((ev.severity == "緊急").sum()),
                high=int((ev.severity == "高").sum()),
                auto=int(ev.automation_ok.sum()),
                human=int((~ev.automation_ok).sum()),
                by_domain=ev.domain.value_counts().to_dict())
