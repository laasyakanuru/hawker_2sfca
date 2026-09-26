"""
Step B1 - Supply side: hawker centres + closure calendar.

Inputs : raw/02_HawkerCentres.csv (NEA/data.gov.sg master, incl. under construction)
         raw/01_DatesofHawkerCentresClosure_2026.csv (NEA 2026 cleaning / works schedule)
Outputs: interim/dim_hawker_centre.csv
         interim/fact_hc_closure.csv         (long: one row per closure window)
         interim/qa_hc_match.csv             (01 <-> 02 match audit)

Join logic 01 <-> 02 (no shared id in the sources):
  1. project both to SVY21 metres
  2. mutual-nearest-neighbour match with distance <= 250 m
  3. audit name similarity; anything below 0.5 similarity is flagged for review
"""
from __future__ import annotations

import difflib

import numpy as np
import pandas as pd

import config
from geo import assign_points_to_features, latlon_to_svy21, name_key, read_geojson

MATCH_MAX_M = 250


def _date(s):
    return pd.to_datetime(s.replace({"NA": None, "nil": None}), format="%d/%m/%Y", errors="coerce")


def main():
    m = pd.read_csv(config.RAW_FILES["hc_master"], encoding="utf-8-sig")
    c = pd.read_csv(config.RAW_FILES["hc_closure"], keep_default_na=False)

    # ---- master (02) ---------------------------------------------------
    m["x_svy21"], m["y_svy21"] = latlon_to_svy21(m["LATITUDE"], m["LONGITUDE"])
    m["qa_xy_mismatch_m"] = np.hypot(m["x_svy21"] - m["LANDXADDRESSPOINT"],
                                     m["y_svy21"] - m["LANDYADDRESSPOINT"]).round(1)
    # ---- closure file (01) --------------------------------------------
    c["latitude_hc"] = pd.to_numeric(c["latitude_hc"], errors="coerce")
    c["longitude_hc"] = pd.to_numeric(c["longitude_hc"], errors="coerce")
    cx, cy = latlon_to_svy21(c["latitude_hc"], c["longitude_hc"])

    # ---- mutual nearest neighbour match -------------------------------
    D = np.hypot(cx[:, None] - m["x_svy21"].values[None], cy[:, None] - m["y_svy21"].values[None])
    j_of_i = D.argmin(1)
    i_of_j = D.argmin(0)
    rows = []
    for i, j in enumerate(j_of_i):
        d = D[i, j]
        mutual = i_of_j[j] == i
        sim = difflib.SequenceMatcher(None, name_key(c.at[i, "name"]), name_key(m.at[j, "NAME"])).ratio()
        ok = mutual and d <= MATCH_MAX_M
        rows.append({"serial_no": c.at[i, "serial_no"], "name_01": c.at[i, "name"],
                     "OBJECTID": m.at[j, "OBJECTID"] if ok else None, "name_02": m.at[j, "NAME"],
                     "distance_m": round(d, 1), "mutual_nn": mutual, "name_similarity": round(sim, 3),
                     "matched": ok, "review_flag": (not ok) or sim < 0.5})
    qa = pd.DataFrame(rows)
    qa.to_csv(config.INTERIM / "qa_hc_match.csv", index=False)
    print(f"01<->02 matched {qa.matched.sum()}/{len(qa)}; flagged for review: {qa.review_flag.sum()}")

    c = c.merge(qa[["serial_no", "OBJECTID"]], on="serial_no", how="left")
    hc = m.merge(c, on="OBJECTID", how="outer", indicator=True)
    # centres only in 01 (none at build time) keep 01 coordinates
    only01 = hc["_merge"] == "right_only"
    hc.loc[only01, "LATITUDE"] = hc.loc[only01, "latitude_hc"]
    hc.loc[only01, "LONGITUDE"] = hc.loc[only01, "longitude_hc"]
    hc["x_svy21"], hc["y_svy21"] = latlon_to_svy21(hc["LATITUDE"], hc["LONGITUDE"])

    stalls01 = pd.to_numeric(hc["no_of_food_stalls"], errors="coerce")
    stalls02 = pd.to_numeric(hc["NUMBER_OF_COOKED_FOOD_STALLS"], errors="coerce")
    hc["cooked_food_stalls"] = stalls01.fillna(stalls02)
    hc["stalls_source"] = np.where(stalls01.notna(), "01_closure_2026", "02_master")
    hc["qa_stall_diff_01_vs_02"] = stalls01 - stalls02
    hc["status"] = hc["STATUS"].fillna(hc["status"])  # 02 lifecycle status is authoritative

    hc = hc.sort_values(["OBJECTID", "serial_no"]).reset_index(drop=True)
    hc["hc_key"] = [f"HC{i:03d}" for i in range(1, len(hc) + 1)]

    dim = pd.DataFrame({
        "hc_key": hc["hc_key"],
        "hc_name": hc["NAME"].fillna(hc["name"]),
        "hc_name_nea_2026": hc["name"].replace("", None),
        "objectid_02": hc["OBJECTID"].astype("Int64"),
        "serial_no_01": pd.to_numeric(hc["serial_no"], errors="coerce").astype("Int64"),
        "status": hc["status"],
        "hup_programme": hc["DESCRIPTION"],
        "in_baseline": hc["status"].isin(config.BASELINE_STATUSES),
        "in_future": hc["status"].isin(config.FUTURE_STATUSES),
        "cooked_food_stalls": hc["cooked_food_stalls"],
        "market_stalls": pd.to_numeric(hc["no_of_market_stalls"], errors="coerce"),
        "stalls_source": hc["stalls_source"],
        "qa_stall_diff_01_vs_02": hc["qa_stall_diff_01_vs_02"],
        "est_completion": hc["EST_ORIGINAL_COMPLETION_DATE"],
        "hup_completion_date": hc["HUP_COMPLETION_DATE"],
        "postal_code": hc["ADDRESSPOSTALCODE"].astype("Int64").astype(str).str.zfill(6).replace("<NA>", None),
        "address": hc["ADDRESS_MYENV_x"].fillna(hc["address_myenv"]) if "ADDRESS_MYENV_x" in hc
                   else hc["ADDRESS_MYENV"].fillna(hc["address_myenv"]),
        "lat": hc["LATITUDE"], "lon": hc["LONGITUDE"],
        "x_svy21": hc["x_svy21"].round(2), "y_svy21": hc["y_svy21"].round(2),
        "qa_xy_mismatch_m": hc["qa_xy_mismatch_m"],
    })
    # ---- subzone / planning area of each centre (needs MP2019 boundaries) ----
    dim["sz_key"], dim["pa_key"] = None, None
    if config.EXTERNAL_FILES["subzone_geojson"].exists():
        feats = read_geojson(config.EXTERNAL_FILES["subzone_geojson"])
        for f in feats:
            f.props["sz_key"] = name_key(f.props.get("SUBZONE_N"))
            f.props["pa_key"] = name_key(f.props.get("PLN_AREA_N"))
        xy = dim[["x_svy21", "y_svy21"]].to_numpy(float)
        dim["sz_key"], _ = assign_points_to_features(xy, feats, "sz_key")
        dim["pa_key"], _ = assign_points_to_features(xy, feats, "pa_key")
    dim.to_csv(config.INTERIM / "dim_hawker_centre.csv", index=False)

    # ---- closure calendar (wide -> long) ------------------------------
    long = []
    for q in ["q1", "q2", "q3", "q4"]:
        t = hc[["hc_key", f"{q}_cleaningstartdate", f"{q}_cleaningenddate", f"remarks_{q}"]].copy()
        t.columns = ["hc_key", "start_date", "end_date", "remarks"]
        t["closure_type"] = "cleaning"
        t["period"] = q.upper()
        long.append(t)
    t = hc[["hc_key", "other_works_startdate", "other_works_enddate", "remarks_other_works"]].copy()
    t.columns = ["hc_key", "start_date", "end_date", "remarks"]
    t["closure_type"] = "other_works"
    t["period"] = "OTHER"
    long.append(t)
    cl = pd.concat(long, ignore_index=True)
    cl["start_date"] = _date(cl["start_date"])
    cl["end_date"] = _date(cl["end_date"])
    cl = cl.dropna(subset=["start_date"])
    cl["end_date"] = cl["end_date"].fillna(cl["start_date"])
    cl["remarks"] = cl["remarks"].replace({"nil": None, "NA": None})
    cl["duration_days"] = (cl["end_date"] - cl["start_date"]).dt.days + 1
    cl["partial_closure_flag"] = cl["remarks"].fillna("").str.contains(
        r"only|market is open|blk \w+ closed on", case=False, regex=True)
    cl = cl.sort_values(["hc_key", "start_date"]).reset_index(drop=True)
    cl.insert(0, "closure_id", [f"CL{i:04d}" for i in range(1, len(cl) + 1)])
    cl.to_csv(config.INTERIM / "fact_hc_closure.csv", index=False)
    print(f"dim_hawker_centre: {len(dim)} rows ({dim.in_baseline.sum()} baseline, {dim.in_future.sum()} future)")
    print(f"fact_hc_closure: {len(cl)} windows; other_works: {(cl.closure_type=='other_works').sum()}")
    bad = dim[dim.qa_xy_mismatch_m > 50]
    if len(bad):
        print("QA: LANDX/LANDY disagree with lat/lon (lat/lon used):", bad.hc_name.tolist())


if __name__ == "__main__":
    main()
