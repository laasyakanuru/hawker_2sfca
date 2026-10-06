"""
Central configuration for the Hawker Centre 2SFCA data build.

Everything that a teammate might want to tweak (paths, API keys, catchment
sizes, which hawker-centre statuses count as supply) lives here so the other
scripts never hard-code it.
"""
from __future__ import annotations

import os
import warnings

warnings.filterwarnings("ignore", module="openpyxl")
from pathlib import Path

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"   # files the team created (never modified)
# HAWKER_DATA_DIR lets tests write external/interim/processed somewhere else
DATA = Path(os.getenv("HAWKER_DATA_DIR", ROOT / "data"))
EXTERNAL = DATA / "external"  # API downloads + caches (safe to delete & re-fetch)
INTERIM = DATA / "interim"    # cleaned single-source tables
PROCESSED = DATA / "processed"  # final keyed tables + 2SFCA outputs

# --------------------------------------------------------------------------
# K-means clustering outputs (separate from the shared pipeline tables above).
# Two specifications are kept side by side:
#   final_pop500  = PRIMARY analysis (resident_pop>=500, pop_hdb==0 -> dropped, n=158)
#   legacy_pop1000 = earlier/sensitivity analysis (resident_pop>=1000, n=212)
# Shared pipeline inputs (fact_subzone_population.csv, agg_access_subzone.csv,
# dim_subzone.csv, ...) stay in PROCESSED and are NOT moved.
# --------------------------------------------------------------------------
CLUSTERING = PROCESSED / "clustering"
CLUSTERING_FINAL = CLUSTERING / "final_pop500"      # data CSVs, primary spec
CLUSTERING_LEGACY = CLUSTERING / "legacy_pop1000"   # data CSVs, legacy spec
OUTPUTS = ROOT / "outputs"
OUTPUTS_CLUSTERING = OUTPUTS / "clustering"
OUTPUTS_CLUSTERING_FINAL = OUTPUTS_CLUSTERING / "final_pop500"      # figures, primary
OUTPUTS_CLUSTERING_LEGACY = OUTPUTS_CLUSTERING / "legacy_pop1000"   # figures, legacy

for _p in (RAW, EXTERNAL, INTERIM, PROCESSED,
           CLUSTERING_FINAL, CLUSTERING_LEGACY,
           OUTPUTS_CLUSTERING_FINAL, OUTPUTS_CLUSTERING_LEGACY):
    _p.mkdir(parents=True, exist_ok=True)

RAW_FILES = {
    "hc_closure": RAW / "01_DatesofHawkerCentresClosure_2026.csv",
    "hc_master": RAW / "02_HawkerCentres.csv",
    "hdb_property": RAW / "06_HDBPropertyInformation.csv",
    "mrt_volume": RAW / "07_train_passenger_volumeEDA.xlsx",
    "hh_income": RAW / "08_ResidentHouseholdsbyPlanningAreaofResidence_2020EDA.xlsx",
    "population": RAW / "Resident_Population_Final_version.xlsx",
}

EXTERNAL_FILES = {
    "subzone_geojson": EXTERNAL / "mp2019_subzone_boundary.geojson",
    "planning_area_geojson": EXTERNAL / "mp2019_planning_area_boundary.geojson",
    "landuse_geojson": EXTERNAL / "mp2019_land_use.geojson",
    "hdb_geocode_cache": EXTERNAL / "onemap_hdb_geocode_cache.csv",
    "mrt_geocode_cache": EXTERNAL / "onemap_mrt_geocode_cache.csv",
    "ura_projects": EXTERNAL / "ura_private_residential_projects.csv",
}

# --------------------------------------------------------------------------
# API settings (read from environment variables – never commit keys)
# --------------------------------------------------------------------------
# data.gov.sg: key is optional (higher rate limit). https://guide.data.gov.sg
DATAGOV_API_KEY = os.getenv("DATAGOV_API_KEY", "")
# URA Data Service: free registration -> AccessKey by email.
# https://eservice.ura.gov.sg/maps/api/reg.html
URA_ACCESS_KEY = os.getenv("URA_ACCESS_KEY", "")
# OneMap search API is public (no token). Keep under 250 calls/min.
ONEMAP_CALLS_PER_MIN = int(os.getenv("ONEMAP_CALLS_PER_MIN", "200"))

# data.gov.sg dataset ids (Master Plan 2019). If an id ever changes, search the
# dataset name on data.gov.sg, copy the new "d_..." id from the URL, update here.
DATAGOV_DATASETS = {
    "subzone_geojson": "d_8594ae9ff96d0c708bc2af633048edfb",        # MP2019 Subzone Boundary (No Sea) (GEOJSON)
    "planning_area_geojson": "d_4765db0e87b9c86336792efe8a1f7a66",  # MP2019 Planning Area Boundary (No Sea) (GEOJSON)
    "landuse_geojson": "d_90d86daa5bfaa371668b84fa5f01424f",        # MP2019 Land Use layer (GEOJSON)
}

# URA rental data quarters to pull (adds projects with no recent sale).
URA_RENTAL_QUARTERS = os.getenv("URA_RENTAL_QUARTERS", "25q3,25q4,26q1,26q2").split(",")

# --------------------------------------------------------------------------
# Supply definition
# --------------------------------------------------------------------------
# Statuses that count as open supply in the baseline scenario
BASELINE_STATUSES = {"Existing", "Existing (new)", "Existing (replacement)", "Interim Centre"}
# Statuses added in the "future" scenario
FUTURE_STATUSES = BASELINE_STATUSES | {"Under Construction"}
SUPPLY_FIELD = "cooked_food_stalls"  # S_j in the 2SFCA formulas

# --------------------------------------------------------------------------
# 2SFCA parameters
# --------------------------------------------------------------------------
CATCHMENT_M = 1000                 # headline catchment d0 (metres, straight line)
SENSITIVITY_CATCHMENTS_M = [500, 1000, 1500]
DETOUR_FACTOR = 1.0                # multiply straight-line distance (e.g. 1.3 ~ walking network)
METHODS = ["2sfca", "e2sfca_gauss", "3sfca_gauss"]
HEADLINE_METHOD = "e2sfca_gauss"
CLOSURE_METHOD = "3sfca_gauss"     # competition-aware: demand re-routes when an HC closes
ACCESS_PER = 1000                  # report A_i as stalls per 1,000 residents

# Dasymetric grid (used for landed / condo fallback when no point data)
GRID_SIZE_M = 100
HDB_EXCLUSION_M = 60               # condo-fallback grid cells this close to an HDB block are dropped

# Daytime (worker) scenario: add AM-peak MRT arrivals as demand at stations
DAYTIME_AM_PEAK_HOURS = [7, 8, 9]
DAYTIME_WEIGHT = 1.0

# Calendar year analysed for date-based closure scenarios
ANALYSIS_YEAR = 2026
# Aug-2026 calendar for MRT day counts (PH 9 Aug falls on Sunday -> 10 Aug observed)
MRT_MONTH = "2026-08"
MRT_PUBLIC_HOLIDAYS = ["2026-08-10"]
