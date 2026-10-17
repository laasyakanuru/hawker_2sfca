"""
Q3b: Which two hawker centres should NOT close on the same day?

Same method as Q2 and Q3 (from each home, straight line, 1 km).

For every pair of centres (A, B):
  - find residents whose ONLY centres within 1 km are exactly A and B
  - if A closes, they can still go to B (and the other way round)
  - if A and B close on the SAME day, they have nothing within 1 km
Then check NEA's 2026 calendar: on how many days were A and B closed together?

Rank pairs by resident-days lost = residents x days closed together.
Pairs with a wet market (0 cooked-food stalls) are skipped, because a wet
market is not a real food option.

Input : ../csv/dim_demand_point.csv
        ../csv/dim_hawker_centre.csv
        ../csv/fact_hc_closure_impact.csv
        ../csv/fact_daily_access.csv
Output: q3_pairs.xlsx  (ClashedIn2026, AllPairs)
        q3_pairs.csv   (pairs that were closed together in 2026)
        q3_pair_map_1.png ... one map picture per pair (for slides)
        q3_pairs_singapore_map.jpg  one Singapore map with all top pairs (for slides)
        (maps need matplotlib:  /usr/local/bin/python3 -m pip install matplotlib)
"""

from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent


def find_data_dir(start):
    """Look in this folder and every folder above it for a 'csv' folder."""
    for folder in [start, *start.parents]:
        if (folder / "csv").is_dir():
            return folder / "csv"
    raise FileNotFoundError("Could not find a 'csv' folder above " + str(start))


DATA_DIR = find_data_dir(HERE)
print("Reading data from:", DATA_DIR)

CATCHMENT_M = 1000
MAP_TOP_N = 5          # how many pairs to draw on the map

# ---------- 1. Read the data (same as Q2/Q3) ----------
dp = pd.read_csv(DATA_DIR / "dim_demand_point.csv")
hc = pd.read_csv(DATA_DIR / "dim_hawker_centre.csv")
impact = pd.read_csv(DATA_DIR / "fact_hc_closure_impact.csv")
daily = pd.read_csv(DATA_DIR / "fact_daily_access.csv", parse_dates=["date"])

dp = dp[(dp["has_coords"] == True) & (dp["population"] > 0)].reset_index(drop=True)
hc = hc.set_index("hc_key")
open_keys = [k for k in impact["hc_key"].unique() if k in hc.index]
open_hc = hc.loc[open_keys].dropna(subset=["x_svy21", "y_svy21"])
open_keys = list(open_hc.index)
wet_market = set(open_hc.index[open_hc["cooked_food_stalls"].fillna(0) == 0])

# ---------- 2. Which centres are within 1 km of each home? ----------
dist = np.hypot(dp["x_svy21"].to_numpy()[:, None] - open_hc["x_svy21"].to_numpy()[None, :],
                dp["y_svy21"].to_numpy()[:, None] - open_hc["y_svy21"].to_numpy()[None, :])
within = dist <= CATCHMENT_M
n_within = within.sum(axis=1)

# ---------- 3. Residents who rely on exactly two centres ----------
pair_points = defaultdict(list)                  # (A, B) -> list of demand points
for i in np.where(n_within == 2)[0]:
    a, b = np.where(within[i])[0]
    pair_points[(open_keys[a], open_keys[b])].append(i)

# ---------- 4. Days each pair was closed together in 2026 ----------
closed_sets = daily["closed_hc_keys"].fillna("").str.split(";").map(set)
dates = daily["date"].dt.strftime("%d %b").tolist()

rows = []
for (a, b), pts in pair_points.items():
    if a in wet_market or b in wet_market:
        continue
    g = dp.loc[pts]
    together = [d for d, s in zip(dates, closed_sets) if a in s and b in s]
    sz = g.groupby("sz_key")["population"].sum().sort_values(ascending=False)
    main_sz = sz[sz >= 0.1 * sz.sum()].index.str.title()
    gap = np.hypot(*(open_hc.loc[a, ["x_svy21", "y_svy21"]].to_numpy(float)
                     - open_hc.loc[b, ["x_svy21", "y_svy21"]].to_numpy(float)))
    rows.append({
        "hc_a": a, "hc_b": b,
        "centre_a": open_hc.loc[a, "hc_name"],
        "centre_b": open_hc.loc[b, "hc_name"],
        "subzones": ", ".join(main_sz),
        "distance_between_m": round(gap),
        "residents_relying_on_pair": round(g["population"].sum()),
        "elderly_65plus": round(g["pop_65plus"].fillna(0).sum()),
        "days_closed_together_2026": len(together),
        "dates_closed_together": ", ".join(together),
        "resident_days_lost": round(g["population"].sum() * len(together)),
    })

pairs = pd.DataFrame(rows)
all_pairs = pairs.sort_values("residents_relying_on_pair", ascending=False).reset_index(drop=True)
clashed = (pairs[pairs["days_closed_together_2026"] > 0]
           .sort_values("resident_days_lost", ascending=False).reset_index(drop=True))
clashed.insert(0, "rank", clashed.index + 1)

# ---------- 5. Show and save ----------
pd.set_option("display.width", 250)
pd.set_option("display.max_colwidth", 38)
show = ["rank", "centre_a", "centre_b", "subzones", "residents_relying_on_pair",
        "elderly_65plus", "days_closed_together_2026", "resident_days_lost"]
print("\n===== PAIRS CLOSED TOGETHER IN 2026 (do not close these on the same day) =====")
print(clashed[show].head(10).to_string(index=False))
print("\n===== LARGEST PAIRS (not closed together in 2026 - keep it that way) =====")
print(all_pairs[["centre_a", "centre_b", "subzones", "residents_relying_on_pair",
                 "days_closed_together_2026"]].head(5).to_string(index=False))

with pd.ExcelWriter(HERE / "q3_pairs.xlsx") as writer:
    clashed.to_excel(writer, sheet_name="ClashedIn2026", index=False)
    all_pairs.to_excel(writer, sheet_name="AllPairs", index=False)
clashed.to_csv(HERE / "q3_pairs.csv", index=False)
print(f"\nSaved q3_pairs.xlsx and q3_pairs.csv in {HERE}")

# ---------- 6. Maps (PNG pictures, one per pair) ----------
# Drawn from our own data in SVY21 metres, so no internet is needed.
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle

plt.rcParams["font.family"] = ["Calibri", "Arial", "DejaVu Sans"]
INK, MUT, RED, TEAL, LG = "#1F2933", "#5F6B76", "#D1495B", "#00798C", "#C9CED3"
PINK = "#F6D5DA"
all_hc = hc.dropna(subset=["x_svy21", "y_svy21"])


def short_name(name, n=46):
    """'Queen Street Blk 270 (Albert Centre)' -> 'Albert Centre'."""
    if "(" in name and name.endswith(")"):
        name = name[name.index("(") + 1:-1]
    return name if len(name) <= n else name[:n - 1] + "..."


def overlaps(box, placed, pad=4):
    return any(not (box.x1 + pad < b.x0 or b.x1 + pad < box.x0 or
                    box.y1 + pad < b.y0 or b.y1 + pad < box.y0) for b in placed)


def pair_map(r, path):
    g = dp.loc[pair_points[(r["hc_a"], r["hc_b"])]]
    a, b = open_hc.loc[r["hc_a"]], open_hc.loc[r["hc_b"]]
    ax_, ay_ = float(a["x_svy21"]), float(a["y_svy21"])
    bx_, by_ = float(b["x_svy21"]), float(b["y_svy21"])

    # view: both 1 km rings + the affected homes, 4:3 shape
    xs = [ax_ - CATCHMENT_M, ax_ + CATCHMENT_M, bx_ - CATCHMENT_M, bx_ + CATCHMENT_M, *g["x_svy21"]]
    ys = [ay_ - CATCHMENT_M, ay_ + CATCHMENT_M, by_ - CATCHMENT_M, by_ + CATCHMENT_M, *g["y_svy21"]]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    w = max(max(xs) - min(xs), (max(ys) - min(ys)) * 4 / 3) + 500
    h = w * 3 / 4
    x0, x1, y0, y1 = cx - w / 2, cx + w / 2, cy - h / 2 - h * 0.12, cy + h / 2  # room for legend

    fig, ax = plt.subplots(figsize=(12, 9.6), dpi=200)
    fig.subplots_adjust(left=0.02, right=0.98, top=0.86, bottom=0.02)
    ax.set_facecolor("#FAFAF8")
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_color(LG)

    view = dp[dp["x_svy21"].between(x0, x1) & dp["y_svy21"].between(y0, y1)]
    hl_sz = set(g["sz_key"].value_counts().index[g.groupby("sz_key")["population"].sum()
                                                  .reindex(g["sz_key"].value_counts().index)
                                                  >= 0.1 * g["population"].sum()])
    in_hl = view["sz_key"].isin(hl_sz)

    # all homes (grey), homes in the highlighted subzones (pink), affected homes (red)
    ax.scatter(view.loc[~in_hl, "x_svy21"], view.loc[~in_hl, "y_svy21"],
               s=6 + view.loc[~in_hl, "population"] / 60, color=LG, lw=0, zorder=1)
    ax.scatter(view.loc[in_hl, "x_svy21"], view.loc[in_hl, "y_svy21"],
               s=6 + view.loc[in_hl, "population"] / 60, color=PINK, lw=0, zorder=2)
    ax.scatter(g["x_svy21"], g["y_svy21"], s=10 + g["population"] / 25,
               color=RED, alpha=0.85, lw=0, zorder=3)

    # other hawker centres in view (small grey squares)
    others = all_hc[all_hc["x_svy21"].between(x0, x1) & all_hc["y_svy21"].between(y0, y1)
                    & ~all_hc.index.isin([r["hc_a"], r["hc_b"]])
                    & (all_hc["in_baseline"] == True)]
    ax.scatter(others["x_svy21"], others["y_svy21"], marker="s", s=40,
               color="white", edgecolor=MUT, lw=1.2, zorder=4)

    # 1 km rings and the two centres
    for x, y in [(ax_, ay_), (bx_, by_)]:
        ax.add_patch(Circle((x, y), CATCHMENT_M, fill=False, ec=TEAL, lw=1.6, ls=(0, (5, 4)), zorder=5))
    ax.scatter([ax_, bx_], [ay_, by_], s=220, color=INK, edgecolor="white", lw=2.5, zorder=7)
    for x, y, t in [(ax_, ay_, "A"), (bx_, by_, "B")]:
        ax.text(x, y, t, color="white", fontsize=9, fontweight="bold",
                ha="center", va="center", zorder=8)

    # scale bar (500 m)
    sx, sy = x1 - w * 0.04 - 500, y0 + h * 0.035
    ax.plot([sx, sx + 500], [sy, sy], color=INK, lw=3, zorder=9)
    ax.text(sx + 250, sy + h * 0.012, "500 m", ha="center", va="bottom", fontsize=10, color=INK)

    # legend
    from matplotlib.lines import Line2D
    handles = [
        Line2D([], [], marker="o", ls="", ms=11, mfc=INK, mec="white", label="The two hawker centres (A, B)"),
        Line2D([], [], marker="o", ls="", ms=8, mfc=RED, mec=RED,
               label="Homes whose ONLY centres within 1 km are A and B"),
        Line2D([], [], marker="o", ls="", ms=8, mfc=PINK, mec=PINK, label="Other homes in the same subzone(s)"),
        Line2D([], [], marker="s", ls="", ms=7, mfc="white", mec=MUT, label="Other hawker centres"),
        Line2D([], [], color=TEAL, ls=(0, (5, 4)), lw=1.6, label="1 km from A and from B"),
    ]
    leg = ax.legend(handles=handles, loc="lower left", fontsize=10.5, frameon=True, facecolor="white",
              edgecolor=LG, ncol=2, borderpad=0.8, handletextpad=0.5, columnspacing=1.5)

    # centre labels: try positions around each centre, keep the first one that
    # stays inside the map and does not overlap the other label
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    ax_box = ax.get_window_extent(rend)
    placed = [ax.get_legend().get_window_extent(rend)]
    away = np.degrees(np.arctan2(by_ - ay_, bx_ - ax_))       # direction A -> B
    off = w * 0.09
    for (x, y, name, base, tag) in [(ax_, ay_, r["centre_a"], away + 180, "A"),
                                    (bx_, by_, r["centre_b"], away, "B")]:
        for turn in [0, 35, -35, 70, -70, 110, -110, 150, -150, 180]:
            ang = np.radians(base + turn)
            tx, ty = x + off * np.cos(ang), y + off * np.sin(ang)
            ha = "left" if np.cos(ang) > 0.3 else "right" if np.cos(ang) < -0.3 else "center"
            ann = ax.annotate(f"{tag}  {short_name(name)}", xy=(x, y), xytext=(tx, ty),
                              fontsize=13, fontweight="bold", color=INK, zorder=9, ha=ha, va="center",
                              bbox=dict(boxstyle="round,pad=0.35", fc="white", ec=INK, lw=1),
                              arrowprops=dict(arrowstyle="-", color=INK, lw=1.2))
            box = ann.get_window_extent(rend)
            inside = (box.x0 > ax_box.x0 + 6 and box.x1 < ax_box.x1 - 6 and
                      box.y0 > ax_box.y0 + ax_box.height * 0.13 and box.y1 < ax_box.y1 - 6)
            if inside and not overlaps(box, placed, pad=8):
                placed.append(box)
                break
            ann.remove()
        else:   # nothing fitted: use the first position anyway, so the name is never lost
            ang = np.radians(base)
            ann = ax.annotate(f"{tag}  {short_name(name)}", xy=(x, y),
                              xytext=(x + off * np.cos(ang), y + off * np.sin(ang)),
                              fontsize=13, fontweight="bold", color=INK, zorder=9, ha="center",
                              va="center", bbox=dict(boxstyle="round,pad=0.35", fc="white", ec=INK, lw=1),
                              arrowprops=dict(arrowstyle="-", color=INK, lw=1.2))
            placed.append(ann.get_window_extent(rend))

    # subzone names: highlighted ones first (red, next to their red homes), then the rest
    rend = fig.canvas.get_renderer()
    for sz in sorted(hl_sz, key=lambda z: -g.loc[g["sz_key"] == z, "population"].sum()):
        gg = g[g["sz_key"] == sz]
        hx = np.average(gg["x_svy21"], weights=gg["population"])
        hy = np.average(gg["y_svy21"], weights=gg["population"])
        for ddx, ddy in [(0, -0.07), (0, 0.07), (0.12, 0), (-0.12, 0), (0, -0.13), (0, 0.13),
                         (0.12, -0.08), (-0.12, 0.08), (0, 0)]:
            t = ax.text(hx + ddx * w, hy + ddy * h, sz.upper(), fontsize=13, fontweight="bold",
                        color=RED, ha="center", va="center", zorder=8,
                        bbox=dict(boxstyle="round,pad=0.2", fc=(1, 1, 1, 0.85), ec="none"))
            box = t.get_window_extent(rend)
            inside = ax_box.x0 < box.x0 and box.x1 < ax_box.x1 and ax_box.y0 < box.y0 and box.y1 < ax_box.y1
            if inside and not overlaps(box, placed):
                placed.append(box)
                break
            t.remove()

    sz_view = (view.groupby("sz_key")
               .apply(lambda d: pd.Series({"x": np.average(d["x_svy21"], weights=d["population"]),
                                           "y": np.average(d["y_svy21"], weights=d["population"]),
                                           "pop": d["population"].sum(), "n": len(d)}))
               .sort_values("pop", ascending=False))
    for sz, row in sz_view.iterrows():
        if row["n"] < 3 or sz in hl_sz:
            continue
        t = ax.text(row["x"], row["y"], sz.upper(), fontsize=9.5, color=MUT,
                    ha="center", va="center", zorder=6,
                    bbox=dict(boxstyle="round,pad=0.15", fc=(1, 1, 1, 0.75), ec="none"))
        box = t.get_window_extent(rend)
        inside = ax_box.x0 < box.x0 and box.x1 < ax_box.x1 and ax_box.y0 < box.y0 and box.y1 < ax_box.y1
        if not inside or overlaps(box, placed):
            t.remove()
        else:
            placed.append(box)

    # title
    fig.text(0.02, 0.955, f"Do not close A and B on the same day  (pair #{r['rank']})",
             fontsize=19, fontweight="bold", color=INK)
    fig.text(0.02, 0.915,
             f"{r['residents_relying_on_pair']:,} residents ({r['elderly_65plus']:,} aged 65+) in "
             f"{r['subzones']} have only A and B within 1 km.", fontsize=13, color=INK)
    fig.text(0.02, 0.882, f"In 2026, A and B were closed together on {r['days_closed_together_2026']} days: "
             f"{r['dates_closed_together']}.", fontsize=13, color=RED)
    fig.savefig(path, facecolor="white")
    plt.close(fig)


for _, r in clashed.head(MAP_TOP_N).iterrows():
    pair_map(r, HERE / f"q3_pair_map_{r['rank']}.png")
print(f"Saved q3_pair_map_1.png ... q3_pair_map_{min(MAP_TOP_N, len(clashed))}.png in {HERE}")

# ---------- 6b. One Singapore overview picture (JPG, for slides) ----------
# Subzone boundaries: downloaded once from GitHub (yinshanyang/singapore, URA Master Plan
# subzones) and saved into the csv folder.
import json
import urllib.request
from matplotlib.collections import PolyCollection

GEO_URL = "https://raw.githubusercontent.com/yinshanyang/singapore/master/maps/"


def load_geo(name):
    path = DATA_DIR / f"sg_{name}.geojson"
    if not path.exists():
        print("Downloading", name, "boundaries ...")
        urllib.request.urlretrieve(GEO_URL + name + ".geojson", path)
    out = []
    for f in json.load(open(path))["features"]:
        g = f["geometry"]
        for poly in ([g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]):
            out.append((f["properties"]["name"], np.array(poly[0])))
    return out


def singapore_jpg(path):
    sz_poly = load_geo("3-subzone")
    pa_poly = load_geo("2-planning-area")
    pairs5 = clashed.head(MAP_TOP_N)
    hl = set()
    for txt in pairs5["subzones"]:
        hl |= {x.strip().upper() for x in txt.split(",")}

    fig = plt.figure(figsize=(16, 9), dpi=150)
    ax = fig.add_axes([0.0, 0.0, 0.70, 0.86])
    ax.add_collection(PolyCollection([p for n, p in sz_poly], facecolors="#EEF0F2",
                                     edgecolors="#E2E6E9", linewidths=0.4))
    ax.add_collection(PolyCollection([p for n, p in sz_poly if n in hl], facecolors="#F7D9DD",
                                     edgecolors=RED, linewidths=1.0))
    ax.add_collection(PolyCollection([p for n, p in pa_poly], facecolors="none",
                                     edgecolors="#C9CFD4", linewidths=0.8))
    ax.set_xlim(103.595, 104.095)
    ax.set_ylim(1.195, 1.480)
    ax.set_aspect("equal")
    ax.axis("off")

    # numbered pin for each pair (midway between its two centres)
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    placed = []
    from matplotlib.transforms import Bbox
    for _, r in pairs5.iterrows():
        a, b = open_hc.loc[r["hc_a"]], open_hc.loc[r["hc_b"]]
        x, y = (a["lon"] + b["lon"]) / 2, (a["lat"] + b["lat"]) / 2
        ax.scatter([x], [y], s=520, color=INK, edgecolor="white", lw=2.5, zorder=6)
        ax.text(x, y, str(r["rank"]), color="white", fontsize=14, fontweight="bold",
                ha="center", va="center", zorder=7)
        d = ax.transData.transform((x, y))
        placed.append(Bbox.from_bounds(d[0] - 16, d[1] - 16, 32, 32))

    # planning area names for orientation (skipped where they would overlap)
    skip = {"NORTH-EASTERN ISLANDS", "SOUTHERN ISLANDS", "WESTERN ISLANDS", "CHANGI BAY",
            "MARINA EAST", "MARINA SOUTH", "STRAITS VIEW", "SIMPANG", "SINGAPORE RIVER", "MUSEUM",
            "DOWNTOWN CORE", "NEWTON", "ORCHARD", "RIVER VALLEY", "OUTRAM", "ROCHOR", "TANGLIN",
            "PAYA LEBAR", "TENGAH"}
    biggest = {}
    for n, p in pa_poly:
        area = 0.5 * abs(np.dot(p[:, 0], np.roll(p[:, 1], 1)) - np.dot(p[:, 1], np.roll(p[:, 0], 1)))
        if n not in biggest or area > biggest[n][0]:
            biggest[n] = (area, p[:, 0].mean(), p[:, 1].mean())
    for n, (area, x, y) in sorted(biggest.items(), key=lambda t: -t[1][0]):
        if n in skip:
            continue
        t = ax.text(x, y, n.title(), fontsize=9.5, color="#9AA3AB", ha="center", va="center", zorder=3)
        bb = t.get_window_extent(rend)
        if any(bb.overlaps(q) for q in placed):
            t.remove()
        else:
            placed.append(bb.padded(4))

    fig.text(0.025, 0.935, "Do not close these hawker centres on the same day",
             fontsize=26, fontweight="bold", color=INK)
    fig.text(0.025, 0.893, f"{len(pairs5)} pairs NEA closed together in 2026. Shaded subzones have homes "
             "whose only hawker centres within 1 km are the two in the pair.", fontsize=14, color=MUT)

    # cards on the right
    x0, w, top_, hcard, gap = 0.715, 0.27, 0.80, 0.142, 0.012
    for i, (_, r) in enumerate(pairs5.iterrows()):
        y = top_ - i * (hcard + gap)
        fig.add_artist(plt.Rectangle((x0, y - hcard), w, hcard, transform=fig.transFigure,
                                     fc="#F7F8F9", ec="none"))
        fig.add_artist(plt.Rectangle((x0, y - hcard), 0.004, hcard, transform=fig.transFigure,
                                     fc=RED, ec="none"))
        fig.text(x0 + 0.022, y - 0.032, str(r["rank"]), fontsize=13, fontweight="bold", color="white",
                 ha="center", va="center", bbox=dict(boxstyle="circle,pad=0.32", fc=INK, ec="none"))
        fig.text(x0 + 0.044, y - 0.032, r["subzones"], fontsize=15, fontweight="bold", color=INK,
                 va="center")
        fig.text(x0 + 0.044, y - 0.066, f"A  {short_name(r['centre_a'], 42)}", fontsize=12,
                 color=INK, va="center")
        fig.text(x0 + 0.044, y - 0.091, f"B  {short_name(r['centre_b'], 42)}", fontsize=12,
                 color=INK, va="center")
        fig.text(x0 + 0.044, y - 0.121,
                 f"{r['residents_relying_on_pair']:,} residents  ·  closed together "
                 f"{r['days_closed_together_2026']} days", fontsize=12, color=RED,
                 fontweight="bold", va="center")
    fig.savefig(path, facecolor="white", pil_kwargs={"quality": 95})
    plt.close(fig)


singapore_jpg(HERE / "q3_pairs_singapore_map.jpg")
print(f"Saved q3_pairs_singapore_map.jpg in {HERE}")
