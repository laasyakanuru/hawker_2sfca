"""
Underserved-profile map for the REVISED pop500 K-means analysis.

Highlights ONLY revised C1 ("Larger-flat / lower-elderly HDB areas") - the
underserved profile - against all other subzones in light grey.

Uses ONLY data/processed/clustering/final_pop500/subzone_clusters.csv (NOT the
legacy results). Does NOT touch the legacy cluster map.

Output: outputs/clustering/final_pop500/fig_underserved_map.png
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
from matplotlib.patches import Patch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
import config  # noqa: E402
import geo  # noqa: E402

OUTDIR = config.OUTPUTS_CLUSTERING_FINAL
OUTDIR.mkdir(parents=True, exist_ok=True)

HIGHLIGHT = "#d7301f"   # strong warm red for the underserved profile
OTHER = "#ececec"       # very light grey for everything else
C1_NAME = "Larger-flat / lower-elderly HDB areas"

# 6 representative low-SPAR C1 subzones to label (confirmed from pop500 data at
# run time; these sz_keys are only used as the preferred label set).
PREFERRED_LABELS = ["YEW TEE", "KEAT HONG", "PASIR RIS WEST",
                    "PUNGGOL FIELD", "TAMPINES NORTH", "WOODLANDS SOUTH"]


def main() -> None:
    # ---- revised pop500 clusters ONLY ------------------------------------
    clusters = pd.read_csv(config.CLUSTERING_FINAL / "subzone_clusters.csv")
    c1 = clusters[clusters["cluster_name"] == C1_NAME]
    c1_keys = set(c1["sz_key"])
    assert len(c1_keys) == 71, f"expected 71 C1 subzones, got {len(c1_keys)}"

    # confirm label candidates are genuinely C1 in the pop500 file
    label_keys = [k for k in PREFERRED_LABELS if k in c1_keys]

    # ---- geometry --------------------------------------------------------
    feats = geo.read_geojson(config.EXTERNAL_FILES["subzone_geojson"])
    dz = pd.read_csv(config.PROCESSED / "dim_subzone.csv")[["sz_key", "subzone"]]
    name_of = dict(zip(dz["sz_key"], dz["subzone"]))

    verts, cols, zords = [], [], []
    highlighted = 0
    centroids = {}  # sz_key -> (x, y) for labelling
    for f in feats:
        szk = geo.name_key(f.props.get("SUBZONE_N"))
        is_c1 = szk in c1_keys
        if is_c1:
            highlighted += 1
            _, cx, cy = geo.feature_area_centroid(f)
            centroids[szk] = (cx, cy)
        for poly in f.polygons:
            verts.append(poly[0])
            cols.append(HIGHLIGHT if is_c1 else OTHER)
            zords.append(2 if is_c1 else 1)

    # draw non-highlight first, highlight on top (so red edges aren't hidden)
    order = np.argsort(zords)
    verts = [verts[i] for i in order]
    cols = [cols[i] for i in order]

    fig, ax = plt.subplots(figsize=(12, 8))
    pc = PolyCollection(verts, facecolors=cols, edgecolors="white", linewidths=0.25)
    ax.add_collection(pc)
    ax.autoscale_view()
    ax.set_aspect("equal")
    ax.axis("off")

    # ---- subtle person-style markers on a few labelled C1 areas ----------
    # Simple circular person-style markers (NOT emoji). They mark "residents
    # potentially affected by low hawker accessibility", not elderly density.
    for k in label_keys:
        if k in centroids:
            cx, cy = centroids[k]
            ax.plot(cx, cy, marker="o", ms=7, mfc="white", mec="#5a0a05",
                    mew=1.6, zorder=6)
            ax.annotate(name_of.get(k, k.title()), (cx, cy),
                        textcoords="offset points", xytext=(7, 6),
                        fontsize=8.5, fontweight="bold", color="#5a0a05",
                        zorder=7,
                        bbox=dict(boxstyle="round,pad=0.15", fc="white",
                                  ec="#5a0a05", lw=0.6, alpha=0.85))

    # ---- titles & annotations -------------------------------------------
    fig.suptitle("Spatial Distribution of the Underserved Neighbourhood Profile",
                 fontsize=15, fontweight="bold", y=0.98)
    ax.set_title("Larger-flat / lower-elderly HDB areas (C1)", fontsize=11,
                 color="#444444", pad=8)

    handles = [
        Patch(facecolor=HIGHLIGHT, edgecolor="white", label="C1 - Underserved profile"),
        Patch(facecolor=OTHER, edgecolor="white", label="Other subzones"),
        plt.Line2D([0], [0], marker="o", color="none", mfc="white", mec="#5a0a05",
                   mew=1.6, ms=8, label="Residents potentially affected by low hawker access"),
    ]
    ax.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, -0.08),
              ncol=1, fontsize=9, frameon=False)

    fig.text(0.5, 0.055,
             "Population-weighted SPAR = 0.38 at the 1 km catchment "
             "(national average = 1.0)",
             ha="center", fontsize=9.5, style="italic", color="#333333")
    fig.text(0.5, 0.030, "71 subzones \u00b7 2.35M residents  |  "
             "revised pop\u2265500 K-means (Model C). Markers show the human/access "
             "dimension, not elderly concentration.",
             ha="center", fontsize=8.5, color="#666666")

    p = OUTDIR / "fig_underserved_map.png"
    fig.savefig(p, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)

    print(f"highlighted C1 subzones: {highlighted}")
    print(f"labelled subzones ({len(label_keys)}): "
          f"{[name_of.get(k, k) for k in label_keys]}")
    print(f"saved -> {p}")


if __name__ == "__main__":
    main()
