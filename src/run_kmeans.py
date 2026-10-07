"""
K-means clustering of subzone neighbourhood profiles  --  PRIMARY MODEL (Model C).

Research question: "Which types of neighbourhoods are more vulnerable to
hawker service gaps?"

Specification (chosen after the feature-redundancy diagnostic in
src/feature_diagnostics.py):
  * Features (non-redundant, parsimonious):
        hdb_share, hdb_small_flat_share, pct_elderly
  * K = 3
  * Rationale: strongest silhouette among K>=3 solutions (0.447), no feature
    pair with |r|>=0.7, relatively balanced clusters, and the three variables
    together describe housing dependence, HDB vintage/flat-size, and age
    structure.

Pipeline:
  1. Load the cleaned feature table (data/processed/clustering/legacy_pop1000/subzone_clustering_features.csv).
  2. Standardise the 3 features with StandardScaler.
  3. Fit K-means (K=3).
  4. Save per-subzone cluster labels + a cluster-profile table.
  5. Save a PCA (2-component) scatter for visual inspection.

IMPORTANT: this stage only identifies neighbourhood PROFILES. No access / SPAR /
income / closure outcome is used or joined here, and no cluster is labelled
"vulnerable" or "underserved" - that comes later, from held-out outcomes.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")  # headless: write a PNG, never open a window
import matplotlib.pyplot as plt  # noqa: E402
from sklearn.cluster import KMeans  # noqa: E402
from sklearn.decomposition import PCA  # noqa: E402
from sklearn.metrics import silhouette_score  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
import config  # noqa: E402

# Model C: parsimonious, non-redundant feature set.
FEATURES = ["hdb_share", "hdb_small_flat_share", "pct_elderly"]
CHOSEN_K = 3
RANDOM_STATE = 42
N_INIT = 25

# Neutral descriptive names assigned AFTER inspecting the cluster centres
# (see name_clusters()). Keys are filled in at run time by rank, so the label
# always matches the actual centre ordering regardless of KMeans label numbers.


def load_features() -> pd.DataFrame:
    df = pd.read_csv(config.CLUSTERING_LEGACY / "subzone_clustering_features.csv")
    assert df["sz_key"].is_unique, "sz_key must be unique"
    assert len(df) == 212, f"expected 212 subzones, got {len(df)}"
    assert df[FEATURES].isna().sum().sum() == 0, "features must have no NaN"
    return df


def name_clusters(profile: pd.DataFrame) -> dict[int, str]:
    """Assign neutral, feature-only descriptive names.

    Logic (purely from the 3 clustering features, no outcomes):
      * The cluster with low hdb_share is the private-housing profile.
      * Among the HDB-dominant clusters, the one with the higher
        hdb_small_flat_share + pct_elderly is the older small-flat profile;
        the other is the newer/larger-flat profile.
    """
    names: dict[int, str] = {}
    # private-housing cluster = lowest hdb_share
    priv = profile["hdb_share"].idxmin()
    names[priv] = "Private-housing areas"
    # the remaining (HDB-dominant) clusters
    rest = [c for c in profile.index if c != priv]
    # small-flat / older profile = higher combined (small-flat share + elderly)
    score = profile.loc[rest, "hdb_small_flat_share"] + profile.loc[rest, "pct_elderly"]
    older = score.idxmax()
    newer = [c for c in rest if c != older][0]
    names[older] = "Small-flat / older HDB areas"
    names[newer] = "Larger-flat / lower-elderly HDB areas"
    return names


def main() -> None:
    df = load_features()
    scaler = StandardScaler()
    X = scaler.fit_transform(df[FEATURES].to_numpy(float))
    print(f"Model C: clustering {len(df)} subzones on {len(FEATURES)} standardised "
          f"features {FEATURES} at K={CHOSEN_K}.")

    # ---- final fit -------------------------------------------------------
    km = KMeans(n_clusters=CHOSEN_K, random_state=RANDOM_STATE, n_init=N_INIT)
    df["cluster"] = km.fit_predict(X)
    sil = silhouette_score(X, df["cluster"])
    print(f"[final model] K={CHOSEN_K} | inertia={km.inertia_:.4f} | silhouette={sil:.4f}")

    # ---- cluster profile (means of ORIGINAL, un-scaled features) ---------
    profile = df.groupby("cluster")[FEATURES].mean()
    names = name_clusters(profile)
    df["cluster_name"] = df["cluster"].map(names)

    prof = df.groupby(["cluster"]).agg(
        cluster_name=("cluster_name", "first"),
        n_subzones=("sz_key", "size"),
        total_resident_pop=("resident_pop", "sum"),
        mean_hdb_share=("hdb_share", "mean"),
        mean_hdb_small_flat_share=("hdb_small_flat_share", "mean"),
        mean_pct_elderly=("pct_elderly", "mean"),
    ).reset_index()
    for c in ["mean_hdb_share", "mean_hdb_small_flat_share", "mean_pct_elderly"]:
        prof[c] = prof[c].round(4)

    # ---- save outputs ----------------------------------------------------
    out_cols = ["sz_key", "pa_key", "resident_pop", "pop_hdb"] + FEATURES + \
               ["cluster", "cluster_name"]
    clusters_path = config.CLUSTERING_LEGACY / "subzone_clusters.csv"
    profile_path = config.CLUSTERING_LEGACY / "cluster_profiles.csv"
    df[out_cols].to_csv(clusters_path, index=False)
    prof.to_csv(profile_path, index=False)

    print("\n[cluster profiles] (clustering features only):")
    print(prof.to_string(index=False))

    # ---- PCA visualisation (2 components of the 3 standardised features) -
    pca = PCA(n_components=2, random_state=RANDOM_STATE)
    pcs = pca.fit_transform(X)
    ev = pca.explained_variance_ratio_
    fig, ax = plt.subplots(figsize=(8, 6))
    palette = ["#1b9e77", "#d95f02", "#7570b3"]
    for c in sorted(df["cluster"].unique()):
        m = df["cluster"] == c
        ax.scatter(pcs[m.to_numpy(), 0], pcs[m.to_numpy(), 1], s=28, alpha=0.75,
                   color=palette[c % len(palette)],
                   label=f"{c}: {names[c]} (n={int(m.sum())})")
    # project cluster centres into PCA space
    cen = pca.transform(km.cluster_centers_)
    ax.scatter(cen[:, 0], cen[:, 1], marker="X", s=220, c="black",
               edgecolors="white", linewidths=1.5, label="centroids", zorder=5)
    ax.set_xlabel(f"PC1 ({ev[0]*100:.1f}% var)")
    ax.set_ylabel(f"PC2 ({ev[1]*100:.1f}% var)")
    ax.set_title("Subzone neighbourhood profiles (Model C, K=3)\n"
                 "features: hdb_share, hdb_small_flat_share, pct_elderly")
    ax.legend(loc="best", fontsize=8, framealpha=0.9)
    fig.tight_layout()
    png_path = config.CLUSTERING_LEGACY / "cluster_pca.png"
    fig.savefig(png_path, dpi=150)
    plt.close(fig)
    print(f"\n[PCA] PC1+PC2 explain {ev.sum()*100:.1f}% of variance "
          f"(PC1 {ev[0]*100:.1f}%, PC2 {ev[1]*100:.1f}%).")

    print("\n[neutral cluster names]")
    for c in sorted(names):
        print(f"    cluster {c}: {names[c]}")

    print("\nSaved ->")
    print(f"  {clusters_path}")
    print(f"  {profile_path}")
    print(f"  {png_path}")


if __name__ == "__main__":
    main()
