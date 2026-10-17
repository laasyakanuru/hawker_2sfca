# Closure what-if analysis

What if nearby hawker centres never closed on the same day?

This folder replays NEA's 2026 hawker centre closure calendar day by day for every home in Singapore. For each day, it checks whether each home still has an open hawker centre within 1 km (straight line). It then separates two cases:

- **No backup**: the home has only one centre within 1 km, and it closed.
- **Backup also closed**: the home has two or more centres within 1 km, and all of them were closed at the same time. This is the part that better scheduling could avoid.

Owner: Zhang Leyi (report section 9.6, slides 18 to 21).

## Scripts

Run them in this order. Each one is standalone and writes its outputs next to itself.

| Script | Question it answers | Outputs |
| --- | --- | --- |
| `q1_closure_calendar.py` | How does access change day by day through the 2026 calendar? | `q1_results.xlsx`, `q1_daily.csv` |
| `q2_resident_distance.py` | Which centres leave the most residents with no other centre within 1 km, and how far is their next one? | `q2_resident_distance.xlsx`, `q2_resident_distance.csv` |
| `q3_schedule_vs_backup.py` | How much lost access is "no backup" vs "backup also closed"? Short vs long closures? | `q3_results.xlsx`, `q3_daily.csv` |
| `q3_pair_clashes.py` | Which pairs of centres closed on the same day, and for how many residents? | `q3_pairs.xlsx`, `q3_pairs.csv`, pair maps |

## Data

The scripts look for a folder named `csv` in their own folder or any folder above it, and read:

- `dim_demand_point.csv` (homes and residents)
- `dim_hawker_centre.csv` (centre locations)
- `fact_hc_closure_impact.csv` (open centres and pipeline results)
- `fact_hc_closure.csv` (2026 closure windows)
- `fact_daily_access.csv` (daily access from the pipeline, used by Q1)
- `sg_3-subzone.geojson`, `sg_2-planning-area.geojson` (map outlines, used by `q3_pair_clashes.py`)

These tables come from the main pipeline in this repo. They are not copied here.

## Setup

```bash
pip install pandas numpy openpyxl matplotlib
python q3_schedule_vs_backup.py
```

## Key results (2026)

- 120,013 residents lost their nearby hawker centre at least once because two nearby centres closed on the same day.
- On the 10 worst days, 4.4% of lost access was avoidable by scheduling (2.4% across the whole year).
- 70% of affected residents were hit in 5 weeks; 5 centre pairs account for 43%.

## Folder

```
closure_whatif/
├── q1_closure_calendar.py
├── q2_resident_distance.py
├── q3_schedule_vs_backup.py
├── q3_pair_clashes.py
└── outputs/
    ├── q1_daily.csv
    ├── q2_resident_distance.csv
    ├── q3_pairs.csv
    └── figures/   (pair maps and the Singapore overview map)
```
