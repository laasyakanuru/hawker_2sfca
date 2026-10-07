"""
Feature diagnostic analysis for the subzone clustering dataset (DIAGNOSTIC ONLY).

Does NOT modify any existing clustering output. It only reads
data/processed/clustering/legacy_pop1000/subzone_clustering_features.csv and prints:

  1. Pearson correlation matrix of the 7 features.
  2. Strongly correlated pairs (|r| >= 0.7).
  3. K-means silhouette sweep (K=2..8) for several candidate feature sets.
  4. A comparison table.

No access / SPAR / income / closure variables are used.
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

ALL7 = ["hdb_share", "condo_share", "landed_share", "hdb_small_flat_share",
        "pct_elderly", "pct_young", "pct_small_floor_area"]

FEATURE_SETS = {
    "A_all7": ALL7,
    "B_reduced": ["hdb_share", "hdb_small_flat_share", "pct_elderly", "pct_young"],
    "C_compact": ["hdb_share", "hdb_small_flat_share", "pct_elderly"],
    # Proposed D: drop the two features most redundant with others
    # (condo/landed are near-mirrors of hdb_share; pct_small_floor_area tracks
    # hdb_small_flat_share). Keep one housing-tenure axis, one HDB-vintage axis,
    # and both demographic axes.
    "D_proposed": ["hdb_share", "hdb_small_flat_share", "pct_elderly", "pct_young",
                   "landed_share"],
}

K_RANGE = range(2, 9)
RANDOM_STATE = 42
N_INIT = 25


def load() -> pd.DataFrame:
    df = pd.read_csv(config.CLUSTERING_LEGACY / "subzone_clustering_features.csv")
    assert len(df) == 212, f"expected 212 subzones, got {len(df)}"
    return df


def correlation(df: pd.DataFrame) -> pd.DataFrame:
    corr = df[ALL7].corr(method="pearson")
    print("=" * 78)
    print("[1] PEARSON CORRELATION MATRIX (7 features, n=212)")
    print("=" * 78)
    print(corr.round(3).to_string())

    print("\n" + "=" * 78)
    print("[2] STRONGLY CORRELATED PAIRS  (|r| >= 0.7)")
    print("=" * 78)
    pairs = []
    cols = ALL7
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            r = corr.iloc[i, j]
            if abs(r) >= 0.7:
                pairs.append((cols[i], cols[j], round(r, 3)))
    if pairs:
        for a, b, r in sorted(pairs, key=lambda t: -abs(t[2])):
            print(f"    {a:<22} <-> {b:<22} r = {r:+.3f}")
    else:
        print("    none")
    return corr


def sweep(df: pd.DataFrame) -> pd.DataFrame:
    print("\n" + "=" * 78)
    print("[3] K-MEANS SILHOUETTE SWEEP BY FEATURE SET (K=2..8)")
    print("=" * 78)
    rows = []
    for name, feats in FEATURE_SETS.items():
        X = StandardScaler().fit_transform(df[feats].to_numpy(float))
        print(f"\n--- {name}  ({len(feats)} features: {', '.join(feats)}) ---")
        print(f"    {'K':>2}  {'silhouette':>11}  cluster_sizes")
        best_k3, best_sil3 = None, -1.0
        for k in K_RANGE:
            km = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=N_INIT)
            labels = km.fit_predict(X)
            sil = silhouette_score(X, labels)
            sizes = np.bincount(labels, minlength=k).tolist()
            print(f"    {k:>2}  {sil:>11.4f}  {sizes}")
            if k >= 3 and sil > best_sil3:
                best_sil3, best_k3 = sil, k
            rows.append({"model": name, "n_features": len(feats), "k": k,
                         "silhouette": round(sil, 4),
                         "min_cluster": min(sizes), "max_cluster": max(sizes),
                         "balance_ratio": round(min(sizes) / max(sizes), 3)})
        print(f"    best silhouette for K>=3: {best_sil3:.4f} at K={best_k3}")
    return pd.DataFrame(rows)


def comparison(sweep_df: pd.DataFrame) -> None:
    print("\n" + "=" * 78)
    print("[5] MODEL COMPARISON  (best K>=3 per feature set)")
    print("=" * 78)
    best = (sweep_df[sweep_df.k >= 3]
            .sort_values("silhouette", ascending=False)
            .groupby("model", as_index=False).first()
            .sort_values("model"))
    print(best[["model", "n_features", "k", "silhouette",
                "min_cluster", "max_cluster", "balance_ratio"]].to_string(index=False))


def main() -> None:
    df = load()
    correlation(df)
    sw = sweep(df)
    comparison(sw)


if __name__ == "__main__":
    main()
