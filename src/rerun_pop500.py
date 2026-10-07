"""
Revised K-means pipeline (pop>=500 sample, consistent with regression preprocessing).

Does NOT reuse previous cluster assignments and does NOT assume K=3. Rebuilds the
clustering sample from scratch and reruns model selection. Writes to
data/processed/clustering/final_pop500/ (base filenames); the legacy outputs are
left untouched.

Preprocessing (NEW):
  * start from fact_subzone_population.csv
  * keep resident_pop >= 500  (was >= 1000)
  * features:
      hdb_share            = pop_hdb / resident_pop
      hdb_small_flat_share = (Dwelling_1_2_Room + Dwelling_3_Room) / pop_hdb
      pct_elderly          = Age_65plus / resident_pop
  * if pop_hdb == 0 -> hdb_small_flat_share = NaN (NOT 0); then DROP any row with
    NaN in any of the three features (consistency with regression sample).
  * clip valid share values to [0,1] only if rounding pushes slightly outside.

Model selection: K=2..8, n_init=25, random_state=42; report silhouette, inertia,
cluster sizes. Final K chosen on silhouette + balance + interpretability.

Then: neutral cluster names, held-out accessibility join (ALL/baseline/
e2sfca_gauss/1000 m), catchment sensitivity (500/1000/1500 m).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
import config  # noqa: E402

FEATURES = ["hdb_share", "hdb_small_flat_share", "pct_elderly"]
MIN_POP = 500
K_RANGE = range(2, 9)
RANDOM_STATE = 42
N_INIT = 25
P = config.PROCESSED          # shared pipeline inputs (NOT moved)
CF = config.CLUSTERING_FINAL  # final_pop500 clustering outputs


def wmean(v, w):
    v, w = np.asarray(v, float), np.asarray(w, float)
    ok = ~np.isnan(v) & (w > 0)
    return float(np.average(v[ok], weights=w[ok])) if ok.any() else np.nan


# ----------------------------------------------------------------------------
# 1-5. Build + report the revised sample
# ----------------------------------------------------------------------------
def build_sample() -> pd.DataFrame:
    pop = pd.read_csv(P / "fact_subzone_population.csv")
    n_before = len(pop)

    df = pop[pop["resident_pop"] >= MIN_POP].copy().reset_index(drop=True)
    n_after_popfilter = len(df)
    rp = df["resident_pop"]

    df["hdb_share"] = df["pop_hdb"] / rp
    small = df["Dwelling_1_2_Room"] + df["Dwelling_3_Room"]
    # NEW: pop_hdb==0 -> NaN (do not coerce to 0)
    df["hdb_small_flat_share"] = np.where(df["pop_hdb"] > 0, small / df["pop_hdb"], np.nan)
    df["pct_elderly"] = df["Age_65plus"] / rp

    n_nan = int(df["hdb_small_flat_share"].isna().sum())
    df = df.dropna(subset=FEATURES).reset_index(drop=True)
    n_final = len(df)

    # clip only if rounding pushed a share slightly outside [0,1]
    n_clipped = int(((df[FEATURES] < 0) | (df[FEATURES] > 1)).sum().sum())
    df[FEATURES] = df[FEATURES].clip(0.0, 1.0)

    print("=" * 76)
    print("REVISED PREPROCESSING REPORT (pop>=500)")
    print("=" * 76)
    print(f"  subzones before population filter        : {n_before}")
    print(f"  remaining after resident_pop >= {MIN_POP}      : {n_after_popfilter}")
    print(f"  removed because pop_hdb==0 (small-flat NaN): {n_nan}")
    print(f"  FINAL clustering sample size             : {n_final}")
    print(f"  feature values clipped to [0,1]          : {n_clipped}")
    print(f"  sz_key unique                            : {df['sz_key'].is_unique}")
    print("\n  missing values per feature (post-drop):")
    for f in FEATURES:
        print(f"    {f:<22} {int(df[f].isna().sum())}")
    print("\n  summary statistics:")
    print(df[FEATURES].describe().round(4).to_string())

    cols = ["sz_key", "pa_key", "resident_pop", "pop_hdb"] + FEATURES
    out = df[cols]
    out.to_csv(CF / "subzone_clustering_features.csv", index=False)
    return out


# ----------------------------------------------------------------------------
# Model selection
# ----------------------------------------------------------------------------
def model_selection(X):
    rows = []
    print("\n" + "=" * 76)
    print("K-MEANS MODEL SELECTION (K=2..8, n_init=25, random_state=42)")
    print("=" * 76)
    print(f"  {'K':>2}  {'silhouette':>11}  {'inertia':>11}  cluster_sizes")
    for k in K_RANGE:
        km = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=N_INIT)
        lab = km.fit_predict(X)
        sil = silhouette_score(X, lab)
        sizes = np.bincount(lab, minlength=k).tolist()
        bal = min(sizes) / max(sizes)
        print(f"  {k:>2}  {sil:>11.4f}  {km.inertia_:>11.2f}  {sizes}  (bal={bal:.2f})")
        rows.append({"k": k, "silhouette": round(sil, 4), "inertia": round(km.inertia_, 2),
                     "min_cluster": min(sizes), "max_cluster": max(sizes),
                     "balance_ratio": round(bal, 3), "cluster_sizes": "|".join(map(str, sizes))})
    sel = pd.DataFrame(rows)
    sel.to_csv(CF / "kmeans_model_selection.csv", index=False)
    return sel


# ----------------------------------------------------------------------------
# naming (features only)
# ----------------------------------------------------------------------------
def name_clusters(profile: pd.DataFrame) -> dict:
    names = {}
    priv = profile["hdb_share"].idxmin()
    names[priv] = "Private-housing areas"
    rest = [c for c in profile.index if c != priv]
    score = profile.loc[rest, "hdb_small_flat_share"] + profile.loc[rest, "pct_elderly"]
    older = score.idxmax()
    names[older] = "Small-flat / older HDB areas"
    for c in rest:
        if c != older:
            names[c] = "Larger-flat / lower-elderly HDB areas"
    return names


def main():
    df = build_sample()
    X = StandardScaler().fit_transform(df[FEATURES].to_numpy(float))
    sel = model_selection(X)

    # choose K: highest silhouette for K>=3 with balance_ratio >= 0.25
    cand = sel[(sel.k >= 3) & (sel.balance_ratio >= 0.25)]
    chosen_k = int(cand.loc[cand.silhouette.idxmax(), "k"])
    print(f"\n  -> selected K = {chosen_k} "
          f"(highest silhouette among K>=3 with balance_ratio>=0.25)")

    km = KMeans(n_clusters=chosen_k, random_state=RANDOM_STATE, n_init=N_INIT)
    df["cluster"] = km.fit_predict(X)
    sil = silhouette_score(X, df["cluster"])

    profile = df.groupby("cluster")[FEATURES].mean()
    names = name_clusters(profile)
    df["cluster_name"] = df["cluster"].map(names)

    out_cols = ["sz_key", "pa_key", "resident_pop", "pop_hdb"] + FEATURES + ["cluster", "cluster_name"]
    df[out_cols].to_csv(CF / "subzone_clusters.csv", index=False)

    prof = df.groupby("cluster").agg(
        cluster_name=("cluster_name", "first"),
        n_subzones=("sz_key", "size"),
        total_resident_pop=("resident_pop", "sum"),
        mean_hdb_share=("hdb_share", "mean"),
        mean_hdb_small_flat_share=("hdb_small_flat_share", "mean"),
        mean_pct_elderly=("pct_elderly", "mean"),
    ).reset_index()
    for c in ["mean_hdb_share", "mean_hdb_small_flat_share", "mean_pct_elderly"]:
        prof[c] = prof[c].round(4)
    prof.to_csv(CF / "cluster_profiles.csv", index=False)
    print(f"\n[final model] K={chosen_k} | silhouette={sil:.4f}")
    print("\n[cluster profiles]")
    print(prof.to_string(index=False))

    # ---- accessibility join (held-out) -----------------------------------
    acc = pd.read_csv(P / "agg_access_subzone.csv")

    def slc(scenario, d0):
        s = acc[(acc.dwelling_type == "ALL") & (acc.scenario == scenario)
                & (acc.method == "e2sfca_gauss") & (acc.catchment_m == d0)]
        return s[["sz_key", "population", "access_per_1000", "spar",
                  "pct_pop_no_access", "stall_deficit_vs_national"]]

    base = slc("baseline", 1000)
    j = df[["sz_key", "cluster", "cluster_name", "resident_pop"]].merge(base, on="sz_key", how="left")
    miss = j["access_per_1000"].isna().sum()
    print(f"\n[accessibility join] {len(df)} subzones; "
          f"{len(df)-miss} matched access row, {miss} unmatched.")
    arows = []
    for cl, g in j.groupby("cluster"):
        m = g[g.access_per_1000.notna()]
        w = m.population
        pop = w.sum()
        arows.append({
            "cluster": cl, "cluster_name": g.cluster_name.iloc[0],
            "n_subzones": len(g), "total_resident_pop": int(g.resident_pop.sum()),
            "w_mean_access_per_1000": round(wmean(m.access_per_1000, w), 4),
            "w_mean_spar": round(wmean(m.spar, w), 4),
            "w_mean_pct_pop_no_access": round(wmean(m.pct_pop_no_access, w), 2),
            "total_stall_deficit_vs_national": round(m.stall_deficit_vs_national.sum(), 2),
            "pct_pop_spar_lt_1_0": round(m.loc[m.spar < 1.0, "population"].sum() / pop * 100, 2),
        })
    accprof = pd.DataFrame(arows).sort_values("cluster")
    accprof.to_csv(CF / "cluster_accessibility_profiles.csv", index=False)
    print("\n[accessibility profiles] (ALL/baseline/e2sfca_gauss/1000 m)")
    print(accprof.to_string(index=False))

    # ---- catchment sensitivity -------------------------------------------
    srows = []
    for d0 in [500, 1000, 1500]:
        s = df[["sz_key", "cluster", "cluster_name"]].merge(slc("baseline", d0), on="sz_key", how="left")
        for cl, g in s.groupby("cluster"):
            m = g[g.spar.notna()]
            srows.append({"catchment_m": d0, "cluster": cl, "cluster_name": g.cluster_name.iloc[0],
                          "w_spar": round(wmean(m.spar, m.population), 4)})
    sens = pd.DataFrame(srows)
    sens.to_csv(CF / "cluster_catchment_sensitivity.csv", index=False)
    print("\n[catchment sensitivity] pop-weighted SPAR")
    piv = sens.pivot(index="catchment_m", columns="cluster", values="w_spar")
    piv.columns = [f"C{c}" for c in piv.columns]
    print(piv.to_string())
    for d0 in [500, 1000, 1500]:
        sub = sens[sens.catchment_m == d0]
        lo = sub.loc[sub.w_spar.idxmin()]
        print(f"  d0={d0}m lowest SPAR -> C{int(lo.cluster)} ({lo.cluster_name})")

    print(f"\nSaved final_pop500 files to {CF}.")


if __name__ == "__main__":
    main()
