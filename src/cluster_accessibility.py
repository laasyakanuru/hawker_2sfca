"""
Post-clustering accessibility profiling (held-out outcomes).

Objective: determine which of the three fixed Model-C neighbourhood profiles are
actually underserved in hawker accessibility. Clusters are NOT refitted here.

Inputs:
  data/processed/clustering/legacy_pop1000/subzone_clusters.csv  (fixed K=3 Model C assignments)
  data/processed/agg_access_subzone.csv      (held-out accessibility outcomes)

Accessibility slice (baseline residential specification):
  dwelling_type = ALL
  scenario      = baseline
  method        = e2sfca_gauss
  catchment_m   = 1000

Per cluster we compute:
  * n_subzones, total_resident_pop (from the clustering table)
  * population-weighted mean of access_per_1000, spar, pct_pop_no_access,
    access_65plus_per_1000  (weighted by the access-table population)
  * total stall_deficit_vs_national
  * % of cluster population in subzones with SPAR < 1.0 and SPAR < 0.8
  * unweighted medians of spar and access_per_1000 (robustness vs big subzones)

Output:
  data/processed/clustering/legacy_pop1000/cluster_accessibility_profiles.csv

No causal claims. No clusters are relabelled "vulnerable" by assumption.
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

OUTCOMES = ["access_per_1000", "spar", "pct_pop_no_access", "access_65plus_per_1000"]


def wmean(values: pd.Series, weights: pd.Series) -> float:
    v, w = values.to_numpy(float), weights.to_numpy(float)
    ok = ~np.isnan(v) & (w > 0)
    return float(np.average(v[ok], weights=w[ok])) if ok.any() else np.nan


def load_joined() -> pd.DataFrame:
    clusters = pd.read_csv(config.CLUSTERING_LEGACY / "subzone_clusters.csv")
    acc = pd.read_csv(config.PROCESSED / "agg_access_subzone.csv")

    slc = acc[(acc.dwelling_type == "ALL") & (acc.scenario == "baseline")
              & (acc.method == "e2sfca_gauss") & (acc.catchment_m == 1000)].copy()
    assert slc["sz_key"].is_unique, "access slice must be one row per subzone"

    keep = ["sz_key", "population", "pop_65plus"] + OUTCOMES + ["stall_deficit_vs_national"]
    j = clusters.merge(slc[keep], on="sz_key", how="left", suffixes=("", "_acc"))

    # Join-coverage report: clustered subzones with no access row (outside any
    # catchment / dropped from the spatial model).
    missing = j["access_per_1000"].isna().sum()
    print(f"Join coverage: {len(clusters)} clustered subzones; "
          f"{len(clusters) - missing} matched an access row, {missing} unmatched.")
    if missing:
        print("  unmatched sz_key (excluded from weighted stats):")
        for k in j.loc[j["access_per_1000"].isna(), "sz_key"]:
            print(f"    - {k}")
    return j


def profile(j: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for cl, g in j.groupby("cluster"):
        name = g["cluster_name"].iloc[0]
        matched = g[g["access_per_1000"].notna()].copy()
        # population weight = access-table population (consistent with the model)
        w = matched["population"]
        in_spar_lt1 = matched.loc[matched["spar"] < 1.0, "population"].sum()
        in_spar_lt08 = matched.loc[matched["spar"] < 0.8, "population"].sum()
        pop_matched = w.sum()
        rows.append({
            "cluster": cl,
            "cluster_name": name,
            "n_subzones": len(g),
            "n_subzones_with_access": len(matched),
            "total_resident_pop": int(g["resident_pop"].sum()),
            "access_pop_matched": int(pop_matched),
            "w_mean_access_per_1000": round(wmean(matched["access_per_1000"], w), 4),
            "w_mean_spar": round(wmean(matched["spar"], w), 4),
            "w_mean_pct_pop_no_access": round(wmean(matched["pct_pop_no_access"], w), 4),
            "w_mean_access_65plus_per_1000": round(wmean(matched["access_65plus_per_1000"], w), 4),
            "total_stall_deficit_vs_national": round(matched["stall_deficit_vs_national"].sum(), 4),
            "pct_pop_spar_lt_1_0": round(in_spar_lt1 / pop_matched * 100, 2) if pop_matched else np.nan,
            "pct_pop_spar_lt_0_8": round(in_spar_lt08 / pop_matched * 100, 2) if pop_matched else np.nan,
            "median_spar": round(matched["spar"].median(), 4),
            "median_access_per_1000": round(matched["access_per_1000"].median(), 4),
        })
    out = pd.DataFrame(rows).sort_values("cluster").reset_index(drop=True)
    return out


def main() -> None:
    j = load_joined()
    out = profile(j)
    path = config.CLUSTERING_LEGACY / "cluster_accessibility_profiles.csv"
    out.to_csv(path, index=False)

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 50)
    print("\n[cluster accessibility profiles] (baseline, e2sfca_gauss, 1000 m, dwelling_type=ALL)")
    print(out.to_string(index=False))
    print(f"\nSaved -> {path}")


if __name__ == "__main__":
    main()
