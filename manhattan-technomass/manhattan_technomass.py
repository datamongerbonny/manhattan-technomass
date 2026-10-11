"""Technomass (Inostroza 2014) for Manhattan: calculation + figures in one script.

Requirements:  pip install numpy shapely matplotlib
Run:           python manhattan_technomass.py
Outputs go to ./technomass_output/ next to this script. Input data is downloaded automatically:
  - Manhattan building footprints from the official NYC Open Data "Building Footprints" dataset
    (id 5zhs-2jue), saved as nyc_buildings_manhattan.geojson (~45 MB, downloaded once)
  - NYC borough boundaries (boroughs.geojson)
Delete nyc_buildings_manhattan.geojson to force a fresh download of the latest city data.
If the NYC Open Data download fails, the script falls back to a GitHub copy of the footprints
(heights only, no construction years; results will differ slightly).
"""
import os, sys, json, math, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "technomass_output"); os.makedirs(OUT, exist_ok=True)
os.chdir(HERE)

OFFICIAL_URL = "https://data.cityofnewyork.us/resource/5zhs-2jue.geojson"
BOROUGHS_URL = "https://raw.githubusercontent.com/dwillis/nyc-maps/master/boroughs.geojson"
FALLBACK_URL = "https://raw.githubusercontent.com/anchitjaincfa/manhattan-3d/HEAD/data/manhattan_payload.json"

def fetch_json(url, tries=5):
    """GET with retries: the NYC Open Data server sometimes drops long requests."""
    import time
    for k in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=300) as r:
                return json.load(r)
        except Exception as e:
            if k == tries - 1: raise
            wait = 5 * (k + 1)
            print(f"  connection problem ({e}); retrying in {wait}s"); time.sleep(wait)

def download_official(path, page=10000):
    """Page through the NYC Open Data API for Manhattan (BBL starting with '1')."""
    feats, off = [], 0
    while True:
        q = urllib.parse.urlencode({"$where": "starts_with(base_bbl,'1')", "$limit": page,
                                    "$offset": off, "$order": "objectid"})
        batch = fetch_json(OFFICIAL_URL + "?" + q)["features"]
        feats += batch
        print(f"  ...{len(feats):,} buildings")
        if len(batch) < page: break
        off += page
    tmp = path + ".part"
    json.dump({"type": "FeatureCollection", "features": feats}, open(tmp, "w"))
    os.replace(tmp, path)   # only keep a complete file

if not os.path.exists("nyc_buildings_manhattan.geojson"):
    print("downloading Manhattan building footprints from NYC Open Data (one-time, ~45 MB)")
    try:
        download_official("nyc_buildings_manhattan.geojson")
    except Exception as e:
        print("  NYC Open Data download failed:", e)
        if not os.path.exists("payload.json"):
            print("  falling back to GitHub copy"); urllib.request.urlretrieve(FALLBACK_URL, "payload.json")
if not os.path.exists("boroughs.geojson"):
    print("downloading boroughs.geojson"); urllib.request.urlretrieve(BOROUGHS_URL, "boroughs.geojson")

import json, base64, struct, math
import numpy as np
from shapely.geometry import Polygon, Point, shape
from shapely.ops import unary_union
from shapely import STRtree
from shapely.affinity import rotate

rng = np.random.default_rng(42)

# ---------- building data ----------
# If nyc_buildings_manhattan.geojson (official NYC Open Data export) is in this folder, use it.
# Otherwise fall back to the GitHub copy of the same NYC Building Footprints data.
from shapely.ops import transform
OFFICIAL = os.path.join(HERE, "nyc_buildings_manhattan.geojson")

def load_official(path):
    feats = json.load(open(path))["features"]
    props0 = feats[0]["properties"]
    print("columns:", sorted(props0))
    hcol = next(c for c in ("height_roof", "heightroof", "HEIGHT_ROOF") if c in props0)
    ycol = next((c for c in ("construction_year", "cnstrct_yr", "CONSTRUCTION_YEAR") if c in props0), None)
    geoms = [shape(f["geometry"]) for f in feats if f.get("geometry")]
    lons = [c[0] for g in geoms for c in g.envelope.exterior.coords]
    lats = [c[1] for g in geoms for c in g.envelope.exterior.coords]
    lon0, lat0 = (min(lons) + max(lons)) / 2, (min(lats) + max(lats)) / 2
    kx, ky = 111320 * math.cos(math.radians(lat0)), 110540
    def proj(lon, lat): return ((lon - lon0) * kx, (lat - lat0) * ky)
    polys, heights, years = [], [], []
    for f in feats:
        if not f.get("geometry"): continue
        p = f["properties"]
        h = float(p.get(hcol) or 0) * 0.3048          # feet -> metres
        g = transform(lambda x, y, z=None: proj(x, y), shape(f["geometry"])).buffer(0)
        if g.is_empty: continue
        polys.append(g); heights.append(h if h > 0 else 4.0)
        y = p.get(ycol) if ycol else None
        years.append(int(float(y)) if y not in (None, "", "0") else None)
    return polys, heights, years, lat0, lon0, proj

def load_github_copy(path):
    p = json.load(open(path)); meta = p["meta"]; raw = base64.b64decode(p["b64"])
    off = 0
    (n,) = struct.unpack_from("<I", raw, off); off += 4
    polys, heights = [], []
    for _ in range(n):
        dm, rc = struct.unpack_from("<HB", raw, off); off += 3
        rings = []
        for _ in range(rc):
            (vc,) = struct.unpack_from("<H", raw, off); off += 2
            pts = struct.unpack_from("<" + "h" * (2 * vc), raw, off); off += 4 * vc
            rings.append(list(zip(pts[0::2], pts[1::2])))
        poly = Polygon(rings[0], rings[1:]).buffer(0)
        if poly.is_empty: continue
        polys.append(poly); heights.append(dm / 10.0)
    lat0, lon0 = meta["lat0"], meta["lon0"]
    kx, ky = 111320 * math.cos(math.radians(lat0)), 110540
    def proj(lon, lat): return ((lon - lon0) * kx, (lat - lat0) * ky)
    return polys, heights, [None] * len(polys), lat0, lon0, proj

if os.path.exists(OFFICIAL):
    print("using official NYC Open Data file:", OFFICIAL)
    polys, heights, years, lat0, lon0, proj = load_official(OFFICIAL)
else:
    print("\n" + "!" * 78 + "\nWARNING: official NYC Open Data file not available; using the GitHub copy.\n"
          "Technomass values will differ slightly from the reference outputs, and the copy has no\n"
          "construction years, so Figs. 8-9 (accumulation rates) will be EMPTY. Re-run when online\n"
          "to fetch the official data.\n" + "!" * 78 + "\n")
    polys, heights, years, lat0, lon0, proj = load_github_copy(os.path.join(HERE, "payload.json"))
heights = np.array(heights)
print("buildings loaded:", len(polys))

# ---------- Manhattan land boundary, same local metric projection ----------
bor = json.load(open("boroughs.geojson"))
man = [f for f in bor["features"] if f["properties"]["BoroName"] == "Manhattan"][0]
mgeom = shape(man["geometry"])
def proj_geom(g):
    from shapely.ops import transform
    return transform(lambda x, y, z=None: proj(np.asarray(x), np.asarray(y)), g)
land = proj_geom(mgeom).buffer(0)
# main island only for sampling (drop Roosevelt/Governors/Randall's small parts? keep all land but sample on largest)
parts = sorted(getattr(land, "geoms", [land]), key=lambda g: g.area, reverse=True)
island = parts[0]
print("Manhattan land km2:", round(land.area / 1e6, 1), " main island km2:", round(island.area / 1e6, 1))

tree = STRtree(polys)

# ---------- CBD: Midtown (Grand Central / Bryant Park area) ----------
CBD = Point(proj(-73.9800, 40.7540))

R = math.sqrt(70000 / math.pi)  # 7 ha circle, ~149 m radius

def technomass(center):
    circ = center.buffer(R, 64)
    land_c = circ.intersection(land)
    A = circ.area
    idx = tree.query(circ)
    vol_b, foot = 0.0, 0.0
    for i in idx:
        inter = polys[i].intersection(circ)
        if inter.is_empty: continue
        a = inter.area
        vol_b += a * heights[i]; foot += a
    r = max(land_c.area - foot, 0.0)          # total sealing of non-building land
    T = (vol_b + 0.5 * r) / (A / 10000.0)      # m3/ha
    return dict(T=T, vol_b=vol_b, foot=foot, r=r, land=land_c.area, A=A,
                cover=foot / land_c.area if land_c.area else 0)

# ---------- random circular samples in the continuous urban tissue ----------
minx, miny, maxx, maxy = island.bounds
inner = island.buffer(-R * 0.5)
samples = []
tries = 0
while len(samples) < 150 and tries < 20000:
    tries += 1
    pt = Point(rng.uniform(minx, maxx), rng.uniform(miny, maxy))
    if not inner.contains(pt): continue
    if any(pt.distance(s["pt"]) < 2 * R for s in samples): continue   # non-overlapping
    res = technomass(pt)
    if res["cover"] < 0.05:   # parks / open land, not urban tissue
        continue
    res["pt"] = pt; res["dist_km"] = pt.distance(CBD) / 1000
    samples.append(res)
print("random samples:", len(samples))

# ---------- transect: band along Manhattan's axis through the CBD ----------
ANG = 29.0   # Manhattan street grid rotation (deg east of north)
band_w = 700
band = Polygon([(-band_w / 2, -25000), (band_w / 2, -25000), (band_w / 2, 25000), (-band_w / 2, 25000)])
band = rotate(band, -ANG, origin=(0, 0))
from shapely.affinity import translate
band = translate(band, CBD.x, CBD.y).intersection(island.buffer(200))
# regular points every 450 m along the axis
ux, uy = math.sin(math.radians(ANG)), math.cos(math.radians(ANG))
transect = []
for k in range(-40, 41):
    pt = Point(CBD.x + ux * k * 450, CBD.y + uy * k * 450)
    if not inner.contains(pt): continue
    res = technomass(pt)
    if res["cover"] < 0.05: continue
    res["pt"] = pt; res["dist_km"] = pt.distance(CBD) / 1000
    res["signed_km"] = k * 0.45
    transect.append(res)
print("transect samples:", len(transect))

for name, S in [("Circular (all)", samples), ("Circular transect", transect)]:
    t = np.array([s["T"] for s in S])
    print(f"{name}: avg {t.mean():,.0f}  min {t.min():,.0f}  max {t.max():,.0f}")

# ================= FIGURES =================
import numpy as np
import matplotlib
matplotlib.use("Agg")  # renders to files, no display needed
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle, Polygon as MPoly, FancyArrow
from matplotlib.collections import PatchCollection
from matplotlib.colors import BoundaryNorm, ListedColormap
from shapely.geometry import box

d = dict(polys=polys, heights=heights, land=land, CBD=CBD, R=R, samples=samples, transect=transect, band=band)
polys, H, land, CBD, R = d["polys"], d["heights"], d["land"], d["CBD"], d["R"]
S, T = d["samples"], d["transect"]
plt.rcParams.update({"font.family": "DejaVu Serif", "font.size": 10})

def poly_patches(geoms):
    out = []
    for g in geoms:
        for p in getattr(g, "geoms", [g]):
            if p.geom_type != "Polygon" or p.is_empty: continue
            out.append(MPoly(np.asarray(p.exterior.coords), closed=True))
    return out

def draw_outline(ax, g, **kw):
    for p in getattr(g, "geoms", [g]):
        ax.plot(*p.exterior.xy, **kw)

def scalebar(ax, x0, y0, km_ticks, h, label="Kilometers"):
    for i in range(len(km_ticks) - 1):
        a, b = km_ticks[i] * 1000, km_ticks[i + 1] * 1000
        ax.add_patch(Rectangle((x0 + a, y0), b - a, h, fc="black" if i % 2 == 0 else "white", ec="black", lw=0.6, zorder=20))
    for t in km_ticks:
        ax.text(x0 + t * 1000, y0 + h * 1.8, f"{t:g}", ha="center", va="bottom", fontsize=7, zorder=20)
    ax.text(x0 + km_ticks[-1] * 1000 + h * 2, y0, label, fontsize=7, va="bottom", zorder=20)

def north(ax, x, y, s):
    ax.add_patch(MPoly([(x, y + s), (x - s * 0.35, y - s * 0.3), (x, y), (x + s * 0.35, y - s * 0.3)], fc="black", zorder=20))
    ax.text(x, y + s * 1.25, "N", ha="center", fontsize=9, zorder=20)

# ---------------- FIGURE 1: analogue of Fig. 3 ----------------
fig = plt.figure(figsize=(13, 12))
axL = fig.add_axes([0.03, 0.08, 0.44, 0.86])
axR = fig.add_axes([0.51, 0.08, 0.46, 0.86])

# Left: overview
pc = PatchCollection(poly_patches(polys), facecolor="#3a3a3a", edgecolor="none", zorder=2)
axL.add_collection(pc)
draw_outline(axL, land, color="black", lw=1.1, zorder=3)
_tx = np.array([q["signed_km"] for q in T]) * 1000
_ux, _uy = math.sin(math.radians(29)), math.cos(math.radians(29)); _hw = 420
_a, _b = _tx.min() - 450, _tx.max() + 450
_corn = [(CBD.x + _ux*t + _uy*w*sgn, CBD.y + _uy*t - _ux*w*sgn) for t, w, sgn in [(_a,_hw,1),(_b,_hw,1),(_b,_hw,-1),(_a,_hw,-1)]]
axL.add_patch(MPoly(np.array(_corn),
                    fill=False, ls=(0, (3, 2)), lw=1.6, ec="black", zorder=6))
for s in S:
    axL.add_patch(Circle((s["pt"].x, s["pt"].y), 115, fc="#d7261e", ec="black", lw=0.4, zorder=7))
for s in T:
    axL.add_patch(Circle((s["pt"].x, s["pt"].y), 115, fc="#5fe0ec", ec="none", zorder=8))
axL.add_patch(Rectangle((CBD.x - 260, CBD.y - 260), 520, 520, fc="black", zorder=9))
minx, miny, maxx, maxy = land.bounds
axL.set_xlim(minx - 700, maxx + 700); axL.set_ylim(miny - 1600, maxy + 500)
axL.set_aspect("equal"); axL.set_xticks([]); axL.set_yticks([])
scalebar(axL, minx - 400, miny - 1200, [0, 0.5, 1, 2, 3, 4], 130)
north(axL, maxx + 100, miny - 900, 600)
axL.text(CBD.x - 450, CBD.y - 60, "CBD\n(Midtown)", fontsize=8, ha="right", zorder=10, bbox=dict(fc="white", ec="none", alpha=0.85, pad=1))

# Right: zoom with 7-ha circles and building heights
import itertools
P = np.array([[q["pt"].x, q["pt"].y] for q in S]); Tv = np.array([q["T"] for q in S])
best = None
for i in range(len(S)):
    nn = np.argsort(np.hypot(*(P - P[i]).T))[:6]
    for g in itertools.combinations(nn, 4):
        pts = P[list(g)]
        if max(np.ptp(pts[:, 0]), np.ptp(pts[:, 1])) > 1300: continue
        sp = Tv[list(g)].max() / Tv[list(g)].min()
        if best is None or sp > best[0]: best = (sp, g)
pick = sorted([S[k] for k in best[1]], key=lambda q: q["T"])
pts = P[list(best[1])]
cx, cy = pts[:, 0].mean(), pts[:, 1].mean()
W = np.ptp(pts[:, 0]) + 2 * R + 900; Hh = max(np.ptp(pts[:, 1]) + 2 * R + 900, W * 1.55)
W = max(W, Hh / 1.55)
win = box(cx - W / 2, cy - Hh / 2, cx + W / 2, cy + Hh / 2)
axR.set_facecolor("#e9e6df")
draw_outline(axR, land, color="#9a9a9a", lw=0.8, zorder=1)
# water background outside land
from shapely.geometry import box as sbox
water = win.difference(land)
axR.add_collection(PatchCollection(poly_patches([water]), fc="#c9d6e0", ec="none", zorder=0.5))
idx = [i for i, p in enumerate(polys) if p.intersects(win)]
axR.add_collection(PatchCollection(poly_patches([polys[i] for i in idx]), fc="#b9b6ad", ec="#8d8a82", lw=0.2, zorder=2))
bounds = [0, 10, 20, 40, 80, 150, 500]
cols = ["#f6dcc6", "#f0bb97", "#e79a72", "#d9724f", "#c9462f", "#a8141a"]
cmap = ListedColormap(cols); norm = BoundaryNorm(bounds, cmap.N)
for s in pick:
    c = s["pt"].buffer(R, 96)
    parts, hs = [], []
    for i in idx:
        g = polys[i].intersection(c)
        if g.is_empty: continue
        pp = poly_patches([g]); parts += pp; hs += [H[i]] * len(pp)
    col = PatchCollection(parts, cmap=cmap, norm=norm, ec="#5a3a2a", lw=0.25, zorder=4)
    col.set_array(np.array(hs)); axR.add_collection(col)
    axR.add_patch(Circle((s["pt"].x, s["pt"].y), R, fill=False, ec="#d7261e", lw=2.2, zorder=6))
    axR.add_patch(Circle((s["pt"].x, s["pt"].y), 16, fc="#d7261e", ec="black", lw=0.5, zorder=7))
    axR.text(s["pt"].x, s["pt"].y + R + 40, f"{s['T']/1000:,.0f}k m³/ha", ha="center", fontsize=8.5,
             bbox=dict(fc="white", ec="none", alpha=0.85, pad=1.2), zorder=8)
axR.set_xlim(cx - W / 2, cx + W / 2); axR.set_ylim(cy - Hh / 2, cy + Hh / 2)
axR.set_aspect("equal"); axR.set_xticks([]); axR.set_yticks([])
# legend
u = W / 2600; lx, ly = cx + W / 2 - 720 * u, cy - Hh / 2 + 80 * u
axR.add_patch(Rectangle((lx - 40*u, ly - 20*u), 700*u, 1060*u, fc="white", ec="black", lw=0.8, zorder=10))
axR.text(lx, ly + 980*u, "Buildings\nheight  m", fontsize=11, fontweight="bold", va="top", zorder=11)
labels = ["0 – 10", "10 – 20", "20 – 40", "40 – 80", "80 – 150", "150 +"]
for k, (c, lab) in enumerate(zip(cols, labels)):
    yy = ly + 690*u - k * 125*u
    axR.add_patch(Rectangle((lx, yy), 180*u, 95*u, fc=c, ec="#777", lw=0.4, zorder=11))
    axR.text(lx + 230*u, yy + 45*u, lab, va="center", fontsize=9, zorder=11)
axR.add_patch(Rectangle((cx - W/2 + 40*u, cy + Hh/2 - 330*u), 1000*u, 290*u, fc="white", ec="none", alpha=0.9, zorder=19))
scalebar(axR, cx - W / 2 + 90*u, cy + Hh / 2 - 250*u, [0, 0.1, 0.2, 0.3, 0.4], 35*u)

fig.text(0.5, 0.035, "Technomass samples in Manhattan, New York (after Inostroza 2014, Fig. 3). "
         "Red: 150 random 7-ha circular samples; cyan: transect samples;\nblack square: CBD (Midtown); dashed box: transect. "
         "Right: four neighbouring samples with the widest Technomass spread, building heights shown.\nData: NYC Building Footprints; NYC borough boundaries.",
         ha="center", fontsize=9.5)
fig.savefig(os.path.join(OUT, "manhattan_technomass_samples.png"), dpi=170)
plt.close(fig)

# ---------------- FIGURE 2: Technomass vs distance to CBD (Figs. 5–6 analogues) ----------------
fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 5.2))
x = np.array([s["dist_km"] for s in S]); y = np.array([s["T"] for s in S]) / 1000
a1.scatter(x, y, s=22, c="#d7261e", ec="black", lw=0.3)
b = np.polyfit(x, np.log(y), 1); xx = np.linspace(0, x.max(), 100)
a1.plot(xx, np.exp(b[1] + b[0] * xx), "k--", lw=1.2, label=f"exponential fit: T ≈ {np.exp(b[1]):.0f}k·e^({b[0]:.2f}·d)")
a1.axhline(28.1, color="#1f77b4", lw=1.2, ls=":", label="Bogotá circular average (28k)")
a1.set_xlabel("Distance to CBD (km)"); a1.set_ylabel("Technomass (thousand m³/ha)")
a1.set_title("All circular samples"); a1.legend(fontsize=8.5, frameon=False)

xs = np.array([s["signed_km"] for s in T]); ys = np.array([s["T"] for s in T]) / 1000
o = np.argsort(xs)
a2.plot(xs[o], ys[o], "-", color="#5fb8c4", lw=1.2, zorder=1)
a2.scatter(xs, ys, s=30, c="#5fe0ec", ec="black", lw=0.4, zorder=2)
a2.axvline(0, color="black", lw=0.8)
a2.text(0.1, ys.max() * 1.02, "Midtown CBD", fontsize=8.5)
a2.text(xs.min() + 0.1, ys.max() * 1.02, "Financial District", fontsize=8.5)
a2.set_xlabel("Distance along transect from CBD (km)   ← south   |   north →")
a2.set_ylabel("Technomass (thousand m³/ha)"); a2.set_title("Transect samples")
for a in (a1, a2):
    a.spines[["top", "right"]].set_visible(False); a.set_ylim(0, None)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "manhattan_technomass_distance.png"), dpi=170)

# summary table (analogue of Table 2)
import csv
with open(os.path.join(OUT, "manhattan_technomass_samples.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["sample_set", "x_m", "y_m", "dist_to_cbd_km", "technomass_m3_per_ha", "building_volume_m3",
                "building_footprint_m2", "sealed_non_building_m2", "land_in_circle_m2"])
    for name, SS in [("circular", S), ("transect", T)]:
        for s in SS:
            w.writerow([name, round(s["pt"].x), round(s["pt"].y), round(s["dist_km"], 3), round(s["T"]),
                        round(s["vol_b"]), round(s["foot"]), round(s["r"]), round(s["land"])])
for name, SS in [("Circular (all)", S), ("Circular transect", T)]:
    t = np.array([s["T"] for s in SS])
    print(f"{name}: avg {t.mean():,.0f} min {t.min():,.0f} max {t.max():,.0f} n={len(t)}")
print("fit", b, "picked", [round(s["T"]) for s in pick])


# ======================================================================
# FIGURES 5–9 (after Inostroza 2014): distance profiles and accumulation rates
# ======================================================================
from shapely.affinity import rotate as _rot
YEARS = np.array([y if y is not None else -1 for y in years])
PERIODS = [(1860, 1879), (1880, 1899), (1900, 1919), (1920, 1939), (1940, 1959),
           (1960, 1979), (1980, 1999), (2000, 2019), (2020, 2026)]
PLAB = [f"{a}–{str(b)[2:]}" for a, b in PERIODS]

def measure(geom):
    """Technomass of any sample polygon + building volume by construction period."""
    land_c = geom.intersection(land); A = geom.area
    vol, foot, vper, undated = 0.0, 0.0, np.zeros(len(PERIODS)), 0.0
    for i in tree.query(geom):
        g = polys[i].intersection(geom)
        if g.is_empty: continue
        a = g.area; v = a * heights[i]; vol += v; foot += a
        y = YEARS[i]
        if y < 0: undated += v; continue
        for k, (p0, p1) in enumerate(PERIODS):
            if p0 <= y <= p1: vper[k] += v; break
    r = max(land_c.area - foot, 0.0)
    ha = A / 10000.0
    yrs = np.array([p1 - p0 + 1 for p0, p1 in PERIODS])
    return dict(T=(vol + 0.5 * r) / ha, vol=vol, undated=undated,
                rate=vper / ha / yrs,                 # m3/ha/yr, buildings only
                vper_ha=vper / ha)

# ---- square samples: five locations from the CBD toward the northern periphery ----
SQ_SITES = [("Midtown (CBD)", -73.9800, 40.7540), ("Upper East Side", -73.9560, 40.7745),
            ("East Harlem", -73.9420, 40.7960), ("Hamilton Heights", -73.9480, 40.8240),
            ("Inwood", -73.9185, 40.8675)]
def square(cx, cy, side):
    s = side / 2
    return _rot(Polygon([(cx - s, cy - s), (cx + s, cy - s), (cx + s, cy + s), (cx - s, cy + s)]), -29, origin=(cx, cy))
squares = []
for name, lon, lat in SQ_SITES:
    x, y = proj(lon, lat)
    for size, side in (("big (64 ha)", 800), ("small (9 ha)", 300)):
        m = measure(square(x, y, side)); m.update(site=name, size=size, dist_km=Point(x, y).distance(CBD) / 1000)
        squares.append(m)

# ---- rates for circular samples ----
for s in samples:
    m = measure(s["pt"].buffer(R, 64)); s["rate"] = m["rate"]; s["undated"] = m["undated"]; s["vol"] = m["vol"]

def style(ax):
    ax.spines[["top", "right"]].set_visible(False); ax.set_ylim(0, None)

def save(fig, name):
    fig.tight_layout(); fig.savefig(os.path.join(OUT, name), dpi=170); plt.close(fig)

K = 1000.0
# Fig. 5 – all circular samples
fig, ax = plt.subplots(figsize=(7.5, 5))
x = np.array([s["dist_km"] for s in samples]); y = np.array([s["T"] for s in samples]) / K
ax.scatter(x, y, s=22, c="#d7261e", ec="black", lw=0.3, zorder=3)
b5 = np.polyfit(x, np.log(y), 1); xx = np.linspace(0, x.max(), 100)
ax.plot(xx, np.exp(b5[1] + b5[0] * xx), "k--", lw=1.2, label=f"exponential fit (−{(1-math.exp(b5[0]))*100:.0f}% per km)")
ax.set_xlabel("Distance to CBD (km)"); ax.set_ylabel("Technomass (thousand m³/ha)")
ax.set_title("Fig. 5 (Manhattan). Technomass vs distance to CBD, all circular samples", fontsize=10.5)
ax.legend(frameon=False, fontsize=9); style(ax); save(fig, "fig5_circular_all.png")

# Fig. 6 – transect
fig, ax = plt.subplots(figsize=(7.5, 5))
xs = np.array([s["signed_km"] for s in transect]); ys = np.array([s["T"] for s in transect]) / K; o = np.argsort(xs)
ax.plot(xs[o], ys[o], "-", color="#5fb8c4", lw=1.2); ax.scatter(xs, ys, s=30, c="#5fe0ec", ec="black", lw=0.4, zorder=3)
ax.axvline(0, color="black", lw=0.8)
ax.annotate("Financial District", (xs.min(), ys[o][:4].max()), xytext=(5, 5), textcoords="offset points", fontsize=8.5)
ax.set_xlabel("Distance from CBD along transect (km)   ← south | north →"); ax.set_ylabel("Technomass (thousand m³/ha)")
ax.set_title("Fig. 6 (Manhattan). Technomass along the transect", fontsize=10.5); style(ax); save(fig, "fig6_transect.png")

# Fig. 7 – square samples
fig, ax = plt.subplots(figsize=(7.5, 5))
for size, c, mk in (("big (64 ha)", "#333333", "s"), ("small (9 ha)", "#d7261e", "o")):
    ss = [q for q in squares if q["size"] == size]
    ax.plot([q["dist_km"] for q in ss], [q["T"] / K for q in ss], "-" + mk, color=c, label=f"square samples, {size}", ms=6)
for q in squares:
    if q["size"].startswith("big"):
        ax.annotate(q["site"], (q["dist_km"], q["T"] / K), xytext=(4, 8), textcoords="offset points", fontsize=7.5, color="#444")
ax.set_xlabel("Distance to CBD (km)"); ax.set_ylabel("Technomass (thousand m³/ha)")
ax.set_title("Fig. 7 (Manhattan). Technomass vs distance to CBD, square samples", fontsize=10.5)
ax.legend(frameon=False, fontsize=9); style(ax); save(fig, "fig7_squares.png")

# Fig. 8 – accumulation rate by period, square samples
fig, ax = plt.subplots(figsize=(8.5, 5))
idx = np.arange(len(PERIODS)); w = 0.4
for j, (size, c) in enumerate((("big (64 ha)", "#555555"), ("small (9 ha)", "#d7261e"))):
    rates = np.array([q["rate"] for q in squares if q["size"] == size])
    ax.bar(idx + (j - 0.5) * w, rates.mean(0), w, color=c, label=f"{size}, mean of 5 sites")
    for r in rates: ax.plot(idx + (j - 0.5) * w, r, ".", color="black", ms=3, alpha=0.6)
ax.set_xticks(idx, PLAB, rotation=0, fontsize=8.5)
ax.set_xlabel("Construction period of buildings standing today"); ax.set_ylabel("Accumulation rate (m³/ha/yr)")
ax.set_title("Fig. 8 (Manhattan). Technomass accumulation rate, square samples (dots = individual sites)", fontsize=10.5)
ax.legend(frameon=False, fontsize=9); style(ax); save(fig, "fig8_rate_squares.png")

# Fig. 9 – accumulation rate by period, all circular samples
fig, ax = plt.subplots(figsize=(8.5, 5))
R9 = np.array([s["rate"] for s in samples])
ax.boxplot([R9[:, k] for k in idx], positions=idx, widths=0.55, showfliers=True,
           flierprops=dict(marker=".", ms=3, alpha=0.5), medianprops=dict(color="#d7261e"))
ax.plot(idx, R9.mean(0), "D-", color="black", ms=4, lw=1, label="mean")
ax.set_xticks(idx, PLAB, fontsize=8.5)
cap = np.percentile(R9, 98) * 1.05; nout = int((R9 > cap).sum())
ax.set_ylim(0, cap)
ax.text(0.99, 0.97, f"{nout} extreme values (single towers) above {cap:,.0f} not shown", transform=ax.transAxes,
        ha="right", va="top", fontsize=8, color="#555")
ax.set_xlabel("Construction period of buildings standing today"); ax.set_ylabel("Accumulation rate (m³/ha/yr)")
ax.set_title("Fig. 9 (Manhattan). Technomass accumulation rate, all 150 circular samples", fontsize=10.5)
ax.legend(frameon=False, fontsize=9, loc="upper left"); ax.spines[["top", "right"]].set_visible(False); save(fig, "fig9_rate_circular.png")

# ---- Table 2 analogue + rate summary ----
rows = []
for name, vals in (("Squared small", [q["T"] for q in squares if q["size"].startswith("small")]),
                   ("Squared big", [q["T"] for q in squares if q["size"].startswith("big")]),
                   ("Circular (all)", [s["T"] for s in samples]), ("Circular transect", [s["T"] for s in transect])):
    v = np.array(vals); rows.append((name, v.mean(), v.min(), v.max()))
with open(os.path.join(OUT, "table2_manhattan.csv"), "w", newline="") as f:
    w_ = csv.writer(f); w_.writerow(["samples", "average_m3_ha", "min_m3_ha", "max_m3_ha"])
    for r in rows: w_.writerow([r[0]] + [round(x) for x in r[1:]])
    avg = np.mean([r[1] for r in rows]); w_.writerow(["Total average", round(avg), round(np.mean([r[2] for r in rows])), round(np.mean([r[3] for r in rows]))])
for r in rows: print(f"{r[0]:18s} avg {r[1]:>9,.0f}  min {r[2]:>9,.0f}  max {r[3]:>9,.0f}")
print("square sites:", [(q['site'], q['size'][:3], round(q['T']), round(q['dist_km'], 1)) for q in squares])
print("circular mean rate by period:", dict(zip(PLAB, R9.mean(0).round(0))))
print("undated share of building volume:", round(sum(s['undated'] for s in samples) / sum(s['vol'] for s in samples) * 100, 1), "%")

# ---------------- Fig. 4 – spatial distribution of the square samples ----------------
from matplotlib.colors import BoundaryNorm as _BN, ListedColormap as _LC
_bounds = [0, 10, 20, 40, 80, 150, 500]
_cols = ["#f6dcc6", "#f0bb97", "#e79a72", "#d9724f", "#c9462f", "#a8141a"]
_cmap, _norm = _LC(_cols), _BN(_bounds, len(_cols))

fig = plt.figure(figsize=(14, 11.5))
axM = fig.add_axes([0.02, 0.07, 0.30, 0.88])
axM.add_collection(PatchCollection(poly_patches(polys), facecolor="#8a8a8a", edgecolor="none", zorder=2))
draw_outline(axM, land, color="black", lw=1.0, zorder=3)
site_xy = []
for k, (name, lon, lat) in enumerate(SQ_SITES):
    x, y = proj(lon, lat); site_xy.append((x, y))
    axM.add_patch(MPoly(np.asarray(square(x, y, 800).exterior.coords), fill=False, ec="black", lw=1.6, zorder=6))
    axM.add_patch(MPoly(np.asarray(square(x, y, 300).exterior.coords), fc="#d7261e", ec="black", lw=0.6, zorder=7))
    axM.text(x + 650, y, str(k + 1), fontsize=12, fontweight="bold", va="center", zorder=8,
             bbox=dict(fc="white", ec="black", lw=0.6, pad=2))
mx0, my0, mx1, my1 = land.bounds
axM.set_xlim(mx0 - 700, mx1 + 1200); axM.set_ylim(my0 - 1600, my1 + 500)
axM.set_aspect("equal"); axM.set_xticks([]); axM.set_yticks([])
scalebar(axM, mx0 - 400, my0 - 1200, [0, 1, 2, 4], 130); north(axM, mx1 + 500, my0 - 900, 600)

# close-ups
slots = [(0.35, 0.53), (0.57, 0.53), (0.79, 0.53), (0.35, 0.07), (0.57, 0.07)]
for k, ((name, lon, lat), (sx, sy)) in enumerate(zip(SQ_SITES, slots)):
    ax = fig.add_axes([sx, sy, 0.20, 0.40])
    x, y = site_xy[k]; half = 560
    win = box(x - half, y - half * 1.25, x + half, y + half * 1.25)
    ax.add_collection(PatchCollection(poly_patches([win.difference(land)]), fc="#c9d6e0", ec="none", zorder=0))
    ax.set_facecolor("#ecebe6")
    ids = tree.query(win)
    col = PatchCollection([], cmap=_cmap, norm=_norm, ec="#6b4a3a", lw=0.15, zorder=2)
    parts, hs = [], []
    for i in ids:
        pp = poly_patches([polys[i]]); parts += pp; hs += [heights[i]] * len(pp)
    col = PatchCollection(parts, cmap=_cmap, norm=_norm, ec="#6b4a3a", lw=0.15, zorder=2); col.set_array(np.array(hs))
    ax.add_collection(col)
    ax.add_patch(MPoly(np.asarray(square(x, y, 800).exterior.coords), fill=False, ec="black", lw=1.8, zorder=5))
    ax.add_patch(MPoly(np.asarray(square(x, y, 300).exterior.coords), fill=False, ec="#d7261e", lw=2.0, zorder=6))
    big = [q for q in squares if q["site"] == name and q["size"].startswith("big")][0]
    sm = [q for q in squares if q["site"] == name and q["size"].startswith("small")][0]
    ax.set_xlim(x - half, x + half); ax.set_ylim(y - half * 1.25, y + half * 1.25)
    ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
    ax.set_title(f"{k+1}. {name}  ({big['dist_km']:.1f} km)", fontsize=9.5)
    ax.text(0.03, 0.03, f"big: {big['T']/1000:,.0f}k m³/ha\nsmall: {sm['T']/1000:,.0f}k m³/ha", transform=ax.transAxes,
            fontsize=8, va="bottom", zorder=10, bbox=dict(fc="white", ec="none", alpha=0.9, pad=2))
# legend panel
axL4 = fig.add_axes([0.79, 0.07, 0.20, 0.40]); axL4.axis("off")
axL4.text(0.05, 0.95, "Buildings\nheight  m", fontsize=12, fontweight="bold", va="top")
for j, (c, lab) in enumerate(zip(_cols, ["0 – 10", "10 – 20", "20 – 40", "40 – 80", "80 – 150", "150 +"])):
    yy = 0.72 - j * 0.075
    axL4.add_patch(Rectangle((0.05, yy), 0.18, 0.055, fc=c, ec="#777", lw=0.4, transform=axL4.transAxes))
    axL4.text(0.28, yy + 0.027, lab, va="center", fontsize=9.5, transform=axL4.transAxes)
axL4.add_patch(Rectangle((0.05, 0.19), 0.18, 0.055, fill=False, ec="black", lw=1.8, transform=axL4.transAxes))
axL4.text(0.28, 0.217, "big square (64 ha)", va="center", fontsize=9.5, transform=axL4.transAxes)
axL4.add_patch(Rectangle((0.05, 0.10), 0.18, 0.055, fill=False, ec="#d7261e", lw=2.0, transform=axL4.transAxes))
axL4.text(0.28, 0.127, "small square (9 ha)", va="center", fontsize=9.5, transform=axL4.transAxes)
fig.text(0.5, 0.02, "Fig. 4 (Manhattan). Spatial distribution of the square samples: big (64 ha) and small (9 ha) squares at five "
         "locations\nat increasing distance from the Midtown CBD. Data: NYC Building Footprints (NYC Open Data).",
         ha="center", fontsize=9.5)
fig.savefig(os.path.join(OUT, "fig4_square_samples.png"), dpi=170); plt.close(fig)
print("fig4 done")
