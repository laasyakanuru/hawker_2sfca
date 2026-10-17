"""
Q2 (resident view): If one critical centre closes, how far do its
residents have to walk to the nearest centre that is still open?

For each of the 10 most critical centres:
  1. Find residents (demand points) who live within 1 km of it
     AND have no other open centre within 1 km.
     -> these are the residents who "lose all access".
  2. For each of these residents, measure the distance from HOME
     to the nearest centre that is still open.
  3. Report the population-weighted average and median distance,
     and the share of these residents who must go more than 1.5 km / 2 km.
  4. Count how many of these residents are aged 65+.

Input : ../csv/dim_demand_point.csv     (where residents live, with population)
        ../csv/dim_hawker_centre.csv    (centre locations)
        ../csv/fact_hc_closure_impact.csv (list of open centres + pipeline numbers)
Output: q2_resident_distance.xlsx and q2_resident_distance.csv
        (saved in the same folder as this script)
"""

from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent


def find_data_dir(start):
    """Look in this folder and every folder above it for a 'csv' folder."""
    for folder in [start, *start.parents]:
        if (folder / "csv").is_dir():
            return folder / "csv"
    raise FileNotFoundError("Could not find a 'csv' folder above " + str(start))


DATA_DIR = find_data_dir(HERE)
print("Reading data from:", DATA_DIR)

CATCHMENT_M = 1000   # walking catchment used by the whole group
TOP_N = 10

# ---------- 1. Read the data ----------
dp = pd.read_csv(DATA_DIR / "dim_demand_point.csv")
hc = pd.read_csv(DATA_DIR / "dim_hawker_centre.csv")
impact = pd.read_csv(DATA_DIR / "fact_hc_closure_impact.csv")

# Residents: keep points with coordinates and people living there
dp = dp[(dp["has_coords"] == True) & (dp["population"] > 0)].copy()

# Open centres = the centres in the closure-impact table (same as the pipeline)
hc = hc.set_index("hc_key")
open_keys = [k for k in impact["hc_key"].unique() if k in hc.index]
open_hc = hc.loc[open_keys].dropna(subset=["x_svy21", "y_svy21"])
open_keys = list(open_hc.index)

# ---------- 2. Distance from every resident point to every open centre ----------
# SVY21 coordinates are in metres, so a straight-line distance is simple.
rx = dp["x_svy21"].to_numpy()[:, None]
ry = dp["y_svy21"].to_numpy()[:, None]
cx = open_hc["x_svy21"].to_numpy()[None, :]
cy = open_hc["y_svy21"].to_numpy()[None, :]
dist = np.sqrt((rx - cx) ** 2 + (ry - cy) ** 2)      # metres, rows = residents

pop = dp["population"].to_numpy()
pop65 = dp["pop_65plus"].fillna(0).to_numpy()
within = dist <= CATCHMENT_M
n_within = within.sum(axis=1)                         # open centres within 1 km


def weighted_median(values, weights):
    order = np.argsort(values)
    v, w = values[order], weights[order]
    cum = np.cumsum(w)
    return v[np.searchsorted(cum, cum[-1] / 2)]


# ---------- 3. The 10 most critical centres ----------
top = (impact.sort_values("pop_losing_all_access", ascending=False)
       .head(TOP_N)[["hc_key", "pop_losing_all_access"]])

rows = []
for _, r in top.iterrows():
    j = open_keys.index(r["hc_key"])
    # residents near this centre with NO other open centre within 1 km
    affected = within[:, j] & (n_within == 1)
    w = pop[affected]
    w65 = pop65[affected]

    # Distance from home to the 2nd nearest hawker centre (all centres open).
    # For these residents the closed centre is the only one within 1 km,
    # so it is always their nearest, and the 2nd nearest is where they
    # must go when it closes.
    d_aff = dist[affected]
    order = np.argsort(d_aff, axis=1)
    assert (order[:, 0] == j).all(), "closed centre should be the nearest"
    second_m = d_aff[np.arange(len(d_aff)), order[:, 1]]
    second_key = np.array(open_keys)[order[:, 1]]
    main_backup = pd.Series(w, index=second_key).groupby(level=0).sum().idxmax()

    rows.append({
        "centre": hc.loc[r["hc_key"], "hc_name"],
        "residents_losing_access_pipeline": round(r["pop_losing_all_access"]),
        "residents_losing_access_check": round(w.sum()),
        "elderly_65plus_losing_access": round(w65.sum()),
        "pct_65plus": round(100 * w65.sum() / w.sum(), 1),
        # 1. population-weighted average distance home -> 2nd nearest centre
        "avg_dist_2nd_nearest_km": round(np.average(second_m, weights=w) / 1000, 2),
        # 2. population-weighted median distance home -> 2nd nearest centre
        "median_dist_2nd_nearest_km": round(weighted_median(second_m, w) / 1000, 2),
        # 3. % of these residents whose 2nd nearest centre is > 1.5 km / > 2 km away
        "pct_2nd_nearest_over_1_5km": round(100 * w[second_m > 1500].sum() / w.sum(), 1),
        "pct_2nd_nearest_over_2km": round(100 * w[second_m > 2000].sum() / w.sum(), 1),
        "main_backup_centre": hc.loc[main_backup, "hc_name"],
    })

result = pd.DataFrame(rows)

# ---------- 4. Show and save ----------
pd.set_option("display.width", 250)
pd.set_option("display.max_colwidth", 40)
print("\n===== Q2: HOW FAR RESIDENTS MUST GO WHEN A CRITICAL CENTRE CLOSES =====")
print(result.to_string(index=False))

result.to_excel(HERE / "q2_resident_distance.xlsx", index=False)
result.to_csv(HERE / "q2_resident_distance.csv", index=False)
print(f"\nDone! Saved q2_resident_distance.xlsx and q2_resident_distance.csv in {HERE}")
