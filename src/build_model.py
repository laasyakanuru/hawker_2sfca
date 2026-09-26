"""
Step E - Publish the keyed data model.

Copies the conformed dimensions into processed/, writes a table-level data
dictionary (data_dictionary.csv), a column-level one with definitions, units and a
quick profile (data_dictionary_columns.csv, text in column_definitions.py) and
packs every processed table into one SQLite file (hawker_2sfca.sqlite) for Python,
DBeaver or DB Browser (Tableau / Power BI need an SQLite ODBC driver - or use the CSVs).
"""
from __future__ import annotations

import sqlite3

import pandas as pd

import config
from column_definitions import describe

DIMENSIONS = {
    "dim_planning_area": "pa_key",
    "dim_subzone": "sz_key",
    "dim_hawker_centre": "hc_key",
    "dim_hdb_block": "block_id",
    "dim_mrt_station": "stn_key",
}
FACTS_INTERIM = ["fact_hc_closure", "fact_subzone_population", "fact_subzone_population_dwelling",
                 "fact_pa_household_income", "fact_mrt_hourly"]

# table -> (grain, primary key, foreign keys)
DICTIONARY = {
    "dim_planning_area": ("1 row per URA planning area", "pa_key", "-"),
    "dim_subzone": ("1 row per MP2019 subzone", "sz_key", "pa_key"),
    "dim_hawker_centre": ("1 row per hawker centre (NEA 02 + 01 matched)", "hc_key", "sz_key, pa_key"),
    "dim_hdb_block": ("1 row per HDB block (06)", "block_id", "sz_key"),
    "dim_mrt_station": ("1 row per MRT/LRT station code", "stn_key", "sz_key"),
    "dim_demand_point": ("1 row per demand point (HDB block / condo / landed / centroid)", "dp_key", "sz_key, pa_key"),
    "fact_hc_closure": ("1 row per closure window", "closure_id", "hc_key"),
    "fact_subzone_population": ("1 row per subzone (census wide)", "sz_key", "pa_key"),
    "fact_subzone_population_dwelling": ("subzone x census dwelling column", "sz_key+census_column", "sz_key, pa_key"),
    "fact_pa_household_income": ("planning area x income band (2020)", "pa_key+income_band", "pa_key"),
    "fact_mrt_hourly": ("station x day type x hour", "stn_key+day_type+hour", "stn_key"),
    "fact_demand_proximity": ("1 row per demand point", "dp_key", "dp_key, nearest_hc_key->hc_key"),
    "fact_access_point": ("demand point x scenario x method x catchment", "dp_key+scenario+method+catchment_m", "dp_key"),
    "fact_supply_ratio": ("hawker centre x scenario x method x catchment", "hc_key+scenario+method+catchment_m", "hc_key"),
    "agg_access_subzone": ("subzone x dwelling type x scenario x method x catchment", "sz_key+dwelling_type+scenario+method+catchment_m", "sz_key"),
    "agg_access_planning_area": ("planning area x dwelling type x scenario x method x catchment", "pa_key+dwelling_type+scenario+method+catchment_m", "pa_key"),
    "fact_hc_closure_impact": ("1 row per open hawker centre (leave-one-out)", "hc_key", "hc_key"),
    "fact_daily_access": ("1 row per day of analysis year", "date", "-"),
    "agg_daily_access_subzone": ("day x subzone", "date+sz_key", "sz_key"),
    "qa_population_conservation": ("subzone x dwelling type: census vs allocated", "sz_key+dwelling_type", "sz_key"),
}


def main():
    for name, pk in DIMENSIONS.items():
        df = pd.read_csv(config.INTERIM / f"{name}.csv", low_memory=False)
        assert df[pk].is_unique, f"{name}.{pk} not unique"
        df.to_csv(config.PROCESSED / f"{name}.csv", index=False)
    for name in FACTS_INTERIM:
        pd.read_csv(config.INTERIM / f"{name}.csv", low_memory=False).to_csv(
            config.PROCESSED / f"{name}.csv", index=False)

    # referential-integrity checks (report, don't fail)
    sz = set(pd.read_csv(config.PROCESSED / "dim_subzone.csv")["sz_key"])
    checks = []
    for t in ["dim_demand_point", "dim_hawker_centre", "dim_hdb_block", "dim_mrt_station"]:
        p = config.PROCESSED / f"{t}.csv"
        if p.exists():
            k = pd.read_csv(p, usecols=["sz_key"], low_memory=False)["sz_key"].dropna()
            checks.append({"table": t, "fk": "sz_key", "rows_with_fk": len(k), "orphans": int((~k.isin(sz)).sum())})
    ri = pd.DataFrame(checks)
    ri.to_csv(config.PROCESSED / "qa_referential_integrity.csv", index=False)
    print(ri.to_string(index=False))

    # data dictionary (tables + columns)
    rows = []
    for t, (grain, pk, fk) in DICTIONARY.items():
        p = config.PROCESSED / f"{t}.csv"
        if not p.exists():
            continue
        cols = pd.read_csv(p, nrows=5).columns
        rows.append({"table": t, "grain": grain, "primary_key": pk, "foreign_keys": fk,
                     "n_columns": len(cols), "columns": ", ".join(cols)})
    pd.DataFrame(rows).to_csv(config.PROCESSED / "data_dictionary.csv", index=False)

    # column-level dictionary: definition, unit + a quick profile from the real data
    col_rows, undefined = [], []
    for t in list(DICTIONARY) + ["qa_referential_integrity", "data_dictionary"]:
        p = config.PROCESSED / f"{t}.csv"
        if not p.exists():
            continue
        df = pd.read_csv(p, low_memory=False)
        for c in df.columns:
            desc, unit = describe(t, c)
            if desc is None:
                undefined.append(f"{t}.{c}")
            s = df[c].dropna()
            col_rows.append({"table": t, "column": c, "description": desc or "(no definition yet)",
                             "unit": unit, "dtype": str(df[c].dtype),
                             "pct_null": round(100 * (1 - len(s) / max(len(df), 1)), 1),
                             "n_distinct": int(s.nunique()),
                             "example": str(s.iloc[0])[:60] if len(s) else None})
    pd.DataFrame(col_rows).to_csv(config.PROCESSED / "data_dictionary_columns.csv", index=False)
    print(f"data_dictionary_columns.csv: {len(col_rows)} columns described")
    if undefined:
        print("  !! add definitions in column_definitions.py for:", ", ".join(undefined))

    db = config.PROCESSED / "hawker_2sfca.sqlite"
    db.unlink(missing_ok=True)
    with sqlite3.connect(db) as con:
        for t in list(DICTIONARY) + ["qa_referential_integrity", "data_dictionary", "data_dictionary_columns"]:
            p = config.PROCESSED / f"{t}.csv"
            if p.exists():
                pd.read_csv(p, low_memory=False).to_sql(t, con, index=False)
        for t, (_, pk, _) in DICTIONARY.items():
            if (config.PROCESSED / f"{t}.csv").exists():
                cols = pk.replace("+", ", ")
                con.execute(f'CREATE INDEX IF NOT EXISTS ix_{t} ON {t} ({cols})')
    print(f"SQLite model written: {db} ({db.stat().st_size/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
