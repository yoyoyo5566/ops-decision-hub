"""生鮮庫存風險評估（D19）。"""
from __future__ import annotations

import pandas as pd

AS_OF = pd.Timestamp("2026-05-20")   # D19 資料的評估基準日


def assess(inv: pd.DataFrame, as_of: pd.Timestamp = AS_OF):
    d = inv.copy()
    d["gap_qty"] = (d.safe_stock - d.current_qty).clip(lower=0)
    d["fill_rate"] = (d.current_qty / d.safe_stock * 100).round(1)
    d["days_since_replenish"] = (as_of - d.last_replenish).dt.days
    d["below_safe"] = d.current_qty < d.safe_stock

    def band(r):
        if not r.below_safe:
            return "正常"
        if r.fill_rate < 40:
            return "斷貨風險"
        if r.fill_rate < 70:
            return "偏低"
        return "接近下限"

    d["status"] = d.apply(band, axis=1)
    d["priority"] = d.gap_qty * d.lead_time_days
    return d.sort_values("priority", ascending=False).reset_index(drop=True)


def summary(d: pd.DataFrame):
    return dict(
        skus=len(d),
        below=int(d.below_safe.sum()),
        below_pct=round(d.below_safe.mean() * 100, 1),
        gap_total=int(d.gap_qty.sum()),
        critical=int((d.status == "斷貨風險").sum()),
        by_zone=d.groupby("temp_zone").below_safe.sum().to_dict(),
        longest_lead=int(d[d.below_safe].lead_time_days.max()) if d.below_safe.any() else 0,
    )
