"""
Final clustering visualisations (FIXED K=3 Model C). Does NOT refit anything.

Reads the saved analysis tables (legacy_pop1000) so every plotted value matches them:
  subzone_clusters.csv               (fixed cluster labels + features)
  cluster_profiles.csv               (feature means per cluster)
  cluster_accessibility_profiles.csv (1000 m baseline accessibility per cluster)
  cluster_catchment_sensitivity.csv  (SPAR by catchment)

Writes to outputs/clustering/legacy_pop1000/:
  fig1_cluster_profiles.png
  fig2a_spar_by_cluster.png
  fig2b_no_access_by_cluster.png
  fig3_catchment_sensitivity.png
  fig4_pca_clusters.png
  fig5_cluster_map.png            (if subzone boundaries are readable)
and the consolidated table data/processed/clustering/legacy_pop1000/cluster_final_summary.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.collections import PolyCollection  # noqa: E402
from sklearn.decomposition import PCA  # noqa: E402
from sklearn.preprocessing import StandardScaler  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
import config  # noqa: E402

OUTDIR = config.OUTPUTS_CLUSTERING_LEGACY
OUTDIR.mkdir(parents=True, exist_ok=True)

FEATURES = ["hdb_share", "hdb_small_flat_share", "pct_elderly"]

# Consistent cluster order, names and colours across every figure.
NAMES = {
    0: "C0: Larger-flat / lower-elderly HDB areas",
    1: "C1: Small-flat / older HDB areas",
    2: "C2: Private-housing areas",
}
SHORT = {0: "C0", 1: "C1", 2: "C2"}
COLORS = {0: "#d95f02", 1: "#1b9e77", 2: "#7570b3"}

plt.rcParams.update({
    "font.size": 11, "axes.titlesize": 13, "axes.titleweight": "bold",
    "axes.spines.top": False, "axes.spines.right": False,
    "figure.dpi": 100, "savefig.dpi": 300,
})


def load():
    clusters = pd.read_csv(config.CLUSTERING_LEGACY / "subzone_clusters.csv")
    prof = pd.read_csv(config.CLUSTERING_LEGACY / "cluster_profiles.csv").set_index("cluster")
    acc = pd.read_csv(config.CLUSTERING_LEGACY / "cluster_accessibility_profiles.csv").set_index("cluster")
    sens = pd.read_csv(config.CLUSTERING_LEGACY / "cluster_catchment_sensitivity.csv")
    return clusters, prof, acc, sens


def fig1_profiles(prof):
    feats = [("mean_hdb_share", "HDB share"),
             ("mean_hdb_small_flat_share", "Small-flat share (of HDB)"),
             ("mean_pct_elderly", "Elderly share (65+)")]
    clusters = [0, 1, 2]
    x = np.arange(len(feats))
    w = 0.26
    fig, ax = plt.subplots(figsize=(10, 6))
    for i, cl in enumerate(clusters):
        vals = [prof.loc[cl, f] * 100 for f, _ in feats]
        bars = ax.bar(x + (i - 1) * w, vals, w, color=COLORS[cl], label=NAMES[cl])
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 1, f"{v:.0f}%",
                    ha="center", va="bottom", fontsize=9)
    ax.set_xticks(x)
    ax.set_xticklabels([lbl for _, lbl in feats])
    ax.set_ylabel("Mean value (%)")
    ax.set_ylim(0, 100)
    ax.set_title("Neighbourhood Profiles Identified by K-means")
    ax.legend(loc="upper right", fontsize=9, framealpha=0.95)
    fig.text(0.5, -0.01,
             "Clusters are based only on housing and demographic characteristics; "
             "accessibility was not used in clustering.",
             ha="center", fontsize=9, style="italic", color="#444444")
    fig.tight_layout()
    p = OUTDIR / "fig1_cluster_profiles.png"
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    return p


def fig2_access(acc):
    clusters = [0, 1, 2]
    labels = [SHORT[c] for c in clusters]
    cols = [COLORS[c] for c in clusters]

    # 2a SPAR
    spar = [acc.loc[c, "w_mean_spar"] for c in clusters]
    fig, ax = plt.subplots(figsize=(8, 6))
    bars = ax.bar(labels, spar, color=cols)
    ax.axhline(1.0, ls="--", lw=1.3, color="#333333")
    ax.text(2.42, 1.03, "SPAR = 1.0\n(national average)", fontsize=8.5,
            color="#333333", ha="right", va="bottom")
    for b, v in zip(bars, spar):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.03, f"{v:.2f}",
                ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax.set_ylabel("Population-weighted SPAR")
    ax.set_ylim(0, max(spar) * 1.15)
    ax.set_title("Hawker Accessibility Differs Strongly Across Neighbourhood Profiles",
                 fontsize=12)
    ax.set_xticks(range(3))
    ax.set_xticklabels([NAMES[c].replace(": ", ":\n") for c in clusters], fontsize=8.5)
    fig.text(0.5, -0.02, "Baseline supply, E2SFCA (Gaussian), 1,000 m catchment. "
             "SPAR below 1.0 means below the national average.",
             ha="center", fontsize=8.5, style="italic", color="#444444")
    fig.tight_layout()
    pa = OUTDIR / "fig2a_spar_by_cluster.png"
    fig.savefig(pa, bbox_inches="tight")
    plt.close(fig)

    # 2b pct_pop_no_access
    noacc = [acc.loc[c, "w_mean_pct_pop_no_access"] for c in clusters]
    fig, ax = plt.subplots(figsize=(8, 6))
    bars = ax.bar(labels, noacc, color=cols)
    for b, v in zip(bars, noacc):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.6, f"{v:.1f}%",
                ha="center", va="bottom", fontsize=10, fontweight="bold")
    ax.set_ylabel("Population-weighted residents with no access (%)")
    ax.set_ylim(0, max(noacc) * 1.18)
    ax.set_title("Residents With No Hawker Centre Within 1 km, by Profile", fontsize=12)
    ax.set_xticks(range(3))
    ax.set_xticklabels([NAMES[c].replace(": ", ":\n") for c in clusters], fontsize=8.5)
    fig.text(0.5, -0.02, "Baseline supply, E2SFCA (Gaussian), 1,000 m catchment.",
             ha="center", fontsize=8.5, style="italic", color="#444444")
    fig.tight_layout()
    pb = OUTDIR / "fig2b_no_access_by_cluster.png"
    fig.savefig(pb, bbox_inches="tight")
    plt.close(fig)
    return pa, pb


def fig3_sensitivity(sens):
    fig, ax = plt.subplots(figsize=(9, 6))
    cats = [500, 1000, 1500]
    for cl in [0, 1, 2]:
        sub = sens[sens.cluster == cl].sort_values("catchment_m")
        y = sub["w_spar"].to_numpy()
        ax.plot(cats, y, marker="o", ms=8, lw=2.2, color=COLORS[cl], label=NAMES[cl])
        for xc, yc in zip(cats, y):
            ax.annotate(f"{yc:.2f}", (xc, yc), textcoords="offset points",
                        xytext=(0, 9), ha="center", fontsize=8.5, color=COLORS[cl])
    ax.axhline(1.0, ls="--", lw=1.3, color="#333333")
    ax.text(1500, 1.04, "SPAR = 1.0 (national average)", fontsize=8.5,
            color="#333333", ha="right", va="bottom")
    ax.set_xticks(cats)
    ax.set_xlabel("Catchment distance (m)")
    ax.set_ylabel("Population-weighted SPAR")
    ax.set_title("Accessibility Pattern Persists Across Catchment Distances")
    ax.legend(loc="center right", fontsize=9, framealpha=0.95)
    ax.margins(x=0.08)
    fig.tight_layout()
    p = OUTDIR / "fig3_catchment_sensitivity.png"
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    return p


def fig4_pca(clusters):
    X = StandardScaler().fit_transform(clusters[FEATURES].to_numpy(float))
    pca = PCA(n_components=2, random_state=42)
    pcs = pca.fit_transform(X)
    ev = pca.explained_variance_ratio_ * 100
    fig, ax = plt.subplots(figsize=(8.5, 6.5))
    for cl in [0, 1, 2]:
        m = (clusters["cluster"] == cl).to_numpy()
        ax.scatter(pcs[m, 0], pcs[m, 1], s=30, alpha=0.75, color=COLORS[cl],
                   label=f"{NAMES[cl]} (n={int(m.sum())})")
        cx, cy = pcs[m, 0].mean(), pcs[m, 1].mean()
        ax.scatter(cx, cy, marker="X", s=240, c="black", edgecolors="white",
                   linewidths=1.6, zorder=5)
    ax.set_xlabel(f"PC1 ({ev[0]:.1f}% of variance)")
    ax.set_ylabel(f"PC2 ({ev[1]:.1f}% of variance)")
    ax.set_title("K-means Cluster Separation in PCA Space")
    ax.legend(loc="best", fontsize=8.5, framealpha=0.95)
    fig.text(0.5, -0.01, "PCA of the 3 standardised clustering features "
             "(hdb_share, hdb_small_flat_share, pct_elderly). Black X = cluster centroid.",
             ha="center", fontsize=8.5, style="italic", color="#444444")
    fig.tight_layout()
    p = OUTDIR / "fig4_pca_clusters.png"
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    return p, ev


def fig5_map(clusters):
    """Choropleth of subzones coloured by cluster, using geo.py (no GIS deps)."""
    import geo  # local helper
    path = config.EXTERNAL_FILES["subzone_geojson"]
    if not path.exists():
        print("  fig5: subzone boundary GeoJSON not found; skipping map.")
        return None
    feats = geo.read_geojson(path)
    label_of = dict(zip(clusters["sz_key"], clusters["cluster"]))

    verts, cols = [], []
    matched = 0
    for f in feats:
        szk = geo.name_key(f.props.get("SUBZONE_N"))
        cl = label_of.get(szk)
        colour = COLORS.get(cl, "#e5e5e5") if cl is not None else "#e5e5e5"
        if cl is not None:
            matched += 1
        for poly in f.polygons:
            verts.append(poly[0])      # exterior ring in SVY21 metres
            cols.append(colour)
    fig, ax = plt.subplots(figsize=(11, 7))
    pc = PolyCollection(verts, facecolors=cols, edgecolors="white", linewidths=0.3)
    ax.add_collection(pc)
    ax.autoscale_view()
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title("Spatial Distribution of Neighbourhood Profiles")
    from matplotlib.patches import Patch
    handles = [Patch(facecolor=COLORS[c], label=NAMES[c]) for c in [0, 1, 2]]
    handles.append(Patch(facecolor="#e5e5e5", label="Not clustered (pop < 1,000 / non-residential)"))
    ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.12),
              ncol=2, fontsize=8.5, frameon=False)
    fig.tight_layout()
    p = OUTDIR / "fig5_cluster_map.png"
    fig.savefig(p, bbox_inches="tight")
    plt.close(fig)
    print(f"  fig5: {matched} subzones coloured by cluster.")
    return p


def summary_table(prof, acc):
    rows = []
    for cl in [0, 1, 2]:
        rows.append({
            "cluster": cl,
            "cluster_name": NAMES[cl].split(": ", 1)[1],
            "n_subzones": int(acc.loc[cl, "n_subzones"]),
            "total_resident_pop": int(acc.loc[cl, "total_resident_pop"]),
            "mean_hdb_share": round(prof.loc[cl, "mean_hdb_share"], 4),
            "mean_hdb_small_flat_share": round(prof.loc[cl, "mean_hdb_small_flat_share"], 4),
            "mean_pct_elderly": round(prof.loc[cl, "mean_pct_elderly"], 4),
            "w_access_per_1000_1000m": round(acc.loc[cl, "w_mean_access_per_1000"], 4),
            "w_spar_1000m": round(acc.loc[cl, "w_mean_spar"], 4),
            "w_pct_pop_no_access_1000m": round(acc.loc[cl, "w_mean_pct_pop_no_access"], 2),
            "total_stall_deficit_vs_national": round(acc.loc[cl, "total_stall_deficit_vs_national"], 2),
            "pct_pop_spar_lt_0_8": round(acc.loc[cl, "pct_pop_spar_lt_0_8"], 2),
        })
    out = pd.DataFrame(rows)
    p = config.CLUSTERING_LEGACY / "cluster_final_summary.csv"
    out.to_csv(p, index=False)
    return out, p


def main():
    clusters, prof, acc, sens = load()
    p1 = fig1_profiles(prof)
    p2a, p2b = fig2_access(acc)
    p3 = fig3_sensitivity(sens)
    p4, ev = fig4_pca(clusters)
    p5 = fig5_map(clusters)
    tbl, tp = summary_table(prof, acc)

    print("\nConsolidated summary table:")
    print(tbl.to_string(index=False))
    print(f"\nPCA explained variance: PC1 {ev[0]:.1f}%, PC2 {ev[1]:.1f}% (sum {ev.sum():.1f}%)")
    print("\nFigures written:")
    for p in [p1, p2a, p2b, p3, p4, p5]:
        if p:
            print(f"  {p}")
    print(f"Summary table -> {tp}")


if __name__ == "__main__":
    main()
