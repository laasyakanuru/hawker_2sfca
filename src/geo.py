"""
Lightweight geo helpers (numpy + matplotlib only, no GDAL/geopandas needed).

* SVY21 (EPSG:3414) forward projection from WGS84 lat/lon -> metres, so all
  distances in the project are plain Euclidean metres.
* GeoJSON reader that also unpacks data.gov.sg's KML-style "Description"
  HTML tables into real attribute columns.
* Point-in-polygon (with holes) and polygon centroids.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from html import unescape
from pathlib import Path

import numpy as np
import pandas as pd
from matplotlib.path import Path as MplPath

# --------------------------------------------------------------------------
# SVY21 forward projection (Transverse Mercator, SLA parameters)
# --------------------------------------------------------------------------
_A = 6378137.0
_F = 1 / 298.257223563
_O_LAT, _O_LON = 1.366666, 103.833333
_O_N, _O_E, _K = 38744.572, 28001.642, 1.0
_E2 = 2 * _F - _F * _F
_E4, _E6 = _E2 ** 2, _E2 ** 3
_A0 = 1 - _E2 / 4 - 3 * _E4 / 64 - 5 * _E6 / 256
_A2 = 3 / 8 * (_E2 + _E4 / 4 + 15 * _E6 / 128)
_A4 = 15 / 256 * (_E4 + 3 * _E6 / 4)
_A6 = 35 * _E6 / 3072


def _meridian(lat_deg):
    r = np.radians(lat_deg)
    return _A * (_A0 * r - _A2 * np.sin(2 * r) + _A4 * np.sin(4 * r) - _A6 * np.sin(6 * r))


def latlon_to_svy21(lat, lon):
    """Vectorised WGS84 -> SVY21. Returns (x_easting, y_northing) in metres."""
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    r = np.radians(lat)
    s, c = np.sin(r), np.cos(r)
    s2 = s * s
    rho = _A * (1 - _E2) / (1 - _E2 * s2) ** 1.5
    v = _A / np.sqrt(1 - _E2 * s2)
    psi = v / rho
    t = np.tan(r)
    w = np.radians(lon - _O_LON)
    M, Mo = _meridian(lat), _meridian(_O_LAT)
    w2, t2 = w * w, t * t
    w4, w6, w8 = w2 * w2, w2 ** 3, w2 ** 4
    t4, t6 = t2 * t2, t2 ** 3
    p2, p3, p4 = psi ** 2, psi ** 3, psi ** 4
    n1 = w2 / 2 * v * s * c
    n2 = w4 / 24 * v * s * c ** 3 * (4 * p2 + psi - t2)
    n3 = w6 / 720 * v * s * c ** 5 * (8 * p4 * (11 - 24 * t2) - 28 * p3 * (1 - 6 * t2)
                                      + p2 * (1 - 32 * t2) - psi * 2 * t2 + t4)
    n4 = w8 / 40320 * v * s * c ** 7 * (1385 - 3111 * t2 + 543 * t4 - t6)
    north = _O_N + _K * (M - Mo + n1 + n2 + n3 + n4)
    e1 = w2 / 6 * c ** 2 * (psi - t2)
    e2 = w4 / 120 * c ** 4 * (4 * p3 * (1 - 6 * t2) + p2 * (1 + 8 * t2) - psi * 2 * t2 + t4)
    e3 = w6 / 5040 * c ** 6 * (61 - 479 * t2 + 179 * t4 - t6)
    east = _O_E + _K * v * w * c * (1 + e1 + e2 + e3)
    return east, north


def svy21_to_latlon(x, y, iters: int = 3):
    """Inverse by Newton iteration on the forward function (accurate to mm)."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    lat = _O_LAT + (y - _O_N) / 110574.0
    lon = _O_LON + (x - _O_E) / 111320.0
    for _ in range(iters + 3):
        ex, ny = latlon_to_svy21(lat, lon)
        lat = lat + (y - ny) / 110574.0
        lon = lon + (x - ex) / (111320.0 * np.cos(np.radians(lat)))
    return lat, lon


# --------------------------------------------------------------------------
# Name keys
# --------------------------------------------------------------------------
def name_key(s) -> str:
    """Canonical join key for place names: upper case, single spaces, no punctuation noise."""
    if s is None or (isinstance(s, float) and np.isnan(s)):
        return ""
    s = str(s).upper().replace("&", " AND ").replace("’", "'")
    s = re.sub(r"[^A-Z0-9' ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# --------------------------------------------------------------------------
# GeoJSON
# --------------------------------------------------------------------------
_TD = re.compile(r"<th>(.*?)</th>\s*<td>(.*?)</td>", re.I | re.S)


def _parse_description(html: str) -> dict:
    return {k.strip(): unescape(v).strip() for k, v in _TD.findall(html or "")}


@dataclass
class Feature:
    props: dict
    # list of polygons; each polygon = [exterior ring (n,2), hole ring, ...] in SVY21 metres
    polygons: list = field(default_factory=list)

    @property
    def bbox(self):
        pts = np.vstack([p[0] for p in self.polygons])
        return pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max()


def _ring_to_svy(ring):
    arr = np.asarray(ring, dtype=float)[:, :2]  # drop Z if present
    x, y = latlon_to_svy21(arr[:, 1], arr[:, 0])
    return np.column_stack([x, y])


def read_geojson(path: Path) -> list[Feature]:
    gj = json.loads(Path(path).read_text(encoding="utf-8"))
    feats = []
    for f in gj["features"]:
        props = dict(f.get("properties") or {})
        if "Description" in props:  # data.gov.sg KML-derived layers
            props.update(_parse_description(props.pop("Description")))
        g = f.get("geometry") or {}
        polys = []
        if g.get("type") == "Polygon":
            polys = [g["coordinates"]]
        elif g.get("type") == "MultiPolygon":
            polys = g["coordinates"]
        elif g.get("type") == "GeometryCollection":
            for sub in g["geometries"]:
                if sub["type"] == "Polygon":
                    polys.append(sub["coordinates"])
                elif sub["type"] == "MultiPolygon":
                    polys.extend(sub["coordinates"])
        feats.append(Feature(props, [[_ring_to_svy(r) for r in poly] for poly in polys]))
    return feats


def ring_area_centroid(ring):
    x, y = ring[:, 0], ring[:, 1]
    x1, y1 = np.roll(x, -1), np.roll(y, -1)
    cross = x * y1 - x1 * y
    a = cross.sum() / 2
    if abs(a) < 1e-9:
        return 0.0, x.mean(), y.mean()
    cx = ((x + x1) * cross).sum() / (6 * a)
    cy = ((y + y1) * cross).sum() / (6 * a)
    return abs(a), cx, cy


def feature_area_centroid(feat: Feature):
    """Area (m^2) and area-weighted centroid, subtracting holes."""
    tot, sx, sy = 0.0, 0.0, 0.0
    for poly in feat.polygons:
        for k, ring in enumerate(poly):
            a, cx, cy = ring_area_centroid(ring)
            sign = 1 if k == 0 else -1
            tot += sign * a
            sx += sign * a * cx
            sy += sign * a * cy
    if tot <= 0:
        pts = np.vstack([p[0] for p in feat.polygons])
        return 0.0, pts[:, 0].mean(), pts[:, 1].mean()
    return tot, sx / tot, sy / tot


def points_in_feature(feat: Feature, xy: np.ndarray) -> np.ndarray:
    """Boolean mask of points inside the feature (holes respected)."""
    inside = np.zeros(len(xy), dtype=bool)
    if len(xy) == 0:
        return inside
    for poly in feat.polygons:
        ext = poly[0]
        bb = (xy[:, 0] >= ext[:, 0].min()) & (xy[:, 0] <= ext[:, 0].max()) & \
             (xy[:, 1] >= ext[:, 1].min()) & (xy[:, 1] <= ext[:, 1].max())
        idx = np.where(bb & ~inside)[0]
        if len(idx) == 0:
            continue
        m = MplPath(ext).contains_points(xy[idx])
        for hole in poly[1:]:
            m &= ~MplPath(hole).contains_points(xy[idx])
        inside[idx[m]] = True
    return inside


def assign_points_to_features(xy: np.ndarray, feats: list[Feature], key: str,
                              fallback_nearest: bool = True):
    """Return (labels, method) arrays. Points outside every polygon get the
    nearest feature centroid (flagged 'nearest_centroid') when fallback_nearest."""
    labels = np.full(len(xy), None, dtype=object)
    method = np.full(len(xy), None, dtype=object)
    for f in feats:
        todo = labels == None  # noqa: E711
        if not todo.any():
            break
        idx = np.where(todo)[0]
        m = points_in_feature(f, xy[idx])
        labels[idx[m]] = f.props.get(key)
        method[idx[m]] = "point_in_polygon"
    if fallback_nearest and (labels == None).any():  # noqa: E711
        cents = np.array([feature_area_centroid(f)[1:] for f in feats])
        idx = np.where(labels == None)[0]  # noqa: E711
        d = ((xy[idx, None, :] - cents[None, :, :]) ** 2).sum(-1)
        labels[idx] = [feats[k].props.get(key) for k in d.argmin(1)]
        method[idx] = "nearest_centroid"
    return labels, method
