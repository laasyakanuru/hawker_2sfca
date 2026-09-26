"""
Step D - 2SFCA / E2SFCA / 3SFCA accessibility, gaps and closure impact.

Inputs : processed/dim_demand_point.csv, interim/dim_hawker_centre.csv,
         interim/fact_hc_closure.csv, interim/dim_mrt_station.csv
Outputs (processed/):
  fact_access_point.csv        dp_key x scenario x method x catchment -> A_i, SPAR, n centres in reach
  fact_demand_proximity.csv    dp_key -> nearest open HC (baseline) and its distance
  fact_supply_ratio.csv        hc_key x scenario x method x catchment -> R_j, catchment pop by dwelling type
  agg_access_subzone.csv       sz_key x dwelling_type(+ALL) x scenario x method x catchment
  agg_access_planning_area.csv pa_key x dwelling_type(+ALL) x ...
  fact_hc_closure_impact.csv   leave-one-out: what happens if each HC closes
  fact_daily_access.csv        every day of ANALYSIS_YEAR with the NEA closure calendar applied
  agg_daily_access_subzone.csv same, by subzone (headline method & catchment)

Scenarios
  baseline : supply = HCs whose status is in config.BASELINE_STATUSES
  future   : + 'Under Construction' centres
  daytime  : baseline supply; demand = residents + weekday AM-peak MRT arrivals (worker proxy)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config
import sfca

TYPES = ["HDB", "CONDO", "LANDED", "OTHER"]


def load():
    dp = pd.read_csv(config.PROCESSED / "dim_demand_point.csv")
    hc = pd.read_csv(config.INTERIM / "dim_hawker_centre.csv")
    missing = (~dp.has_coords).sum()
    if missing:
        print(f"  !! {missing} demand points have no coordinates (population "
              f"{dp.loc[~dp.has_coords, 'population'].sum():,.0f}) and are excluded")
    dp = dp[dp.has_coords].reset_index(drop=True)
    if dp.empty:
        raise SystemExit("No demand point has coordinates yet - run `python run_pipeline.py --fetch` "
                         "(needs MP2019 subzone boundaries and the OneMap HDB geocode).")
    return dp, hc


def daytime_points():
    st = pd.read_csv(config.INTERIM / "dim_mrt_station.csv").dropna(subset=["x_svy21"])
    st = st.groupby("station_key").agg(x_svy21=("x_svy21", "mean"), y_svy21=("y_svy21", "mean"),
                                       sz_key=("sz_key", "first"),
                                       population=("wkday_am_peak_tap_out_avg", "sum")).reset_index()
    st["population"] *= config.DAYTIME_WEIGHT
    st["dp_key"] = "WORKER-" + st["station_key"]
    st["dwelling_type"] = "WORKER"
    return st


def summarise(df: pd.DataFrame, by: list[str], A_col="A") -> pd.DataFrame:
    """population-weighted mean access and gap metrics."""
    g = df.assign(PA=df.population * df[A_col],
                  no_access=np.where(df.n_hc_in_reach == 0, df.population, 0.0),
                  PA65=df.pop_65plus * df[A_col])
    out = g.groupby(by).agg(population=("population", "sum"), pop_65plus=("pop_65plus", "sum"),
                            PA=("PA", "sum"), PA65=("PA65", "sum"),
                            pop_no_access=("no_access", "sum"),
                            deficit=("deficit_stalls", "sum"), n_points=("dp_key", "size")).reset_index()
    out["access_per_1000"] = out.PA / out.population
    out["access_65plus_per_1000"] = out.PA65 / out.pop_65plus.replace(0, np.nan)
    out["pct_pop_no_access"] = out.pop_no_access / out.population * 100
    out = out.rename(columns={"deficit": "stall_deficit_vs_national"})
    return out.drop(columns=["PA", "PA65"])


def main():
    dp, hc = load()
    dxy = dp[["x_svy21", "y_svy21"]].to_numpy(float)
    sxy = hc[["x_svy21", "y_svy21"]].to_numpy(float)
    S = hc[config.SUPPLY_FIELD].fillna(0).to_numpy(float)
    D = sfca.distance_matrix(dxy, sxy, config.DETOUR_FACTOR)
    P = dp["population"].to_numpy(float)
    type_idx = {t: (dp.dwelling_type == t).to_numpy() for t in TYPES}
    open_base = hc["in_baseline"].to_numpy(float)
    open_future = hc["in_future"].to_numpy(float)

    # ---- proximity (baseline) --------------------------------------------------
    Db = np.where(open_base[None, :] > 0, D, np.inf)
    near = Db.argmin(1)
    prox = pd.DataFrame({"dp_key": dp.dp_key, "nearest_hc_key": hc.hc_key.to_numpy()[near],
                         "nearest_hc_dist_m": Db[np.arange(len(dp)), near].round(1),
                         "n_hc_within_500m": (Db <= 500).sum(1), "n_hc_within_1km": (Db <= 1000).sum(1),
                         "n_hc_within_1_5km": (Db <= 1500).sum(1)})
    prox.to_csv(config.PROCESSED / "fact_demand_proximity.csv", index=False)

    # ---- scenario runs ---------------------------------------------------------
    acc_rows, sup_rows, agg_sz, agg_pa = [], [], [], []
    wk = daytime_points()
    scenarios = {
        "baseline": (dp, D, open_base),
        "future": (dp, D, open_future),
    }
    if len(wk):
        dp_day = pd.concat([dp, wk.assign(pop_65plus=0.0, pa_key=None)], ignore_index=True)
        D_day = np.vstack([D, sfca.distance_matrix(wk[["x_svy21", "y_svy21"]].to_numpy(float), sxy,
                                                   config.DETOUR_FACTOR)])
        scenarios["daytime"] = (dp_day, D_day, open_base)

    for scen, (dpx, Dx, mask) in scenarios.items():
        Px = dpx["population"].to_numpy(float)
        for method in config.METHODS:
            for d0 in config.SENSITIVITY_CATCHMENTS_M:
                A, R, dem = sfca.run(Px, S, Dx, d0, method, open_mask=mask)
                A1k = A * config.ACCESS_PER
                Abar = (Px * A1k).sum() / Px.sum()
                n_reach = ((Dx <= d0) & (mask[None, :] > 0)).sum(1)
                a = pd.DataFrame({"dp_key": dpx.dp_key, "scenario": scen, "method": method,
                                  "catchment_m": d0, "A": A1k, "spar": A1k / Abar,
                                  "n_hc_in_reach": n_reach})
                acc_rows.append(a)
                # supply side: effective catchment population by dwelling type
                kind, three = sfca.method_spec(method)
                W = sfca.weight_matrix(Dx, d0, kind) * mask[None, :]
                if three:
                    rs = W.sum(1, keepdims=True)
                    W = np.divide(W, rs, out=np.zeros_like(W), where=rs > 0) * W
                s = pd.DataFrame({"hc_key": hc.hc_key, "scenario": scen, "method": method,
                                  "catchment_m": d0, "is_open": mask > 0, "stalls": S * mask,
                                  "catchment_pop": dem, "R_per_1000": R * config.ACCESS_PER})
                for t in TYPES + (["WORKER"] if scen == "daytime" else []):
                    idx = (dpx.dwelling_type == t).to_numpy()
                    s[f"catchment_pop_{t.lower()}"] = W[idx].T @ Px[idx]
                sup_rows.append(s)
                # aggregation
                m = dpx[["dp_key", "dwelling_type", "sz_key", "pa_key", "population", "pop_65plus"]].copy()
                m["A"] = A1k
                m["n_hc_in_reach"] = n_reach
                m["deficit_stalls"] = m.population * np.clip(Abar - A1k, 0, None) / config.ACCESS_PER
                m = m[m.dwelling_type != "WORKER"]
                for level, lst, key in [("sz", agg_sz, "sz_key"), ("pa", agg_pa, "pa_key")]:
                    t1 = summarise(m, [key, "dwelling_type"])
                    t2 = summarise(m, [key]).assign(dwelling_type="ALL")
                    t = pd.concat([t1, t2], ignore_index=True)
                    t["spar"] = t.access_per_1000 / Abar
                    t[["scenario", "method", "catchment_m", "national_access_per_1000"]] = scen, method, d0, Abar
                    lst.append(t)
    pd.concat(acc_rows).round(6).to_csv(config.PROCESSED / "fact_access_point.csv", index=False)
    pd.concat(sup_rows).round(4).to_csv(config.PROCESSED / "fact_supply_ratio.csv", index=False)
    pd.concat(agg_sz).round(4).to_csv(config.PROCESSED / "agg_access_subzone.csv", index=False)
    pd.concat(agg_pa).round(4).to_csv(config.PROCESSED / "agg_access_planning_area.csv", index=False)

    # ---- closure impact: leave-one-out (competition-aware 3SFCA) ---------------
    d0, meth = config.CATCHMENT_M, config.CLOSURE_METHOD
    A0, R0, _ = sfca.run(P, S, D, d0, meth, open_mask=open_base)
    rows = []
    for j in np.where(open_base > 0)[0]:
        mk = open_base.copy()
        mk[j] = 0
        A1, R1, _ = sfca.run(P, S, D, d0, meth, open_mask=mk)
        dA = (A1 - A0) * config.ACCESS_PER
        affected = D[:, j] <= d0
        lost_all = affected & (A1 == 0) & (A0 > 0)
        others = (mk > 0) & (R0 > 0)
        crowd = (R0[others] - R1[others]) / R0[others] * 100  # +ve = fewer stalls per resident
        r = {"hc_key": hc.hc_key[j], "stalls": S[j], "method": meth, "catchment_m": d0,
             "pop_in_catchment": P[affected].sum(), "pop_losing_all_access": P[lost_all].sum(),
             "mean_delta_access_affected": np.average(dA[affected], weights=P[affected]) if affected.any() else 0,
             "national_delta_access": (P * dA).sum() / P.sum(),
             "max_neighbour_crowding_pct": crowd.max() if len(crowd) else 0,
             "n_neighbours_crowded_5pct": int((crowd >= 5).sum())}
        for t in TYPES:
            ix = type_idx[t]
            r[f"pop_in_catchment_{t.lower()}"] = P[affected & ix].sum()
            r[f"pop_losing_all_access_{t.lower()}"] = P[lost_all & ix].sum()
        rows.append(r)
    imp = pd.DataFrame(rows).merge(hc[["hc_key", "hc_name"]], on="hc_key")
    imp["impact_rank"] = imp["pop_losing_all_access"].rank(ascending=False, method="min") \
        + imp["mean_delta_access_affected"].rank(method="min")
    imp.sort_values("impact_rank").round(4).to_csv(config.PROCESSED / "fact_hc_closure_impact.csv", index=False)

    # ---- daily calendar with NEA closures --------------------------------------
    cl = pd.read_csv(config.INTERIM / "fact_hc_closure.csv", parse_dates=["start_date", "end_date"])
    days = pd.date_range(f"{config.ANALYSIS_YEAR}-01-01", f"{config.ANALYSIS_YEAR}-12-31", freq="D")
    hc_pos = {k: i for i, k in enumerate(hc.hc_key)}
    closed = np.zeros((len(days), len(hc)), bool)
    for r in cl.itertuples():
        a = days.searchsorted(r.start_date)
        b = days.searchsorted(r.end_date, side="right")
        closed[a:b, hc_pos[r.hc_key]] = True
    meth, d0 = config.HEADLINE_METHOD, config.CATCHMENT_M
    daily, daily_sz, cache = [], [], {}
    base_mask = open_base > 0
    for t, day in enumerate(days):
        mk = (base_mask & ~closed[t]).astype(float)
        key = mk.tobytes()
        if key not in cache:
            A, _, _ = sfca.run(P, S, D, d0, meth, open_mask=mk)
            cache[key] = A * config.ACCESS_PER
        A = cache[key]
        reach = ((D <= d0) & (mk[None, :] > 0)).any(1)
        row = {"date": day.date(), "method": meth, "catchment_m": d0,
               "n_hc_closed": int((base_mask & closed[t]).sum()),
               "stalls_closed": S[base_mask & closed[t]].sum(),
               "closed_hc_keys": ";".join(hc.hc_key[base_mask & closed[t]]),
               "access_per_1000_all": (P * A).sum() / P.sum(),
               "pop_no_access_all": P[~reach].sum()}
        for tp in TYPES:
            ix = type_idx[tp]
            row[f"access_per_1000_{tp.lower()}"] = (P[ix] * A[ix]).sum() / P[ix].sum() if ix.any() else np.nan
            row[f"pop_no_access_{tp.lower()}"] = P[ix & ~reach].sum()
        daily.append(row)
        g = pd.DataFrame({"sz_key": dp.sz_key, "PA": P * A, "P": P, "noacc": np.where(reach, 0, P)}) \
            .groupby("sz_key").sum()
        daily_sz.append(pd.DataFrame({"date": day.date(), "sz_key": g.index,
                                      "access_per_1000": g.PA / g.P, "pop_no_access": g.noacc}))
    pd.DataFrame(daily).round(4).to_csv(config.PROCESSED / "fact_daily_access.csv", index=False)
    pd.concat(daily_sz).round(4).to_csv(config.PROCESSED / "agg_daily_access_subzone.csv", index=False)

    nat = pd.concat(agg_pa)
    print(nat[(nat.dwelling_type != "ALL") & (nat.scenario == "baseline") & (nat.method == config.HEADLINE_METHOD)
              & (nat.catchment_m == config.CATCHMENT_M)].groupby("dwelling_type")
          .apply(lambda g: pd.Series({"population": g.population.sum(),
                                      "access_per_1000": (g.population * g.access_per_1000).sum() / g.population.sum(),
                                      "pct_no_access": g.pop_no_access.sum() / g.population.sum() * 100}),
                 include_groups=False).round(2).to_string())
    print(f"closure impact rows: {len(imp)} | daily rows: {len(daily)} | distinct daily supply states: {len(cache)}")


if __name__ == "__main__":
    main()
