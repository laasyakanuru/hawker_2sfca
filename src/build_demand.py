"""
Step C - Build demand points (HDB, CONDO, LANDED, OTHER) and allocate the
subzone census population onto them (dasymetric allocation).

Output: processed/dim_demand_point.csv          one row per demand point with population
        processed/qa_population_conservation.csv census vs allocated, by subzone x dwelling type

Allocation hierarchy (per subzone s, dwelling type t) - first level that has
points in s is used, so every resident is placed exactly once:

  HDB     1. geocoded HDB blocks in s, split by flat-type units (see README 4.3)
          2. subzone centroid
  CONDO   1. URA private projects (Condo/Apt/EC) in s, weight = sale units + rental contracts
          2. MP2019 residential land-use grid cells (GPR != LND) in s, >60 m from any HDB block
          3. subzone centroid
  LANDED  1. URA landed projects/streets in s (same weight)
          2. MP2019 residential land-use grid cells with GPR = 'LND' in s
          3. subzone centroid
  OTHER   1. subzone centroid (shophouses, institutions, etc.)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

import config
from geo import (assign_points_to_features, name_key, points_in_feature, read_geojson,
                 svy21_to_latlon)
from prep_hdb import UNIT_GROUPS

RES_LU = {"RESIDENTIAL", "RESIDENTIAL WITH COMMERCIAL AT 1ST STOREY", "COMMERCIAL & RESIDENTIAL",
          "RESIDENTIAL / INSTITUTION", "WHITE"}


def _subzone_feats():
    p = config.EXTERNAL_FILES["subzone_geojson"]
    if not p.exists():
        return None
    feats = read_geojson(p)
    for f in feats:
        f.props["sz_key"] = name_key(f.props.get("SUBZONE_N"))
    return feats


def _allocate(points: pd.DataFrame, pop_by_sz: pd.Series) -> pd.Series:
    """pop_i = P_s * w_i / sum_{k in s} w_k"""
    wsum = points.groupby("sz_key")["weight"].transform("sum")
    return points["sz_key"].map(pop_by_sz).fillna(0) * points["weight"] / wsum


def hdb_points(blocks: pd.DataFrame, pop_wide: pd.DataFrame):
    """Returns HDB demand points and the set of subzones they cover."""
    b = blocks[blocks.residential & blocks.x_svy21.notna() & blocks.sz_key.notna()].copy()
    b = b[b.total_dwelling_units > 0]
    b["pop"] = 0.0
    for g in UNIT_GROUPS:
        ucol = f"units_{g}"
        P = pop_wide.set_index("sz_key")[g]  # census residents of flat group g in subzone
        grp_units = b.groupby("sz_key")[ucol].transform("sum")
        tot_units = b.groupby("sz_key")["total_dwelling_units"].transform("sum")
        # if a subzone has residents of group g but no units of g, fall back to all units
        use_total = grp_units == 0
        share = np.where(use_total, b["total_dwelling_units"] / tot_units, b[ucol] / grp_units.replace(0, np.nan))
        b[f"pop_{g}"] = b["sz_key"].map(P).fillna(0).to_numpy() * np.nan_to_num(share)
        b["pop"] += b[f"pop_{g}"]
    b["dp_key"] = "HDB-" + b["block_id"]
    b["dwelling_type"] = "HDB"
    b["source"] = "hdb_block_onemap"
    b["weight"] = b["total_dwelling_units"]
    return b


def ura_points(cls: str, sz_feats):
    p = config.EXTERNAL_FILES["ura_projects"]
    if not p.exists() or sz_feats is None:
        return pd.DataFrame()
    u = pd.read_csv(p)
    u = u[u.dwelling_class == cls].copy()
    xy = u[["x_svy21", "y_svy21"]].to_numpy(float)
    u["sz_key"], u["sz_assign_method"] = assign_points_to_features(xy, sz_feats, "sz_key")
    u["dp_key"] = f"{cls}-" + u["project_id"]
    u["source"] = "ura_project"
    u["label"] = u["project"] + " | " + u["street"].fillna("")
    return u[["dp_key", "sz_key", "sz_assign_method", "x_svy21", "y_svy21", "weight", "source", "label"]]


def landuse_grid(cls: str, sz_feats, hdb_xy):
    p = config.EXTERNAL_FILES["landuse_geojson"]
    if not p.exists() or sz_feats is None:
        return pd.DataFrame()
    cache = config.INTERIM / f"landuse_grid_{cls.lower()}.csv"
    if cache.exists():
        return pd.read_csv(cache)
    print(f"  building {config.GRID_SIZE_M} m land-use grid for {cls} (one-off, cached)...")
    lu = read_geojson(p)
    sel = []
    for f in lu:
        desc = str(f.props.get("LU_DESC", "")).upper()
        gpr = str(f.props.get("GPR", "")).upper()
        if desc not in RES_LU:
            continue
        if cls == "LANDED" and gpr == "LND":
            sel.append(f)
        elif cls == "CONDO" and gpr != "LND" and desc != "WHITE":
            sel.append(f)
    if not sel:
        return pd.DataFrame()
    bb = np.array([f.bbox for f in sel])
    g = config.GRID_SIZE_M
    xs = np.arange(np.floor(bb[:, 0].min() / g) * g + g / 2, bb[:, 2].max(), g)
    ys = np.arange(np.floor(bb[:, 1].min() / g) * g + g / 2, bb[:, 3].max(), g)
    X, Y = np.meshgrid(xs, ys)
    xy = np.column_stack([X.ravel(), Y.ravel()])
    keep = np.zeros(len(xy), bool)
    for f in sel:
        keep |= points_in_feature(f, xy)
    xy = xy[keep]
    if cls == "CONDO" and hdb_xy is not None and len(hdb_xy):
        d, _ = cKDTree(hdb_xy).query(xy)
        xy = xy[d > config.HDB_EXCLUSION_M]
    ix = ((xy[:, 0] - xs[0]) / g).round().astype(int)
    iy = ((xy[:, 1] - ys[0]) / g).round().astype(int)
    out = pd.DataFrame({"dp_key": [f"{cls}-G{a:04d}{b:04d}" for a, b in zip(ix, iy)],
                        "x_svy21": xy[:, 0], "y_svy21": xy[:, 1], "weight": 1.0,
                        "source": "mp2019_landuse_grid", "label": None})
    out["sz_key"], out["sz_assign_method"] = assign_points_to_features(xy, sz_feats, "sz_key",
                                                                       fallback_nearest=False)
    out = out.dropna(subset=["sz_key"])
    out.to_csv(cache, index=False)
    return out


def centroid_points(dtype: str, sz_keys, dim_sz: pd.DataFrame):
    s = dim_sz.set_index("sz_key").reindex(list(sz_keys))
    return pd.DataFrame({"dp_key": [f"{dtype}-SZ-{k}" for k in s.index], "sz_key": s.index,
                         "x_svy21": s["centroid_x"].to_numpy(), "y_svy21": s["centroid_y"].to_numpy(),
                         "weight": 1.0, "source": "subzone_centroid", "sz_assign_method": "by_definition",
                         "label": None})


def main():
    dim_sz = pd.read_csv(config.INTERIM / "dim_subzone.csv")
    popw = pd.read_csv(config.INTERIM / "fact_subzone_population.csv")
    long = pd.read_csv(config.INTERIM / "fact_subzone_population_dwelling.csv")
    blocks = pd.read_csv(config.INTERIM / "dim_hdb_block.csv", dtype={"blk_no": str, "postal_code": str})
    sz_feats = _subzone_feats()

    rename = {"Dwelling_1_2_Room": "HDB_1_2R", "Dwelling_3_Room": "HDB_3R", "Dwelling_4_Room": "HDB_4R",
              "Dwelling_5Room_Executive": "HDB_5R_EX"}
    pop_wide = popw.rename(columns=rename)
    pop_t = long.groupby(["sz_key", "dwelling_type"])["population"].sum().unstack(fill_value=0)
    elderly_share = (popw.set_index("sz_key")["Age_65plus"] / popw.set_index("sz_key")["resident_pop"]).fillna(0)

    frames = []
    # ---- HDB --------------------------------------------------------------
    hb = hdb_points(blocks, pop_wide)
    covered = set(hb.loc[hb["pop"] > 0, "sz_key"])
    hb = hb[hb["pop"] > 0]
    frames.append(hb.rename(columns={"pop": "population", "block_id": "label"})[
        ["dp_key", "dwelling_type", "source", "sz_key", "sz_assign_method", "x_svy21", "y_svy21",
         "weight", "population", "label"] + [f"pop_{g}" for g in UNIT_GROUPS]])
    rest = pop_t.index[(pop_t["HDB"] > 0) & ~pop_t.index.isin(covered)]
    if len(rest):
        c = centroid_points("HDB", rest, dim_sz)
        c["population"] = c["sz_key"].map(pop_t["HDB"])
        c["dwelling_type"] = "HDB"
        frames.append(c)

    geo_blocks = blocks[blocks.residential & blocks.x_svy21.notna()]
    hdb_xy = geo_blocks[["x_svy21", "y_svy21"]].to_numpy(float) if len(geo_blocks) else None
    # ---- CONDO / LANDED -----------------------------------------------------
    for cls in ["CONDO", "LANDED"]:
        need = set(pop_t.index[pop_t[cls] > 0])
        for level in (ura_points(cls, sz_feats), landuse_grid(cls, sz_feats, hdb_xy)):
            if level is None or level.empty or not need:
                continue
            lv = level[level.sz_key.isin(need)].copy()
            if lv.empty:
                continue
            lv["population"] = _allocate(lv, pop_t[cls])
            lv["dwelling_type"] = cls
            frames.append(lv)
            need -= set(lv.sz_key)
        if need:
            c = centroid_points(cls, need, dim_sz)
            c["population"] = c["sz_key"].map(pop_t[cls])
            c["dwelling_type"] = cls
            frames.append(c)
    # ---- OTHER ----------------------------------------------------------------
    oth = pop_t.index[pop_t["OTHER"] > 0]
    c = centroid_points("OTHER", oth, dim_sz)
    c["population"] = c["sz_key"].map(pop_t["OTHER"])
    c["dwelling_type"] = "OTHER"
    frames.append(c)

    dp = pd.concat(frames, ignore_index=True)
    dp = dp[dp["population"] > 0].copy()
    dp["pa_key"] = dp["sz_key"].map(dim_sz.set_index("sz_key")["pa_key"])
    dp["pop_65plus"] = dp["population"] * dp["sz_key"].map(elderly_share).fillna(0)
    dp["has_coords"] = dp["x_svy21"].notna()
    lat, lon = svy21_to_latlon(dp["x_svy21"].fillna(0), dp["y_svy21"].fillna(0))
    dp["lat"] = np.where(dp.has_coords, lat, np.nan)
    dp["lon"] = np.where(dp.has_coords, lon, np.nan)
    cols = ["dp_key", "dwelling_type", "source", "label", "sz_key", "pa_key", "sz_assign_method",
            "x_svy21", "y_svy21", "lat", "lon", "has_coords", "weight", "population", "pop_65plus"] + \
           [f"pop_{g}" for g in UNIT_GROUPS]
    dp = dp.reindex(columns=cols)
    assert dp["dp_key"].is_unique
    dp.to_csv(config.PROCESSED / "dim_demand_point.csv", index=False)

    # ---- QA: population conservation -----------------------------------------
    alloc = dp.groupby(["sz_key", "dwelling_type"])["population"].sum()
    src = dp.groupby(["sz_key", "dwelling_type"])["source"].agg(lambda s: "+".join(sorted(set(s))))
    census = long.groupby(["sz_key", "dwelling_type"])["population"].sum()
    qa = pd.DataFrame({"census_pop": census, "allocated_pop": alloc, "source": src}).fillna(
        {"allocated_pop": 0}).reset_index()
    qa["diff"] = qa["allocated_pop"] - qa["census_pop"]
    qa.to_csv(config.PROCESSED / "qa_population_conservation.csv", index=False)

    print(f"dim_demand_point: {len(dp):,} points; {dp.population.sum():,.0f} residents "
          f"(census {long.population.sum():,}); without coords: {(~dp.has_coords).sum()}")
    print(dp.groupby(["dwelling_type", "source"]).agg(points=("dp_key", "size"),
                                                      population=("population", "sum")).round(0).to_string())
    placed = blocks[blocks.residential & blocks.sz_key.notna()]
    zero = placed[~placed.sz_key.isin(pop_t.index[pop_t["HDB"] > 0])]
    if len(zero):
        print(f"  note: {len(zero)} geocoded blocks ({zero.total_dwelling_units.sum():,} units) sit in subzones "
              f"with 0 census HDB residents (new estates / boundary edge) and receive no population")


if __name__ == "__main__":
    main()
