"""
End-to-end plumbing test with MOCK external data (fake rectangular subzones,
random block coordinates). Verifies every script runs, keys join and population
is conserved. Results are meaningless - never use them for analysis.

    python tests/integration_mock.py
Writes to a throw-away folder (HAWKER_DATA_DIR), never to data/.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TMP = Path(tempfile.mkdtemp(prefix="hawker_mock_"))
os.environ["HAWKER_DATA_DIR"] = str(TMP)
sys.path.insert(0, str(SRC))
import config  # noqa: E402
from geo import svy21_to_latlon  # noqa: E402

rng = np.random.default_rng(42)
X0, X1, Y0, Y1 = 2000, 50000, 22000, 50000


def ring(x0, y0, x1, y1):
    xs = np.array([x0, x1, x1, x0, x0]); ys = np.array([y0, y0, y1, y1, y0])
    lat, lon = svy21_to_latlon(xs, ys)
    return [[float(a), float(b), 0.0] for a, b in zip(lon, lat)]


def desc(d):
    return "<center><table>" + "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in d.items()) + "</table></center>"


pop = pd.read_excel(config.RAW_FILES["population"])
n = len(pop)
nc = 21
nr = int(np.ceil(n / nc))
w, h = (X1 - X0) / nc, (Y1 - Y0) / nr
feats = []
for k, r in enumerate(pop.itertuples(index=False)):
    c, rr = k % nc, k // nc
    x0, y0 = X0 + c * w, Y0 + rr * h
    geom = {"type": "Polygon", "coordinates": [ring(x0, y0, x0 + w, y0 + h)]}
    if k == 0:  # exercise MultiPolygon + hole handling
        geom = {"type": "MultiPolygon", "coordinates": [[ring(x0, y0, x0 + w, y0 + h),
                                                         ring(x0 + 100, y0 + 100, x0 + 300, y0 + 300)]]}
    feats.append({"type": "Feature", "geometry": geom, "properties": {"Name": f"kml_{k}", "Description": desc({
        "SUBZONE_NO": k, "SUBZONE_N": str(r[1]).upper(), "SUBZONE_C": f"SZ{k:03d}",
        "PLN_AREA_N": str(r[0]).upper(), "PLN_AREA_C": "XX", "REGION_N": "MOCK"})}})
config.EXTERNAL_FILES["subzone_geojson"].write_text(json.dumps({"type": "FeatureCollection", "features": feats}))

# land use: 400 random 300 m squares
lu = []
for k in range(400):
    x0, y0 = rng.uniform(X0, X1 - 300), rng.uniform(Y0, Y1 - 300)
    lu.append({"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring(x0, y0, x0 + 300, y0 + 300)]},
               "properties": {"Description": desc({"LU_DESC": "RESIDENTIAL", "GPR": "LND" if k % 2 else "2.8"})}})
config.EXTERNAL_FILES["landuse_geojson"].write_text(json.dumps({"type": "FeatureCollection", "features": lu}))

# HDB geocode cache
hdb = pd.read_csv(config.RAW_FILES["hdb_property"], dtype={"blk_no": str})
hdb = hdb[hdb.residential == "Y"]
xs, ys = rng.uniform(X0, X1, len(hdb)), rng.uniform(Y0, Y1, len(hdb))
lat, lon = svy21_to_latlon(xs, ys)
nf = rng.random(len(hdb)) < 0.03
pd.DataFrame({"block_id": hdb.blk_no.str.upper() + "|" + hdb.street.str.upper(), "blk_no": hdb.blk_no,
              "street": hdb.street, "query": "", "status": np.where(nf, "not_found", "matched"),
              "road_similarity": 1.0, "onemap_blk": hdb.blk_no, "onemap_road": hdb.street,
              "postal_code": "000000", "x_svy21": np.where(nf, np.nan, xs), "y_svy21": np.where(nf, np.nan, ys),
              "lat": np.where(nf, np.nan, lat), "lon": np.where(nf, np.nan, lon)}
             ).to_csv(config.EXTERNAL_FILES["hdb_geocode_cache"], index=False)

# URA projects (only 60% of subzones get some -> exercises the fallbacks)
m = 500
pd.DataFrame({"project_id": [f"P{i:05d}" for i in range(1, m + 1)], "project": [f"MOCK {i}" for i in range(m)],
              "street": "MOCK ST", "x_svy21": rng.uniform(X0, X1 * 0.6, m), "y_svy21": rng.uniform(Y0, Y1, m),
              "market_segment": "OCR", "property_type_mode": "Condominium",
              "dwelling_class": np.where(rng.random(m) < 0.7, "CONDO", "LANDED"),
              "n_sale_units": 10, "n_rental_contracts": 5, "weight": rng.integers(1, 300, m)}
             ).to_csv(config.EXTERNAL_FILES["ura_projects"], index=False)

pd.DataFrame({"PT_CODE": ["CC30", "CC31", "CC32", "TE1", "TE3"], "MRT_STATION": list("ABCDE"),
              "onemap_match": "", "lat": [1.27, 1.275, 1.29, 1.448, 1.427], "lon": [103.83, 103.84, 103.85, 103.785, 103.794]}
             ).to_csv(config.EXTERNAL_FILES["mrt_geocode_cache"], index=False)

for step in ["prep_supply.py", "prep_population.py", "prep_hdb.py", "prep_mrt.py", "build_demand.py",
             "compute_access.py", "build_model.py"]:
    print(f"\n=== {step}")
    r = subprocess.run([sys.executable, str(SRC / step)], cwd=SRC, env=os.environ)
    assert r.returncode == 0, step

P = config.PROCESSED
dp = pd.read_csv(P / "dim_demand_point.csv")
census = pd.read_csv(config.INTERIM / "fact_subzone_population_dwelling.csv")["population"].sum()
assert abs(dp.population.sum() - census) < 1, (dp.population.sum(), census)
qa = pd.read_csv(P / "qa_population_conservation.csv")
assert qa["diff"].abs().max() < 1e-6
ri = pd.read_csv(P / "qa_referential_integrity.csv")
assert ri.orphans.sum() == 0, ri
acc = pd.read_csv(P / "fact_access_point.csv")
hc = pd.read_csv(P / "dim_hawker_centre.csv")
sub = acc[(acc.scenario == "baseline") & (acc.method == "2sfca") & (acc.catchment_m == 1000)].merge(dp, on="dp_key")
sup = pd.read_csv(P / "fact_supply_ratio.csv").query("scenario=='baseline' and method=='2sfca' and catchment_m==1000")
lhs = (sub.population * sub.A / 1000).sum()
rhs = sup.loc[sup.catchment_pop > 0, "stalls"].sum()
assert abs(lhs - rhs) < 1e-3 * rhs, (lhs, rhs)
print(f"\nMOCK INTEGRATION PASSED  (outputs in {TMP})  sum P*A = {lhs:.1f} = reachable stalls {rhs:.0f}")
