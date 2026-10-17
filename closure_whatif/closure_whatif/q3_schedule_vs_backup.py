"""
Q3: Could better scheduling fix the problem? And which closures need a backup?

Same method as Q2 (q2_resident_distance.py):
  - residents = demand points (dim_demand_point), weighted by population
  - open centres = the centres in fact_hc_closure_impact
  - distance = straight line from HOME to centre (SVY21, metres)
  - access = at least one open centre within 1 km

Part A - For every day in NEA's 2026 calendar, each resident who loses
access is put into one of two groups:
  - NO BACKUP           : only ONE centre within 1 km, and it closed
                          -> no schedule could have helped
  - BACKUP ALSO CLOSED  : two or more centres within 1 km, but ALL of
                          them closed on the same day
                          -> better scheduling could have helped

Part B - Short vs long closures:
  - SHORT : closure window of fewer than 7 days (quarterly cleaning, 1-5 days)
  - LONG  : closure window of 7 days or more (repairs and redecoration)
  A resident's lost day counts as LONG if at least one of their nearby
  centres was closed for long works that day.
  Elderly (65+) residents are counted separately.

Part C - One row per long closure in 2026: who loses access, how many are
  65+, and how far they must go to the 2nd nearest centre.

Input : ../csv/dim_demand_point.csv
        ../csv/dim_hawker_centre.csv
        ../csv/fact_hc_closure_impact.csv
        ../csv/fact_daily_access.csv
        ../csv/fact_hc_closure.csv
Output: q3_results.xlsx (Summary, ByLength, LongClosures, Worst10, Daily)
        q3_daily.csv    (for Power BI web)
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

CATCHMENT_M = 1000
LONG_DAYS = 7          # a closure window this long or longer counts as "long"
YEAR = 2026

# ---------- 1. Read the data (same as Q2) ----------
dp = pd.read_csv(DATA_DIR / "dim_demand_point.csv")
hc = pd.read_csv(DATA_DIR / "dim_hawker_centre.csv")
impact = pd.read_csv(DATA_DIR / "fact_hc_closure_impact.csv")
daily = pd.read_csv(DATA_DIR / "fact_daily_access.csv", parse_dates=["date"])
daily = daily.sort_values("date").reset_index(drop=True)
windows = pd.read_csv(DATA_DIR / "fact_hc_closure.csv", parse_dates=["start_date", "end_date"])

dp = dp[(dp["has_coords"] == True) & (dp["population"] > 0)].copy()

hc = hc.set_index("hc_key")
open_keys = [k for k in impact["hc_key"].unique() if k in hc.index]
open_hc = hc.loc[open_keys].dropna(subset=["x_svy21", "y_svy21"])
open_keys = list(open_hc.index)
col = {k: i for i, k in enumerate(open_keys)}

# ---------- 2. Which centres are within 1 km of each home? (same as Q2) ----------
dist = np.hypot(dp["x_svy21"].to_numpy()[:, None] - open_hc["x_svy21"].to_numpy()[None, :],
                dp["y_svy21"].to_numpy()[:, None] - open_hc["y_svy21"].to_numpy()[None, :])
within = dist <= CATCHMENT_M
n_within = within.sum(axis=1)
pop = dp["population"].to_numpy()
pop65 = dp["pop_65plus"].fillna(0).to_numpy()

# ---------- 3. Long closure windows in 2026 ----------
windows["duration_days"] = (windows["end_date"] - windows["start_date"]).dt.days + 1
long_w = windows[(windows["duration_days"] >= LONG_DAYS)
                 & (windows["end_date"].dt.year >= YEAR)
                 & (windows["start_date"].dt.year <= YEAR)
                 & (windows["hc_key"].isin(open_keys))].copy()


def long_closed_on(day):
    """Centres closed for LONG works on this day."""
    hit = long_w[(long_w["start_date"] <= day) & (long_w["end_date"] >= day)]
    return set(hit["hc_key"])


# ---------- 4. Part A + B: each day, who loses access, and why? ----------
cols_out = {c: [] for c in ["lost_no_backup", "lost_backup_also_closed",
                            "lost_short", "lost_long",
                            "lost_65_short", "lost_65_long"]}

for day, keys in zip(daily["date"], daily["closed_hc_keys"].fillna("")):
    closed = np.zeros(len(open_keys), dtype=bool)
    for k in keys.split(";"):
        if k in col:
            closed[col[k]] = True
    long_closed = np.zeros(len(open_keys), dtype=bool)
    for k in long_closed_on(day):
        long_closed[col[k]] = True

    # lost access = had a centre within 1 km, but none of them is open today
    lost = (n_within >= 1) & ~(within & ~closed).any(axis=1)
    is_long = (within & long_closed).any(axis=1)

    cols_out["lost_no_backup"].append(pop[lost & (n_within == 1)].sum())
    cols_out["lost_backup_also_closed"].append(pop[lost & (n_within >= 2)].sum())
    cols_out["lost_short"].append(pop[lost & ~is_long].sum())
    cols_out["lost_long"].append(pop[lost & is_long].sum())
    cols_out["lost_65_short"].append(pop65[lost & ~is_long].sum())
    cols_out["lost_65_long"].append(pop65[lost & is_long].sum())

for c, v in cols_out.items():
    daily[c] = np.round(v)
daily["lost_total"] = daily["lost_no_backup"] + daily["lost_backup_also_closed"]

# Check against the pipeline (same as Q1's extra_no_access)
base = daily.loc[daily["n_hc_closed"] == 0, "pop_no_access_all"].min()
daily["extra_no_access_pipeline"] = (daily["pop_no_access_all"] - base).round()
max_diff = (daily["lost_total"] - daily["extra_no_access_pipeline"]).abs().max()
print(f"Check vs pipeline: largest difference on any day = {max_diff:.0f} residents")

# ---------- 5. Summary (Part A) ----------
worst10 = daily.nlargest(10, "lost_total")


def share(g, column):
    return g[column].sum() / g["lost_total"].sum()


summary = pd.DataFrame({
    "metric": [
        "Worst 10 days: resident-days who lost access",
        "Worst 10 days: lost because their only centre closed (no backup)",
        "Worst 10 days: lost because their backup also closed",
        "Worst 10 days: % no backup",
        "Worst 10 days: % backup also closed (scheduling could help)",
        "Whole year: resident-days who lost access",
        "Whole year: % no backup",
        "Whole year: % backup also closed (scheduling could help)",
    ],
    "value": pd.Series([
        round(worst10["lost_total"].sum()),
        round(worst10["lost_no_backup"].sum()),
        round(worst10["lost_backup_also_closed"].sum()),
        f"{share(worst10, 'lost_no_backup'):.1%}",
        f"{share(worst10, 'lost_backup_also_closed'):.1%}",
        round(daily["lost_total"].sum()),
        f"{share(daily, 'lost_no_backup'):.1%}",
        f"{share(daily, 'lost_backup_also_closed'):.1%}",
    ], dtype=object),
})

# ---------- 6. Part B: short vs long closures (whole year) ----------
tot = daily["lost_total"].sum()
by_length = pd.DataFrame({
    "closure_length": [f"Short (< {LONG_DAYS} days, cleaning)",
                       f"Long (>= {LONG_DAYS} days, repairs)", "Total"],
    "resident_days_lost": [round(daily["lost_short"].sum()),
                           round(daily["lost_long"].sum()), round(tot)],
    "pct_of_resident_days": [round(100 * daily["lost_short"].sum() / tot, 1),
                             round(100 * daily["lost_long"].sum() / tot, 1), 100.0],
    "elderly_65plus_resident_days": [round(daily["lost_65_short"].sum()),
                                     round(daily["lost_65_long"].sum()),
                                     round(daily["lost_65_short"].sum() + daily["lost_65_long"].sum())],
})

# ---------- 7. Part C: one row per long closure ----------
rows = []
for _, w in long_w.sort_values("start_date").iterrows():
    j = col[w["hc_key"]]
    affected = within[:, j] & (n_within == 1)     # no other centre within 1 km
    a_pop, a_65 = pop[affected], pop65[affected]
    start = max(w["start_date"], pd.Timestamp(f"{YEAR}-01-01"))
    end = min(w["end_date"], pd.Timestamp(f"{YEAR}-12-31"))
    days_in_year = (end - start).days + 1
    if a_pop.sum() > 0:
        d_aff = dist[affected]
        second_m = np.sort(d_aff, axis=1)[:, 1]
        avg2 = round(np.average(second_m, weights=a_pop) / 1000, 2)
        over2 = round(100 * a_pop[second_m > 2000].sum() / a_pop.sum(), 1)
    else:
        avg2, over2 = np.nan, np.nan
    rows.append({
        "centre": hc.loc[w["hc_key"], "hc_name"],
        "start_date": w["start_date"].strftime("%Y-%m-%d"),
        "end_date": w["end_date"].strftime("%Y-%m-%d"),
        f"days_closed_in_{YEAR}": days_in_year,
        "residents_losing_access": round(a_pop.sum()),
        "elderly_65plus_losing_access": round(a_65.sum()),
        "avg_dist_2nd_nearest_km": avg2,
        "pct_2nd_nearest_over_2km": over2,
        "resident_days_lost": round(a_pop.sum() * days_in_year),
    })
long_table = pd.DataFrame(rows).sort_values("resident_days_lost", ascending=False)

# ---------- 8. Show and save ----------
pd.set_option("display.width", 250)
pd.set_option("display.max_colwidth", 40)
out_cols = ["date", "n_hc_closed", "lost_total", "lost_no_backup",
            "lost_backup_also_closed", "lost_short", "lost_long",
            "lost_65_short", "lost_65_long", "extra_no_access_pipeline"]
print("\n===== A. SUMMARY: SCHEDULING VS NO BACKUP =====")
print(summary.to_string(index=False))
print("\n===== B. SHORT VS LONG CLOSURES (WHOLE YEAR) =====")
print(by_length.to_string(index=False))
print(f"\n===== C. LONG CLOSURES IN {YEAR} =====")
print(long_table.to_string(index=False))

daily_out = daily[out_cols].copy()
daily_out["date"] = daily_out["date"].dt.strftime("%Y-%m-%d")
worst_out = worst10[out_cols].copy()
worst_out["date"] = worst_out["date"].dt.strftime("%Y-%m-%d")

with pd.ExcelWriter(HERE / "q3_results.xlsx") as writer:
    summary.to_excel(writer, sheet_name="Summary", index=False)
    by_length.to_excel(writer, sheet_name="ByLength", index=False)
    long_table.to_excel(writer, sheet_name="LongClosures", index=False)
    worst_out.to_excel(writer, sheet_name="Worst10", index=False)
    daily_out.to_excel(writer, sheet_name="Daily", index=False)
daily_out.to_csv(HERE / "q3_daily.csv", index=False)

print(f"\nDone! Saved q3_results.xlsx and q3_daily.csv in {HERE}")
