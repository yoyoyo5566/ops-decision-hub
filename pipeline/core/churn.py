"""流失預測。

刻意選用單棵決策樹而非集成模型：這份分析的產出要拿去給客戶經理打電話，
「為什麼是他」必須答得出來。可解釋性在這裡不是加分項，是主體。

主指標為 Recall 而非 Accuracy：流失率僅約一成，「永遠猜留客」也能拿到
接近九成的準確率卻一個都沒抓到。漏掉一位要走的客戶與誤打一通電話，
代價差兩個數量級。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support
from sklearn.model_selection import train_test_split
from sklearn.tree import DecisionTreeClassifier, export_text

FEATURES = ["Recency", "Frequency", "Monetary", "AvgOrder", "ComplaintCnt", "Tenure"]
LABEL = "Churn"

VALUE_SAVED = 30_000   # 挽留一位流失客戶的年營收貢獻
COST_CALL = 200        # 誤打一通電話的成本


def _split(df, seed=42):
    X, y = df[FEATURES], df[LABEL]
    Xtr, Xtmp, ytr, ytmp = train_test_split(X, y, test_size=.30, random_state=seed, stratify=y)
    Xva, Xte, yva, yte = train_test_split(Xtmp, ytmp, test_size=.50, random_state=seed, stratify=ytmp)
    return (Xtr, ytr), (Xva, yva), (Xte, yte)


def depth_scan(df, depths=range(2, 13), seed=42):
    (Xtr, ytr), (Xva, yva), _ = _split(df, seed)
    rows = []
    for d in depths:
        m = DecisionTreeClassifier(max_depth=d, random_state=seed).fit(Xtr, ytr)
        rows.append(dict(max_depth=d, 訓練集=round(m.score(Xtr, ytr), 4),
                         驗證集=round(m.score(Xva, yva), 4)))
    return pd.DataFrame(rows)


def scores_at(y_true, prob, threshold):
    pred = (np.asarray(prob) >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, pred, labels=[0, 1]).ravel()
    p, r, f1, _ = precision_recall_fscore_support(y_true, pred, average="binary",
                                                  zero_division=0)
    return dict(threshold=round(float(threshold), 2),
                TN=int(tn), FP=int(fp), FN=int(fn), TP=int(tp),
                accuracy=round((tp + tn) / len(y_true), 4),
                precision=round(float(p), 4), recall=round(float(r), 4),
                f1=round(float(f1), 4),
                net_value=int(tp * VALUE_SAVED - (tp + fp) * COST_CALL))


def fit(df, max_depth=4, seed=42, threshold=0.5):
    (Xtr, ytr), (Xva, yva), (Xte, yte) = _split(df, seed)
    clf = DecisionTreeClassifier(max_depth=max_depth, random_state=seed).fit(Xtr, ytr)
    prob_te = clf.predict_proba(Xte)[:, 1]

    metrics = scores_at(yte, prob_te, threshold)
    naive = scores_at(yte, np.zeros(len(yte)), 0.5)
    naive["accuracy"] = round(float((yte == 0).mean()), 4)
    sweep = pd.DataFrame([scores_at(yte, prob_te, t) for t in np.arange(.05, .96, .05)])

    imp = (pd.DataFrame(dict(feature=FEATURES, importance=clf.feature_importances_))
           .sort_values("importance", ascending=False).reset_index(drop=True))

    out = df.copy()
    out["churn_prob"] = clf.predict_proba(df[FEATURES])[:, 1]
    out["at_risk_value"] = (out.Monetary * out.churn_prob).round(0)

    return dict(model=clf, scored=out, metrics=metrics, naive=naive, sweep=sweep,
                importance=imp, y_test=yte, prob_test=prob_te,
                depth_scan=depth_scan(df, seed=seed),
                leaf_count=int(clf.get_n_leaves()), threshold=threshold,
                test_n=len(yte))


def explain_path(clf, row):
    t = clf.tree_
    NAME = {"Recency": "最近購買天數", "Frequency": "購買頻次", "Monetary": "累積消費",
            "AvgOrder": "平均客單", "ComplaintCnt": "客訴次數", "Tenure": "往來天數"}
    node, steps = 0, []
    x = np.asarray(row[FEATURES].values, dtype=float)
    while t.children_left[node] != -1:
        fi = t.feature[node]; thr = t.threshold[node]
        if x[fi] <= thr:
            steps.append(f"{NAME[FEATURES[fi]]} {x[fi]:.0f} ≤ {thr:.0f}")
            node = t.children_left[node]
        else:
            steps.append(f"{NAME[FEATURES[fi]]} {x[fi]:.0f} > {thr:.0f}")
            node = t.children_right[node]
    v = t.value[node][0]
    return steps, float(v[1] / v.sum()), int(v.sum())


def top_targets(scored, n=10):
    return (scored.nlargest(n, "at_risk_value")
            [["customer_id", "Recency", "Frequency", "Monetary", "ComplaintCnt",
              "Segment_D4", "cluster_name", "churn_prob", "at_risk_value"]]
            .reset_index(drop=True))
