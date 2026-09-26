"""
Step B2 - Demand side at subzone level + planning-area context.

Inputs : raw/Resident_Population_Final_version.xlsx  (subzone x age / dwelling / floor area)
         raw/08_ResidentHouseholdsbyPlanningAreaofResidence_2020EDA.xlsx (PA x income band)
         external/mp2019_subzone_boundary.geojson (optional: codes, centroids, area)
Outputs: interim/dim_planning_area.csv
         interim/dim_subzone.csv
         interim/fact_subzone_population.csv          (wide, cleaned)
         interim/fact_subzone_population_dwelling.csv (long: sz_key x dwelling_group)
         interim/fact_pa_household_income.csv         (long: pa_key x income band)
"""
from __future__ import annotations

import difflib

import numpy as np
import pandas as pd

import config
from geo import feature_area_centroid, name_key, read_geojson, svy21_to_latlon

# census dwelling column -> (dwelling_group, dwelling_type)
DWELLING_MAP = {
    "Dwelling_1_2_Room": ("HDB_1_2R", "HDB"),
    "Dwelling_3_Room": ("HDB_3R", "HDB"),
    "Dwelling_4_Room": ("HDB_4R", "HDB"),
    "Dwelling_5Room_Executive": ("HDB_5R_EX", "HDB"),
    "Dwelling_Condo_Apartment": ("CONDO", "CONDO"),
    "Dwelling_Landed": ("LANDED", "LANDED"),
    "Dwelling_Others": ("OTHER", "OTHER"),
}

INCOME_BANDS = ["NoEmployedPerson", "Below_1_000", "1_000_1_999", "2_000_2_999", "3_000_3_999",
                "4_000_4_999", "5_000_5_999", "6_000_6_999", "7_000_7_999", "8_000_8_999",
                "9_000_9_999", "10_000_10_999", "11_000_11_999", "12_000_12_999", "13_000_13_999",
                "14_000_14_999", "15_000_17_499", "17_500_19_999", "20_000andOver"]
# band lower / upper bounds in SGD per month (for approximate median)
BAND_BOUNDS = [(0, 0), (0, 1000), (1000, 2000), (2000, 3000), (3000, 4000), (4000, 5000),
               (5000, 6000), (6000, 7000), (7000, 8000), (8000, 9000), (9000, 10000),
               (10000, 11000), (11000, 12000), (12000, 13000), (13000, 14000), (14000, 15000),
               (15000, 17500), (17500, 20000), (20000, 30000)]

REGION_OF_PA = {  # URA regions (used when boundary file is not yet downloaded)
    "CENTRAL REGION": ["BISHAN", "BUKIT MERAH", "BUKIT TIMAH", "DOWNTOWN CORE", "GEYLANG", "KALLANG",
                       "MARINA EAST", "MARINA SOUTH", "MARINE PARADE", "MUSEUM", "NEWTON", "NOVENA",
                       "ORCHARD", "OUTRAM", "QUEENSTOWN", "RIVER VALLEY", "ROCHOR", "SINGAPORE RIVER",
                       "SOUTHERN ISLANDS", "STRAITS VIEW", "TANGLIN", "TOA PAYOH"],
    "EAST REGION": ["BEDOK", "CHANGI", "CHANGI BAY", "PASIR RIS", "PAYA LEBAR", "TAMPINES"],
    "NORTH REGION": ["CENTRAL WATER CATCHMENT", "LIM CHU KANG", "MANDAI", "SEMBAWANG", "SIMPANG",
                     "SUNGEI KADUT", "WOODLANDS", "YISHUN"],
    "NORTH-EAST REGION": ["ANG MO KIO", "HOUGANG", "NORTH-EASTERN ISLANDS", "PUNGGOL", "SELETAR",
                          "SENGKANG", "SERANGOON"],
    "WEST REGION": ["BOON LAY", "BUKIT BATOK", "BUKIT PANJANG", "CHOA CHU KANG", "CLEMENTI",
                    "JURONG EAST", "JURONG WEST", "PIONEER", "TENGAH", "TUAS", "WESTERN ISLANDS",
                    "WESTERN WATER CATCHMENT"],
}
PA_TO_REGION = {name_key(pa): r for r, pas in REGION_OF_PA.items() for pa in pas}


def load_population() -> pd.DataFrame:
    p = pd.read_excel(config.RAW_FILES["population"])
    p = p.rename(columns={"Planning Area": "planning_area", "Subzone": "subzone",
                          "Resident Population": "resident_pop"})
    p["pa_key"] = p["planning_area"].map(name_key)
    p["sz_key"] = p["subzone"].map(name_key)
    dw = list(DWELLING_MAP)
    p["qa_dwelling_minus_total"] = p[dw].sum(axis=1) - p["resident_pop"]  # DOS rounds to nearest 10
    p["pop_hdb"] = p[dw[:4]].sum(axis=1)
    return p


def subzone_geometry():
    """Return DataFrame of MP2019 subzones (code, area, centroid) or None if not fetched."""
    path = config.EXTERNAL_FILES["subzone_geojson"]
    if not path.exists():
        print("  (subzone boundaries not downloaded yet - run fetch_datagov.py; codes/centroids left blank)")
        return None, None
    feats = read_geojson(path)
    rows = []
    for f in feats:
        a, cx, cy = feature_area_centroid(f)
        rows.append({"sz_key": name_key(f.props.get("SUBZONE_N")), "sz_code": f.props.get("SUBZONE_C"),
                     "pa_key_geo": name_key(f.props.get("PLN_AREA_N")), "pa_code": f.props.get("PLN_AREA_C"),
                     "region_geo": f.props.get("REGION_N"), "area_km2": a / 1e6,
                     "centroid_x": cx, "centroid_y": cy})
        f.props["sz_key"] = rows[-1]["sz_key"]
    g = pd.DataFrame(rows)
    g["centroid_lat"], g["centroid_lon"] = svy21_to_latlon(g["centroid_x"], g["centroid_y"])
    return g, feats


def reconcile_names(pop_keys, geo_keys):
    """Map census subzone keys to boundary keys: exact, then fuzzy (>=0.85)."""
    geo_set = set(geo_keys)
    mapping, report = {}, []
    for k in pop_keys:
        if k in geo_set:
            mapping[k] = k
            continue
        cand = difflib.get_close_matches(k, geo_keys, n=1, cutoff=0.85)
        mapping[k] = cand[0] if cand else None
        report.append({"census_sz_key": k, "boundary_sz_key": mapping[k]})
    return mapping, pd.DataFrame(report)


def main():
    p = load_population()
    g, _ = subzone_geometry()

    # ---- dim_subzone ----------------------------------------------------
    sz = p[["sz_key", "subzone", "pa_key", "planning_area"]].copy()
    if g is not None:
        mapping, rep = reconcile_names(sz["sz_key"].tolist(), g["sz_key"].tolist())
        if len(rep):
            rep.to_csv(config.INTERIM / "qa_subzone_name_reconcile.csv", index=False)
            print(f"  {len(rep)} subzone names needed fuzzy reconcile (see qa_subzone_name_reconcile.csv)")
        sz["sz_key_geo"] = sz["sz_key"].map(mapping)
        sz = sz.merge(g.rename(columns={"sz_key": "sz_key_geo"}), on="sz_key_geo", how="left")
    else:
        for col in ["sz_key_geo", "sz_code", "pa_code", "region_geo", "area_km2",
                    "centroid_x", "centroid_y", "centroid_lat", "centroid_lon"]:
            sz[col] = np.nan
    sz["region"] = sz["pa_key"].map(PA_TO_REGION)
    sz.to_csv(config.INTERIM / "dim_subzone.csv", index=False)

    # ---- dim_planning_area ---------------------------------------------
    pa = p.groupby(["pa_key", "planning_area"], as_index=False)["resident_pop"].sum()
    pa["region"] = pa["pa_key"].map(PA_TO_REGION)
    pa["n_subzones"] = p.groupby("pa_key")["sz_key"].nunique().reindex(pa["pa_key"]).values

    # ---- household income (PA level, 2020) -----------------------------
    inc = pd.read_excel(config.RAW_FILES["hh_income"], sheet_name=0)
    inc = inc.rename(columns={"Planning Area": "planning_area_income", "Total": "households_2020"})
    inc = inc[inc["households_2020"].notna()]  # drop blank / title rows
    inc = inc[inc["planning_area_income"].str.strip().str.lower() != "total"].copy()
    inc["pa_key"] = inc["planning_area_income"].map(name_key)
    # NB: DOS 2020 groups small PAs into 'Others' (kept in the long table; no PA join)
    hh = inc[INCOME_BANDS].to_numpy(float)
    tot = hh.sum(1)
    inc["pct_hh_no_employed"] = hh[:, 0] / tot * 100
    inc["pct_hh_below_3k"] = hh[:, :4].sum(1) / tot * 100  # incl. no employed person
    inc["pct_hh_20k_plus"] = hh[:, -1] / tot * 100
    # grouped-data median (linear interpolation within the median band)
    med = []
    for row in hh:
        cum, half = np.cumsum(row), row.sum() / 2
        k = int(np.searchsorted(cum, half))
        lo, hi = BAND_BOUNDS[k]
        prev = cum[k - 1] if k else 0
        med.append(lo + (hi - lo) * (half - prev) / row[k] if row[k] else lo)
    inc["median_hh_income_approx"] = np.round(med, 0)
    pa = pa.merge(inc[["pa_key", "households_2020", "pct_hh_no_employed", "pct_hh_below_3k",
                       "pct_hh_20k_plus", "median_hh_income_approx"]], on="pa_key", how="left")
    missing_inc = sorted(set(inc["pa_key"]) - set(pa["pa_key"]))
    if missing_inc:
        print("  income PAs not in population file:", missing_inc)
    pa.to_csv(config.INTERIM / "dim_planning_area.csv", index=False)

    inc_long = inc.melt(id_vars=["pa_key"], value_vars=INCOME_BANDS, var_name="income_band",
                        value_name="households")
    inc_long["band_order"] = inc_long["income_band"].map({b: i for i, b in enumerate(INCOME_BANDS)})
    inc_long.to_csv(config.INTERIM / "fact_pa_household_income.csv", index=False)

    # ---- population facts ----------------------------------------------
    keep = ["sz_key", "pa_key", "resident_pop", "Age_0_19", "Age_20_64", "Age_65plus",
            "Pct_Age_65plus", "pop_hdb"] + list(DWELLING_MAP) + \
           [c for c in p.columns if c.startswith("FloorArea") or c.startswith("Pct_FloorArea")] + \
           ["qa_dwelling_minus_total"]
    p[keep].to_csv(config.INTERIM / "fact_subzone_population.csv", index=False)

    long = p.melt(id_vars=["sz_key", "pa_key"], value_vars=list(DWELLING_MAP),
                  var_name="census_column", value_name="population")
    long["dwelling_group"] = long["census_column"].map(lambda c: DWELLING_MAP[c][0])
    long["dwelling_type"] = long["census_column"].map(lambda c: DWELLING_MAP[c][1])
    long.to_csv(config.INTERIM / "fact_subzone_population_dwelling.csv", index=False)

    print(f"dim_subzone: {len(sz)} | dim_planning_area: {len(pa)} | residents: {p.resident_pop.sum():,}")
    print(long.groupby("dwelling_type")["population"].sum().to_string())


if __name__ == "__main__":
    main()
