"""
Step A2 - Geocode with the OneMap Search API.

    python src/fetch_onemap.py hdb               # all residential HDB blocks (~10.8k, ~55 min)
    python src/fetch_onemap.py hdb --limit 50    # quick smoke test
    python src/fetch_onemap.py mrt               # MRT/LRT stations with no lat/lon in file 07
    python src/fetch_onemap.py check             # one test call; prints exactly what OneMap returns

API:
    GET https://www.onemap.gov.sg/api/common/elastic/search
        ?searchVal=<blk + street>&returnGeom=Y&getAddrDetails=Y&pageNum=1
Returned fields used: BLK_NO, ROAD_NAME, POSTAL, X, Y (SVY21), LATITUDE, LONGITUDE.

Authentication (only if OneMap rejects anonymous calls - `check` will tell you):
    free account: https://www.onemap.gov.sg/apidocs/register
    export ONEMAP_EMAIL=...  ONEMAP_PASSWORD=...     (token fetched automatically, valid 3 days)
    or  export ONEMAP_TOKEN=<access_token>

API errors (blocked, 401/403, HTML page, timeouts) are NEVER written to the cache;
after 5 consecutive errors the run stops so nothing bad is saved.

The run is resumable: results are appended to
data/external/onemap_hdb_geocode_cache.csv and blocks already in the cache
are skipped on the next run. Rate is capped at config.ONEMAP_CALLS_PER_MIN.
"""
from __future__ import annotations

import argparse
import csv
import difflib
import os
import sys
import time

import pandas as pd
import requests

import config
from keys import hdb_block_id

URL = "https://www.onemap.gov.sg/api/common/elastic/search"
TOKEN_URL = "https://www.onemap.gov.sg/api/auth/post/getToken"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
           "Accept": "application/json"}


class OneMapError(RuntimeError):
    pass


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    token = os.getenv("ONEMAP_TOKEN", "")
    if not token and os.getenv("ONEMAP_EMAIL") and os.getenv("ONEMAP_PASSWORD"):
        r = s.post(TOKEN_URL, json={"email": os.getenv("ONEMAP_EMAIL"),
                                    "password": os.getenv("ONEMAP_PASSWORD")}, timeout=30)
        if not r.ok or "access_token" not in r.text:
            raise OneMapError(f"OneMap login failed ({r.status_code}): {r.text[:200]}")
        token = r.json()["access_token"]
        print("  OneMap token obtained")
    if token:
        s.headers["Authorization"] = token
    return s


def onemap_search(s: requests.Session, q: str, retries: int = 4) -> list:
    """Return OneMap results list. Raises OneMapError when the API itself fails
    (so callers never confuse an outage with 'address not found')."""
    last = ""
    for attempt in range(retries):
        try:
            r = s.get(URL, params={"searchVal": q, "returnGeom": "Y", "getAddrDetails": "Y",
                                   "pageNum": 1}, timeout=30)
        except requests.RequestException as exc:
            last = f"network error: {exc}"
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code == 429:
            last = "429 rate limited"
            time.sleep(30)
            continue
        if r.status_code in (401, 403):
            raise OneMapError(f"{r.status_code} from OneMap - authentication needed or request blocked. "
                              f"Set ONEMAP_EMAIL/ONEMAP_PASSWORD (see docstring). Body: {r.text[:200]!r}")
        try:
            data = r.json()
        except ValueError:
            last = f"HTTP {r.status_code}, non-JSON body: {r.text[:200]!r}"
            time.sleep(5 * (attempt + 1))
            continue
        if isinstance(data, dict) and "results" in data:
            return data["results"]
        last = f"HTTP {r.status_code}, unexpected JSON: {str(data)[:200]}"
        time.sleep(5 * (attempt + 1))
    raise OneMapError(f"OneMap failed for {q!r}: {last}")

# HDB dataset abbreviations -> OneMap full road names
ABBREV = {
    "AVE": "AVENUE", "RD": "ROAD", "DR": "DRIVE", "CRES": "CRESCENT", "CL": "CLOSE",
    "CTRL": "CENTRAL", "NTH": "NORTH", "STH": "SOUTH", "UPP": "UPPER", "LOR": "LORONG",
    "JLN": "JALAN", "BT": "BUKIT", "KG": "KAMPONG", "TG": "TANJONG", "PK": "PARK",
    "PL": "PLACE", "SQ": "SQUARE", "TER": "TERRACE", "HTS": "HEIGHTS", "GDNS": "GARDENS",
    "GDN": "GARDEN", "MKT": "MARKET", "IND": "INDUSTRIAL", "C'WEALTH": "COMMONWEALTH",
    "ST.": "SAINT",
}


def expand_street(street: str) -> str:
    toks = street.upper().split()
    out = []
    for i, t in enumerate(toks):
        if t == "ST":  # 'ST' = STREET, except 'ST GEORGE'S' style (rare, handled by 'ST.')
            out.append("STREET")
        else:
            out.append(ABBREV.get(t, t))
    return " ".join(out)


def _best(results, blk, street_full):
    best, best_score = None, -1.0
    for r in results:
        if str(r.get("BLK_NO", "")).upper() != blk.upper():
            continue
        score = difflib.SequenceMatcher(None, str(r.get("ROAD_NAME", "")).upper(), street_full).ratio()
        if score > best_score:
            best, best_score = r, score
    return best, best_score


def geocode(blk: str, street: str, session: requests.Session, pause: float):
    full = expand_street(street)
    for q in (f"{blk} {full}", f"{blk} {street}"):
        res = onemap_search(session, q)  # raises OneMapError on API failure -> not cached
        time.sleep(pause)
        hit, score = _best(res, blk, full)
        if hit is not None:
            status = "matched" if score >= 0.8 else "matched_low_road_similarity"
            return {"query": q, "status": status, "road_similarity": round(score, 3),
                    "onemap_blk": hit.get("BLK_NO"), "onemap_road": hit.get("ROAD_NAME"),
                    "postal_code": hit.get("POSTAL"), "x_svy21": hit.get("X"), "y_svy21": hit.get("Y"),
                    "lat": hit.get("LATITUDE"), "lon": hit.get("LONGITUDE")}
    return {"query": f"{blk} {full}", "status": "not_found", "road_similarity": None,
            "onemap_blk": None, "onemap_road": None, "postal_code": None,
            "x_svy21": None, "y_svy21": None, "lat": None, "lon": None}


def main(limit: int | None = None, include_non_residential: bool = False):
    hdb = pd.read_csv(config.RAW_FILES["hdb_property"], dtype={"blk_no": str})
    if not include_non_residential:
        hdb = hdb[hdb["residential"] == "Y"]
    hdb["block_id"] = hdb_block_id(hdb["blk_no"], hdb["street"])
    cache_path = config.EXTERNAL_FILES["hdb_geocode_cache"]
    done = set()
    if cache_path.exists():
        done = set(pd.read_csv(cache_path, usecols=["block_id"])["block_id"])
    todo = hdb[~hdb["block_id"].isin(done)]
    if limit:
        todo = todo.head(limit)
    print(f"{len(done)} cached, {len(todo)} to geocode")
    pause = 60.0 / config.ONEMAP_CALLS_PER_MIN
    fields = ["block_id", "blk_no", "street", "query", "status", "road_similarity", "onemap_blk",
              "onemap_road", "postal_code", "x_svy21", "y_svy21", "lat", "lon"]
    new_file = not cache_path.exists()
    s = make_session()
    onemap_search(s, "1 BEACH ROAD")  # fail fast before touching the cache
    fails = 0
    with open(cache_path, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        if new_file:
            w.writeheader()
        for n, row in enumerate(todo.itertuples(index=False), 1):
            try:
                rec = geocode(row.blk_no, row.street, s, pause)
                fails = 0
            except OneMapError as exc:
                fails += 1
                print(f"  !! {row.block_id}: {exc}")
                if fails >= 5:
                    fh.flush()
                    sys.exit("Stopping: 5 consecutive OneMap errors. Nothing bad was cached; "
                             "fix the issue and re-run - it resumes where it stopped.")
                continue
            w.writerow({"block_id": row.block_id, "blk_no": row.blk_no, "street": row.street, **rec})
            if n % 50 == 0:
                fh.flush()
                print(f"  {n}/{len(todo)}")
    out = pd.read_csv(cache_path)
    print(out["status"].value_counts())


def check():
    """One call, printed raw - use this to diagnose blocking / auth problems."""
    s = make_session()
    r = s.get(URL, params={"searchVal": "1 BEACH ROAD", "returnGeom": "Y", "getAddrDetails": "Y",
                           "pageNum": 1}, timeout=30)
    print("auth header:", "yes" if "Authorization" in s.headers else "no")
    print("HTTP", r.status_code, "| content-type:", r.headers.get("content-type"))
    print(r.text[:500])


def main_mrt():
    """Geocode stations whose LATITUDE/LONGITUDE are blank in file 07 (new stations)."""
    d = pd.read_excel(config.RAW_FILES["mrt_volume"], sheet_name=0)
    miss = d[d["LATITUDE"].isna()].drop_duplicates("PT_CODE")
    out = []
    s = make_session()
    for r in miss.itertuples(index=False):
        name = str(r.MRT_STATION).strip()
        kind = "LRT" if r.TYPE == "LRT" else "MRT"
        res = onemap_search(s, f"{name} {kind} STATION")
        hit = next((h for h in res if kind in str(h.get("SEARCHVAL", "")).upper()), res[0] if res else None)
        out.append({"PT_CODE": r.PT_CODE, "MRT_STATION": name,
                    "onemap_match": hit.get("SEARCHVAL") if hit else None,
                    "lat": hit.get("LATITUDE") if hit else None,
                    "lon": hit.get("LONGITUDE") if hit else None})
        time.sleep(0.5)
    pd.DataFrame(out).to_csv(config.EXTERNAL_FILES["mrt_geocode_cache"], index=False)
    print(pd.DataFrame(out))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=["hdb", "mrt", "check"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--all-blocks", action="store_true", help="also geocode non-residential blocks")
    a = ap.parse_args()
    try:
        if a.what == "hdb":
            main(a.limit, a.all_blocks)
        elif a.what == "mrt":
            main_mrt()
        else:
            check()
    except OneMapError as exc:
        sys.exit(f"OneMap error: {exc}\nRun `python src/fetch_onemap.py check` to see the raw response.")
