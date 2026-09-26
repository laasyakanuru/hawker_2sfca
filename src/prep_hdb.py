"""
Step B3 - HDB blocks: keys, unit groups aligned to census dwelling groups,
coordinates (from OneMap cache) and subzone assignment.

Inputs : raw/06_HDBPropertyInformation.csv
         external/onemap_hdb_geocode_cache.csv         (from fetch_onemap.py hdb)
         external/mp2019_subzone_boundary.geojson      (from fetch_datagov.py)
Output : interim/dim_hdb_block.csv
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config
from geo import assign_points_to_features, latlon_to_svy21, name_key, read_geojson
from keys import hdb_block_id

HDB_TOWN = {"AMK": "ANG MO KIO", "BB": "BUKIT BATOK", "BD": "BEDOK", "BH": "BISHAN", "BM": "BUKIT MERAH",
            "BP": "BUKIT PANJANG", "BT": "BUKIT TIMAH", "CCK": "CHOA CHU KANG", "CL": "CLEMENTI",
            "CT": "CENTRAL AREA", "GL": "GEYLANG", "HG": "HOUGANG", "JE": "JURONG EAST",
            "JW": "JURONG WEST", "KWN": "KALLANG/WHAMPOA", "MP": "MARINE PARADE", "PG": "PUNGGOL",
            "PRC": "PASIR RIS", "QT": "QUEENSTOWN", "SB": "SEMBAWANG", "SGN": "SERANGOON",
            "SK": "SENGKANG", "TAP": "TAMPINES", "TG": "TENGAH", "TP": "TOA PAYOH",
            "WL": "WOODLANDS", "YS": "YISHUN"}

# HDB unit columns -> census dwelling group (must match prep_population.DWELLING_MAP)
UNIT_GROUPS = {
    "HDB_1_2R": ["1room_sold", "2room_sold", "studio_apartment_sold", "1room_rental", "2room_rental",
                 "other_room_rental"],
    "HDB_3R": ["3room_sold", "3room_rental"],
    "HDB_4R": ["4room_sold"],
    "HDB_5R_EX": ["5room_sold", "exec_sold", "multigen_sold"],
}


def main():
    h = pd.read_csv(config.RAW_FILES["hdb_property"], dtype={"blk_no": str})
    h["block_id"] = hdb_block_id(h["blk_no"], h["street"])
    assert h["block_id"].is_unique, "block_id must be unique"
    h["hdb_town"] = h["bldg_contract_town"].map(HDB_TOWN)
    for g, cols in UNIT_GROUPS.items():
        h[f"units_{g}"] = h[cols].sum(axis=1)
    ucols = [f"units_{g}" for g in UNIT_GROUPS]
    h["qa_units_minus_total"] = h[ucols].sum(axis=1) - h["total_dwelling_units"]
    for c in ["residential", "commercial", "market_hawker", "miscellaneous", "multistorey_carpark",
              "precinct_pavilion"]:
        h[c] = h[c].eq("Y")

    # ---- coordinates ----------------------------------------------------
    cache = config.EXTERNAL_FILES["hdb_geocode_cache"]
    if cache.exists():
        g = pd.read_csv(cache, dtype={"postal_code": str})
        g = g.drop_duplicates("block_id", keep="last")
        h = h.merge(g[["block_id", "status", "postal_code", "x_svy21", "y_svy21", "lat", "lon",
                       "onemap_road"]].rename(columns={"status": "geocode_status"}),
                    on="block_id", how="left")
        # trust lat/lon; recompute SVY21 so every table uses the same projection code
        ok = h["lat"].notna()
        h.loc[ok, "x_svy21"], h.loc[ok, "y_svy21"] = latlon_to_svy21(h.loc[ok, "lat"], h.loc[ok, "lon"])
        h["geocode_status"] = h["geocode_status"].fillna("not_attempted")
    else:
        print("  (no OneMap cache yet - run: python src/fetch_onemap.py hdb)")
        for c in ["geocode_status", "postal_code", "x_svy21", "y_svy21", "lat", "lon", "onemap_road"]:
            h[c] = np.nan
        h["geocode_status"] = "not_attempted"

    # ---- subzone assignment --------------------------------------------
    h["sz_key"] = None
    h["sz_assign_method"] = None
    sz_path = config.EXTERNAL_FILES["subzone_geojson"]
    ok = h["x_svy21"].notna()
    if sz_path.exists() and ok.any():
        feats = read_geojson(sz_path)
        for f in feats:
            f.props["sz_key"] = name_key(f.props.get("SUBZONE_N"))
        xy = h.loc[ok, ["x_svy21", "y_svy21"]].to_numpy(float)
        lab, meth = assign_points_to_features(xy, feats, "sz_key")
        h.loc[ok, "sz_key"] = lab
        h.loc[ok, "sz_assign_method"] = meth

    keep = ["block_id", "blk_no", "street", "hdb_town", "bldg_contract_town", "max_floor_lvl",
            "year_completed", "residential", "commercial", "market_hawker", "total_dwelling_units",
            *ucols, "qa_units_minus_total", "geocode_status", "postal_code", "onemap_road",
            "lat", "lon", "x_svy21", "y_svy21", "sz_key", "sz_assign_method"]
    h[keep].to_csv(config.INTERIM / "dim_hdb_block.csv", index=False)
    res = h[h.residential]
    print(f"dim_hdb_block: {len(h)} blocks ({len(res)} residential, {res.total_dwelling_units.sum():,} units)")
    print("  geocode:", res["geocode_status"].value_counts().to_dict())
    print("  unit-group check (sum groups - total) non-zero rows:", int((h.qa_units_minus_total != 0).sum()))


if __name__ == "__main__":
    main()
