"""
Catchment sensitivity analysis using the FIXED K=3 Model-C cluster assignments.

Does NOT refit the clusters and does NOT change the accessibility model.

For catchment_m in {500, 1000, 1500}, with
  dwelling_type = ALL, scenario = baseline, method = e2sfca_gauss,
compute per cluster:
  * population-weighted access_per_1000, SPAR, pct_pop_no_access
  * % of cluster population in subzones with SPAR < 1.0 and SPAR < 0.8

Main question: does Cluster 0 remain the relatively lower-access profile at all
three catchment radii?  (No causal claims.)

Output: data/processed/clustering/legacy_pop1000/cluster_catchment_sensitivity.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
import config  # noqa: E402

CATCHMENTS = [500, 1000, 1500]


def wmean(v: pd.Series, w: pd.Series) -> float:
    v, w = v.to_numpy(float), w.to_numpy(float)
    ok = ~np.isnan(v) & (w > 0)
    return float(np.average(v[ok], weights=w[ok])) if ok.any() else np.nan


def main() -> None:
    clusters = pd.read_csv(config.CLUSTERING_LEGACY / "subzone_clusters.csv")[
        ["sz_key", "cluster", "cluster_name"]]
    acc = pd.read_csv(config.PROCESSED / "agg_access_subzone.csv")

    rows = []
    for d0 in CATCHMENTS:
        slc = acc[(acc.dwelling_type == "ALL") & (acc.scenario == "baseline")
                  & (acc.method == "e2sfca_gauss") & (acc.catchment_m == d0)]
        slc = slc[["sz_key", "population", "access_per_1000", "spar", "pct_pop_no_access"]]
        j = clusters.merge(slc, on="sz_key", how="left")
        miss = j["access_per_1000"].isna().sum()
        if miss:
            print(f"  note: {miss} clustered subzones have no access row at d0={d0}")
        for cl, g in j.groupby("cluster"):
            m = g[g["access_per_1000"].notna()]
            w = m["population"]
            pop = w.sum()
            rows.append({
                "catchment_m": d0,
                "cluster": cl,
                "cluster_name": g["cluster_name"].iloc[0],
                "n_subzones": len(m),
                "pop": int(pop),
                "w_access_per_1000": round(wmean(m.access_per_1000, w), 4),
                "w_spar": round(wmean(m.spar, w), 4),
                "w_pct_pop_no_access": round(wmean(m.pct_pop_no_access, w), 2),
                "pct_pop_spar_lt_1_0": round(m.loc[m.spar < 1.0, "population"].sum() / pop * 100, 2),
                "pct_pop_spar_lt_0_8": round(m.loc[m.spar < 0.8, "population"].sum() / pop * 100, 2),
            })
    out = pd.DataFrame(rows).sort_values(["catchment_m", "cluster"]).reset_index(drop=True)
    path = config.CLUSTERING_LEGACY / "cluster_catchment_sensitivity.csv"
    out.to_csv(path, index=False)

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 50)

    # side-by-side view: one block per metric, clusters as columns, catchments as rows
    print("=" * 90)
    print("CATCHMENT SENSITIVITY (baseline, e2sfca_gauss, dwelling_type=ALL; fixed K=3 clusters)")
    print("=" * 90)
    name_by_cl = {r.cluster: r.cluster_name for r in out.itertuples()}
    print("\nclusters:")
    for cl in sorted(name_by_cl):
        print(f"  C{cl} = {name_by_cl[cl]}")

    for metric, label in [("w_access_per_1000", "pop-weighted access_per_1000"),
                          ("w_spar", "pop-weighted SPAR"),
                          ("w_pct_pop_no_access", "pop-weighted pct_pop_no_access"),
                          ("pct_pop_spar_lt_1_0", "% cluster pop with SPAR < 1.0"),
                          ("pct_pop_spar_lt_0_8", "% cluster pop with SPAR < 0.8")]:
        piv = out.pivot(index="catchment_m", columns="cluster", values=metric)
        piv.columns = [f"C{c}" for c in piv.columns]
        print(f"\n--- {label} ---")
        print(piv.to_string())

    # answer the main question explicitly
    print("\n" + "=" * 90)
    print("MAIN QUESTION: is C0 the lowest-access profile at every catchment?")
    print("=" * 90)
    for d0 in CATCHMENTS:
        sub = out[out.catchment_m == d0]
        lo_access = sub.loc[sub.w_access_per_1000.idxmin(), "cluster"]
        lo_spar = sub.loc[sub.w_spar.idxmin(), "cluster"]
        print(f"  d0={d0:>4}m : lowest access -> C{lo_access} | lowest SPAR -> C{lo_spar}")
    print(f"\nSaved -> {path}")


if __name__ == "__main__":
    main()
