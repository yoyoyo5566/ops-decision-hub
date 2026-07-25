"""配送路徑最佳化：OR-Tools CVRPTW。

兩種方案皆為實際求解結果，非預先寫死的數字：
  distance_first  只最小化行駛距離，不理會門市時窗（作為對照基準）
  window_feasible 將時窗設為硬約束求解（實際上線方案）

溫層為硬約束：冷藏門市只能由冷藏車服務，常溫門市只能由常溫車服務。
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

DAY_START_MIN = 6 * 60      # 06:00 出車
DAY_END_MIN = 18 * 60       # 18:00 收車


def _hhmm_to_min(v) -> float | None:
    if pd.isna(v) or v in ("", "—"):
        return None
    h, m = str(v).split(":")
    return int(h) * 60 + int(m)


def load_network(data_dir):
    stores = pd.read_csv(f"{data_dir}/配送網絡_台中20門市.csv")
    vehicles = pd.read_csv(f"{data_dir}/配送網絡_車型.csv")
    dist = pd.read_csv(f"{data_dir}/配送網絡_距離矩陣.csv").set_index("from_id")
    time = pd.read_csv(f"{data_dir}/配送網絡_時間矩陣.csv").set_index("from_id")
    order = stores["store_id"].tolist()
    dist = dist.loc[order, order]
    time = time.loc[order, order]
    return stores, vehicles, dist, time


def solve(stores, vehicles, dist, time, mode="window_feasible", time_limit_s=12,
          allow_drop=True, drop_penalty=2_000_000):
    """回傳 (routes_df, summary_dict)。mode: distance_first | window_feasible"""
    n = len(stores)
    depot = 0
    ids = stores["store_id"].tolist()
    demand = stores["demand_kg"].fillna(0).astype(int).tolist()
    service = stores["service_min"].fillna(0).astype(int).tolist()
    zone = stores["temp_zone"].fillna("—").tolist()

    tw = []
    for _, r in stores.iterrows():
        o, c = _hhmm_to_min(r["tw_open"]), _hhmm_to_min(r["tw_close"])
        tw.append((o, c) if o is not None and c is not None else None)

    nv = len(vehicles)
    cap = vehicles["capacity_kg"].astype(int).tolist()
    vzone = vehicles["temp_zone"].tolist()
    fuel = vehicles["fuel_cost_per_km"].astype(float).tolist()
    fixed = vehicles["fixed_cost_per_day"].astype(float).tolist()
    maxwork = vehicles["max_work_min"].astype(int).tolist()

    # 距離以公尺為整數單位，時間以分鐘為整數單位
    D = (dist.values * 1000).round().astype(int)
    T = time.values.round().astype(int)

    mgr = pywrapcp.RoutingIndexManager(n, nv, depot)
    routing = pywrapcp.RoutingModel(mgr)

    def dist_cb(i, j):
        return int(D[mgr.IndexToNode(i)][mgr.IndexToNode(j)])

    dist_idx = routing.RegisterTransitCallback(dist_cb)

    # 各車以自身油耗計價（單位：元 / 公尺 × 1000 放大避免整數截斷）
    for v in range(nv):
        def cost_cb(i, j, v=v):
            return int(D[mgr.IndexToNode(i)][mgr.IndexToNode(j)] * fuel[v])
        routing.SetArcCostEvaluatorOfVehicle(routing.RegisterTransitCallback(cost_cb), v)

    def demand_cb(i):
        return demand[mgr.IndexToNode(i)]

    routing.AddDimensionWithVehicleCapacity(
        routing.RegisterUnaryTransitCallback(demand_cb), 0, cap, True, "Capacity"
    )

    def time_cb(i, j):
        a, b = mgr.IndexToNode(i), mgr.IndexToNode(j)
        return int(T[a][b] + service[a])

    time_idx = routing.RegisterTransitCallback(time_cb)
    routing.AddDimension(time_idx, 600, DAY_END_MIN, False, "Time")
    time_dim = routing.GetDimensionOrDie("Time")

    for v in range(nv):
        s, e = routing.Start(v), routing.End(v)
        time_dim.CumulVar(s).SetRange(DAY_START_MIN, DAY_END_MIN)
        time_dim.CumulVar(e).SetRange(DAY_START_MIN, DAY_END_MIN)
        routing.solver().Add(time_dim.CumulVar(e) - time_dim.CumulVar(s) <= maxwork[v])

    # 溫層硬約束
    for node in range(n):
        if node == depot:
            continue
        allowed = [int(v) for v in range(nv) if vzone[v] == zone[node]]
        if allow_drop:
            allowed = allowed + [-1]
        routing.VehicleVar(mgr.NodeToIndex(node)).SetValues(allowed)

    # 時窗：僅 window_feasible 模式套用
    if mode == "window_feasible":
        for node in range(n):
            if node == depot or tw[node] is None:
                continue
            time_dim.CumulVar(mgr.NodeToIndex(node)).SetRange(tw[node][0], tw[node][1])

    if allow_drop:
        for node in range(n):
            if node != depot:
                routing.AddDisjunction([mgr.NodeToIndex(node)], drop_penalty)

    for v in range(nv):
        routing.AddVariableMinimizedByFinalizer(time_dim.CumulVar(routing.Start(v)))
        routing.AddVariableMinimizedByFinalizer(time_dim.CumulVar(routing.End(v)))

    p = pywrapcp.DefaultRoutingSearchParameters()
    p.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    p.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    p.time_limit.FromSeconds(time_limit_s)

    sol = routing.SolveWithParameters(p)
    if sol is None:
        return None, {"feasible": False, "mode": mode}

    rows, stops = [], []
    for v in range(nv):
        idx = routing.Start(v)
        seq, load, km, order_i = [], 0, 0.0, 0
        while not routing.IsEnd(idx):
            node = mgr.IndexToNode(idx)
            arrive = sol.Value(time_dim.CumulVar(idx))
            if node != depot:
                order_i += 1
                late = early = 0
                if tw[node] is not None:
                    if arrive > tw[node][1]:
                        late = arrive - tw[node][1]
                    elif arrive < tw[node][0]:
                        early = tw[node][0] - arrive
                load += demand[node]
                stops.append(dict(
                    vehicle_id=vehicles.vehicle_id[v], vehicle_name=vehicles.vehicle_name[v],
                    stop_order=order_i, store_id=ids[node],
                    store_name=stores.store_name[node], district=stores.district[node],
                    temp_zone=zone[node], demand_kg=demand[node],
                    arrive_min=arrive,
                    arrive_hhmm=f"{arrive//60:02d}:{arrive%60:02d}",
                    tw_open=stores.tw_open[node], tw_close=stores.tw_close[node],
                    late_min=late, early_min=early, lat=stores.lat[node], lon=stores.lon[node],
                ))
            nxt = sol.Value(routing.NextVar(idx))
            km += D[mgr.IndexToNode(idx)][mgr.IndexToNode(nxt)] / 1000
            seq.append(ids[node])
            idx = nxt
        end_t = sol.Value(time_dim.CumulVar(idx))
        start_t = sol.Value(time_dim.CumulVar(routing.Start(v)))
        served = [s for s in stops if s["vehicle_id"] == vehicles.vehicle_id[v]]
        rows.append(dict(
            vehicle_id=vehicles.vehicle_id[v], vehicle_name=vehicles.vehicle_name[v],
            temp_zone=vzone[v], stops=len(served), load_kg=load, capacity_kg=cap[v],
            util_pct=round(load / cap[v] * 100, 1),
            distance_km=round(km, 2),
            work_min=end_t - start_t,
            depart_hhmm=f"{start_t//60:02d}:{start_t%60:02d}",
            return_hhmm=f"{end_t//60:02d}:{end_t%60:02d}",
            late_min=sum(s["late_min"] for s in served),
            violations=sum(1 for s in served if s["late_min"] > 0),
            fuel_cost=round(km * fuel[v], 1),
            fixed_cost=fixed[v],
            total_cost=round(km * fuel[v] + fixed[v], 1),
            sequence=" → ".join(seq[1:]) if len(seq) > 1 else "（未派車）",
        ))

    served_ids = {s["store_id"] for s in stops}
    dropped = [dict(store_id=ids[k], store_name=stores.store_name[k], temp_zone=zone[k],
                    demand_kg=demand[k],
                    tw=f"{stores.tw_open[k]}-{stores.tw_close[k]}" if tw[k] else "無時窗")
               for k in range(n) if k != depot and ids[k] not in served_ids]

    routes = pd.DataFrame(rows)
    summary = dict(
        feasible=True, mode=mode,
        vehicles_used=int((routes.stops > 0).sum()),
        total_km=round(routes.distance_km.sum(), 2),
        total_cost=round(routes.total_cost.sum(), 1),
        total_load=int(routes.load_kg.sum()),
        violations=int(routes.violations.sum()),
        late_min=int(routes.late_min.sum()),
        dropped=len(dropped),
        dropped_stores=dropped,
        max_work_min=int(routes.work_min.max()),
    )
    return (routes, pd.DataFrame(stops), pd.DataFrame(dropped)), summary


# ---------------------------------------------------------------------------
def naive_plan(stores, vehicles, dist, time, depart_min=9 * 60):
    """人的直覺方案：按溫層分派、小單給機車、最近鄰排序、早上九點出車。

    這是最佳化真正的對照組——不是另一個演算法的解，而是沒有工具時
    調度員會怎麼排。它的價值不在成本，在於暴露「看起來合理但跑不動」。
    """
    ids = stores.store_id.tolist()
    idx = {s: i for i, s in enumerate(ids)}
    D = dist.values
    T = time.values
    dem = dict(zip(stores.store_id, stores.demand_kg))
    svc = dict(zip(stores.store_id, stores.service_min))
    zone = dict(zip(stores.store_id, stores.temp_zone))
    name = dict(zip(stores.store_id, stores.store_name))
    tw = {r.store_id: (_hhmm_to_min(r.tw_open), _hhmm_to_min(r.tw_close))
          for _, r in stores.iterrows()}

    V = vehicles.set_index("vehicle_id")
    small = [v for v in V.index if V.loc[v, "capacity_kg"] <= 300]
    assign = {v: [] for v in V.index}
    for z in stores.temp_zone.unique():
        if z in ("—", None) or pd.isna(z):
            continue
        members = [s for s in ids if zone[s] == z and s != "DEPOT"]
        cars = [v for v in V.index if V.loc[v, "temp_zone"] == z]
        tiny = [v for v in cars if v in small]
        if tiny:
            members = sorted(members, key=lambda s: dem[s])
            assign[tiny[0]] = members[:3]
            rest = [v for v in cars if v not in tiny]
            assign[rest[0]] += members[3:]
        else:
            assign[cars[0]] += members

    rows, stops = [], []
    for vid, mem in assign.items():
        if not mem:
            rows.append(dict(vehicle_id=vid, vehicle_name=V.loc[vid, "vehicle_name"],
                             temp_zone=V.loc[vid, "temp_zone"], stops=0, load_kg=0,
                             capacity_kg=int(V.loc[vid, "capacity_kg"]), util_pct=0.0,
                             distance_km=0.0, work_min=0, violations=0, late_min=0,
                             early_min=0, total_cost=0.0, sequence="（未派車）"))
            continue
        cur, t, km, seq = "DEPOT", depart_min, 0.0, []
        left = set(mem)
        order_i = 0
        while left:
            nxt = min(left, key=lambda s: D[idx[cur]][idx[s]])
            km += D[idx[cur]][idx[nxt]]
            t += T[idx[cur]][idx[nxt]]
            order_i += 1
            o, c = tw[nxt]
            late = max(0, t - c) if c is not None else 0
            early = max(0, o - t) if o is not None else 0
            stops.append(dict(vehicle_id=vid, vehicle_name=V.loc[vid, "vehicle_name"],
                              stop_order=order_i, store_id=nxt, store_name=name[nxt],
                              temp_zone=zone[nxt], demand_kg=dem[nxt],
                              arrive_min=int(t), arrive_hhmm=f"{int(t)//60:02d}:{int(t)%60:02d}",
                              tw_open=stores.set_index('store_id').tw_open.get(nxt),
                              tw_close=stores.set_index('store_id').tw_close.get(nxt),
                              late_min=int(late), early_min=int(early),
                              lat=stores.set_index('store_id').lat[nxt],
                              lon=stores.set_index('store_id').lon[nxt]))
            t += svc[nxt]
            seq.append(nxt)
            left.discard(nxt)
            cur = nxt
        km += D[idx[cur]][idx["DEPOT"]]
        t += T[idx[cur]][idx["DEPOT"]]
        mine = [s for s in stops if s["vehicle_id"] == vid]
        load = sum(dem[s] for s in seq)
        cost = km * V.loc[vid, "fuel_cost_per_km"] + V.loc[vid, "fixed_cost_per_day"]
        rows.append(dict(vehicle_id=vid, vehicle_name=V.loc[vid, "vehicle_name"],
                         temp_zone=V.loc[vid, "temp_zone"], stops=len(seq), load_kg=int(load),
                         capacity_kg=int(V.loc[vid, "capacity_kg"]),
                         util_pct=round(load / V.loc[vid, "capacity_kg"] * 100, 1),
                         distance_km=round(km, 2), work_min=int(t - depart_min),
                         violations=sum(1 for s in mine if s["late_min"] > 0),
                         late_min=sum(s["late_min"] for s in mine),
                         early_min=sum(s["early_min"] for s in mine),
                         total_cost=round(cost, 1), sequence=" → ".join(seq)))

    routes = pd.DataFrame(rows)
    summary = dict(mode="naive", feasible=True,
                   vehicles_used=int((routes.stops > 0).sum()),
                   total_km=round(routes.distance_km.sum(), 2),
                   total_cost=round(routes.total_cost.sum(), 1),
                   total_load=int(routes.load_kg.sum()),
                   violations=int(routes.violations.sum()),
                   late_min=int(routes.late_min.sum()),
                   early_min=int(routes.early_min.sum()),
                   max_work_min=int(routes.work_min.max()),
                   dropped=0, dropped_stores=[])
    return (routes, pd.DataFrame(stops), pd.DataFrame()), summary
