"""
Step A3 - Locations of private housing (condos / apartments / ECs / landed)
from the URA Data Service.

    set URA_ACCESS_KEY=xxxxxxxx      (Windows)   |  export URA_ACCESS_KEY=xxxxxxxx  (mac/linux)
    python src/fetch_ura_private.py

Register (free) at https://eservice.ura.gov.sg/maps/api/reg.html to receive
an AccessKey by e-mail. A daily token is generated from it:
    GET https://eservice.ura.gov.sg/uraDataService/insertNewToken/v1   header AccessKey
Data calls:
    ?service=PMI_Resi_Transaction&batch=1..4          (5 years of private sales)
    ?service=PMI_Resi_Rental&refPeriod=25q3 ...       (rental contracts per quarter)
Each result row is a project/street with SVY21 x, y and a list of records.

Output: data/external/ura_private_residential_projects.csv, one row per
(project, street, x, y) with
    dwelling_class  CONDO | LANDED  (mapped from URA propertyType)
    weight          n sale units + n rental contracts (project-size proxy used to
                    split the subzone condo / landed population between projects)

Without an AccessKey this script exits and build_demand.py falls back to the
MP2019 land-use dasymetric grid (see README section 4.4).
"""
from __future__ import annotations

import sys
import time
from collections import Counter

import pandas as pd
import requests

import config

TOKEN_URL = "https://eservice.ura.gov.sg/uraDataService/insertNewToken/v1"
DATA_URL = "https://eservice.ura.gov.sg/uraDataService/invokeUraDS/v1"
UA = {"User-Agent": "Mozilla/5.0 (hawker-2sfca)"}  # URA rejects some default client UAs

LANDED_TYPES = {"terrace", "terrace house", "semi-detached", "semi-detached house", "detached",
                "detached house", "strata terrace", "strata semi-detached", "strata detached"}


def dwelling_class(ptype: str) -> str:
    return "LANDED" if str(ptype).strip().lower() in LANDED_TYPES else "CONDO"


def get_token(key: str) -> str:
    r = requests.get(TOKEN_URL, headers={"AccessKey": key, **UA}, timeout=60)
    r.raise_for_status()
    tok = r.json().get("Result")
    if not tok:
        raise RuntimeError(f"URA token error: {r.text[:200]}")
    return tok


def call(key, token, **params):
    for attempt in range(4):
        r = requests.get(DATA_URL, params=params, headers={"AccessKey": key, "Token": token, **UA}, timeout=300)
        if r.ok and r.json().get("Status") == "Success":
            return r.json().get("Result", [])
        time.sleep(5 * (attempt + 1))
    print(f"  !! URA call failed {params}: {r.status_code} {r.text[:200]}")
    return []


def main():
    key = config.URA_ACCESS_KEY
    if not key:
        print("URA_ACCESS_KEY not set -> skipping (demand build will use land-use fallback).")
        return 1
    token = get_token(key)
    agg: dict[tuple, dict] = {}

    def add(row, kind, records):
        try:
            x, y = float(row.get("x")), float(row.get("y"))
        except (TypeError, ValueError):
            x = y = None
        k = (row.get("project", "").strip(), row.get("street", "").strip(), x, y)
        a = agg.setdefault(k, {"sale_units": 0, "rentals": 0, "types": Counter(),
                               "segment": row.get("marketSegment")})
        for rec in records:
            if kind == "sale":
                a["sale_units"] += int(rec.get("noOfUnits") or 1)
            else:
                a["rentals"] += int(rec.get("noOfRentalContract") or 1)
            a["types"][rec.get("propertyType", "")] += 1

    for b in range(1, 5):
        rows = call(key, token, service="PMI_Resi_Transaction", batch=b)
        print(f"sales batch {b}: {len(rows)} projects")
        for row in rows:
            add(row, "sale", row.get("transaction", []))
    for q in config.URA_RENTAL_QUARTERS:
        rows = call(key, token, service="PMI_Resi_Rental", refPeriod=q.strip())
        print(f"rental {q}: {len(rows)} projects")
        for row in rows:
            add(row, "rental", row.get("rental", []))

    out = []
    for (proj, street, x, y), a in agg.items():
        top = a["types"].most_common(1)[0][0] if a["types"] else ""
        # rental file labels all condos as 'Non-landed Properties'
        cls = dwelling_class(top)
        out.append({"project": proj, "street": street, "x_svy21": x, "y_svy21": y,
                    "market_segment": a["segment"], "property_type_mode": top,
                    "dwelling_class": cls, "n_sale_units": a["sale_units"],
                    "n_rental_contracts": a["rentals"],
                    "weight": max(1, a["sale_units"] + a["rentals"])})
    df = pd.DataFrame(out).sort_values(["dwelling_class", "project", "street"]).reset_index(drop=True)
    missing = df["x_svy21"].isna().sum()
    df = df.dropna(subset=["x_svy21", "y_svy21"])
    df.insert(0, "project_id", [f"P{i:05d}" for i in range(1, len(df) + 1)])
    df.to_csv(config.EXTERNAL_FILES["ura_projects"], index=False)
    print(df["dwelling_class"].value_counts(), f"\n{missing} rows without coordinates dropped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
