"""
Cluster 0 sanity check (DIAGNOSTIC ONLY).

Determines whether Cluster 0's very low measured hawker accessibility reflects a
genuine supply-access gap or could be an artefact of data coverage / modelling.

Does NOT change the clustering model or the accessibility model. Reads only.

Covers the 7 requested checks:
  1. List Cluster 0 subzones with demographics + access outcomes.
  2. Sort by lowest SPAR / largest population / largest stall deficit.
  3. Demand-point coverage (n points, allocated vs census pop, conservation,
     geocoded-block vs fallback share).
  4. HDB geocoding quality (unmatched / fallback blocks; newer-estate pattern).
  5. Hawker supply around low-SPAR subzones (nearest HC distance; counts within
     500/1000/1500 m; whether nearby centres are under-construction only).
  6. Baseline vs future scenario (pop-weighted SPAR, access, no-access).
  7. Classify the pattern (A broad / B concentrated / C data-quality / D future-fixed).

Outputs a per-subzone diagnostic CSV; prints the narrative tables.
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

ACC_SLICE = dict(dwelling_type="ALL", scenario="baseline",
                 method="e2sfca_gauss", catchment_m=1000)


def wmean(v: pd.Series, w: pd.Series) -> float:
    v, w = v.to_numpy(float), w.to_numpy(float)
    ok = ~np.isnan(v) & (w > 0)
    return float(np.average(v[ok], weights=w[ok])) if ok.any() else np.nan


def main() -> None:
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 60)
    pd.set_option("display.max_rows", 200)

    clusters = pd.read_csv(config.CLUSTERING_LEGACY / "subzone_clusters.csv")
    c0 = clusters[clusters.cluster == 0].copy()
    c0_keys = set(c0.sz_key)
    dimsz = pd.read_csv(config.PROCESSED / "dim_subzone.csv")[["sz_key", "subzone", "planning_area"]]

    acc = pd.read_csv(config.PROCESSED / "agg_access_subzone.csv")

    def slice_acc(scenario):
        s = acc[(acc.dwelling_type == "ALL") & (acc.scenario == scenario)
                & (acc.method == "e2sfca_gauss") & (acc.catchment_m == 1000)]
        return s[["sz_key", "population", "pop_65plus", "access_per_1000", "spar",
                  "pct_pop_no_access", "stall_deficit_vs_national"]]

    base = slice_acc("baseline")
    fut = slice_acc("future")

    # ---- [1] Cluster-0 subzone table -------------------------------------
    t = (c0.merge(dimsz, on="sz_key", how="left")
           .merge(base, on="sz_key", how="left"))
    t1 = t[["sz_key", "subzone", "planning_area", "resident_pop", "hdb_share",
            "pct_elderly", "access_per_1000", "spar", "pct_pop_no_access",
            "stall_deficit_vs_national"]].copy()
    print("=" * 80)
    print(f"[1] CLUSTER 0 SUBZONES  (n={len(t1)})")
    print("=" * 80)
    print(t1.sort_values("spar").to_string(index=False))

    # ---- [2] sorted views -------------------------------------------------
    print("\n" + "=" * 80)
    print("[2] SORTED VIEWS")
    print("=" * 80)
    print("\n-- lowest SPAR (bottom 10) --")
    print(t1.sort_values("spar").head(10)[["sz_key", "planning_area", "resident_pop",
                                           "spar", "access_per_1000", "pct_pop_no_access"]].to_string(index=False))
    print("\n-- largest resident population (top 10) --")
    print(t1.sort_values("resident_pop", ascending=False).head(10)[
        ["sz_key", "planning_area", "resident_pop", "spar", "access_per_1000",
         "stall_deficit_vs_national"]].to_string(index=False))
    print("\n-- largest stall deficit (top 10) --")
    print(t1.sort_values("stall_deficit_vs_national", ascending=False).head(10)[
        ["sz_key", "planning_area", "resident_pop", "stall_deficit_vs_national",
         "spar", "access_per_1000"]].to_string(index=False))

    # ---- [3] demand-point coverage ---------------------------------------
    dp = pd.read_csv(config.PROCESSED / "dim_demand_point.csv")
    dp0 = dp[dp.sz_key.isin(c0_keys)].copy()
    cov = dp0.groupby("sz_key").agg(
        n_points=("dp_key", "size"),
        n_with_coords=("has_coords", "sum"),
        alloc_pop=("population", "sum"),
    ).reset_index()
    # geocoded-block vs fallback for HDB points
    hdb0 = dp0[dp0.dwelling_type == "HDB"].copy()
    geo = hdb0.assign(is_block=hdb0.source.eq("hdb_block_onemap")).groupby("sz_key").agg(
        hdb_points=("dp_key", "size"),
        hdb_pop=("population", "sum"),
        hdb_pop_at_blocks=("population", lambda s: s[hdb0.loc[s.index, "source"] == "hdb_block_onemap"].sum()),
    ).reset_index()
    geo["pct_hdb_pop_at_blocks"] = (geo.hdb_pop_at_blocks / geo.hdb_pop * 100).round(1)
    cov = cov.merge(geo[["sz_key", "hdb_points", "pct_hdb_pop_at_blocks"]], on="sz_key", how="left")
    cov = cov.merge(t1[["sz_key", "resident_pop"]], on="sz_key", how="left")
    cov["alloc_minus_census"] = (cov.alloc_pop - cov.resident_pop).round(1)

    print("\n" + "=" * 80)
    print("[3] DEMAND-POINT COVERAGE (Cluster 0)")
    print("=" * 80)
    print(cov.sort_values("n_points").to_string(index=False))
    low_cov = cov[(cov.n_points <= 2) | (cov.pct_hdb_pop_at_blocks < 50)]
    print(f"\n  subzones with <=2 demand points OR <50% HDB pop at geocoded blocks: {len(low_cov)}")
    if len(low_cov):
        print(low_cov[["sz_key", "n_points", "hdb_points", "pct_hdb_pop_at_blocks",
                       "alloc_minus_census"]].to_string(index=False))

    # population conservation
    qa = pd.read_csv(config.PROCESSED / "qa_population_conservation.csv")
    qa0 = qa[qa.sz_key.isin(c0_keys)]
    print(f"\n  population conservation: max |diff| across Cluster-0 rows = "
          f"{qa0['diff'].abs().max():.4f}  (sum diff = {qa0['diff'].sum():.4f})")

    # ---- [4] HDB geocoding quality ---------------------------------------
    blk = pd.read_csv(config.PROCESSED / "dim_hdb_block.csv")
    blk0 = blk[blk.sz_key.isin(c0_keys)].copy()
    gq = blk0.groupby("sz_key").agg(
        n_blocks=("block_id", "size"),
        n_matched=("geocode_status", lambda s: (s == "matched").sum()),
        n_centroid_fallback=("sz_assign_method", lambda s: (s != "point_in_polygon").sum()),
        median_year=("year_completed", "median"),
    ).reset_index()
    gq["pct_matched"] = (gq.n_matched / gq.n_blocks * 100).round(1)
    print("\n" + "=" * 80)
    print("[4] HDB GEOCODING QUALITY (Cluster 0)")
    print("=" * 80)
    print(f"  geocode_status values present: {sorted(blk0.geocode_status.unique())}")
    print(f"  overall Cluster-0 blocks: {len(blk0)} | matched: {(blk0.geocode_status=='matched').sum()} "
          f"({(blk0.geocode_status=='matched').mean()*100:.1f}%)")
    print(f"  blocks using centroid/nearest fallback for subzone: "
          f"{(blk0.sz_assign_method!='point_in_polygon').sum()}")
    # newer-estate pattern: correlation of median completion year with pct_matched
    print("\n  per-subzone (sorted by worst geocoding):")
    print(gq.sort_values("pct_matched").head(12).to_string(index=False))
    print("\n  median year_completed of Cluster-0 blocks: "
          f"{blk0.year_completed.median():.0f} (min {blk0.year_completed.min():.0f}, "
          f"max {blk0.year_completed.max():.0f})")

    # ---- [5] hawker supply around low-SPAR subzones ----------------------
    prox = pd.read_csv(config.PROCESSED / "fact_demand_proximity.csv")
    dp_key_sz = dp[["dp_key", "sz_key"]]
    prox = prox.merge(dp_key_sz, on="dp_key", how="left")
    prox0 = prox[prox.sz_key.isin(c0_keys)]
    # population-weighted-ish: use simple per-subzone mean over its demand points
    sup = prox0.groupby("sz_key").agg(
        mean_nearest_hc_m=("nearest_hc_dist_m", "mean"),
        min_nearest_hc_m=("nearest_hc_dist_m", "min"),
        mean_n_500m=("n_hc_within_500m", "mean"),
        mean_n_1km=("n_hc_within_1km", "mean"),
        mean_n_1_5km=("n_hc_within_1_5km", "mean"),
    ).reset_index().merge(t1[["sz_key", "spar", "resident_pop"]], on="sz_key", how="left")
    print("\n" + "=" * 80)
    print("[5] HAWKER SUPPLY AROUND LOW-SPAR CLUSTER-0 SUBZONES (10 lowest SPAR)")
    print("=" * 80)
    low = sup.sort_values("spar").head(10)
    print(low[["sz_key", "spar", "resident_pop", "mean_nearest_hc_m", "min_nearest_hc_m",
               "mean_n_500m", "mean_n_1km", "mean_n_1_5km"]].round(2).to_string(index=False))
    print(f"\n  Cluster-0 overall: mean nearest open HC = {prox0.nearest_hc_dist_m.mean():.0f} m; "
          f"share of points with 0 HC within 1 km = {(prox0.n_hc_within_1km==0).mean()*100:.1f}%")

    # under-construction centres near low-SPAR subzones (future - baseline)
    hc = pd.read_csv(config.PROCESSED / "dim_hawker_centre.csv")
    uc = hc[(hc.in_future) & (~hc.in_baseline)]
    print(f"\n  centres that are future-only (under construction): {len(uc)} "
          f"-> {sorted(uc.hc_key.tolist())}")

    # ---- [6] baseline vs future (pop-weighted) ---------------------------
    b0 = base[base.sz_key.isin(c0_keys)]
    f0 = fut[fut.sz_key.isin(c0_keys)]
    print("\n" + "=" * 80)
    print("[6] BASELINE vs FUTURE (Cluster 0, pop-weighted)")
    print("=" * 80)
    for name, s in [("baseline", b0), ("future", f0)]:
        print(f"  {name:9s}: SPAR={wmean(s.spar, s.population):.4f} | "
              f"access_per_1000={wmean(s.access_per_1000, s.population):.4f} | "
              f"pct_pop_no_access={wmean(s.pct_pop_no_access, s.population):.2f}")
    # per-subzone change
    chg = b0[["sz_key", "population", "spar", "access_per_1000", "pct_pop_no_access"]].merge(
        f0[["sz_key", "spar", "access_per_1000", "pct_pop_no_access"]],
        on="sz_key", suffixes=("_base", "_fut"))
    chg["d_access"] = (chg.access_per_1000_fut - chg.access_per_1000_base).round(4)
    chg["d_spar"] = (chg.spar_fut - chg.spar_base).round(4)
    improved = chg[chg.d_access > 0.01]
    print(f"\n  Cluster-0 subzones materially improved by future centres (d_access>0.01): "
          f"{len(improved)} of {len(chg)}")
    if len(improved):
        print(improved.sort_values("d_access", ascending=False).head(10)[
            ["sz_key", "population", "spar_base", "spar_fut", "d_spar",
             "access_per_1000_base", "access_per_1000_fut", "d_access"]].to_string(index=False))

    # ---- [7] concentration analysis --------------------------------------
    print("\n" + "=" * 80)
    print("[7] DISTRIBUTION OF THE LOW-ACCESS BURDEN WITHIN CLUSTER 0")
    print("=" * 80)
    lowspar = t1[t1.spar < 0.8]
    print(f"  subzones with SPAR<0.8: {len(lowspar)}/{len(t1)} "
          f"({len(lowspar)/len(t1)*100:.0f}%), holding "
          f"{lowspar.resident_pop.sum()/t1.resident_pop.sum()*100:.0f}% of Cluster-0 population")
    tot_def = t1.stall_deficit_vs_national.sum()
    top5 = t1.sort_values("stall_deficit_vs_national", ascending=False).head(5)
    print(f"  top-5 subzones by deficit hold {top5.stall_deficit_vs_national.sum()/tot_def*100:.0f}% "
          f"of Cluster-0's total stall deficit ({tot_def:.0f})")
    print(f"  median SPAR = {t1.spar.median():.3f}; "
          f"share of subzones (unweighted) with SPAR<1.0 = {(t1.spar<1).mean()*100:.0f}%")

    # ---- save per-subzone diagnostic -------------------------------------
    diag = (t1.merge(cov[["sz_key", "n_points", "hdb_points", "pct_hdb_pop_at_blocks",
                          "alloc_minus_census"]], on="sz_key", how="left")
              .merge(sup[["sz_key", "mean_nearest_hc_m", "mean_n_1km"]], on="sz_key", how="left")
              .merge(chg[["sz_key", "spar_fut", "access_per_1000_fut", "d_access"]],
                     on="sz_key", how="left"))
    out = config.CLUSTERING_LEGACY / "cluster0_sanity_check.csv"
    diag.sort_values("spar").to_csv(out, index=False)
    print(f"\nSaved per-subzone diagnostic -> {out}")


if __name__ == "__main__":
    main()
