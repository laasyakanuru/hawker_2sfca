"""
Build the SUBZONE-level clustering feature table (main K-means input).

Research question: "Which types of neighbourhoods are more vulnerable to
hawker service gaps?"

Methodology:
  * Unit of analysis = subzone (sz_key). One row per subzone.
  * Only subzones with resident_pop >= MIN_RESIDENT_POP are kept. Very small
    subzones produce unstable percentage-based features and do not represent
    meaningful neighbourhood profiles, so they are dropped BEFORE feature
    engineering.
  * Features describe NEIGHBOURHOOD STRUCTURE + DEMOGRAPHICS only.
  * Access outcomes (access_per_1000, spar, pct_pop_no_access,
    stall_deficit_vs_national), closure impact and INCOME are deliberately
    EXCLUDED from the feature set. Income is PA-level only, so it is kept as a
    post-cluster context/limitation variable, not a clustering input.

Input : data/processed/fact_subzone_population.csv
Output: data/processed/clustering/legacy_pop1000/subzone_clustering_features.csv
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

# Minimum resident population for a subzone to be clustered. Below this, the
# share-based features are statistically unstable (small denominators).
MIN_RESIDENT_POP = 1000

# Features used as K-means clustering inputs (in display order)
FEATURES = [
    "hdb_share",            # pop_hdb / resident_pop
    "condo_share",          # Dwelling_Condo_Apartment / resident_pop
    "landed_share",         # Dwelling_Landed / resident_pop
    "hdb_small_flat_share",  # (Dwelling_1_2_Room + Dwelling_3_Room) / pop_hdb
    "pct_elderly",          # Pct_Age_65plus
    "pct_young",            # Age_0_19 / resident_pop
    "pct_small_floor_area",  # Pct_FloorArea_60_or_less
]


def build() -> tuple[pd.DataFrame, dict]:
    pop = pd.read_csv(config.PROCESSED / "fact_subzone_population.csv")

    # 1) Population filter (applied BEFORE any feature engineering).
    #    Baseline = subzones with any residents; then drop the very small ones.
    before = pop[pop["resident_pop"] > 0].copy()
    df = before[before["resident_pop"] >= MIN_RESIDENT_POP].copy().reset_index(drop=True)
    counts = {
        "before": len(before),            # subzones with resident_pop > 0
        "removed": len(before) - len(df),  # dropped by the >= 1000 filter
        "final": len(df),
    }
    rp = df["resident_pop"]

    # 2A) Housing structure (shares of resident population)
    df["hdb_share"] = df["pop_hdb"] / rp
    df["condo_share"] = df["Dwelling_Condo_Apartment"] / rp
    df["landed_share"] = df["Dwelling_Landed"] / rp

    # hdb_small_flat_share: share of HDB residents in 1-2R or 3R flats.
    # Denominator is pop_hdb, which is 0 for non-HDB subzones -> define as 0
    # (a subzone with no HDB residents has, by definition, no small-flat share).
    small = df["Dwelling_1_2_Room"] + df["Dwelling_3_Room"]
    df["hdb_small_flat_share"] = np.where(df["pop_hdb"] > 0, small / df["pop_hdb"], 0.0)

    # 2B) Demographic
    # Pct_Age_65plus is stored as a percentage (e.g. 19.42). Convert to a share
    # so all features live on a comparable 0-1 scale before standardisation.
    df["pct_elderly"] = df["Pct_Age_65plus"] / 100.0
    df["pct_young"] = df["Age_0_19"] / rp

    # 2C) Housing-condition proxy. Pct_FloorArea_60_or_less is also a percentage.
    df["pct_small_floor_area"] = df["Pct_FloorArea_60_or_less"] / 100.0

    # 3) Final cleaning: clip every share-based feature to [0, 1]. The only
    #    values that fall outside are tiny DOS-rounding artefacts (e.g.
    #    hdb_share = 1.0025 when pop_hdb is rounded above resident_pop); clipping
    #    removes them without affecting any genuine value.
    n_clipped = int(((df[FEATURES] < 0) | (df[FEATURES] > 1)).sum().sum())
    df[FEATURES] = df[FEATURES].clip(lower=0.0, upper=1.0)
    counts["clipped_values"] = n_clipped

    cols = ["sz_key", "pa_key", "resident_pop", "pop_hdb"] + FEATURES
    return df[cols], counts


def validate(df: pd.DataFrame, counts: dict) -> None:
    pd.set_option("display.width", 160)
    pd.set_option("display.max_columns", 50)

    print("=" * 72)
    print("SUBZONE CLUSTERING FEATURE TABLE - VALIDATION")
    print("=" * 72)

    print("\n[1] Final column names:")
    for c in df.columns:
        tag = "  <- clustering feature" if c in FEATURES else ""
        print(f"    - {c}{tag}")

    print(f"\n[2] Population filter (resident_pop >= {MIN_RESIDENT_POP}):")
    print(f"    Subzones before filtering (resident_pop > 0): {counts['before']}")
    print(f"    Subzones removed (resident_pop < {MIN_RESIDENT_POP})     : {counts['removed']}")
    print(f"    Final number of subzones                   : {counts['final']}")
    print(f"    Unique sz_key                              : {df['sz_key'].nunique()}")
    print(f"    sz_key is unique                           : {df['sz_key'].is_unique}")
    print(f"    Feature values clipped to [0,1]            : {counts.get('clipped_values', 0)}")

    print("\n[3] Missing values per feature:")
    miss = df[FEATURES].isna().sum()
    for f in FEATURES:
        print(f"    {f:<22} {int(miss[f])}")
    print(f"    rows with any NaN in features: {int(df[FEATURES].isna().any(axis=1).sum())}")

    print("\n[4] Summary statistics (clustering features):")
    print(df[FEATURES].describe().round(4).to_string())

    # Sanity note: how many non-HDB subzones got hdb_small_flat_share = 0
    n_zero_hdb = int((df["pop_hdb"] == 0).sum())
    print(f"\n    note: {n_zero_hdb} subzones have no HDB residents "
          f"-> hdb_small_flat_share set to 0 for those.")


def main() -> None:
    df, counts = build()
    validate(df, counts)
    out = config.CLUSTERING_LEGACY / "subzone_clustering_features.csv"
    df.to_csv(out, index=False)
    print(f"\nSaved -> {out}  ({len(df)} rows, {len(df.columns)} columns)")


if __name__ == "__main__":
    main()
