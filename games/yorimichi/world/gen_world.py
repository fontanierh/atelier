import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parent)); import yori  # noqa: E402,F401
#!/usr/bin/env python3
"""World generator for the demo slice (numpy only) -> build/yorimichi/world.json + heightmap.npy

Metres, Z up, X east, Y north (Blender frame; the Unreal loader flips Y). 600 x 600 m map
centred on the origin: sea to the south-west, a ridge rising to ~60 m in the north-east, and a
narrow road climbing along the hillside from a shore hamlet to a shrine knoll. Places poles
(with wire anchors), guardrail, trees by biome, bushes, grass, lanterns, a torii and houses.
"""
import os, json, math
import numpy as np
from PIL import Image

HERE = str(yori.WORLD)
OUT = str(yori.OUT)
os.makedirs(OUT, exist_ok=True)
SIZE = 600.0; N = 301; STEP = SIZE / (N - 1)
rng = np.random.default_rng(3)
RNGS = {k: np.random.default_rng(100 + i) for i, k in enumerate(["houses", "poles", "trees", "bushes", "bank", "rocks", "grass", "far", "litter"])}
def use(k):
    global rng
    rng = RNGS[k]


def fbm(n, scale, octaves, seed):
    r = np.random.default_rng(seed); out = np.zeros((n, n), np.float32); amp = 1.0; tot = 0.0
    for o in range(octaves):
        c = max(2, int(scale * 2 ** o)); g = r.random((c, c)).astype(np.float32)
        out += np.asarray(Image.fromarray((g * 255).astype(np.uint8)).resize((n, n), Image.BICUBIC), np.float32) / 255 * amp
        tot += amp; amp *= 0.5
    return out / tot


def smooth(t):
    t = np.clip(t, 0, 1); return t * t * (3 - 2 * t)


# ------------------------------------------------------------------ terrain
xs = np.linspace(-SIZE / 2, SIZE / 2, N); X, Y = np.meshgrid(xs, xs)          # H[j, i] at (xs[i], xs[j])
coast = 50 * (fbm(N, 2, 2, 4) - 0.5)
t = (Y + 150 + coast) / 380
H = np.where(t > 0, 2 + 66 * np.clip(t, 0, 1) ** 1.4, 2 + 90 * t)
H += 20 * (fbm(N, 3, 4, 1) - 0.5) * (0.25 + 0.75 * np.clip(t, 0, 1)) + 6 * (fbm(N, 9, 3, 2) - 0.5)
H += 12 * smooth((t - 0.7) / 0.3) * (fbm(N, 5, 2, 3) - 0.3)              # rougher crest
SHRINE = (200, 85)
knoll = np.exp(-(((X - SHRINE[0]) ** 2 + (Y - SHRINE[1]) ** 2) / (2 * 30 ** 2)))
H += 9 * knoll


def sample_h(x, y):
    fx = (x + SIZE / 2) / STEP; fy = (y + SIZE / 2) / STEP
    i = int(np.clip(fx, 0, N - 2)); j = int(np.clip(fy, 0, N - 2)); u = fx - i; v = fy - j
    return (H[j, i] * (1 - u) * (1 - v) + H[j, i + 1] * u * (1 - v) + H[j + 1, i] * (1 - u) * v + H[j + 1, i + 1] * u * v)


# ------------------------------------------------------------------ road (Catmull-Rom, 1 m samples)
CP = [(-295, -95), (-230, -100), (-170, -85), (-110, -70), (-50, -70), (10, -45), (70, -30), (130, -25), (190, -5), (240, 25), (295, 60)]
pts = []
P = [CP[0]] + CP + [CP[-1]]
for k in range(1, len(P) - 2):
    p0, p1, p2, p3 = (np.array(P[k + d], float) for d in (-1, 0, 1, 2))
    for s in np.linspace(0, 1, 60, endpoint=False):
        pts.append(0.5 * ((2 * p1) + (-p0 + p2) * s + (2 * p0 - 5 * p1 + 4 * p2 - p3) * s * s + (-p0 + 3 * p1 - 3 * p2 + p3) * s ** 3))
pts = np.array(pts)
seg = np.linalg.norm(np.diff(pts, axis=0), axis=1); arc = np.concatenate([[0], np.cumsum(seg)])
L = arc[-1]; S = np.arange(0, L, 1.0)
RX = np.interp(S, arc, pts[:, 0]); RY = np.interp(S, arc, pts[:, 1])
RZraw = np.array([sample_h(x, y) for x, y in zip(RX, RY)])
# gentle profile: heavy smoothing, then limit the grade to 9 %
k = 90; ker = np.ones(k) / k
RZ = np.convolve(np.pad(RZraw, (k // 2, k - k // 2 - 1), mode="edge"), ker, mode="valid")
RZ = np.maximum(RZ, 1.8)
for i in range(1, len(RZ)):
    RZ[i] = min(RZ[i], RZ[i - 1] + 0.09)
for i in range(len(RZ) - 2, -1, -1):
    RZ[i] = min(RZ[i], RZ[i + 1] + 0.09)
TX = np.gradient(RX); TY = np.gradient(RY); tn = np.hypot(TX, TY); TX /= tn; TY /= tn
NX, NY = -TY, TX                                                                # left normal (uphill side is +left here: ridge is NE, road runs SW->NE, left = NW)
# which side is uphill? sample terrain 12 m either side
up_left = np.array([sample_h(x + nx * 12, y + ny * 12) - sample_h(x - nx * 12, y - ny * 12) for x, y, nx, ny in zip(RX, RY, NX, NY)])
UP = np.sign(np.convolve(np.pad(up_left, 20, mode="edge"), np.ones(41) / 41, mode="valid")); UP[UP == 0] = 1

# cut the road into the terrain: every cell takes its target height from its NEAREST road sample
# (blending per sample in sequence let the last sample win, which buried the strip on grades)
D = np.full((N, N), 1e9, np.float32); NEAR = np.zeros((N, N), np.int32)
for i in range(0, len(S), 1):
    x, y = RX[i], RY[i]
    i0 = int((x + SIZE / 2) / STEP); j0 = int((y + SIZE / 2) / STEP); r = int(20 / STEP) + 1
    sl = (slice(max(0, j0 - r), min(N, j0 + r + 1)), slice(max(0, i0 - r), min(N, i0 + r + 1)))
    d = np.hypot(X[sl] - x, Y[sl] - y)
    closer = d < D[sl]
    D[sl] = np.where(closer, d, D[sl]); NEAR[sl] = np.where(closer, i, NEAR[sl])
mask = D < 18.5
w = smooth((18 - D) / 12.5)
ni = NEAR
side = ((X - RX[ni]) * NX[ni] + (Y - RY[ni]) * NY[ni]) * UP[ni]
target = RZ[ni] + np.where(side > 3.2, (side - 3.2) * 1.1, np.where(side < -3.2, (side + 3.2) * 0.7, 0.0))      # steep earth bank uphill
H = np.where(mask, H * (1 - w) + target * w, H)

# flat pads: shrine knoll and two house lots
def flatten(cx, cy, r, z=None):
    d = np.hypot(X - cx, Y - cy); w = smooth((r + 8 - d) / 8)
    zz = sample_h(cx, cy) if z is None else z
    H[:] = H * (1 - w) + zz * w
    return zz

SLOPE = np.hypot(*np.gradient(H, STEP))

# ------------------------------------------------------------------ placements
inst = {}
def put(name, x, y, z=None, yaw=None, scale=1.0):
    inst.setdefault(str(name), []).append([round(float(x), 2), round(float(y), 2), round(float(sample_h(x, y) if z is None else z), 2),
                                      round(float(rng.uniform(0, 360) if yaw is None else yaw), 1), round(float(scale), 3)])

def road_frame(s):
    i = int(np.clip(s, 0, len(S) - 1)); return RX[i], RY[i], RZ[i], TX[i], TY[i], NX[i] * UP[i], NY[i] * UP[i]

def dist_road(x, y):
    i = int(np.clip((x + SIZE / 2) / STEP, 0, N - 1)); j = int(np.clip((y + SIZE / 2) / STEP, 0, N - 1)); return D[j, i]

def slope(x, y):
    i = int(np.clip((x + SIZE / 2) / STEP, 0, N - 1)); j = int(np.clip((y + SIZE / 2) / STEP, 0, N - 1)); return SLOPE[j, i]

use("houses")
# houses at the shore end (downhill side), shrine on the knoll
houses = []
for s, side in ((96, -1), (150, -1), (185, +1), (300, -1), (338, +1)):
    x, y, z, tx, ty, ux, uy = road_frame(s)
    hx, hy = x + ux * side * 11, y + uy * side * 11
    hz = flatten(hx, hy, 7.5, z - 0.4 if side < 0 else z + 0.6)
    yaw = math.degrees(math.atan2(ty, tx)) + (90 if side < 0 else -90)
    houses.append((hx, hy, hz, yaw))
sz = flatten(*SHRINE, 16)
SLOPE = np.hypot(*np.gradient(H, STEP))
for (hx, hy, hz, yaw) in houses:
    put("House", hx, hy, hz, yaw)
    for k in range(3):                                   # tall pines and a maple behind each house
        a = math.radians(yaw + 180 + rng.uniform(-50, 50)); rr = rng.uniform(7, 11)
        px_, py_ = hx + math.cos(a) * rr, hy + math.sin(a) * rr
        put("Tree_Pine_A" if k < 2 else "Tree_Maple_A", px_, py_, sample_h(px_, py_) - 0.15, scale=rng.uniform(1.0, 1.3))
    put("Lantern", hx + math.cos(math.radians(yaw)) * 5.5, hy + math.sin(math.radians(yaw)) * 5.5, sample_h(hx, hy), yaw)
put("Torii", SHRINE[0] - 14, SHRINE[1] - 6, sz, 25)
# Keep the pair on the flat knoll, flanking the approach behind the gate.
# The former positions were outside the plateau and floated 2–6 metres.
for side in (-1, 1):
    a=math.radians(25)
    lx=SHRINE[0]-14+3*math.cos(a)-side*3*math.sin(a)
    ly=SHRINE[1]-6+3*math.sin(a)+side*3*math.cos(a)
    put("Lantern", lx, ly, sz, 25)
for dx, dy in ((6, 4), (12, -4), (2, 10)):
    put("Tree_Pine_A", SHRINE[0] + dx, SHRINE[1] + dy, sz, scale=1.1)

use("poles")
# poles every 30 m on the uphill side, every third with a lamp; wire anchors per pole
poles = []
for s in np.arange(12, L - 10, 30):
    x, y, z, tx, ty, ux, uy = road_frame(s)
    px, py = x + ux * 4.3, y + uy * 4.3
    yaw = math.degrees(math.atan2(ty, tx))
    lamp = (len(poles) % 3 == 1)
    put("Pole_Lamp" if lamp else "Pole", px, py, sample_h(px, py), yaw)
    poles.append((px, py, sample_h(px, py), yaw))
anchors = []          # per pole: list of (x, y, z) wire attach points
for (px, py, pz, yaw) in poles:
    a = math.radians(yaw); nx, ny = -math.sin(a), math.cos(a)        # pole local +Y (crossarm direction)
    pts_ = []
    for (off, zz) in ((-1.05, 10.58), (0.0, 10.58), (1.05, 10.58), (-0.85, 9.68), (0.85, 9.68)):
        pts_.append([round(px + nx * off, 3), round(py + ny * off, 3), round(pz + zz, 3)])
    anchors.append(pts_)

# guardrail line on the downhill side where the drop is real: contiguous runs at 1 m, built as one mesh in build_terrain
rail_runs = []; cur = []
for s in np.arange(1, L - 1, 1.0):
    x, y, z, tx, ty, ux, uy = road_frame(s)
    drop = z - sample_h(x - ux * 9, y - uy * 9)
    if drop > 1.2:
        cur.append([round(float(x - ux * 3.1), 3), round(float(y - uy * 3.1), 3), round(float(z), 3), round(float(-ux), 4), round(float(-uy), 4)])
    elif cur:
        if len(cur) > 6: rail_runs.append(cur)
        cur = []
if len(cur) > 6: rail_runs.append(cur)

# vegetation: jittered grid + rejection by masks
def scatter(spacing, fn, jitter=0.45):
    for gy in np.arange(-SIZE / 2 + 5, SIZE / 2 - 5, spacing):
        for gx in np.arange(-SIZE / 2 + 5, SIZE / 2 - 5, spacing):
            x = gx + rng.uniform(-jitter, jitter) * spacing; y = gy + rng.uniform(-jitter, jitter) * spacing
            h = sample_h(x, y)
            if h < 1.2: continue
            fn(x, y, h, dist_road(x, y), slope(x, y))

def trees(x, y, h, d, sl):
    if d < 8.5 or sl > 1.6: return
    if any(math.hypot(x - hx, y - hy) < 12 for hx, hy, _, _ in houses): return
    if math.hypot(x - SHRINE[0], y - SHRINE[1]) < 18: return
    r = rng.random()
    if d < 26:                       # roadside: pines, maples, ginkgo
        if r > 0.8: return
        name = rng.choice(["Tree_Pine_A", "Tree_Pine_B", "Tree_Maple_A", "Tree_Maple_B", "Tree_Broad_A", "Tree_Ginkgo"], p=[0.12, 0.05, 0.16, 0.08, 0.38, 0.21])
    elif h > 30:                     # upper slopes: cedar forest with maples in it
        if r > 0.95: return
        name = rng.choice(["Tree_Cedar_A", "Tree_Cedar_B", "Tree_Pine_A", "Tree_Maple_A", "Tree_Maple_B", "Tree_Broad_B", "Tree_Ginkgo"], p=[0.04, 0.02, 0.06, 0.36, 0.14, 0.2, 0.18])
    else:
        if r > 0.85: return
        name = rng.choice(["Tree_Broad_A", "Tree_Broad_B", "Tree_Maple_A", "Tree_Maple_B", "Tree_Ginkgo", "Tree_Pine_A", "Tree_Cedar_B"], p=[0.12, 0.08, 0.28, 0.14, 0.14, 0.2, 0.04])
    if d > 90 and name.startswith(("Tree_Maple", "Tree_Ginkgo", "Tree_Broad")):
        name = {"Tree_Maple": "Tree_Maple_lo", "Tree_Ginkgo": "Tree_Ginkgo_lo", "Tree_Broad": "Tree_Broad_lo"}[name[:name.index("_", 5)] if name.count("_") > 1 else name]
    put(name, x, y, h - 0.15, scale=rng.uniform(0.85, 1.25) * (1.25 if d > 26 else 1.0))     # bigger crowns away from the road: the canopy closes
    if name.startswith("Tree_Maple") or name.startswith("Tree_Ginkgo"):
        for _ in range(4):
            a = rng.uniform(0, 2 * math.pi); rr = rng.uniform(0.5, 3.2)
            lx, ly = x + math.cos(a) * rr, y + math.sin(a) * rr
            put("Litter", lx, ly, sample_h(lx, ly) + 0.02, scale=rng.uniform(0.8, 1.3))
use("trees"); scatter(5.0, trees)

def far_trees(x, y, h, d, sl):
    if d < 95 or sl > 1.6 or rng.random() > 0.6: return
    if math.hypot(x - SHRINE[0], y - SHRINE[1]) < 18: return
    name = rng.choice(["Tree_Maple_lo", "Tree_Broad_lo", "Tree_Ginkgo_lo", "Tree_Cedar_B", "Tree_Pine_B"], p=[0.48, 0.18, 0.12, 0.08, 0.14])
    put(name, x, y, h - 0.15, scale=rng.uniform(0.9, 1.3))
use("far"); scatter(3.2, far_trees, jitter=0.5)

def bushes(x, y, h, d, sl):
    if d < 4.3 or sl > 1.8: return
    p = 0.9 if d < 9 else (0.35 if d < 40 else 0.08)
    if rng.random() > p: return
    near_house = any(math.hypot(x - hx, y - hy) < 14 for hx, hy, _, _ in houses)
    if near_house and rng.random() < 0.5:
        name = rng.choice(["Bush_Flower_A", "Bush_Flower_B"])
    else:
        name = rng.choice(["Bush_Green_A", "Bush_Green_B", "Bush_Ochre_A", "Bush_Ochre_B", "Bush_Flower_A", "Bush_Flower_B"], p=[0.36, 0.24, 0.13, 0.09, 0.11, 0.07])
    put(name, x, y, h - 0.1, scale=rng.uniform(0.6, 0.95) if d < 6.5 else rng.uniform(0.8, 1.3))
use("bushes"); scatter(2.4, bushes)

use("bank")
# the uphill bank: thick golden grass and small bushes on the cut slope
for s_ in np.arange(2, L - 2, 1.0):
    x, y, z, tx, ty, ux, uy = road_frame(s_)
    for off in (3.5, 4.8, 6.3, 8.0):
        bx, by = x + ux * off + rng.uniform(-0.3, 0.3), y + uy * off + rng.uniform(-0.3, 0.3)
        if sample_h(bx, by) - z < 0.3 and off > 5: continue
        put("Grass_A" if rng.random() < 0.5 else "Grass_B", bx, by, sample_h(bx, by) - 0.03, scale=rng.uniform(1.4, 1.9))
    if rng.random() < 0.25:
        off = rng.uniform(4.5, 8.5); bx, by = x + ux * off, y + uy * off
        put(rng.choice(["Bush_Green_B", "Bush_Ochre_B", "Bush_Flower_B"]), bx, by, sample_h(bx, by) - 0.1, scale=rng.uniform(0.6, 1.0))

use("rocks")
# rocks and boulders on the uphill bank of the road
for s_ in np.arange(6, L - 6, 3.0):
    if rng.random() > 0.6: continue
    x, y, z, tx, ty, ux, uy = road_frame(s_)
    off = rng.uniform(3.9, 8.0); rx, ry = x + ux * off, y + uy * off
    if sample_h(rx, ry) - z < 0.6: continue
    put(rng.choice(["Rock_A", "Rock_B", "Rock_C"]), rx, ry, sample_h(rx, ry) - 0.45, scale=rng.uniform(0.45, 0.9))

def grass(x, y, h, d, sl):
    if d < 3.2: return
    p = 1.0 if d < 40 else (0.4 if d < 90 else 0.08)
    if rng.random() > p: return
    put("Grass_A" if rng.random() < 0.5 else "Grass_B", x, y, h - 0.03, scale=rng.uniform(0.7, 1.25) * (1.25 if d < 6 else 1.0))
use("grass"); scatter(0.85, grass, jitter=0.5)

# player start on the road near the shore, facing up the road; camera shots along the road
x, y, z, tx, ty, ux, uy = road_frame(40)
player_start = [round(x, 2), round(y, 2), round(z + 1.0, 2), round(math.degrees(math.atan2(ty, tx)), 1)]
shots = []
for frac in (0.08, 0.3, 0.5, 0.7, 0.88):
    x, y, z, tx, ty, ux, uy = road_frame(frac * L)
    shots.append([round(x - tx * 2, 2), round(y - ty * 2, 2), round(z + 1.7, 2), round(math.degrees(math.atan2(ty, tx)), 1), -4.0])
    x2, y2, z2, tx2, ty2, ux2, uy2 = road_frame(frac * L + 40)
    shots.append([round(x - ux * 4, 2), round(y - uy * 4, 2), round(z + 1.7, 2), round(math.degrees(math.atan2(y2 - y, x2 - x)), 1), -3.0])
shots.append([SHRINE[0] - 6, SHRINE[1] - 9, sz + 1.7, -100.0, -8.0])                 # from the shrine over the sea
x, y, z, tx, ty, ux, uy = road_frame(0.45 * L)
shots.append([round(x - tx * 90, 2), round(y - ty * 90, 2), round(z + 88, 2), round(math.degrees(math.atan2(ty, tx)) + 20, 1), -12.0])   # bird's eye toward the hills, sky in frame

shots.append([round(x, 2), round(y, 2), round(z + 1.7, 2), 0.0, 55.0])                      # straight up: sky check
hx, hy, hz, hyaw = houses[0]
x, y, z, tx, ty, ux, uy = road_frame(96)                                                       # from the road, looking at the first house's front
shots.append([round(x + tx * 4, 2), round(y + ty * 4, 2), z + 4.5, round(math.degrees(math.atan2(hy - y, hx - x)), 1), -10.0])   # house from the road, roof in view
x, y, z, tx, ty, ux, uy = road_frame(0.2 * L)
shots.append([round(x, 2), round(y, 2), round(z + 1.7, 2), round(math.degrees(math.atan2(uy, ux)), 1), 14.0])          # looking up the bank at the trees
use("far")
# far hills ring (out to 3.2 km, open sea to the south) + cheap trees on its near part for silhouettes
FN = 96; FSZ = 6400.0; FSTEP = FSZ / (FN - 1)
fx_ = np.linspace(-FSZ / 2, FSZ / 2, FN); FX, FY = np.meshgrid(fx_, fx_)
FH1 = fbm(FN, 3, 4, 3); FH2 = fbm(FN, 7, 3, 5)
fdist = np.maximum(np.abs(FX), np.abs(FY))
framp = np.clip((fdist - 280) / 300, 0, 1); fnorth = np.clip((FY + 100) / 1500, 0, 1); fland = np.clip((FY + 60) / 260, 0, 1)
finner = 70 * fland - 30 * (1 - fland)                                   # continue the playable terrain's north edge (~70 m), sea to the south
FZ = framp * fland * (60 + 140 * FH1 * (0.4 + 0.6 * fnorth) + 40 * FH2 + 70 * fnorth) + (1 - framp * fland) * finner
FZ = np.where(fdist < 290, -30.0, FZ)
np.save(os.path.join(OUT, "farhills.npy"), FZ.astype(np.float32))
def far_h(x, y):
    fx = (x + FSZ / 2) / FSTEP; fy = (y + FSZ / 2) / FSTEP
    i = int(np.clip(fx, 0, FN - 2)); j = int(np.clip(fy, 0, FN - 2)); u = fx - i; v = fy - j
    return FZ[j, i] * (1 - u) * (1 - v) + FZ[j, i + 1] * u * (1 - v) + FZ[j + 1, i] * (1 - u) * v + FZ[j + 1, i + 1] * u * v
for gy in np.arange(-1300, 2600, 11.0):
    for gx in np.arange(-2600, 2600, 11.0):
        x = gx + rng.uniform(-6, 6); y = gy + rng.uniform(-6, 6)
        if max(abs(x), abs(y)) < 300: continue
        h = far_h(x, y)
        if h < 1 or rng.random() > 0.75: continue
        name = rng.choice(["Tree_Maple_lo", "Tree_Broad_lo", "Tree_Cedar_B", "Tree_Pine_B", "Tree_Ginkgo_lo"], p=[0.5, 0.14, 0.08, 0.14, 0.14])
        put(name, x, y, h - 0.3, scale=rng.uniform(2.0, 3.2) * (1.0 if max(abs(x), abs(y)) > 700 else 0.75))

road = [[round(float(a), 2), round(float(b), 2), round(float(c), 2)] for a, b, c in zip(RX, RY, RZ)]
world = {"size": SIZE, "n": N, "sea_level": 0.0, "wind_dir": [0.30, 0.95], "wind_speed": 3.5, "rail_runs": rail_runs, "road": road, "road_width": 5.2, "anchors": anchors,
         "instances": inst, "player_start": player_start, "shots": shots}
from village.layout import integrate
integrate(world, H)
from mega.layout import integrate as integrate_mega
integrate_mega(world, H)
from southwest.layout import integrate as integrate_southwest
integrate_southwest(world, H)
from forest_lake.layout import integrate as integrate_forest_lake
integrate_forest_lake(world, H)
from zeppelin.layout import integrate as integrate_zeppelin
integrate_zeppelin(world, H)
from house_clearance import clear_house_vegetation
clear_house_vegetation(world)
from torii_clearance import clear_torii_vegetation
clear_torii_vegetation(world)
np.save(os.path.join(OUT, "heightmap.npy"), H.astype(np.float32))
H.astype("<f4").tofile(os.path.join(OUT, "heightmap.bin"))  # runtime cosmetic-particle ground sampling
with open(os.path.join(OUT, "world.json"), "w") as fh:
    json.dump(world, fh)
counts = {k: len(v) for k, v in inst.items()}
print("road length %.0f m, z %.1f -> %.1f" % (L, RZ[0], RZ[-1]))
print("instances:", counts, "total", sum(counts.values()))
print("heightmap min %.1f max %.1f" % (H.min(), H.max()))
# quick map preview
img = np.clip((H + 20) / 100, 0, 1)
rgb = np.stack([img, img, img], -1)
sea = H < 0; rgb[sea] = [0.3, 0.45, 0.6]
rgb[D < 2.6] = [0.2, 0.2, 0.2]
Image.fromarray((rgb[::-1] * 255).astype(np.uint8)).resize((600, 600)).save(os.path.join(OUT, "map_preview.png"))
