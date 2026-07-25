"""統一運算入口。頁面上的每個數字都由此處實際計算，沒有預先寫入的結果。"""
from __future__ import annotations

import pickle
import time
from pathlib import Path

import pandas as pd

from . import basket, bridge, churn, events, forecast, inventory, loaders, routing, voice

ART = Path(__file__).resolve().parent.parent / "artifacts"
ART.mkdir(exist_ok=True)
PKL = ART / "results.pkl"


def build(time_limit_s: int = 15) -> dict:
    t0 = time.time()
    R: dict = {}

    stores, veh, dist, tmat = routing.load_network(loaders.DATA)
    nv_res, nv_sum = routing.naive_plan(stores, veh, dist, tmat)
    op_res, op_sum = routing.solve(stores, veh, dist, tmat, mode="window_feasible",
                                   time_limit_s=time_limit_s)
    stress = []
    for pct in (0, 5, 9, 15, 20):
        s2 = stores.copy()
        s2["demand_kg"] = (s2.demand_kg * (1 + pct / 100)).round().astype(int)
        _, ss = routing.solve(s2, veh, dist, tmat, mode="window_feasible",
                              time_limit_s=max(6, time_limit_s // 2))
        stress.append(dict(需求成長=f"+{pct}%", 總需求kg=int(s2.demand_kg.sum()),
                           未能服務門市=ss["dropped"], 總成本=ss["total_cost"]))
    R["routing"] = dict(
        naive=dict(routes=nv_res[0], stops=nv_res[1], summary=nv_sum),
        opt=dict(routes=op_res[0], stops=op_res[1], dropped=op_res[2], summary=op_sum),
        stores=stores, vehicles=veh, stress=pd.DataFrame(stress))

    inv = inventory.assess(loaders.inventory())
    R["inventory"] = dict(table=inv, summary=inventory.summary(inv))

    fc, det = forecast.backtest_all(loaders.sales_monthly())
    R["forecast"] = dict(table=fc, detail=det, sales=loaders.sales_monthly())

    linked = bridge.linked_products(fc, loaders.inventory())
    R["bridge"] = dict(
        linked=linked,
        candidates=bridge.candidate_matches(loaders.sku_catalog().sku_name,
                                            loaders.inventory().sku_name),
        allocation=bridge.allocate_to_stores(linked, stores),
        bottleneck=bridge.bottleneck(linked, stores, veh))

    cus = loaders.customers()
    R["churn"] = churn.fit(cus)

    tx = loaders.transactions()
    rules, stats = basket.mine(tx, min_support=0.02, min_lift=1.05, min_conf=0.2)
    R["basket"] = dict(rules=rules, stats=stats, tx=tx,
                       coverage=basket.coverage(rules, tx, cus))

    cx = voice.enrich(loaders.complaints())
    R["voice"] = dict(raw=cx, pain=voice.pain_summary(cx), trend=voice.monthly_trend(cx),
                      with_value=voice.join_customer_value(cx, R["churn"]["scored"]))

    R["events"] = events.build(R)
    R["event_summary"] = events.summary(R["events"])
    R["_meta"] = dict(built_at=pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
                      seconds=round(time.time() - t0, 1))
    return R


def load(force=False) -> dict:
    if PKL.exists() and not force:
        try:
            with open(PKL, "rb") as f:
                return pickle.load(f)
        except Exception:
            pass
    R = build()
    with open(PKL, "wb") as f:
        pickle.dump(R, f)
    return R


