"""
Step A1 - Download Master Plan 2019 boundary / land-use layers from data.gov.sg.

    python src/fetch_datagov.py            # all layers
    python src/fetch_datagov.py subzone_geojson

Uses the data.gov.sg v1 public download API:
    GET https://api-open.data.gov.sg/v1/public/api/datasets/{id}/initiate-download
    GET https://api-open.data.gov.sg/v1/public/api/datasets/{id}/poll-download
        -> {"data": {"status": "DOWNLOAD_SUCCESS", "url": "<signed S3 url>"}}

If the API is blocked on your network, download the GeoJSON manually from
data.gov.sg and save it under data/external/ with the file name shown in
config.EXTERNAL_FILES - every later step only looks at that path.
"""
from __future__ import annotations

import sys
import time

import requests

import config

BASE = "https://api-open.data.gov.sg/v1/public/api/datasets/{id}/{action}"


def _headers():
    h = {"User-Agent": "hawker-2sfca/1.0"}
    if config.DATAGOV_API_KEY:
        h["x-api-key"] = config.DATAGOV_API_KEY
    return h


def download(name: str, force: bool = False):
    out = config.EXTERNAL_FILES[name]
    if out.exists() and not force:
        print(f"[skip] {out.name} already present")
        return out
    ds = config.DATAGOV_DATASETS[name]
    print(f"[data.gov.sg] {name} ({ds})")
    try:
        requests.get(BASE.format(id=ds, action="initiate-download"), headers=_headers(), timeout=60)
    except requests.RequestException:
        pass  # initiate is best-effort; poll works for pre-generated files
    url = None
    for attempt in range(20):
        r = requests.get(BASE.format(id=ds, action="poll-download"), headers=_headers(), timeout=60)
        if r.status_code == 429:
            time.sleep(10)
            continue
        r.raise_for_status()
        data = r.json().get("data", {})
        if data.get("url"):
            url = data["url"]
            break
        time.sleep(3)
    if not url:
        raise RuntimeError(f"Could not obtain download url for {name}; download manually (see docstring).")
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        tmp = out.with_suffix(".part")
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
        tmp.replace(out)
    print(f"  saved {out} ({out.stat().st_size/1e6:.1f} MB)")
    return out


if __name__ == "__main__":
    names = sys.argv[1:] or list(config.DATAGOV_DATASETS)
    for n in names:
        try:
            download(n)
        except Exception as exc:  # keep going with the other layers
            print(f"  !! {n} failed: {exc}")
