"""
Plain-English definition + unit for every column in data/processed/.

Used by build_model.py to write data_dictionary_columns.csv (and the same table
inside hawker_2sfca.sqlite). Lookup order: table-specific -> shared -> pattern.
If you add a column to any script, add its definition here; build_model.py
prints a warning for any column without one.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Shared columns (same meaning in every table they appear in)
# ---------------------------------------------------------------------------
SHARED = {
    # keys
    "pa_key": ("Planning area key: upper-case name, punctuation removed (joins to dim_planning_area)", "key"),
    "sz_key": ("Subzone key: upper-case name, punctuation removed (joins to dim_subzone)", "key"),
    "hc_key": ("Hawker centre key HC001-HC129 (joins to dim_hawker_centre)", "key"),
    "dp_key": ("Demand point key '<TYPE>-<id>', e.g. HDB-1|BEACH RD, CONDO-P00042 (joins to dim_demand_point)", "key"),
    "stn_key": ("MRT/LRT station code(s) from LTA, e.g. NS24/NE6/CC1 (joins to dim_mrt_station)", "key"),
    "block_id": ("HDB block key 'BLK_NO|STREET' as in the HDB file, e.g. 1|BEACH RD", "key"),
    # coordinates
    "lat": ("Latitude, WGS84", "degrees"),
    "lon": ("Longitude, WGS84", "degrees"),
    "x_svy21": ("Easting in SVY21 (Singapore's metre grid, EPSG:3414); used for all distances", "m"),
    "y_svy21": ("Northing in SVY21 (EPSG:3414)", "m"),
    "sz_assign_method": ("How the subzone was found: point_in_polygon, nearest_centroid (point fell just outside all "
                         "subzones, e.g. on the coast), or by_definition (a subzone centre point)", "category"),
    "postal_code": ("6-digit Singapore postal code", "text"),
    # 2SFCA run identifiers
    "scenario": ("baseline = centres open today; future = + 6 under construction; daytime = baseline supply with "
                 "weekday AM-peak MRT arrivals added as extra demand", "category"),
    "method": ("2sfca = every centre inside the catchment counts fully; e2sfca_gauss = nearer centres count more "
               "(Gaussian decay to 0 at the edge, headline); 3sfca_gauss = Gaussian + each resident's demand split "
               "between competing centres (used for closures)", "category"),
    "catchment_m": ("Catchment radius d0 (straight-line distance x DETOUR_FACTOR)", "m"),
    # population / access measures
    "population": ("Residents", "persons"),
    "pop_65plus": ("Residents aged 65+ (subzone 65+ share applied to the population)", "persons"),
    "dwelling_type": ("HDB, CONDO (incl. ECs and apartments), LANDED, OTHER (shophouses, institutions etc.); "
                      "ALL = every type combined; WORKER = MRT commuters (daytime scenario only)", "category"),
    "access_per_1000": ("2SFCA accessibility: hawker stalls reachable per 1,000 residents, after accounting for how "
                        "many other residents share those stalls; population-weighted average for the row", "stalls / 1,000 residents"),
    "access_65plus_per_1000": ("Same score, weighted by residents aged 65+ instead of all residents", "stalls / 1,000 residents"),
    "pop_no_access": ("Residents with no open hawker centre within the catchment", "persons"),
    "pct_pop_no_access": ("pop_no_access as a share of population", "%"),
    "spar": ("Spatial Access Ratio = access / national average for the same scenario, method and catchment; "
             "1 = average, <1 below average", "ratio"),
    "stall_deficit_vs_national": ("Extra stalls needed to lift these residents to the national average: "
                                  "sum of population x max(0, national - own access) / 1,000", "stalls"),
    "national_access_per_1000": ("Population-weighted national average access for the same scenario, method and catchment",
                                 "stalls / 1,000 residents"),
    "n_points": ("Number of demand points (HDB blocks, private projects, land-use cells or centre points) the residents "
                 "were placed at", "count"),
    "date": ("Calendar day", "date"),
    "planning_area": ("Planning area name as written in the census file", "text"),
    "region": ("URA region (Central, East, North, North-East, West)", "category"),
    "hc_name": ("Hawker centre name (NEA master list, file 02)", "text"),
}

# ---------------------------------------------------------------------------
# Table-specific columns (or shared names that mean something different here)
# ---------------------------------------------------------------------------
TABLE = {
    "dim_planning_area": {
        "resident_pop": ("Total residents (census file)", "persons"),
        "n_subzones": ("Number of subzones in the planning area", "count"),
        "households_2020": ("Resident households, Census 2020", "households"),
        "pct_hh_no_employed": ("Households with no employed person, Census 2020", "%"),
        "pct_hh_below_3k": ("Households earning < $3,000/month from work, incl. no employed person, Census 2020", "%"),
        "pct_hh_20k_plus": ("Households earning >= $20,000/month from work, Census 2020", "%"),
        "median_hh_income_approx": ("Approximate median monthly household income from work, interpolated within the "
                                    "median income band, Census 2020", "SGD / month"),
    },
    "dim_subzone": {
        "subzone": ("Subzone name as written in the census file", "text"),
        "sz_key_geo": ("Matching subzone key in the MP2019 boundary file (differs from sz_key only if names were "
                       "fuzzy-matched; see qa_subzone_name_reconcile.csv)", "key"),
        "sz_code": ("URA MP2019 subzone code, e.g. AMSZ01", "code"),
        "pa_key_geo": ("Planning area key from the boundary file", "key"),
        "pa_code": ("URA MP2019 planning area code", "code"),
        "region_geo": ("Region name from the boundary file", "category"),
        "area_km2": ("Land area of the subzone", "km2"),
        "centroid_x": ("Subzone centre point, SVY21 easting (area-weighted centroid)", "m"),
        "centroid_y": ("Subzone centre point, SVY21 northing", "m"),
        "centroid_lat": ("Subzone centre point, latitude", "degrees"),
        "centroid_lon": ("Subzone centre point, longitude", "degrees"),
    },
    "dim_hawker_centre": {
        "hc_name_nea_2026": ("Name in NEA's 2026 cleaning/closure file (01); blank if the centre is not in it", "text"),
        "objectid_02": ("OBJECTID in the NEA master file (02)", "id"),
        "serial_no_01": ("serial_no in the NEA closure file (01)", "id"),
        "status": ("Lifecycle status from file 02: Existing, Existing (new), Existing (replacement), Interim Centre, "
                   "Under Construction", "category"),
        "hup_programme": ("Hawker Upgrading Programme category from file 02, e.g. HUP Standard Upgrading, New Centre", "category"),
        "in_baseline": ("True if the centre counts as open supply today (config.BASELINE_STATUSES)", "boolean"),
        "in_future": ("True if the centre counts as supply in the future scenario (adds Under Construction)", "boolean"),
        "cooked_food_stalls": ("Number of cooked-food stalls = supply S_j in 2SFCA (2026 figure from file 01, else file 02)", "stalls"),
        "market_stalls": ("Number of wet-market stalls (file 01; not used as supply)", "stalls"),
        "stalls_source": ("Which file cooked_food_stalls came from: 01_closure_2026 or 02_master", "category"),
        "qa_stall_diff_01_vs_02": ("Stall count in file 01 minus file 02 (0 = files agree)", "stalls"),
        "est_completion": ("Original / expected completion date or year (file 02)", "date"),
        "hup_completion_date": ("Date its Hawker Upgrading Programme works finished (file 02)", "date"),
        "address": ("Street address (NEA)", "text"),
        "qa_xy_mismatch_m": ("Distance between file 02's own SVY21 point and its lat/lon; >50 m flags a bad record "
                             "(lat/lon is used)", "m"),
    },
    "dim_hdb_block": {
        "blk_no": ("Block number (HDB file)", "text"),
        "street": ("Street name as abbreviated in the HDB file, e.g. BT BATOK ST 21", "text"),
        "hdb_town": ("HDB town name decoded from bldg_contract_town", "category"),
        "bldg_contract_town": ("HDB town code, e.g. AMK, TAP, KWN", "code"),
        "max_floor_lvl": ("Highest floor of the block", "floors"),
        "year_completed": ("Year the block was completed", "year"),
        "residential": ("Block has flats", "boolean"),
        "commercial": ("Block has shops/commercial units", "boolean"),
        "market_hawker": ("Block houses a market or hawker centre", "boolean"),
        "total_dwelling_units": ("Total flats in the block", "flats"),
        "qa_units_minus_total": ("Sum of the four unit groups minus total_dwelling_units (0 = reconciles)", "flats"),
        "geocode_status": ("OneMap result: matched, matched_low_road_similarity, not_found, or not_attempted "
                           "(non-residential blocks)", "category"),
        "onemap_road": ("Full road name returned by OneMap", "text"),
    },
    "dim_mrt_station": {
        "station_name": ("Station name, upper case (LTA)", "text"),
        "station_name_display": ("Station name, mixed case", "text"),
        "rail_type": ("MRT or LRT", "category"),
        "station_key": ("Physical-station key (name); groups codes at one location, e.g. STEVENS DT10 + TE11", "key"),
        "coord_source": ("Where lat/lon came from: file_07 or onemap (stations missing in file 07)", "category"),
        "wkday_tap_in_avg": ("Average weekday tap-ins per day, all hours, Aug 2026", "trips / day"),
        "wkday_tap_out_avg": ("Average weekday tap-outs per day, all hours, Aug 2026", "trips / day"),
        "wkday_am_peak_tap_out_avg": ("Average weekday tap-outs 07:00-09:59 per day (people arriving, worker proxy "
                                      "used as demand in the daytime scenario)", "trips / day"),
        "wkday_lunch_tap_in_avg": ("Average weekday tap-ins 11:00-13:59 per day", "trips / day"),
        "wkday_lunch_tap_out_avg": ("Average weekday tap-outs 11:00-13:59 per day", "trips / day"),
    },
    "dim_demand_point": {
        "source": ("Where the location came from: hdb_block_onemap, ura_project, mp2019_landuse_grid (100 m cell of "
                   "residential land), subzone_centroid (fallback)", "category"),
        "label": ("Readable id of the location: HDB block_id, or 'project | street' for URA points; blank otherwise", "text"),
        "has_coords": ("True if the point has coordinates (points without are excluded from 2SFCA)", "boolean"),
        "weight": ("Allocation weight used to split the subzone population between points: HDB = flats, URA = sale "
                   "units + rental contracts, grid cell / centre point = 1", "weight"),
        "population": ("Residents allocated to this point", "persons"),
        "pop_HDB_1_2R": ("Of which in HDB 1- and 2-room flats (incl. studios, rental)", "persons"),
        "pop_HDB_3R": ("Of which in HDB 3-room flats", "persons"),
        "pop_HDB_4R": ("Of which in HDB 4-room flats", "persons"),
        "pop_HDB_5R_EX": ("Of which in HDB 5-room, executive and multi-generation flats", "persons"),
    },
    "fact_hc_closure": {
        "closure_id": ("Closure window key CL0001...", "key"),
        "start_date": ("First day closed", "date"),
        "end_date": ("Last day closed (inclusive)", "date"),
        "remarks": ("NEA remarks, e.g. Repairs and Redecoration", "text"),
        "closure_type": ("cleaning (quarterly) or other_works (renovation, repairs, redevelopment)", "category"),
        "period": ("Q1-Q4 for cleaning, OTHER for other works", "category"),
        "duration_days": ("Days closed, inclusive", "days"),
        "partial_closure_flag": ("True if the remarks say only part of the centre closed (still treated as a full "
                                 "closure of cooked-food supply)", "boolean"),
    },
    "fact_subzone_population": {
        "resident_pop": ("Total residents", "persons"),
        "Age_0_19": ("Residents aged 0-19", "persons"),
        "Age_20_64": ("Residents aged 20-64", "persons"),
        "Age_65plus": ("Residents aged 65+", "persons"),
        "Pct_Age_65plus": ("Share of residents aged 65+", "%"),
        "pop_hdb": ("Residents in HDB flats (sum of the four HDB dwelling columns)", "persons"),
        "Dwelling_1_2_Room": ("Residents in HDB 1- and 2-room flats", "persons"),
        "Dwelling_3_Room": ("Residents in HDB 3-room flats", "persons"),
        "Dwelling_4_Room": ("Residents in HDB 4-room flats", "persons"),
        "Dwelling_5Room_Executive": ("Residents in HDB 5-room and executive flats", "persons"),
        "Dwelling_Condo_Apartment": ("Residents in condominiums and other apartments (incl. ECs)", "persons"),
        "Dwelling_Landed": ("Residents in landed properties", "persons"),
        "Dwelling_Others": ("Residents in other dwellings (shophouses, institutions etc.)", "persons"),
        "FloorArea_Population_Total": ("Residents with a known dwelling floor area", "persons"),
        "FloorArea_Coverage_Pct": ("FloorArea_Population_Total as a share of resident_pop", "%"),
        "qa_dwelling_minus_total": ("Sum of dwelling columns minus resident_pop (non-zero from DOS rounding to 10)", "persons"),
    },
    "fact_subzone_population_dwelling": {
        "census_column": ("Original census column name, e.g. Dwelling_4_Room", "text"),
        "population": ("Residents in that dwelling group", "persons"),
        "dwelling_group": ("HDB_1_2R, HDB_3R, HDB_4R, HDB_5R_EX, CONDO, LANDED, OTHER", "category"),
    },
    "fact_pa_household_income": {
        "income_band": ("Monthly household income from work band, e.g. 3_000_3_999 = $3,000-3,999; "
                        "NoEmployedPerson = no one working", "category"),
        "households": ("Resident households in the band, Census 2020", "households"),
        "band_order": ("Sort order of the band, 0 = NoEmployedPerson ... 18 = $20,000 and over", "rank"),
    },
    "fact_mrt_hourly": {
        "day_type": ("WEEKDAY or WEEKENDS/HOLIDAY", "category"),
        "hour": ("Hour of day the trip started/ended, 0-23", "hour"),
        "tap_in_month": ("Total tap-ins in Aug 2026 for this day type and hour", "trips"),
        "tap_out_month": ("Total tap-outs in Aug 2026 for this day type and hour", "trips"),
        "n_days": ("Days of this day type in Aug 2026 (20 weekdays, 11 weekend/holiday)", "days"),
        "tap_in_avg_day": ("tap_in_month / n_days", "trips / day"),
        "tap_out_avg_day": ("tap_out_month / n_days", "trips / day"),
    },
    "fact_access_point": {
        "A": ("Accessibility of this demand point: stalls reachable per 1,000 residents", "stalls / 1,000 residents"),
        "spar": ("A / national average (1 = average)", "ratio"),
        "n_hc_in_reach": ("Open hawker centres within the catchment", "count"),
    },
    "fact_demand_proximity": {
        "nearest_hc_key": ("Nearest hawker centre open in the baseline", "key"),
        "nearest_hc_dist_m": ("Straight-line distance to it (x DETOUR_FACTOR)", "m"),
        "n_hc_within_500m": ("Open centres within 500 m", "count"),
        "n_hc_within_1km": ("Open centres within 1 km", "count"),
        "n_hc_within_1_5km": ("Open centres within 1.5 km", "count"),
    },
    "fact_supply_ratio": {
        "is_open": ("Centre is open in this scenario", "boolean"),
        "stalls": ("Cooked-food stalls counted (0 if closed)", "stalls"),
        "catchment_pop": ("Effective population competing for this centre = sum of distance-weighted residents "
                          "(3SFCA: also x selection share)", "persons (weighted)"),
        "R_per_1000": ("Supply ratio R_j: stalls per 1,000 effective catchment residents (higher = less crowded)",
                       "stalls / 1,000 residents"),
    },
    "fact_hc_closure_impact": {
        "stalls": ("Cooked-food stalls at the centre being closed", "stalls"),
        "pop_in_catchment": ("Residents within the catchment of the closed centre", "persons"),
        "pop_losing_all_access": ("Residents left with no open centre in reach when it closes", "persons"),
        "mean_delta_access_affected": ("Population-weighted change in access for residents in its catchment "
                                       "(negative = worse)", "stalls / 1,000 residents"),
        "national_delta_access": ("Change in the national average access", "stalls / 1,000 residents"),
        "max_neighbour_crowding_pct": ("Largest % fall in R_per_1000 at any other centre as displaced diners move there",
                                       "%"),
        "n_neighbours_crowded_5pct": ("Other centres whose R_per_1000 falls by 5% or more", "count"),
        "impact_rank": ("Criticality score: rank by pop_losing_all_access + rank by mean_delta_access_affected; "
                        "lower = more critical", "rank score"),
    },
    "fact_daily_access": {
        "n_hc_closed": ("Baseline centres closed that day (NEA cleaning / works calendar)", "count"),
        "stalls_closed": ("Cooked-food stalls in those centres", "stalls"),
        "closed_hc_keys": ("hc_keys of the closed centres, ';'-separated", "text"),
    },
    "agg_daily_access_subzone": {
        "access_per_1000": ("Population-weighted access in the subzone on that day (headline method, 1 km)",
                            "stalls / 1,000 residents"),
    },
    "qa_population_conservation": {
        "census_pop": ("Residents in the census for this subzone and dwelling type", "persons"),
        "allocated_pop": ("Residents allocated to demand points", "persons"),
        "source": ("Location source(s) used, '+'-joined", "category"),
        "diff": ("allocated_pop - census_pop (should be 0)", "persons"),
    },
    "qa_referential_integrity": {
        "table": ("Table checked", "text"),
        "fk": ("Foreign-key column checked", "text"),
        "rows_with_fk": ("Rows where the key is filled", "count"),
        "orphans": ("Rows whose key is missing from the parent table (should be 0)", "count"),
    },
    "data_dictionary": {
        "table": ("Table name", "text"), "grain": ("What one row represents", "text"),
        "primary_key": ("Column(s) that uniquely identify a row, '+'-joined", "text"),
        "foreign_keys": ("Columns that join to other tables", "text"),
        "n_columns": ("Number of columns", "count"), "columns": ("Column names", "text"),
    },
}

# ---------------------------------------------------------------------------
# Pattern families (checked last)
# ---------------------------------------------------------------------------
_FA = {"60_or_less": "60 m2 or less", "60_80": "61-80 m2", "80_100": "81-100 m2", "100_120": "101-120 m2",
       "over_120": "over 120 m2"}
_T = {"hdb": "HDB", "condo": "condo", "landed": "landed", "other": "other-dwelling", "worker": "MRT-commuter", "all": "all"}
_UNITS = {"HDB_1_2R": "1- and 2-room (incl. studios, rental)", "HDB_3R": "3-room (sold + rental)",
          "HDB_4R": "4-room", "HDB_5R_EX": "5-room, executive and multi-generation"}

PATTERNS = [
    (r"^FloorArea_(.+)$", lambda m: (f"Residents in homes with floor area {_FA.get(m[1], m[1])}", "persons")),
    (r"^Pct_FloorArea_(.+)$", lambda m: (f"Share of residents in homes with floor area {_FA.get(m[1], m[1])}", "%")),
    (r"^units_(HDB_.+)$", lambda m: (f"Flats in the block of type {_UNITS.get(m[1], m[1])}", "flats")),
    (r"^catchment_pop_(\w+)$", lambda m: (f"Part of catchment_pop that is {_T.get(m[1], m[1])} residents "
                                          f"(worker = daytime scenario only)", "persons (weighted)")),
    (r"^pop_in_catchment_(\w+)$", lambda m: (f"pop_in_catchment: {_T.get(m[1], m[1])} residents only", "persons")),
    (r"^pop_losing_all_access_(\w+)$", lambda m: (f"pop_losing_all_access: {_T.get(m[1], m[1])} residents only", "persons")),
    (r"^access_per_1000_(\w+)$", lambda m: (f"Access that day for {_T.get(m[1], m[1])} residents",
                                            "stalls / 1,000 residents")),
    (r"^pop_no_access_(\w+)$", lambda m: (f"{_T.get(m[1], m[1]).capitalize()} residents with no open centre in reach "
                                          f"that day", "persons")),
]


def describe(table: str, column: str):
    """Return (description, unit) or (None, None) if undefined."""
    if column in TABLE.get(table, {}):
        return TABLE[table][column]
    if column in SHARED:
        return SHARED[column]
    for pat, fn in PATTERNS:
        m = re.match(pat, column)
        if m:
            return fn(m)
    return None, None
