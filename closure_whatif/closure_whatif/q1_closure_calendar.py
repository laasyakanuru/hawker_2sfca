"""
Q1: What if NEA follows the 2026 closure calendar,
    how many residents are affected, and on which days is it worst?

This script ONLY does the calculations.
Charts are made in Power BI / Tableau so they match the group's format.

Input : ../csv/fact_daily_access.csv
Output: q1_results.xlsx (saved in the same folder as this script)
        - Summary : key numbers for the report
        - Top10   : the 10 worst days
        - Daily   : one row per day
        q1_daily.csv    (same daily table, for uploading to Power BI web)
"""

from pathlib import Path
import pandas as pd

# Folder layout:
#   ABD(GC)/csv/     <- all the CSV data files
#   ABD(GC)/whatif/  <- this script + the results it saves
HERE = Path(__file__).resolve().parent      # folder of this script (results are saved here)


def find_data_dir(start):
    """Look in this folder and every folder above it for a 'csv' folder."""
    for folder in [start, *start.parents]:
        if (folder / "csv").is_dir():
            return folder / "csv"
    raise FileNotFoundError("Could not find a 'csv' folder above " + str(start))


DATA_DIR = find_data_dir(HERE)              # e.g. ABD(GC)/csv
print("Reading data from:", DATA_DIR)

# ---------- 1. Read the data ----------
df = pd.read_csv(DATA_DIR / "fact_daily_access.csv", parse_dates=["date"])
df = df.sort_values("date").reset_index(drop=True)

# ---------- 2. Find the baseline (a day with no closures) ----------
no_closure_days = df[df["n_hc_closed"] == 0]
base_no_access = no_closure_days["pop_no_access_all"].min()

# ---------- 3. Add the two new columns ----------
# Extra residents with no centre within 1 km, caused by closures
df["extra_no_access"] = (df["pop_no_access_all"] - base_no_access).round()
# Note: no "% drop in access" here. That needs the group's 2SFCA method,
# but fact_daily_access was computed with e2sfca_gauss, so we report
# people counts only (these do not depend on the method).

# ---------- 4. Summary numbers ----------
worst = df.loc[df["extra_no_access"].idxmax()]
summary = pd.DataFrame(
    {
        "metric": [
            "Baseline people with no access (all centres open)",
            "Total person-days lost in 2026",
            "Average extra people affected per day",
            "Worst day: date",
            "Worst day: extra people affected",
            "Worst day: centres closed",
            "Days with 20+ centres closed",
            "Days with no closures",
        ],
        "value": [
            round(base_no_access),
            round(df["extra_no_access"].sum()),
            round(df["extra_no_access"].mean()),
            worst["date"].strftime("%Y-%m-%d"),
            round(worst["extra_no_access"]),
            int(worst["n_hc_closed"]),
            int((df["n_hc_closed"] >= 20).sum()),
            int((df["n_hc_closed"] == 0).sum()),
        ],
    }
)

# ---------- 5. Top 10 worst days ----------
top10 = (
    df.sort_values("extra_no_access", ascending=False)
    .head(10)[["date", "n_hc_closed", "stalls_closed", "extra_no_access",
               "closed_hc_keys"]]
)

# ---------- 6. Show results on screen ----------
print("\n===== SUMMARY =====")
print(summary.to_string(index=False))
print("\n===== TOP 10 WORST DAYS =====")
print(top10.to_string(index=False))

# ---------- 7. Save to Excel (for Power BI / Tableau) ----------
daily_cols = ["date", "n_hc_closed", "stalls_closed", "closed_hc_keys",
              "pop_no_access_all", "extra_no_access",
              ]
with pd.ExcelWriter(HERE / "q1_results.xlsx") as writer:
    summary.to_excel(writer, sheet_name="Summary", index=False)
    top10.to_excel(writer, sheet_name="Top10", index=False)
    df[daily_cols].to_excel(writer, sheet_name="Daily", index=False)

# ---------- 8. Save the daily table as CSV (for Power BI web upload) ----------
daily_out = df[daily_cols].copy()
daily_out["date"] = daily_out["date"].dt.strftime("%Y-%m-%d")
daily_out.to_csv(HERE / "q1_daily.csv", index=False)

print(f"\nDone! Saved q1_results.xlsx and q1_daily.csv in {HERE}")
