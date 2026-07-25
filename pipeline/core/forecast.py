"""需求預測。

先跑四種最笨的方法，再決定模型值不值得上。
模型的維護成本遠高於一行算式，所以它必須贏得夠明顯才值得採用；
這裡把門檻設在 2 個百分點，並且把完整對照攤出來讓人自己判斷。
"""
from __future__ import annotations

import logging
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
for n in ("prophet", "cmdstanpy"):
    logging.getLogger(n).setLevel(logging.CRITICAL)

TEST_N = 6
MARGIN_PP = 2.0   # 模型須贏過最佳笨方法多少個百分點才採用

# 台灣節慶（Prophet 不會自己知道）
HOLIDAYS = pd.DataFrame({
    "holiday": ["雙十一"] * 4 + ["春節"] * 4 + ["中秋"] * 4,
    "ds": pd.to_datetime(
        ["2023-11-11", "2024-11-11", "2025-11-11", "2026-11-11",
         "2023-01-22", "2024-02-10", "2025-01-29", "2026-02-17",
         "2023-09-29", "2024-09-17", "2025-10-06", "2026-09-25"]),
    "lower_window": [-3] * 4 + [-7] * 4 + [-5] * 4,
    "upper_window": [1] * 4 + [3] * 4 + [1] * 4,
})


def mape(actual, pred):
    a, p = np.asarray(actual, float), np.asarray(pred, float)
    m = a != 0
    return float(np.mean(np.abs((a[m] - p[m]) / a[m])) * 100)


def baselines(train: pd.Series, horizon: int) -> dict:
    """四種一行就能寫完的笨方法。"""
    out = {"上個月一樣": np.repeat(train.iloc[-1], horizon),
           "近三個月平均": np.repeat(train.iloc[-3:].mean(), horizon)}
    if len(train) >= 12:
        v = train.iloc[-12:].values
        out["去年同期"] = np.resize(v, horizon)
    if len(train) >= 6:
        c = np.polyfit(np.arange(6), train.iloc[-6:].values, 1)
        out["線性外推"] = np.polyval(c, np.arange(6, 6 + horizon))
    return out


def _prophet(train_df, periods, holidays=True):
    from prophet import Prophet
    m = Prophet(yearly_seasonality=True, weekly_seasonality=False,
                daily_seasonality=False, interval_width=0.80,
                holidays=HOLIDAYS if holidays else None)
    m.fit(train_df.rename(columns={"date": "ds", "qty": "y"})[["ds", "y"]])
    fc = m.predict(m.make_future_dataframe(periods=periods, freq="MS"))
    return m, fc


def backtest_sku(g: pd.DataFrame, test_n=TEST_N):
    s = g.sort_values("date").reset_index(drop=True)
    train, test = s.iloc[:-test_n], s.iloc[-test_n:]

    _, fc = _prophet(train, test_n)
    p_mape = mape(test.qty.values, fc.yhat.iloc[-test_n:].values)

    bl = {k: mape(test.qty.values, v) for k, v in baselines(train.qty, test_n).items()}
    best_name = min(bl, key=bl.get)
    best_mape = bl[best_name]
    gain = best_mape - p_mape
    use_model = gain >= MARGIN_PP

    if use_model:
        _, full = _prophet(s, 1)
        nx = full.iloc[-1]
        yhat, lo, hi = float(nx.yhat), float(nx.yhat_lower), float(nx.yhat_upper)
    else:
        yhat = float(baselines(s.qty, 1)[best_name][0])
        sd = float(s.qty.iloc[-12:].std()) if len(s) >= 12 else float(s.qty.std())
        lo, hi = yhat - 1.28 * sd, yhat + 1.28 * sd

    row = dict(sku_id=s.sku_id.iloc[0], sku_name=s.sku_name.iloc[0],
               模型誤差=round(p_mape, 2), 最佳笨方法=best_name,
               笨方法誤差=round(best_mape, 2), 領先幅度=round(gain, 2),
               採用="Prophet" if use_model else best_name,
               採用誤差=round(p_mape if use_model else best_mape, 2),
               下月預測=round(yhat, 0), 區間下限=round(max(lo, 0), 0),
               區間上限=round(hi, 0),
               預測月份=(s.date.max() + pd.DateOffset(months=1)).strftime("%Y-%m"))
    detail = dict(train=train, test=test, fc=fc.iloc[-test_n:],
                  all_baselines={k: round(v, 2) for k, v in bl.items()})
    return row, detail


def backtest_all(sales: pd.DataFrame, test_n=TEST_N):
    rows, det = [], {}
    for sku, g in sales.groupby("sku_id"):
        r, d = backtest_sku(g, test_n)
        rows.append(r); det[sku] = d
    t = pd.DataFrame(rows).sort_values("領先幅度", ascending=False).reset_index(drop=True)
    return t, det
