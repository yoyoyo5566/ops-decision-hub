"""把運算結果匯出成靜態網站用的 JSON。

跑法：
    python build_static.py

會重新配適所有模型、重解路徑，再把結果寫進 site/data/。
網站本身不含任何運算，但每個數字都來自這支腳本，改資料重跑即可全部更新。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from core import compute, loaders  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT
OUT = ROOT / "data"


def jsonable(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return round(float(o), 4)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, pd.Timestamp):
        return o.strftime("%Y-%m-%d")
    if isinstance(o, pd.DataFrame):
        return o.to_dict("records")
    if isinstance(o, pd.Series):
        return o.tolist()
    raise TypeError(str(type(o)))


def clean(o):
    """把 NaN / NaT / Inf 一律轉成 null——瀏覽器的 JSON.parse 不接受 NaN。"""
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, pd.DataFrame):
        return clean(o.to_dict("records"))
    if isinstance(o, float) and (np.isnan(o) or np.isinf(o)):
        return None
    if o is pd.NaT:
        return None
    if isinstance(o, (np.floating,)):
        f = float(o)
        return None if (np.isnan(f) or np.isinf(f)) else round(f, 4)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, pd.Timestamp):
        return o.strftime("%Y-%m-%d")
    return o


def write(name: str, payload):
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"{name}.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(clean(payload), f, ensure_ascii=False, default=jsonable,
                  separators=(",", ":"), allow_nan=False)
    print(f"  {p.relative_to(ROOT)}  {p.stat().st_size/1024:.0f} KB")


def main():
    print("重新計算全部結果…")
    R = compute.load(force="--cached" not in sys.argv)

    # ── 決策事件 ───────────────────────────────────────
    write("events", dict(
        events=R["events"].to_dict("records"),
        summary=R["event_summary"],
        built_at=R["_meta"]["built_at"],
        seconds=R["_meta"]["seconds"],
    ))

    # ── 顧客 ──────────────────────────────────────────
    ch = R["churn"]
    sc = ch["scored"]
    cl = (sc.groupby("cluster_name")
            .agg(人數=("customer_id", "count"), 最近購買=("Recency", "mean"),
                 購買次數=("Frequency", "mean"), 累積消費=("Monetary", "mean"),
                 流失機率=("churn", "mean"))
            .round(1).reset_index())
    cross = pd.crosstab(sc.Segment_D4, sc.cluster_name).reset_index()
    top = sc.assign(風險金額=(sc.Monetary * sc.churn)).nlargest(20, "風險金額")
    write("customers", dict(
        metrics=ch["metrics"], naive=ch["naive"],
        sweep=ch["sweep"].to_dict("records"),
        importance=ch["importance"].to_dict("records"),
        depth_scan=ch["depth_scan"].to_dict("records"),
        clusters=cl.to_dict("records"),
        cross=cross.to_dict("records"),
        cluster_names=sorted(sc.cluster_name.unique().tolist()),
        top_targets=top[["customer_id", "Recency", "Frequency", "Monetary",
                         "ComplaintCnt", "Segment_D4", "cluster_name",
                         "churn", "風險金額"]].to_dict("records"),
        scatter=sc.sample(600, random_state=1)[
            ["Recency", "Frequency", "Monetary", "churn", "cluster_name"]
        ].to_dict("records"),
        n=len(sc), churn_rate=round(float(sc.Churn.mean()), 4),
        tree_rules=ch.get("tree_text", ""),
    ))

    # ── 商品關聯 ──────────────────────────────────────
    bk = R["basket"]
    rules = bk["rules"].copy()
    # Lift 陷阱：找出現率最高、且以它為結果時信賴度好看但提升度貼近 1 的品項
    tx = bk["tx"]
    n_orders = tx.order_id.nunique()
    freq = (tx.groupby("sku_name").order_id.nunique() / n_orders).sort_values(ascending=False)
    trap_item = None
    for item in freq.index[:6]:
        sub = rules[rules["後項"] == item]
        if len(sub) >= 3 and sub.lift.max() < 1.25:
            trap_item = item
            break
    trap = {}
    if trap_item:
        sub = rules[rules["後項"] == trap_item].nlargest(6, "confidence")
        trap = dict(item=trap_item, base_rate=round(float(freq[trap_item]), 4),
                    rules=sub.to_dict("records"),
                    max_conf=round(float(sub.confidence.max()), 4),
                    max_lift=round(float(sub.lift.max()), 4),
                    min_lift=round(float(sub.lift.min()), 4))
    write("basket", dict(
        rules=rules.to_dict("records"),
        stats=bk["stats"], coverage=bk["coverage"],
        trap=trap,
        bands=dict(
            配套販售=int((rules.lift > 2.0).sum()),
            跨類擺放=int(((rules.lift >= 1.3) & (rules.lift <= 2.0)).sum()),
            結帳加購=int(((rules.lift >= 1.1) & (rules.lift < 1.3)).sum()),
            接近無效=int((rules.lift < 1.1).sum()),
        ),
    ))

    # ── 客訴 ──────────────────────────────────────────
    vo = R["voice"]
    write("voice", dict(
        pain=vo["pain"].to_dict("records"),
        trend=vo["trend"].to_dict("records"),
        samples=vo["raw"].sample(60, random_state=2)[
            ["id", "timestamp", "channel", "sentiment", "pain_category", "content"]
        ].to_dict("records"),
        total=len(vo["raw"]),
        negative_rate=round(float(vo["raw"].is_negative.mean()), 4),
        customers=int(vo["raw"].customer_id.nunique()),
        by_channel=vo["raw"].groupby(["channel", "sentiment"]).size()
                            .reset_index(name="件數").to_dict("records"),
    ))

    # ── 預測與庫存 ────────────────────────────────────
    fc = R["forecast"]
    series = {}
    for sku, d in fc["detail"].items():
        tr, te, f = d["train"], d["test"], d["fc"]
        series[sku] = dict(
            name=tr.sku_name.iloc[0],
            history=[dict(d=x.strftime("%Y-%m"), y=int(v))
                     for x, v in zip(tr.date, tr.qty)],
            test=[dict(d=x.strftime("%Y-%m"), y=int(v))
                  for x, v in zip(te.date, te.qty)],
            pred=[dict(d=pd.Timestamp(x).strftime("%Y-%m"), y=round(float(a), 1),
                       lo=round(float(b), 1), hi=round(float(c), 1))
                  for x, a, b, c in zip(f.ds, f.yhat, f.yhat_lower, f.yhat_upper)],
            baselines={k: round(float(v), 1) for k, v in d["all_baselines"].items()},
        )
    inv = R["inventory"]
    br = R["bridge"]
    write("supply", dict(
        forecast=fc["table"].to_dict("records"),
        series=series,
        inventory=inv["table"].drop(columns=["last_replenish"]).to_dict("records"),
        inventory_summary=inv["summary"],
        linked=br["linked"].to_dict("records"),
        candidates=br["candidates"].to_dict("records"),
        allocation=br["allocation"].to_dict("records"),
        bottleneck=br["bottleneck"].to_dict("records"),
    ))

    # ── 配送 ──────────────────────────────────────────
    rt = R["routing"]
    write("delivery", dict(
        naive=dict(routes=rt["naive"]["routes"].to_dict("records"),
                   stops=rt["naive"]["stops"].to_dict("records"),
                   summary=rt["naive"]["summary"]),
        optimized=dict(routes=rt["opt"]["routes"].to_dict("records"),
                       stops=rt["opt"]["stops"].to_dict("records"),
                       summary=rt["opt"]["summary"]),
        stores=rt["stores"].to_dict("records"),
        vehicles=rt["vehicles"].to_dict("records"),
        stress=rt["stress"].to_dict("records"),
    ))

    # ── 資料血緣 ──────────────────────────────────────
    write("lineage", dict(
        tables=loaders.LINEAGE,
        conflicts=loaders.ID_CONFLICTS,
        mdm=loaders.mdm_rules().to_dict("records"),
    ))


    print(f"\n完成。計算於 {R['_meta']['built_at']}，耗時 {R['_meta']['seconds']} 秒。")


if __name__ == "__main__":
    main()
