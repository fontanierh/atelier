"""Repaint the south-west island on the painted world map, and only there.

    uv run python games/yorimichi/world/map/repaint_island.py prepare    # crop inputs from the committed sheet and island.py
    uv run python games/yorimichi/world/map/repaint_island.py paint      # one Sunburst call, never sent twice
    uv run python games/yorimichi/world/map/repaint_island.py register   # fit, blend, check -> world_map_candidate.png
    uv run python games/yorimichi/world/map/promote_map.py build/yorimichi/map/island_repaint/world_map_candidate.png

The same local correction as the mini-mega landmark (docs/WORLD_MAP.md): the rest of the sheet, its bounds, its
projection and the travel zones stay as they are. Work files go to build/yorimichi/map/island_repaint/.

- prepare keeps a copy of the committed sheet and its provenance (parent.png, parent_provenance.json), finds the old
  painted island and the new one (island.py's heightfield through the map projection), picks a 3:2 crop box around
  both and writes current-crop.png (that box of the sheet) and layout-crop.png (a plain plan of the island as built:
  its coastline, rock, cove, every placed tree crown by species, the stair with its torii and the temple), both at
  1536 x 1024.
- paint sends them with the aerial island concept to gpt-image-2.5-sunburst (quality high, /v1/images/edits). The
  call's provenance file, painted/island_repaint.provenance.json, is its ledger (the repository has no shared ledger
  module): written with status `submitted` before the call and completed or marked failed after it. With that file
  present the call is never sent again; delete it only to pay for a new painting.
- register fits the painting to the projection (scale and offset that best lay its island on the data island),
  matches the sea colour, blends it in through a feathered mask around the old and new islands only, and checks
  that every pixel outside the mask is identical to the parent. It writes world_map_candidate.png, the
  paint_provenance.json that promote_map.py copies to painted/world_map_provenance.json (the parent's record nested
  under `parent`), registration-check.json and registration-check.jpg (the data coastline and stair over the result).
"""
import sys as _sys; from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[1])); import yori  # noqa: E402
_sys.path.insert(0, str(yori.REGIONS)); _sys.path.insert(0, str(_Path(__file__).resolve().parent))
import argparse, hashlib, json, math, shutil, sys, time
from datetime import datetime, timezone

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from map_projection import BOUNDS, X_KNOTS, Y_KNOTS, project, unproject
from southwest import island as ISL

SHEET = yori.MAP / 'painted' / 'world_map.png'
PROVENANCE = yori.MAP / 'painted' / 'world_map_provenance.json'
LEDGER = yori.MAP / 'painted' / 'island_repaint.provenance.json'
CONCEPT = yori.ASSETS / 'southwest' / 'concepts' / 'aerial.jpg'
WORK = yori.OUT / 'map' / 'island_repaint'
OW, OH = 1536, 1024                  # the painting, and the sheet (both 3:2)
MARGIN = 40                          # sheet pixels of sea kept around both islands in the crop
OLD_SEED = (210, 880)                # a sheet pixel inside the old painted island


def sha(data):
    return hashlib.sha256(data).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


# ---- geometry: sheet pixels <-> world metres <-> island-local metres
def to_sheet(x, y):
    return ((project(x, X_KNOTS) - BOUNDS[0]) / (BOUNDS[2] - BOUNDS[0]) * OW,
            (BOUNDS[3] - project(y, Y_KNOTS)) / (BOUNDS[3] - BOUNDS[1]) * OH)


def to_world(sx, sy):
    return (unproject(BOUNDS[0] + np.asarray(sx) / OW * (BOUNDS[2] - BOUNDS[0]), X_KNOTS),
            unproject(BOUNDS[3] - np.asarray(sy) / OH * (BOUNDS[3] - BOUNDS[1]), Y_KNOTS))


def placement():
    isl = json.load(open(yori.OUT / 'world.json'))['southwest']['island']
    return isl['origin'][0], isl['origin'][1], math.radians(isl['yaw'])


OX, OY, YAW = placement()
CA, SA = math.cos(YAW), math.sin(YAW)


def local_to_sheet(lx, ly):
    lx, ly = np.asarray(lx, float), np.asarray(ly, float)
    return to_sheet(OX + lx * CA - ly * SA, OY + lx * SA + ly * CA)


def heights(sx, sy):
    """island.py's height at sheet pixel positions (sea floor outside its grid), and the local coordinates."""
    x, y = to_world(sx, sy); dx, dy = x - OX, y - OY
    lx, ly = (dx * CA + dy * SA).ravel(), (-dx * SA + dy * CA).ravel()
    z = np.full(lx.shape, -5.0)
    idx = np.flatnonzero((np.abs(lx) < ISL.SIZE[0] / 2) & (np.abs(ly) < ISL.SIZE[1] / 2))
    for part in np.array_split(idx, max(1, len(idx) // 20000)):
        z[part] = ISL.height(lx[part], ly[part])
    shape = np.shape(sx)
    return z.reshape(shape), lx.reshape(shape), ly.reshape(shape)


def data_land(box, factor=1):
    """Where island.py is above the sea, on the crop box's pixel grid (factor samples per sheet pixel)."""
    w, h = (box[2] - box[0]) * factor, (box[3] - box[1]) * factor
    sx, sy = np.meshgrid(box[0] + (np.arange(w) + .5) / factor, box[1] + (np.arange(h) + .5) / factor)
    return heights(sx, sy)[0] > 0.0


# ---- masks without scipy: PIL filters and flood fill
def painted_land(rgb):
    """Land on the painted sheet: warmer than the sea, whose water and shallows are all blue-green."""
    r, b = rgb[..., 0].astype(int), rgb[..., 2].astype(int)
    return (r - b) > -8


def dilate(mask, r):
    im = Image.fromarray(mask.astype(np.uint8) * 255)
    while r > 0:                                  # small square steps: a large rank filter is slow
        step = min(r, 3); im = im.filter(ImageFilter.MaxFilter(2 * step + 1)); r -= step
    return np.asarray(im) > 127


def shallow(rgb):
    """The pale shallows around a painted island (the open sea is darker)."""
    return (rgb[..., 1].astype(int) > 105) & ~painted_land(rgb)


def erode(mask, r):
    return ~dilate(~mask, r)


def component(mask, seed):
    """The connected region of mask that holds seed (x, y), holes filled."""
    im = Image.fromarray(mask.astype(np.uint8) * 255).copy()   # (flood fill needs its own buffer)
    if not mask[seed[1], seed[0]]: return np.zeros_like(mask)
    ImageDraw.floodfill(im, seed, 128)
    part = np.asarray(im) == 128
    outside = Image.fromarray(np.where(part, 0, 255).astype(np.uint8))   # fill the holes: flood the sea from a corner
    outside = np.pad(np.asarray(outside), 1, constant_values=255); im = Image.fromarray(outside).copy()
    ImageDraw.floodfill(im, (0, 0), 64)
    return (np.asarray(im) != 64)[1:-1, 1:-1]


def bbox(mask):
    ys, xs = np.nonzero(mask)
    return [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1]


# ---- prepare
def crop_box(old, new):
    """3:2 box around both islands with MARGIN of sea, inside the sheet."""
    x0, y0, x1, y1 = bbox(old | new)
    x0, y0, x1, y1 = x0 - MARGIN, y0 - MARGIN, x1 + MARGIN, y1 + MARGIN
    w, h = x1 - x0, y1 - y0
    if w < h * 1.5: w = math.ceil(h * 1.5)
    else: h = math.ceil(w / 1.5)
    w += w % 2; h = w * 2 // 3
    cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
    bx = min(max(cx - w // 2, 0), OW - w); by = min(max(cy - h // 2, 0), OH - h)
    return [int(bx), int(by), int(bx + w), int(by + h)]


SPECIES = [('Tree_PineLean', (52, 92, 60)), ('Tree_Pine', (46, 86, 56)), ('Tree_Cedar', (32, 70, 60)),
           ('Tree_Canopy_Crimson', (190, 58, 40)), ('Tree_Canopy_Maple', (214, 92, 42)),
           ('Tree_Canopy_Ginkgo', (228, 184, 60)), ('Tree_Canopy_Amber', (224, 146, 50)), ('Tree_Maple', (206, 82, 42)),
           ('Tree_Ginkgo', (230, 186, 62)), ('Tree_Broad', (120, 148, 66))]


def layout(box):
    """A plain plan of the island as island.py builds it, over the crop box at OW x OH."""
    k = OW / (box[2] - box[0]); half = 2                           # sampled every 2 output pixels
    u = (np.arange(OW // half) + .5) * half; v = (np.arange(OH // half) + .5) * half
    sx, sy = np.meshgrid(box[0] + u / k, box[1] + v / k)
    z, lx, ly = heights(sx, sy)
    sl = ISL.slope_deg(lx, ly)
    gy, gx = np.gradient(np.where(z > 0, z, 0.0))
    shade = np.clip(.78 + .09 * (-gx - gy), .55, 1.1)[..., None]
    cove = (np.hypot(lx - ISL.LANDING[0], ly - ISL.LANDING[1]) < ISL.COVE_R + 4) & (z < 4.0)
    rock = ((sl > ISL.ROCK_SLOPE) | (z < ISL.SHORE_ROCK_Z)) & ~cove
    col = np.empty(z.shape + (3,)); col[:] = (58, 108, 150)                                  # sea
    col[z > 0] = (138, 164, 92); col[rock & (z > 0)] = (122, 116, 108); col[cove & (z > 0)] = (228, 210, 164)
    col = np.where((z > 0)[..., None], col * shade, col)
    im = Image.fromarray(np.clip(col, 0, 255).astype(np.uint8)).resize((OW, OH), Image.LANCZOS)
    d = ImageDraw.Draw(im)
    m = k * OW / (BOUNDS[2] - BOUNDS[0])                               # output pixels per metre (the projection is ~1:1 here)
    def at(lx_, ly_):
        sx_, sy_ = local_to_sheet(lx_, ly_); return (float(sx_) - box[0]) * k, (float(sy_) - box[1]) * k
    sc = ISL.scatter(1207)
    for asset, x, y, z0, yaw, s in sc['boulders']:
        cx, cy = at(x, y); r = 1.2 * s * m; d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(104, 100, 94))
    trees = sorted(sc['trees'], key=lambda t: t[3] + ISL.TREE_DIMS['Tree_Canopy' if t[0].startswith('Tree_Canopy') else t[0]][2] * t[5])
    for asset, x, y, z0, yaw, s in trees:
        colour = next(c for p, c in SPECIES if asset.startswith(p))
        rr = ISL.TREE_DIMS['Tree_Canopy' if asset.startswith('Tree_Canopy') else asset][3]
        rr = .75 * (4.0 if asset.startswith('Tree_PineLean') else rr) * s * m      # a little small: the rock and grass show
        cx, cy = at(x, y); dark = tuple(int(c * .6) for c in colour)
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=colour, outline=dark)
    path = [at(x, y) for x, y, t in ISL.path_points()]
    d.line(path, fill=(96, 84, 70), width=max(3, round(5.5 * m)), joint='curve')
    d.line(path, fill=(222, 214, 196), width=max(2, round(3.5 * m)), joint='curve')
    for lx_, ly_, lz, yaw in ISL.torii_points(5):
        a = math.radians(yaw); dx, dy = 3.5 * math.cos(a), 3.5 * math.sin(a)
        d.line([at(lx_ - dx, ly_ - dy), at(lx_ + dx, ly_ + dy)], fill=(214, 58, 36), width=max(3, round(1.6 * m)))
    tx, ty, tz = ISL.summit_transform()
    cx, cy = at(tx, ty); r = ISL.SUMMIT_R * m; d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(196, 186, 164))
    a = math.radians(180.0); corners = []
    for ex, ey in ((-13, -10), (13, -10), (13, 10), (-13, 10)):
        corners.append(at(tx + ex * math.cos(a) - ey * math.sin(a), ty + ex * math.sin(a) + ey * math.cos(a)))
    d.polygon(corners, fill=(52, 58, 96), outline=(206, 64, 40), width=3)
    return im


def prepare(args):
    WORK.mkdir(parents=True, exist_ok=True)
    if (WORK / 'parent.png').exists() and not args.force:
        sys.exit('prepare: parent.png is already there (the sheet before the edit); --force to take the committed one again')
    shutil.copyfile(SHEET, WORK / 'parent.png'); shutil.copyfile(PROVENANCE, WORK / 'parent_provenance.json')
    parent = np.asarray(Image.open(WORK / 'parent.png').convert('RGB'))
    region = [0, 640, 640, OH]                                                  # the south-west corner of the sheet
    old = np.zeros(parent.shape[:2], bool)
    part = parent[region[1]:region[3], region[0]:region[2]]
    land = erode(dilate(painted_land(part), 2), 2)
    old[region[1]:region[3], region[0]:region[2]] = component(land, (OLD_SEED[0] - region[0], OLD_SEED[1] - region[1]))
    new = np.zeros_like(old); new[region[1]:region[3], region[0]:region[2]] = data_land(region)
    box = crop_box(old, new)
    Image.fromarray(parent).crop(box).resize((OW, OH), Image.LANCZOS).save(WORK / 'current-crop.png')
    layout(box).save(WORK / 'layout-crop.png')
    info = dict(crop_box=box, old_island_bbox=bbox(old), new_island_bbox=bbox(new), region=region,
                parent_file_sha256=sha((WORK / 'parent.png').read_bytes()), parent_pixels_sha256=sha(parent.tobytes()))
    json.dump(info, open(WORK / 'prepare.json', 'w'), indent=2)
    print('prepare:', json.dumps(info))


# ---- paint
PROMPT = (
    'Image 1 is a crop of the hand-painted watercolour world map of Yorimichi, a stylised Japanese autumn '
    'exploration game: a top-down map, north up, showing a small round wooded island in a blue sea. Image 2 is the '
    'exact plan of the redesigned island as it is now built in the game, at the same scale and in the same place in '
    'the frame: a flat diagram with blue sea, green grass, grey rock cliffs, a pale sand cove, one coloured disc for '
    'every tree crown (dark green pines and cedars, red and orange maples, gold ginkgo), the pale stone stairway with '
    'red torii marks, and the temple (dark indigo roof) on its round stone terrace. Image 3 is a concept painting of '
    'the same island from the air, for its character.\n\n'
    'Paint the same map crop as Image 1 with the new island: keep Image 1\'s framing, scale, paper texture, colours '
    'and watercolour style exactly, and keep the sea and anything else outside the island as it is in Image 1. '
    'Replace the old round island with the island of Image 2, following its plan exactly: the same outline and size, '
    'the rocky headlands, the small pale sand cove on the north-west side, the small rocky sea stacks, the zigzag '
    'stone stairway from the cove up to the temple terrace, and the temple, all exactly where Image 2 has them. Paint '
    'it in Image 1\'s map style with Image 3\'s character: dark grey-brown rock cliffs with a thin line of white surf '
    'along the whole shore, fallen boulders at their feet, the forest in the masses and colours of Image 2 (dark '
    'green pine and cedar, drifts of red-orange maple and gold ginkgo, a few grassy glades) drawn as small painted '
    'trees seen from above like the trees of Image 1, a small temple with a dark indigo roof, and tiny vermilion '
    'torii along the stair.\n\n'
    'Top-down map view like Image 1, not the oblique view of Image 3. No text, labels, pins, markers, frames, compass '
    'or legend, no other islands, boats or buildings besides the temple and the torii, and no diagram look: a '
    'painted map.'
)


def paint(args):
    sys.path.insert(0, str(yori.GAME / 'tools'))
    from treehouse_art import MODEL, QUALITY, rel, redact, sunburst
    inputs = [WORK / 'current-crop.png', WORK / 'layout-crop.png', CONCEPT]
    missing = [rel(p) for p in inputs if not p.exists()]
    if missing: sys.exit(f'paint: missing {missing}; run prepare first')
    if args.dry_run:
        print(PROMPT); return
    if LEDGER.exists():
        sys.exit(f'paint: {rel(LEDGER)} exists (status {json.load(open(LEDGER)).get("status")}): the call is never sent twice')
    from atelier.env import require
    require('OPENAI_API_KEY')                       # loads the ignored .env; never prints the value
    record = dict(stage='world-map-island-repaint', status='submitted', requested_model=MODEL, quality=QUALITY,
                  size=f'{OW}x{OH}', endpoint='/v1/images/edits', execution='games/yorimichi/world/map/repaint_island.py',
                  prompt=PROMPT, prompt_sha256=sha(PROMPT.encode()),
                  reference_files={rel(p): sha(p.read_bytes()) for p in inputs},
                  crop_box=json.load(open(WORK / 'prepare.json'))['crop_box'], started_at=now())
    LEDGER.write_text(json.dumps(record, indent=2) + '\n')          # recorded before the paid call
    t = time.time()
    try:
        png, usage = sunburst(PROMPT, f'{OW}x{OH}', inputs)
        (WORK / 'generated.png').write_bytes(png)
        record.update(status='done', usage=usage, output={'build/yorimichi/map/island_repaint/generated.png': sha(png)},
                      error=None)
    except Exception as e:  # noqa: BLE001 - recorded, never retried
        record.update(status='failed', error=redact(e)[:600])
    record.update(finished_at=now(), elapsed_seconds=round(time.time() - t, 1),
                  hashes='of the files as the API saw and returned them; the generated crop is kept outside the '
                         'repository, its blend is the committed sheet')
    LEDGER.write_text(json.dumps(record, indent=2) + '\n')
    print('paint:', record['status'], record.get('error') or '', f'({record["elapsed_seconds"]} s)')
    if record['status'] != 'done': sys.exit(1)


# ---- register
def warp(im, box, p, resample=Image.BICUBIC):
    """The painting (OW x OH over the crop box) laid on the crop box's sheet pixels with scale (sx, sy) and offset
    (tx, ty) in sheet pixels: sheet = box + painting / k * s + t."""
    sx, sy, tx, ty = p; w, h = box[2] - box[0], box[3] - box[1]; k = OW / w
    small = im.resize((max(1, round(OW / k * sx)), max(1, round(OH / k * sy))), Image.LANCZOS)   # at the sheet's scale
    ax, ay = small.width / (OW / k * sx), small.height / (OH / k * sy)                              # rounding of that size
    return small.transform((w, h), Image.AFFINE, (ax, 0, -tx * ax, 0, ay, -ty * ay), resample=resample)


def iou(a, b):
    return float(np.minimum(a, b).sum() / max(np.maximum(a, b).sum(), 1e-6))


def register(args):
    info = json.load(open(WORK / 'prepare.json')); box = info['crop_box']
    parent_im = Image.open(WORK / 'parent.png').convert('RGB'); parent = np.asarray(parent_im)
    gen = Image.open(WORK / 'generated.png').convert('RGB')
    if gen.size != (OW, OH): gen = gen.resize((OW, OH), Image.LANCZOS)
    w, h = box[2] - box[0], box[3] - box[1]; k = OW / w
    crop = parent[box[1]:box[3], box[0]:box[2]]
    # the data island (main body, for the fit) and all its land (the stacks too, for the mask)
    new_all = data_land(box)
    centre = local_to_sheet(*ISL.CENTRE); seed = (int(centre[0]) - box[0], int(centre[1]) - box[1])
    new_main = component(new_all, seed)
    target = np.asarray(Image.fromarray(new_main.astype(np.uint8) * 255).filter(ImageFilter.GaussianBlur(.7)), float) / 255
    # the painted island in the generated crop: its main body around the same place
    gl = erode(dilate(painted_land(np.asarray(gen)), 3), 3)
    gseed = (int((centre[0] - box[0]) * k), int((centre[1] - box[1]) * k))
    gen_main = component(gl, gseed)
    if gen_main.sum() < 1000: sys.exit('register: no island found in the painting at the data island centre')
    gmask = Image.fromarray(gen_main.astype(np.uint8) * 255)
    def score(p): return iou(np.asarray(warp(gmask, box, p, Image.BILINEAR), float) / 255, target)
    # start from the areas and centroids, then a pattern search on scale and offset
    def moments(m):
        ys, xs = np.nonzero(m); return xs.mean(), ys.mean(), m.sum()
    gx, gy, ga = moments(gen_main); dx, dy, da = moments(new_main)
    s0 = math.sqrt(da / (ga / k / k)); p = [s0, s0, dx - gx / k * s0, dy - gy / k * s0]
    best = score(p); steps = [.02, .02, 2.0, 2.0]
    while max(steps[2:]) > .124:
        moved = False
        for i in range(4):
            for sgn in (1, -1):
                q = list(p); q[i] += sgn * steps[i]; sc = score(q)
                if sc > best + 1e-5: p, best, moved = q, sc, True
        if not moved: steps = [s / 2 for s in steps]
    fitted = np.asarray(warp(gen, box, p), float)
    fitted_land = np.asarray(warp(gmask, box, p, Image.BILINEAR)) > 127
    # the edit mask: the old painted island, the new island (stacks too) and the painted one where it lies on it
    old = np.zeros((h, w), bool)
    o = component(erode(dilate(painted_land(crop), 2), 2), (OLD_SEED[0] - box[0], OLD_SEED[1] - box[1]))
    old |= o
    old |= dilate(old, 26) & shallow(crop)                    # and its pale shallows
    fu8 = fitted.astype(np.uint8)
    gen_land = erode(dilate(painted_land(fu8), 2), 2) & dilate(new_all, 10)
    gen_land |= dilate(gen_land, 20) & shallow(fu8)           # the painting's own shallows around the new island
    union = dilate(old, 4) | dilate(new_all, 6) | gen_land
    core = dilate(union, 5)
    alpha = np.asarray(Image.fromarray(core.astype(np.uint8) * 255).filter(ImageFilter.GaussianBlur(5)), float) / 255
    alpha[alpha < 1.5 / 255] = 0.0
    inner = [box[1] > 0 and alpha[0].any(), box[3] < OH and alpha[-1].any(), box[0] > 0 and alpha[:, 0].any(),
             box[2] < OW and alpha[:, -1].any()]
    if any(inner): sys.exit(f'register: the edit reaches the crop box edge {inner}; widen MARGIN')
    # the painting's sea to the sheet's sea: a mean shift measured on the open water just outside the island
    ring = dilate(core, 20) & ~dilate(core, 10) & ~painted_land(crop) & ~painted_land(fu8)
    shift = np.clip(crop[ring].mean(0) - fitted[ring].mean(0), -25, 25) if ring.sum() > 200 else np.zeros(3)
    fitted = np.clip(fitted + shift, 0, 255)
    blend = np.rint(crop * (1 - alpha[..., None]) + fitted * alpha[..., None]).astype(np.uint8)
    out = parent.copy(); out[box[1]:box[3], box[0]:box[2]] = blend
    # the check: nothing changed outside the mask, anywhere on the sheet
    changed = (out != parent).any(-1)
    outside = np.ones(changed.shape, bool); outside[box[1]:box[3], box[0]:box[2]] = alpha == 0
    if (changed & outside).any(): sys.exit('register: pixels changed outside the edit mask')
    unchanged = 100.0 * (1 - changed.sum() / changed.size)
    cb = bbox(changed)
    cand = Image.fromarray(out); cand.save(WORK / 'world_map_candidate.png', optimize=True)
    # overlays for review: the data coastline (magenta) and stair (yellow) over the parent and the result
    def overlay(img):
        im = Image.fromarray(img).resize((w * 3, h * 3), Image.LANCZOS); d = ImageDraw.Draw(im)
        edge = new_all & ~erode(new_all, 1); ys, xs = np.nonzero(edge)
        for x, y in zip(xs, ys): d.point([(x * 3 + 1, y * 3 + 1)], fill=(255, 0, 255))
        pts = [local_to_sheet(x, y) for x, y, t in ISL.path_points()]
        d.line([((float(a) - box[0]) * 3, (float(b) - box[1]) * 3) for a, b in pts], fill=(255, 230, 0), width=2)
        return im
    a, b = overlay(crop), overlay(blend)
    sheet = Image.new('RGB', (a.width * 2 + 12, a.height), 'white'); sheet.paste(a, (0, 0)); sheet.paste(b, (a.width + 12, 0))
    sheet.save(WORK / 'registration-check.jpg', quality=88)
    ledger = json.load(open(LEDGER))
    check = dict(crop_box=box, fit=dict(scale=[round(p[0], 4), round(p[1], 4)], offset_px=[round(p[2], 2), round(p[3], 2)],
                                        iou_main_island=round(best, 4)),
                 sea_shift_rgb=[round(float(v), 1) for v in shift], changed_bbox=cb, changed_pixels=int(changed.sum()),
                 unchanged_percent=round(unchanged, 4), outside_edit_identical=True,
                 parent_pixels_sha256=sha(parent.tobytes()), candidate_pixels_sha256=sha(out.tobytes()))
    json.dump(check, open(WORK / 'registration-check.json', 'w'), indent=2)
    parent_prov = json.load(open(WORK / 'parent_provenance.json'))
    prov = dict(model='mixed; south-west island by gpt-image-2.5-sunburst', quality='high', parent=parent_prov,
                local_edit=dict(scope='The south-west island only (redesigned island.py); the rest of the sheet, its '
                                      'bounds, projection and zones are the parent\'s.',
                                model=ledger['requested_model'], quality=ledger['quality'], size=ledger['size'],
                                call='games/yorimichi/world/map/painted/island_repaint.provenance.json',
                                execution='games/yorimichi/world/map/repaint_island.py', crop_box=box, changed_bbox=cb,
                                unchanged_percent=check['unchanged_percent'], outside_edit_identical=True,
                                fit=check['fit'], sea_shift_rgb=check['sea_shift_rgb'],
                                generated_sha256=next(iter(ledger['output'].values())),
                                parent_sha256=info['parent_file_sha256'], parent_pixels_sha256=check['parent_pixels_sha256'],
                                art_pixels_sha256=check['candidate_pixels_sha256']),
                prompt='games/yorimichi/world/map/painted/island_repaint.provenance.json')
    json.dump(prov, open(WORK / 'paint_provenance.json', 'w'), indent=2)
    print('register:', json.dumps(check))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('stage', choices=['prepare', 'paint', 'register'])
    ap.add_argument('--force', action='store_true', help='prepare: take the committed sheet as the parent again')
    ap.add_argument('--dry-run', action='store_true', help='paint: print the prompt and stop')
    args = ap.parse_args()
    {'prepare': prepare, 'paint': paint, 'register': register}[args.stage](args)


if __name__ == '__main__':
    main()
