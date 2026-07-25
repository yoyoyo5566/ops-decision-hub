"""購物籃關聯分析：以 13,026 筆交易明細實跑 Apriori。"""
from __future__ import annotations

import pandas as pd
from mlxtend.frequent_patterns import apriori, association_rules
from mlxtend.preprocessing import TransactionEncoder


def basket_matrix(tx: pd.DataFrame):
    baskets = tx.groupby("order_id")["sku_name"].apply(list).tolist()
    te = TransactionEncoder()
    mat = pd.DataFrame(te.fit(baskets).transform(baskets), columns=te.columns_)
    return mat, baskets


def mine(tx: pd.DataFrame, min_support=0.02, min_lift=1.0, min_conf=0.2):
    mat, baskets = basket_matrix(tx)
    freq = apriori(mat, min_support=min_support, use_colnames=True, max_len=3)
    if freq.empty:
        return pd.DataFrame(), dict(orders=len(baskets), rules=0)

    rules = association_rules(freq, metric="lift", min_threshold=min_lift)
    rules = rules[(rules.confidence >= min_conf)].copy()
    rules["antecedents_s"] = rules.antecedents.apply(lambda x: "、".join(sorted(x)))
    rules["consequents_s"] = rules.consequents.apply(lambda x: "、".join(sorted(x)))
    rules["n_orders"] = (rules.support * len(baskets)).round().astype(int)
    rules = rules.sort_values("lift", ascending=False).reset_index(drop=True)

    stats = dict(
        orders=len(baskets),
        items=mat.shape[1],
        avg_basket=round(mat.sum(axis=1).mean(), 2),
        frequent_sets=len(freq),
        rules=len(rules),
    )
    cols = ["antecedents_s", "consequents_s", "support", "confidence", "lift",
            "leverage", "n_orders"]
    return rules[cols].rename(columns={"antecedents_s": "前項", "consequents_s": "後項"}), stats


def recommend_for_basket(rules: pd.DataFrame, owned: set, top=5):
    """給定顧客已購品項，回傳尚未擁有的推薦品。"""
    if rules.empty:
        return pd.DataFrame()
    hits = []
    for _, r in rules.iterrows():
        ante = set(r["前項"].split("、"))
        cons = set(r["後項"].split("、"))
        if ante <= owned and not cons <= owned:
            hits.append(dict(推薦品="、".join(sorted(cons - owned)),
                             因為已購="、".join(sorted(ante)),
                             信賴度=r.confidence, 提升度=r.lift, 支持度=r.support))
    if not hits:
        return pd.DataFrame()
    return (pd.DataFrame(hits).sort_values("提升度", ascending=False)
            .drop_duplicates("推薦品").head(top).reset_index(drop=True))


def coverage(rules: pd.DataFrame, tx: pd.DataFrame, customers: pd.DataFrame):
    """實際能給出推薦的顧客比例，避免宣稱過高的適用範圍。"""
    owned = tx.groupby("customer_id")["sku_name"].apply(set)
    n_cov = 0
    for cid in customers.customer_id:
        o = owned.get(cid)
        if o is None:
            continue
        if not recommend_for_basket(rules, o, top=1).empty:
            n_cov += 1
    return dict(customers=len(customers), with_history=int(owned.index.isin(customers.customer_id).sum()),
                covered=n_cov, pct=round(n_cov / len(customers) * 100, 1))
