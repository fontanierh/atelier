"""In-game world map: a label-free top-down texture of the whole playable world plus the teleport zones.

    python games/yorimichi/world/map/build_map.py [--data build/yorimichi] [--out build/yorimichi/map]

Writes map.png (game texture), map.jpg (phone page) and map.json (bounds, pixel scale, zones). Everything is drawn
from the generated data (world.json, heightmap.npy, farhills.npy, hidamari/city.json and the island/city height
functions), never from screenshots or hand placement, so positions match the game exactly. Zones are the teleport
targets: each one is snapped to a walkable polyline (road, lane, route or stair) so the player lands on paved ground.
Coordinates are Blender metres (x east, y north); the runtime converts to Unreal. See docs/WORLD_MAP.md.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[1])); import yori  # noqa: E402,F401
import argparse, json, math, os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = str(yori.WORLD)
ap = argparse.ArgumentParser()
ap.add_argument('--data', default=str(yori.OUT))
ap.add_argument('--out', default=str(yori.OUT / 'map'))
ap.add_argument('--px', type=float, default=2.0, help='pixels per metre')
A = ap.parse_args()
S = A.data
W = json.load(open(f'{S}/world.json'))
CITY_PATH = f'{S}/hidamari/city.json'
C = json.load(open(CITY_PATH)) if os.path.exists(CITY_PATH) else None
H = np.load(f'{S}/heightmap.npy').astype(np.float32)
SIZE = W['size']
NORTH = C.get('north_bounds') if C else None
PX = min(A.px,1.0) if NORTH else A.px
from map_projection import X_KNOTS,Y_KNOTS,BOUNDS,project,unproject
# the sheet: the 600 m square, the island to the south and Hidamari to the east, with a margin of sea and hills
X0, X1 = -330.0, (1330.0 if C else 330.0)
Y0 = -650.0; Y1 = (Y0 + (X1 - X0) * 2 / 3) if C else 330.0   # 3:2 sheet, the aspect gpt-image-2 paints at (1536 x 1024)
if NORTH:X0,Y0,X1,Y1=BOUNDS
MW, MH = int((X1 - X0) * PX), int((Y1 - Y0) * PX)

def wp(x, y):
    """world metres -> image pixels (north up)"""
    return ((project(x,X_KNOTS) if NORTH else x) - X0) * PX, (Y1 - (project(y,Y_KNOTS) if NORTH else y)) * PX

def bilinear(grid, fx, fy):
    """grid[row, col] sampled at fractional (col=fx, row=fy), clamped"""
    n1, n0 = grid.shape[1] - 1, grid.shape[0] - 1
    fx = np.clip(fx, 0, n1 - 1e-3); fy = np.clip(fy, 0, n0 - 1e-3)
    i = fx.astype(int); j = fy.astype(int); u = fx - i; v = fy - j
    return (grid[j, i] * (1 - u) + grid[j, i + 1] * u) * (1 - v) + (grid[j + 1, i] * (1 - u) + grid[j + 1, i + 1] * u) * v

# ---------- height raster over the whole sheet
xs = X0 + (np.arange(MW) + .5) / PX
ys = Y1 - (np.arange(MH) + .5) / PX
GX, GY = np.meshgrid(unproject(xs,X_KNOTS) if NORTH else xs, unproject(ys,Y_KNOTS) if NORTH else ys)
try:
    from hidamari import layout as CITY
    Z = CITY.backdrop_height(GX, GY).astype(np.float32)        # far hills with the city transition applied
except Exception as e:  # noqa: BLE001
    print('city height helpers unavailable:', e); CITY = None
    FZ = np.load(f'{S}/farhills.npy').astype(np.float32)
    Z = bilinear(FZ, (GX + 3200) / 6400 * (FZ.shape[1] - 1), (GY + 3200) / 6400 * (FZ.shape[0] - 1)).astype(np.float32)
square = (np.abs(GX) <= SIZE / 2) & (np.abs(GY) <= SIZE / 2)
Z[square] = bilinear(H, (GX[square] + SIZE / 2) / SIZE * (H.shape[1] - 1), (GY[square] + SIZE / 2) / SIZE * (H.shape[0] - 1))
if C and CITY:
    bx0, by0, bx1, by1 = C['bounds']
    inside = (GX >= bx0) & (GY >= by0) & (GX <= bx1) & (GY <= by1) & ~square
    Z[inside] = CITY.height(GX[inside], GY[inside])
if NORTH and CITY:
    mask=(GX>=NORTH[0])&(GX<=NORTH[2])&(GY>=NORTH[1])&(GY<=NORTH[3])
    Z[mask]=CITY.north_height(GX[mask],GY[mask])
# the island lives outside the heightmap: sample its own height function in island-local coordinates
SW = W.get('southwest')
if SW:
    from southwest import island as ISL
    ox, oy, _ = SW['island']['origin']; ya = math.radians(SW['island']['yaw']); ca, sa = math.cos(ya), math.sin(ya)
    LX = (GX - ox) * ca + (GY - oy) * sa; LY = -(GX - ox) * sa + (GY - oy) * ca
    rr = np.sqrt((LX / (ISL.SIZE[0] * .55)) ** 2 + (LY / (ISL.SIZE[1] * .55)) ** 2)
    isl = rr < 1.15
    iz = ISL.height(LX[isl], LY[isl]).astype(np.float32)
    wgt = np.clip((1.15 - rr[isl]) / .15, 0, 1)
    Z[isl] = np.maximum(Z[isl], iz * wgt + Z[isl] * (1 - wgt))
    def island_world(lx, ly):
        return ox + lx * ca - ly * sa, oy + lx * sa + ly * ca

# the sea: one depth field from the distance to land, so the square, the city and the backdrop seas match at their seams
land = (Z >= 0).astype(np.float32)
near = np.array(Image.fromarray((land * 255).astype(np.uint8), 'L').filter(ImageFilter.GaussianBlur(28 * PX))).astype(np.float32) / 255
Z = np.where(Z < 0, np.minimum(Z, -1.5 - 30.0 * (1 - near) ** 1.6), Z).astype(np.float32)
# the playable world: the square, the city, the island and the sea; everything else is scenery and fades to paper
playable = square | (Z < 0)
if C: playable |= (GX >= C['bounds'][0]) & (GY >= C['bounds'][1]) & (GX <= C['bounds'][2]) & (GY <= C['bounds'][3])
if NORTH: playable |= (GX>=NORTH[0])&(GX<=NORTH[2])&(GY>=NORTH[1])&(GY<=NORTH[3])
if SW: playable |= isl
fade = np.array(Image.fromarray((playable * 255).astype(np.uint8), 'L').filter(ImageFilter.GaussianBlur(6 * PX))).astype(np.float32) / 255

def hillshade(z, az=315, alt=42):
    gy, gx = np.gradient(z * PX)     # metres per pixel -> slope
    a, e = math.radians(az), math.radians(alt)
    nx, ny, nz = -gx, -gy, np.ones_like(z); L = np.sqrt(nx * nx + ny * ny + nz * nz)
    return np.clip((nx * math.cos(e) * math.sin(a) + ny * math.cos(e) * math.cos(a) + nz * math.sin(e)) / L, 0, 1)
sh = hillshade(Z)
def ramp(z):
    stops = [(-40, (44, 78, 120)), (-8, (78, 126, 166)), (-1.5, (126, 172, 196)), (0, (176, 204, 208)), (0.01, (222, 206, 164)),
             (2.5, (200, 208, 146)), (12, (172, 192, 122)), (30, (148, 170, 106)), (60, (140, 152, 104)), (95, (166, 158, 138)), (130, (145, 162, 125)), (330, (130, 153, 156)), (480, (157, 174, 196)), (620, (229, 235, 235)), (1000, (251, 249, 238))]
    out = np.zeros(z.shape + (3,), np.float32)
    for (a, ca_), (b, cb) in zip(stops, stops[1:]):
        m = (z >= a) & (z < b); t = ((z - a) / (b - a))[..., None]
        out[m] = (np.array(ca_) * (1 - t) + np.array(cb) * t)[m]
    out[z < stops[0][0]] = stops[0][1]; out[z >= stops[-1][0]] = stops[-1][1]; return out
col = ramp(Z)
light = 0.62 + 0.55 * sh[..., None]
col = col * np.where(Z[..., None] < 0, 0.92 + 0.16 * sh[..., None], light)

# ---------- forest cover from the placed trees (the city loader drops the old backdrop trees inside its footprint)
warm = ('Tree_Maple', 'Tree_Ginkgo', 'Tree_Broad'); cool = ('Tree_Pine', 'Tree_Cedar')
def tree_points(prefixes):
    pts = []
    for k, v in W['instances'].items():
        if k.startswith(prefixes):
            a = np.array([p[:2] for p in v], dtype=float)
            if C:
                excluded=(a[:,0]>300)&(a[:,0]<2200)&(a[:,1]>-450)&(a[:,1]<1600)
                if NORTH:excluded|=(a[:,0]>NORTH[0])&(a[:,0]<NORTH[2])&(a[:,1]>NORTH[1])&(a[:,1]<NORTH[3])
                a=a[~excluded]
            pts.append(a)
    if C:
        for k, v in C['instances'].items():
            if k.startswith(prefixes): pts.append(np.array([p[:2] for p in v], dtype=float))
    return np.concatenate(pts) if pts else np.zeros((0, 2))
def density(prefixes):
    cell = 4.0
    g = np.zeros((int((Y1 - Y0) / cell), int((X1 - X0) / cell)), np.float32)
    a = tree_points(prefixes)
    if len(a):
        ax=project(a[:,0],X_KNOTS) if NORTH else a[:,0];ay=project(a[:,1],Y_KNOTS) if NORTH else a[:,1]
        ix = ((ax - X0) / cell).astype(int); iy = ((Y1 - ay) / cell).astype(int)
        ok = (ix >= 0) & (ix < g.shape[1]) & (iy >= 0) & (iy < g.shape[0]); np.add.at(g, (iy[ok], ix[ok]), 1)
    g8 = Image.fromarray(np.clip(g * 24, 0, 255).astype(np.uint8), 'L').resize((MW, MH), Image.BILINEAR).filter(ImageFilter.GaussianBlur(3.5 * PX / 2))
    return np.array(g8).astype(np.float32) / 24
dw = density(warm); dc = density(cool); tot = dw + dc
ref = np.percentile(tot[tot > 0], 85) if (tot > 0).any() else 1
forest = np.clip(tot / ref, 0, 1)[..., None]
tint = (dw[..., None] * np.array((168, 112, 58)) + dc[..., None] * np.array((62, 92, 70))) / np.maximum(tot, 1e-3)[..., None]
col = col * (1 - 0.7 * forest) + tint * 0.7 * forest * light
paper = np.array((228, 222, 206), np.float32)
grey = col.mean(axis=-1, keepdims=True)
col = col * fade[..., None] + (0.22 * paper + 0.78 * (0.25 * grey + 0.75 * col)) * (1 - fade[..., None])   # scenery hills: slightly hazier, still land
img = Image.fromarray(np.clip(col, 0, 255).astype(np.uint8))

# ---------- contours (land only)
cont = np.zeros((MH, MW), np.uint8)
for lvl in range(5, int(Z.max()) + 1, 5):
    m = (Z >= lvl).astype(np.uint8); e = (m[1:, 1:] != m[:-1, 1:]) | (m[1:, 1:] != m[1:, :-1])
    if NORTH and lvl % 25: e &= GY[1:,1:] < NORTH[1]
    cont[1:, 1:] |= e.astype(np.uint8) * (2 if lvl % 25 == 0 else 1)
cont[fade < .5] = 0
oa = np.zeros((MH, MW, 4), np.uint8); oa[cont == 1] = (60, 50, 30, 55); oa[cont == 2] = (60, 50, 30, 120)
ov = Image.fromarray(oa, 'RGBA'); img.paste(ov, (0, 0), ov)
d = ImageDraw.Draw(img, 'RGBA')

LINES = []   # every polyline drawn, kept for the alignment check of the painted sheet (tools/paint_map.py)
def line(pts, fill, width):
    if len(pts) > 1:
        d.line([wp(p[0], p[1]) for p in pts], fill=fill, width=max(1, int(round(width * PX))), joint='curve')
        LINES.append([[round(float(p[0]), 2), round(float(p[1]), 2)] for p in pts])
def rect(cx, cy, w, h, yaw, fill, outline=None):
    a = math.radians(yaw); c, s = math.cos(a), math.sin(a)
    pts = [wp(cx + dx * c - dy * s, cy + dx * s + dy * c) for dx, dy in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))]
    d.polygon(pts, fill=fill, outline=outline)
def dot(x, y, r, fill, outline=None, width=1):
    px, py = wp(x, y); d.ellipse([px - r, py - r, px + r, py + r], fill=fill, outline=outline, width=width)

# ---------- water features the game tests against (canal, park pond, plaza basin)
if C:
    canal = [(848 - 7.8, -130), (848 + 7.8, -130), (848 + 7.8, -5), (848 - 7.8, -5)]
    d.polygon([wp(x, y) for x, y in canal], fill=(126, 172, 196, 235))
    px, py = wp(1030, 284); d.ellipse([px - 46 * PX, py - 32 * PX, px + 46 * PX, py + 32 * PX], fill=(120, 168, 196, 235), outline=(70, 110, 140))
    for p in C['instances'].get('HD_PlazaWater', []): dot(p[0], p[1], 5 * PX, (120, 168, 196), (70, 110, 140))
# Woodland lake geometry matches its authored irregular shore.
if W.get('forest_lake'):
    lake=W['forest_lake'];cx,cy=lake['center'];rx,ry=lake['radii']
    shore=[]
    for angle in np.linspace(0,2*np.pi,120):
        rr=.975*(1+.045*np.sin(angle*3)+.035*np.cos(angle*5))
        shore.append(wp(cx+rx*rr*np.cos(angle),cy+ry*rr*np.sin(angle)))
    d.polygon(shore,fill=(79,145,153),outline=(170,185,130))
# ---------- roads, streets, lanes, trails
for run in W['rail_runs']: line(run, (255, 255, 255, 220), 1.0)
ROAD_W = W['road_width']
line(W['road'], (58, 54, 52), ROAD_W + 2.4); line(W['road'], (150, 148, 150), ROAD_W); line(W['road'], (232, 228, 220), .6)
if C:
    for r in C['roads']: line(r, (214, 206, 190), 16)
    for r in C['roads']: line(r, (120, 118, 122), 7.6)
    line(C['arrival'], (58, 54, 52), ROAD_W + 2.4); line(C['arrival'], (150, 148, 150), ROAD_W)
    for key, w, colr in (('north_trail', 4, (206, 178, 128)), ('plaza_route', 4, (214, 206, 190)), ('arcade_route', 5, (214, 206, 190)), ('harbor_route', 5, (200, 190, 170)), ('harbor_pier_route', 3, (150, 120, 84))):
        line(C.get(key, []), colr, w)
V = W['village']
for path in V['surface_paths']:
    line(path, (120, 96, 60), V['lane_width'] + 1.4); line(path, (206, 178, 128), V['lane_width'])
for bx, by, bw, bh in V['planting_beds']:
    px, py = wp(bx, by); d.ellipse([px - bw * PX / 2, py - bh * PX / 2, px + bw * PX / 2, py + bh * PX / 2], fill=(104, 140, 70, 220))
if W.get('forest_lake'):
    lake=W['forest_lake']
    line(lake['trail'],(206,178,128),2.5)
    rect(lake['cabin'][0],lake['cabin'][1],7,5,-135,(66,72,104),(40,20,12))
    line([[-59.1,218.1],[-65.2,224.2]],(173,127,78),2)
M = W['mega']
line(M['trail'], (90, 60, 30), M['width'] + 1.4); line(M['trail'], (190, 160, 110), M['width'])
# Draw the actual two riding sections and their open gap, not an ambiguous
# landmark dot that a map painter can mistake for a cottage.
mega_x, mega_y = M['origin'][:2]
for profile in M['profiles']:
    LINES.append([[mega_x+p[0],mega_y] for p in profile])
    for a, b in zip(profile, profile[1:]):
        height = (a[1]+b[1])*.5
        shade = int(min(30, height*2.5))
        corners = [wp(mega_x+a[0],mega_y-M['width']/2),wp(mega_x+b[0],mega_y-M['width']/2),
                   wp(mega_x+b[0],mega_y+M['width']/2),wp(mega_x+a[0],mega_y+M['width']/2)]
        d.polygon(corners,fill=(192+shade,154+shade,101+shade))
    for side in (-1,1):
        d.line([wp(mega_x+p[0],mega_y+side*M['width']/2) for p in profile],fill=(75,57,38),width=max(1,round(PX)))
line([[mega_x+p[0],mega_y+p[1],p[2]] for p in M['rollout']],(190,154,103),3)
line([[mega_x-2.05,mega_y-5.55,0],[mega_x-1.8,mega_y,10.7]],(90,64,37),1.2)
if SW:
    line(SW['lane'], (120, 96, 60), 3.2); line(SW['lane'], (206, 178, 128), 2.2)
    stair = [island_world(p[0], p[1]) for p in ISL.path_points()]
    line(stair, (90, 70, 50), 3.0); line(stair, (222, 210, 190), 1.6)
# ---------- buildings, landmarks, props
NAVY, NAVY_OUT = (52, 58, 92), (20, 22, 36)
for b in V['buildings']: rect(b['position'][0], b['position'][1], b['width'], b['depth'], b['yaw'], NAVY, NAVY_OUT)
for h in W['instances'].get('House', []): rect(h[0], h[1], 9, 7, h[3], NAVY, NAVY_OUT)
if SW:
    for b in SW['buildings']: rect(b['position'][0], b['position'][1], b['width'], b['depth'], b['yaw'], NAVY, NAVY_OUT)
    for p in W['instances'].get('SW_CoconutStand', []): rect(p[0], p[1], 3.2, 2.6, p[3], (196, 120, 60), (80, 40, 10))
    for p in W['instances'].get('SW_Dock', []): rect(p[0], p[1] - 5, 2.4, 12, p[3], (150, 120, 84), (80, 60, 30))
    for p in W['instances'].get('SW_Temple', []): rect(p[0], p[1], 20, 16, p[3], (170, 52, 40), (70, 20, 10))
    for p in W['instances'].get('SW_Boat', []): dot(p[0], p[1], 1.8 * PX, (240, 236, 220), (80, 70, 60))
if C:
    for b in C['buildings']: rect(b['position'][0], b['position'][1], b['width'], b['depth'], b['yaw'], (66, 72, 104), NAVY_OUT)
    for key, size, colr in (('HD_ClockHall', (18, 14), (170, 52, 40)), ('HD_Temple', (16, 12), (170, 52, 40)), ('HD_Shrine', (10, 8), (170, 52, 40)),
                            ('HD_Station', (26, 12), (96, 100, 132)), ('HD_Market', (22, 10), (150, 120, 84)), ('HD_Pavilion', (8, 8), (196, 150, 70)),
                            ('HD_Lighthouse', (5, 5), (240, 236, 220)), ('HD_Playground', (12, 10), (196, 150, 70))):
        for p in C['instances'].get(key, []): rect(p[0], p[1], size[0], size[1], p[3], colr, (40, 20, 12))
    for p in C['instances'].get('HD_Boat', []): dot(p[0], p[1], 2.2 * PX, (240, 236, 220), (80, 70, 60))
for t in W['instances'].get('Torii', []):
    px, py = wp(t[0], t[1]); r = 2.4 * PX
    d.rectangle([px - r, py - r, px + r, py + r], outline=(190, 50, 30), width=max(1, int(PX)))
dot(W['player_start'][0], W['player_start'][1], 3 * PX, (255, 255, 255), (200, 40, 40), max(1, int(PX)))

# ---------- zones: the teleport targets, each snapped to a walkable polyline
def nearest(polyline, x, y):
    a = np.array([p[:3] if len(p) > 2 else [p[0], p[1], 0.0] for p in polyline], dtype=float)
    k = int(np.argmin((a[:, 0] - x) ** 2 + (a[:, 1] - y) ** 2)); return a[k], k, a
def facing(fx, fy, x, y):
    return math.degrees(math.atan2(fy - y, fx - x))
def zone(key, name, polyline, near, face=None, hint=''):
    (x, y, z), k, a = nearest(polyline, *near)
    if face is None:
        nxt = a[min(k + 3, len(a) - 1)] if k + 3 < len(a) else a[k]; prv = a[max(k - 3, 0)]
        yaw = facing(nxt[0], nxt[1], prv[0], prv[1])
    else: yaw = facing(face[0], face[1], x, y)
    return dict(key=key, name=name, x=round(float(x), 2), y=round(float(y), 2), z=round(float(z), 2), yaw=round(yaw, 1), hint=hint)
zones = []
ps = W['player_start']
zones.append(dict(key='spawn', name='Coastal road (spawn)', x=ps[0], y=ps[1], z=ps[2], yaw=ps[3], hint='Where the walk begins'))
centre = np.mean([b['position'][:2] for b in V['buildings']], axis=0)
zones.append(zone('hamlet', V.get('name', 'Momiji Hamlet'), V['surface_paths'][-1], centre, hint='Tea house, cottages and the pottery workshop'))
zones.append(zone('mega', 'Mini-mega ramp', M['trail'], M['trail'][-1][:2], face=M['origin'][:2], hint='The forest mini-mega ramp in its sunlit clearing'))
if SW:
    zones.append(zone('fishing', 'Fishing village', SW['lane'], SW['terrace'][:2], hint='Fisher houses and the boat shed'))
    # The tested dry launch beside the stand; the old midpoint lay in the surf.
    zones.append(dict(key='cove',name='Coconut stand beach',x=-216.,y=-169.,z=1.,yaw=-80.,hint='The beach: launch a sailboat from the sand'))
    landing = SW['island']['landing']
    stair_start = island_world(*ISL.WAYPOINTS[1])
    zones.append(dict(key='landing', name='Island landing', x=landing[0], y=landing[1], z=landing[2], yaw=round(facing(stair_start[0], stair_start[1], landing[0], landing[1]), 1), hint='The cove at the foot of the stair'))
    top = ISL.WAYPOINTS[-1]; tx, ty = island_world(*top); tz = float(ISL.height(np.array([top[0]]), np.array([top[1]]))[0])
    temple = W['instances']['SW_Temple'][0]
    zones.append(dict(key='temple', name='Island temple', x=round(tx, 2), y=round(ty, 2), z=round(tz, 2), yaw=round(facing(temple[0], temple[1], tx, ty), 1), hint='The summit shrine above the sea'))
if C:
    roads = [p for r in C['roads'] for p in r]
    city = C.get('name', 'Hidamari')   # the big city keeps its own name on every zone
    districts = {dd['name']: dd['bounds'] for dd in C.get('districts', [])}
    def centre_of(name, fallback):
        b = districts.get(name); return ((b[0] + b[2]) / 2, (b[1] + b[3]) / 2) if b else fallback
    zones.append(zone('arrival', f'{city} · arrival terraces', C['arrival'], centre_of('Arrival terraces', (450, 175)), hint='The terraces where the road enters the city'))
    zones.append(zone('arcade', f'{city} · shopping arcade', C['arcade_route'], C['arcade_route'][0][:2], face=C['arcade_route'][-1][:2], hint='Covered street of shops and lanterns'))
    zones.append(zone('plaza', f'{city} · clock square', C['plaza_route'], C['plaza_route'][0][:2], face=C['plaza_route'][-1][:2], hint='The fountain square under the clock hall'))
    zones.append(zone('harbor', f'{city} · fishing harbor', C['harbor_route'], C['harbor_route'][0][:2], face=C['harbor_route'][-1][:2], hint='Quays, boats and the lighthouse'))
    tpl = C['instances']['HD_Temple'][0]
    zones.append(zone('hillside', f'{city} · temple hillside', roads, tpl[:2], hint='The hill temple and the shrine'))   # along the street: the temple's blank back wall is not a view
    pav = C['instances']['HD_Pavilion'][-1]
    zones.append(zone('park', f'{city} · sunlit park', roads, pav[:2], face=pav[:2], hint='Pavilions, the pond and the playground'))
    st = C['instances']['HD_Station'][0]
    stz = zone('station', f'{city} · station', roads, st[:2], hint='The far end of town'); stz['yaw'] = 180.0   # looking back down the street into town
    zones.append(stz)
    if NORTH:
        zones.append(zone('foothills',f'{city} · northern foothills',C['north_trail'],C['north_trail'][-1][:2],face=(720,1930),hint='Wooded trail with a view of the snowcapped summit'))

if W.get('forest_lake'):
    lake=W['forest_lake'];safe=lake['safe_shore']
    zones.append(dict(key='forest_lake',name='Hidden woodland lake',x=safe[0],y=safe[1],z=safe[2],yaw=180.,hint='A quiet fishing cabin and timber jetty deep in the woods'))
# the skate pier (japan/skatepark/park.json): its spawn on the plaza floor
PARK = str(yori.REGIONS / 'skatepark' / 'park.json')
if os.path.exists(PARK):
    P = json.load(open(PARK)); o = P['origin']; sp = P['spawns']['park']; pr = math.radians(P.get('yaw_deg', 0.))
    px = o[0] + sp['pos'][0] * math.cos(pr) - sp['pos'][1] * math.sin(pr); py = o[1] + sp['pos'][0] * math.sin(pr) + sp['pos'][1] * math.cos(pr)
    zones.append(dict(key='skatepier', name='Skate pier', x=round(px, 2), y=round(py, 2), z=round(o[2] + sp['pos'][2], 2), yaw=round(sp['yaw_deg'] + P.get('yaw_deg', 0.), 1),
                      hint='Concrete plaza on the sea: ramps, rails and ledges (B for the board)'))
if W.get('zeppelin'):
    for station in W['zeppelin']['stations']:
        p=station['safe']
        zones.append(dict(key=station['key'],name=station['name'],x=p[0],y=p[1],z=p[2],yaw=90.,hint='Climb the short steps and use the zeppelin to travel'))

os.makedirs(A.out, exist_ok=True)
img.save(os.path.join(A.out, 'rough.png'), optimize=True)
img.convert('RGB').save(os.path.join(A.out, 'rough.jpg'), quality=86, progressive=True)
# A painted sheet is valid only for the exact geographical bounds it depicts.
# Otherwise use the accurately generated sheet; never stretch old artwork over
# an expanded world, which silently moves every marker off its destination.
committed = str(yori.MAP / 'painted' / 'world_map.png')
bounds_file = str(yori.MAP / 'painted' / 'world_map_bounds.json')
paint_bounds = json.load(open(bounds_file)) if os.path.exists(bounds_file) else [-330.,-650.,1330.,456.66666666666674]
matched = len(paint_bounds)==4 and all(abs(a-b)<.01 for a,b in zip(paint_bounds,[X0,Y0,X1,Y1]))
registration=str(yori.MAP / 'painted' / 'world_map_registration.json')
if os.path.exists(registration):
    registered=json.load(open(registration))
    matched=matched and registered.get('projection_x',[])==(X_KNOTS if NORTH else []) and registered.get('projection_y',[])==(Y_KNOTS if NORTH else [])
sheet = Image.open(committed).convert('RGB') if os.path.exists(committed) and matched else img
sheet.save(os.path.join(A.out, 'map.png'), optimize=True)
sheet.convert('RGB').save(os.path.join(A.out, 'map.jpg'), quality=88, progressive=True)
print('map sheet:', 'registered painted sheet' if sheet is not img else 'accurate generated layout')
meta = dict(frame='blender_metres_north_up', bounds=[X0, Y0, X1, Y1], px_per_m=PX, width=MW, height=MH,
            sea_level=W.get('sea_level', 0), zones=zones, sources=['world.json', 'heightmap.npy', 'farhills.npy'] + (['hidamari/city.json'] if C else []))
if NORTH:meta.update(projection_x=X_KNOTS,projection_y=Y_KNOTS,world_bounds=[-700,-650,2400,3030])
json.dump(meta, open(os.path.join(A.out, 'map.json'), 'w'), indent=1)
json.dump(LINES, open(os.path.join(A.out, 'map_lines.json'), 'w'))
print('map', MW, 'x', MH, 'px,', len(zones), 'zones ->', A.out)
for z in zones: print(f"  {z['key']:9s} {z['name']:18s} ({z['x']:8.2f},{z['y']:8.2f},{z['z']:6.2f}) yaw {z['yaw']:6.1f}")
