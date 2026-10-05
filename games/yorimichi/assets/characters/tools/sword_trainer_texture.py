"""Kaede's texture made game-ready: Tripo's baked lighting taken out, and her face redrawn clean (eyes, brows, mouth).

    blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/sword_trainer_texture.py -- \\
        --input <revision>/SwordTrainer-Rig-rNN.blend --output <asset>/rig-rMM [--strength 0.35]

Tripo paints its own light into the colour: darker hair undersides, a gradient over the face, occlusion in every fold.
In the game the engine lights her, so that light is taken out: the texels are grouped by colour (k-means in Lab, the
lightness counted at half weight, so a shadowed and a lit patch of the same cloth fall together), and in each group the
lightness is pulled toward the group's median, keeping `strength` (0.35) of its departure from it. Hue and chroma stay.

The face is redrawn in 3D, because the texture atlas is cut into hundreds of islands: every texel's position on the
body is baked (Cycles), and the texels of the face (skin on the front of the head) are laid out in a front view at
0.6 mm a cell. There the painted eyes are the two dark blobs inside the skin, side by side; each becomes a clean solid
oval (Cairo's eye style) of the blob's own size and place. The brows and the mouth (the other dark blobs inside the
skin) are kept, made solid and smoothed; everything else dark or muddy on the skin (pencil strokes, smudges, the
sketchy scar) becomes plain skin, of the face's own median colour. Writes the revision with the new texture packed
(the mesh, rig and clips untouched), before/after renders of the face and the body (lit and albedo) and texture.json.
"""
import argparse, json, math, shutil, sys
from collections import deque
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector

ap = argparse.ArgumentParser()
ap.add_argument('--input', required=True)
ap.add_argument('--output', required=True)
ap.add_argument('--strength', type=float, default=.35)
ap.add_argument('--clusters', type=int, default=12)
ap.add_argument('--no-renders', action='store_true')
a = ap.parse_args(sys.argv[sys.argv.index('--') + 1:])
src = Path(a.input).resolve()
out = Path(a.output); out.mkdir(parents=True, exist_ok=True)
rev = out.name   # rig-rNN
NAME = f'SwordTrainer-Rig-{rev.split("-")[-1]}'
bpy.ops.wm.open_mainfile(filepath=str(src))
scene = bpy.context.scene
arm = next(o for o in scene.objects if o.type == 'ARMATURE')
body = next(o for o in scene.objects if o.type == 'MESH' and o.vertex_groups)
mat = body.data.materials[0]
nt = mat.node_tree
bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
color_node = bsdf.inputs['Base Color'].links[0].from_node
image = color_node.image
W, H = image.size
arm.data.pose_position = 'REST'
bpy.context.view_layer.update()
# Tripo's normal map embosses its own drawing (the eye outlines, the pencil strokes) into the surface, so the old
# eyes come back as creases under any light. The game's character material uses no normal map; neither does this.
normal_links = [l for l in nt.links if l.to_node == bsdf and l.to_socket.name == 'Normal']
for link in normal_links:
    nt.links.remove(link)


def render(tag, albedo):
    """Front three-quarter of the face, and the whole body front, lit or as bare albedo."""
    if a.no_renders:
        return
    out_node = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL')
    surface = out_node.inputs['Surface'].links[0].from_socket
    em = None
    if albedo:
        em = nt.nodes.new('ShaderNodeEmission')
        nt.links.new(color_node.outputs['Color'], em.inputs['Color'])
        nt.links.new(em.outputs[0], out_node.inputs['Surface'])
    cam = scene.camera
    if cam is None:
        cam = bpy.data.objects.new('Review camera', bpy.data.cameras.new('Review camera')); scene.collection.objects.link(cam); scene.camera = cam
    scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in {e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items} else 'BLENDER_EEVEE'
    scene.render.resolution_x = scene.render.resolution_y = 800
    top = max((body.matrix_world @ v.co).z for v in body.data.vertices)
    for shot, loc, at, scale in (('face', (3, .9, .87 * top), (0, 0, .87 * top), .3 * top), ('body', (3, 0, .5 * top), (0, 0, .5 * top), 1.1 * top)):
        cam.data.type = 'ORTHO'; cam.data.ortho_scale = scale
        cam.location = Vector(loc); cam.rotation_euler = (Vector(at) - cam.location).to_track_quat('-Z', 'Y').to_euler()
        scene.render.filepath = str(out / f'{tag}-{shot}-{"albedo" if albedo else "lit"}.png')
        bpy.ops.render.render(write_still=True)
    if em:
        nt.links.new(surface, out_node.inputs['Surface'])
        nt.nodes.remove(em)


for albedo in (False, True):
    render('before', albedo)

# --- bake every texel's place and facing on the body (Cycles emission bakes) ---------------------------------------
scene.render.engine = 'CYCLES'
scene.cycles.samples = 1
scene.cycles.device = 'CPU'
scene.render.bake.margin = 4
geo = nt.nodes.new('ShaderNodeNewGeometry')
em = nt.nodes.new('ShaderNodeEmission')
out_node = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL')
surface = out_node.inputs['Surface'].links[0].from_socket
nt.links.new(em.outputs[0], out_node.inputs['Surface'])
bpy.ops.object.select_all(action='DESELECT'); body.select_set(True); bpy.context.view_layer.objects.active = body


BW, BH = W // 2, H // 2   # positions at half the texture's size (a texel pair shares one), to bake in little memory


def bake(socket):
    target = bpy.data.images.new('bake', BW, BH, float_buffer=True, alpha=True)
    target.generated_color = (0, 0, 0, 0)
    node = nt.nodes.new('ShaderNodeTexImage'); node.image = target
    nt.nodes.active = node
    if socket is None:
        em.inputs['Color'].default_value = (1, 1, 1, 1)
        for link in list(em.inputs['Color'].links):
            nt.links.remove(link)
    else:
        nt.links.new(socket, em.inputs['Color'])
    bpy.ops.object.bake(type='EMIT', margin=4)
    px = np.empty(BW * BH * 4, np.float32); target.pixels.foreach_get(px)
    nt.nodes.remove(node); bpy.data.images.remove(target)
    return px.reshape(BH, BW, 4)


def full(x):
    return np.repeat(np.repeat(x, H // BH, 0), W // BW, 1)


# Kept at the bake's size and read through `half` (a texel's pair), to stay in little memory.
position = bake(geo.outputs['Position'])[..., :3].copy()
normal = bake(geo.outputs['Normal'])[..., :3].copy()
cover_half = bake(None)[..., 0] > .5
cover = full(cover_half)
nt.links.new(surface, out_node.inputs['Surface'])
nt.nodes.remove(em); nt.nodes.remove(geo)

px = np.empty(W * H * 4, np.float32); image.pixels.foreach_get(px)
rgba = px.reshape(H, W, 4)


def chunked(fn, x, rows=256):
    """fn over x in bands of rows (the conversions' temporaries stay small)."""
    out = np.empty(x.shape, np.float32)
    for i in range(0, len(x), rows):
        out[i:i + rows] = fn(x[i:i + rows])
    return out


def to_lab(c):
    lin = np.where(c <= .04045, c / 12.92, ((c + .055) / 1.055) ** 2.4)
    M = np.array([[.4124, .3576, .1805], [.2126, .7152, .0722], [.0193, .1192, .9505]], np.float32)
    xyz = lin @ M.T / np.array([.95047, 1., 1.08883], np.float32)
    f = np.where(xyz > .008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def from_lab(lab):
    fy = (lab[..., 0] + 16) / 116; fx = fy + lab[..., 1] / 500; fz = fy - lab[..., 2] / 200
    f = np.stack([fx, fy, fz], -1)
    xyz = np.where(f ** 3 > .008856, f ** 3, (f - 16 / 116) / 7.787) * np.array([.95047, 1., 1.08883], np.float32)
    M = np.array([[3.2406, -1.5372, -.4986], [-.9689, 1.8758, .0415], [.0557, -.2040, 1.0570]], np.float32)
    lin = np.clip(xyz @ M.T, 0, 1)
    return np.where(lin <= .0031308, lin * 12.92, 1.055 * lin ** (1 / 2.4) - .055)


# --- take Tripo's light out ---------------------------------------------------------------------------------------
lab = chunked(to_lab, rgba[..., :3])
# The face's line work (mouth, nose, brows) is drawing, not light: its texels on the front of the head are kept as
# they were, and put back after the light pass.
top = float(position[..., 2][cover_half].max())
front_head = full(cover_half & (position[..., 2] > .74 * top) & (normal[..., 0] > .05) & (position[..., 0] > 0))
head_rows, head_cols = np.nonzero(front_head)
head_before = lab[head_rows, head_cols].copy()
used = cover.reshape(-1)
flat = lab.reshape(-1, 3)
feat = flat * np.array([.5, 1., 1.], np.float32)
rng = np.random.default_rng(7)
sample = feat[used][rng.choice(int(used.sum()), 200000, replace=False)]
centres = sample[rng.choice(len(sample), a.clusters, replace=False)]
for _ in range(25):
    d = ((sample[:, None, :] - centres[None]) ** 2).sum(-1)
    k = d.argmin(1)
    centres = np.stack([sample[k == i].mean(0) if (k == i).any() else centres[i] for i in range(a.clusters)])
del sample
labels = np.empty(len(feat), np.int32)
for s in range(0, len(feat), 1 << 20):
    labels[s:s + (1 << 20)] = ((feat[s:s + (1 << 20), None, :] - centres[None]) ** 2).sum(-1).argmin(1)
L = flat[:, 0].copy()
clusters = []
for i in range(a.clusters):
    m = used & (labels == i)
    if not m.any():
        continue
    med = float(np.median(L[m]))
    L[m] = med + a.strength * (L[m] - med)
    clusters.append({'share': round(float(m.mean() / used.mean()), 4), 'lab_median': [round(med, 1), round(float(np.median(flat[m, 1])), 1), round(float(np.median(flat[m, 2])), 1)],
                     'lightness_spread_before': round(float(np.percentile(flat[m, 0], 90) - np.percentile(flat[m, 0], 10)), 1)})
del feat
lab2 = flat.copy(); lab2[:, 0] = L
del L, flat, lab
lab = lab2.reshape(H, W, 3)

# --- the face, laid out in a front view ---------------------------------------------------------------------------
P = full(position); N = None
hz = position[..., 2][cover_half]
top = float(hz.max())
# Her head: the top 26% of her height; the face is its front (facing +X), skin coloured.
skin_ref = to_lab(np.array([[.93, .76, .62]], np.float32))[0]    # a light warm skin, to pick the skin cluster
skin_cluster = int((((centres / np.array([.5, 1., 1.])) - skin_ref) ** 2 * np.array([.25, 1, 1])).sum(1).argmin())
head = full(cover_half & (position[..., 2] > .74 * top) & (normal[..., 0] > .05) & (position[..., 0] > 0))
del normal
skin = head & (labels.reshape(H, W) == skin_cluster)
sy, sz = P[..., 1][skin], P[..., 2][skin]
face_box = (float(np.percentile(sy, 1)), float(np.percentile(sy, 99)), float(np.percentile(sz, 1)), float(np.percentile(sz, 99)))
CELL = .0006 * top
y0, y1, z0, z1 = face_box[0] - .01 * top, face_box[1] + .01 * top, face_box[2] - .01 * top, face_box[3] + .01 * top
GW, GH = int((y1 - y0) / CELL) + 1, int((z1 - z0) / CELL) + 1
inface = head & (P[..., 1] > y0) & (P[..., 1] < y1) & (P[..., 2] > z0) & (P[..., 2] < z1)
skin_before = float(np.median(head_before[(labels.reshape(H, W)[head_rows, head_cols] == skin_cluster), 0]))
lines = inface[head_rows, head_cols] & (head_before[:, 0] > 36.) & (head_before[:, 0] < skin_before - 8.)
lab[head_rows[lines], head_cols[lines]] = head_before[lines]
del head_before
ty, tx = np.nonzero(inface)
gx = ((P[ty, tx, 1] - y0) / CELL).astype(int); gz = ((z1 - P[ty, tx, 2]) / CELL).astype(int)   # columns along y, rows down z
depth = np.full((GH, GW), -1e9, np.float32)
np.maximum.at(depth, (gz, gx), P[ty, tx, 0])
front = P[ty, tx, 0] >= depth[gz, gx] - .004 * top   # the texels on the visible surface of each cell
grid_L = np.full((GH, GW), np.nan, np.float32); grid_skin = np.zeros((GH, GW), bool); grid_any = np.zeros((GH, GW), bool)
Lf = lab[ty, tx, 0]; isskin = (labels.reshape(H, W)[ty, tx] == skin_cluster)
grid_any[gz[front], gx[front]] = True
order = np.argsort(P[ty, tx, 0][front])
grid_L[gz[front][order], gx[front][order]] = Lf[front][order]   # the frontmost sample of each cell: what is seen there
grid_skin[gz[front & isskin], gx[front & isskin]] = True
# The baked places are sparser than the cells: an empty cell takes a neighbour's sample (twice, over 8 neighbours).
for _ in range(2):
    empty = ~grid_any
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if not (dr or dc):
                continue
            src_any = np.roll(np.roll(grid_any, dr, 0), dc, 1)
            take = empty & src_any & ~grid_any
            grid_L[take] = np.roll(np.roll(grid_L, dr, 0), dc, 1)[take]
            grid_skin[take] = np.roll(np.roll(grid_skin, dr, 0), dc, 1)[take]
            grid_any |= take
skin_L = float(np.median(lab[skin][:, 0]))
dark = grid_any & (np.nan_to_num(grid_L, nan=100.) < skin_L - 28.)


def save_map(path, rgb):
    img = bpy.data.images.new('face map', GW, GH)
    img.pixels.foreach_set(np.dstack([rgb[::-1], np.ones((GH, GW, 1))]).astype(np.float32).reshape(-1))
    img.filepath_raw = str(path); img.file_format = 'PNG'; img.save()
    bpy.data.images.remove(img)


# The face as found, for review: lightness, skin tinted green, the dark cells red.
debug = np.dstack([np.nan_to_num(grid_L, nan=0.) / 100.] * 3)
debug[grid_skin] *= (.8, 1., .8)
debug[dark] = (1., .1, .1)
debug[grid_any & (np.nan_to_num(grid_L, nan=100.) < skin_L - 10.) & ~dark] = (1., .9, .1)
save_map(out / 'face-found.png', debug)
print('FACE GRID', GW, GH, 'skin L', round(skin_L, 1), 'dark cells', int(dark.sum()), 'skin cells', int(grid_skin.sum()), flush=True)


def components(mask):
    seen = np.zeros_like(mask); comps = []
    for r0, c0 in zip(*np.nonzero(mask)):
        if seen[r0, c0]:
            continue
        q = deque([(r0, c0)]); seen[r0, c0] = True; cells = []
        while q:
            r, c = q.popleft(); cells.append((r, c))
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                rr, cc = r + dr, c + dc
                if 0 <= rr < mask.shape[0] and 0 <= cc < mask.shape[1] and mask[rr, cc] and not seen[rr, cc]:
                    seen[rr, cc] = True; q.append((rr, cc))
        comps.append(np.array(cells))
    return comps


# Dark blobs inside the skin: not touching the hair (cells that are neither skin nor dark-in-skin border them).
inside = []
for c in components(dark):
    if len(c) < 12:
        continue
    r, k = c[:, 0], c[:, 1]
    ring = set()
    for dr, dc in ((2, 0), (-2, 0), (0, 2), (0, -2)):
        for rr, cc in zip(r + dr, k + dc):
            if 0 <= rr < GH and 0 <= cc < GW and not dark[rr, cc]:
                ring.add((rr, cc))
    skin_share = np.mean([grid_skin[rr, cc] for rr, cc in ring]) if ring else 0.
    h, w = r.max() - r.min() + 1, k.max() - k.min() + 1
    inside.append(dict(cells=c, skin=float(skin_share), h=int(h), w=int(w), rc=(float(r.mean()), float(k.mean())), n=len(c)))
inside_all = inside
inside = [b for b in inside if b['skin'] > .75]
# The eyes: the pair of roundish blobs (taller than half their width) side by side, mirrored about the middle.
mid = (0. - y0) / CELL
rounds = [b for b in inside if b['h'] >= .6 * b['w'] and b['n'] >= 40]
pair = None
for i, b in enumerate(rounds):
    for c in rounds[i + 1:]:
        if abs(b['rc'][0] - c['rc'][0]) < .25 * max(b['h'], c['h']) and (b['rc'][1] - mid) * (c['rc'][1] - mid) < 0:
            score = abs(b['n'] - c['n']) / max(b['n'], c['n']) + abs(abs(b['rc'][1] - mid) - abs(c['rc'][1] - mid)) / max(b['w'], 1)
            if pair is None or score < pair[0]:
                pair = (score, b, c)
assert pair, ('no pair of eyes found', [(b['n'], b['h'], b['w'], b['rc']) for b in inside])
eyes = [pair[1], pair[2]]
# The others inside the skin: brows (above the eyes) and the mouth (below them) stay as drawn; a small blob (under
# 9 mm across: a pencil stroke, the sketchy scar, a smudge) is a mark, wiped to skin. Anything larger (a strand of
# hair across the forehead) is left alone.
eye_row = np.mean([e['rc'][0] for e in eyes]); eye_h = np.mean([e['h'] for e in eyes])
MARK = 9. / 1000 * top / 1.68 / CELL   # cells
features, marks = [], []
for b in inside:
    if any(b is e for e in eyes):
        continue
    above = b['rc'][0] < eye_row - .5 * eye_h and b['w'] > 1.5 * b['h'] and b['w'] > MARK
    below = b['rc'][0] > eye_row + 1.5 * eye_h and abs(b['rc'][1] - mid) < .25 * GW and b['w'] > 2 * b['h']
    if above or below:
        features.append(dict(b, kind='brow' if above else 'mouth'))
    elif max(b['h'], b['w']) < MARK:
        marks.append(b)
# Small dark strokes with hair beside them (the hatching at a temple): marks too, when skin is most of what is round them.
for b in inside_all:
    if b['skin'] <= .75 and b['skin'] > .5 and max(b['h'], b['w']) < MARK and not any(abs(b['rc'][0] - e['rc'][0]) < .5 * e['h'] and abs(b['rc'][1] - e['rc'][1]) < .5 * e['w'] for e in eyes):
        marks.append(b)
# Fainter marks too (a light-brown pencil stroke, the scratch between the brows): small mid-dark blobs inside the skin,
# away from the eyes, the brows and the nose and mouth (the middle of the face below the eyes).
muddy = grid_any & (np.nan_to_num(grid_L, nan=100.) < skin_L - 10.) & ~dark
for c in components(muddy):
    if len(c) < 6:
        continue
    r, k = c[:, 0], c[:, 1]
    h, w = r.max() - r.min() + 1, k.max() - k.min() + 1
    rc = (float(r.mean()), float(k.mean()))
    near_eye = any(abs(rc[0] - e['rc'][0]) < e['h'] and abs(rc[1] - e['rc'][1]) < e['w'] for e in eyes)
    nose_mouth = rc[0] > eye_row + .5 * eye_h and abs(rc[1] - mid) < .14 * GW
    ring = [(rr, cc) for rr, cc in zip(np.concatenate([r - 2, r + 2, r, r]), np.concatenate([k, k, k - 2, k + 2]))
            if 0 <= rr < GH and 0 <= cc < GW and not muddy[rr, cc]]
    skinny = np.mean([grid_skin[rr, cc] for rr, cc in ring]) if ring else 0.
    if max(h, w) < MARK and skinny > .6 and not near_eye and not nose_mouth:
        marks.append(dict(cells=c, h=int(h), w=int(w), rc=rc, n=len(c), skin=float(skinny)))

# Repaint: each eye a clean solid oval of the blob's size, with a ring of skin round it (Tripo's muddy rim); the brows
# found made solid (their own dark texels, one colour); the marks wiped to the face's median skin; the rest of the skin
# as the light pass left it (its mouth, nose and ears drawn in it).
paint = np.zeros((GH, GW), np.int8)   # 0 leave, 1 eye, 2 skin (not over hair), 3 feature colour, 4 skin (eye ring)
yy, xx = np.mgrid[0:GH, 0:GW]
ovals, eye_ovals = [], []
# Each eye's whole drawing (its outline and rim too, lighter than its core): the mid-dark region round the core.
drawn = grid_any & (np.nan_to_num(grid_L, nan=100.) < skin_L - 12.)
drawn_parts = components(drawn)
for e in eyes:
    core = {(int(r), int(c)) for r, c in e['cells']}
    whole = next((p for p in drawn_parts if (int(p[0, 0]), int(p[0, 1])) in core or any((int(r), int(c)) in core for r, c in p[:50])), None)
    if whole is not None and len(whole) < 4 * e['n']:
        cells = whole
    else:
        cells = e['cells']
    r, c = cells[:, 0], cells[:, 1]
    cr, cc = (r.min() + r.max()) / 2, (c.min() + c.max()) / 2
    rh, rw = (r.max() - r.min() + 1) / 2 * .94, (c.max() - c.min() + 1) / 2 * .9
    core_c = e['cells'][:, 1]
    core_w = (core_c.max() - core_c.min() + 1) / 2 * .9   # the dark core's half width: the eye's own width
    q = ((yy - cr) / rh) ** 2 + ((xx - cc) / rw) ** 2
    paint[(q <= 1.5) & (paint == 0)] = 4   # the ring (drawn per texel below)
    paint[q <= 1] = 1
    eye_ovals.append((cr, cc, rh, rw, core_w, (core_c.min() + core_c.max()) / 2))   # the drawing's oval, and the core's middle
    ovals.append({'centre_mm': [round((cc * CELL + y0) * 1000 / top * 1.68, 1), round((z1 - cr * CELL) * 1000 / top * 1.68, 1)],
                  'size_mm': [round(2 * rw * CELL * 1000 / top * 1.68, 1), round(2 * rh * CELL * 1000 / top * 1.68, 1)]})
for b in marks:
    m = np.zeros((GH, GW), bool); m[b['cells'][:, 0], b['cells'][:, 1]] = True
    m = np.max([np.pad(m, 4)[4 + dr:4 + dr + GH, 4 + dc:4 + dc + GW] for dr in range(-4, 5) for dc in range(-4, 5)], 0)   # its faint edges too
    paint[m & (paint == 0)] = 2
for f in features:
    if f['kind'] == 'brow':
        paint[f['cells'][:, 0], f['cells'][:, 1]] = np.where(paint[f['cells'][:, 0], f['cells'][:, 1]] == 0, 3, paint[f['cells'][:, 0], f['cells'][:, 1]])
cls = paint[gz, gx]
here = front | isskin
skin_lab = np.median(lab[skin], 0)
eye_lab = to_lab(np.array([[.11, .08, .075]], np.float32))[0]
feature_lab = to_lab(np.array([[.16, .11, .09]], np.float32))[0]
dark_here = lab[ty, tx, 0] < skin_L - 28.
target = np.full(len(ty), -1, np.int8)
# the rings and the marks, not hair crossing them (hair is the darkest thing on the face: lightness under 35)
target[(cls == 2) & here & (lab[ty, tx, 0] > 35.)] = 2
target[(cls == 3) & dark_here] = 3                          # the brows' strokes, solid
for code, value in ((2, skin_lab), (3, feature_lab)):
    m = target == code
    lab[ty[m], tx[m]] = value
# The eyes, per texel from its own place (not its cell), with a soft edge a fifth of a millimetre wide; each ring in the
# colour of the skin just outside it.
# Under each eye the old drawing (its core, outline and rim) becomes skin, the colour of the skin just round it: the
# eye itself is geometry (below), drawn crisp at any distance, where a texture over this cut-up atlas stays ragged.
cy, cx = (z1 - P[ty, tx, 2]) / CELL, (P[ty, tx, 1] - y0) / CELL
# The skin round each eye in the front view (each cell's mean of its skin texels), then diffused into the eye's
# region, so the patch takes the shading of the skin all round it rather than one flat colour.
skin_t = here & isskin
grid_sum = np.zeros((GH, GW, 3), np.float64); grid_n = np.zeros((GH, GW))
np.add.at(grid_sum, (gz[skin_t], gx[skin_t]), lab[ty[skin_t], tx[skin_t]])
np.add.at(grid_n, (gz[skin_t], gx[skin_t]), 1)
for cr, cc, rh, rw, core_w, core_cc in eye_ovals:
    q_cell = np.sqrt(((yy - cr) / rh) ** 2 + ((xx - cc) / rw) ** 2)
    region = q_cell <= 1.5
    fill = np.where(grid_n[..., None] > 0, grid_sum / np.maximum(grid_n, 1)[..., None], np.nan)
    fill[region] = np.nan
    known = ~np.isnan(fill[..., 0])
    fill = np.where(known[..., None], fill, 0.)
    w = known.astype(np.float64)
    for _ in range(300):   # Jacobi: each unknown cell the mean of its known (or filled) neighbours
        nb = sum(np.roll(np.roll(fill * w[..., None], dr, 0), dc, 1) for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)))
        nw = sum(np.roll(np.roll(w, dr, 0), dc, 1) for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)))
        upd = ~known & (nw > 0)
        fill[upd] = nb[upd] / nw[upd, None]
        w = np.where(upd, 1., w)
    q = np.sqrt(((cy - cr) / rh) ** 2 + ((cx - cc) / rw) ** 2)
    # Tripo's outline and lashes hug the eye: to 1.42 they are repainted whatever their colour; farther out, never hair.
    under = here & ((q <= 1.42) | ((q <= 1.5) & (lab[ty, tx, 0] > 35.)))
    lab[ty[under], tx[under]] = fill[gz[under], gx[under]].astype(np.float32)
del P
rgba[..., :3] = np.where(cover[..., None], chunked(from_lab, lab), rgba[..., :3])
image.pixels.foreach_set(rgba.reshape(-1))
image.update()
image.pack()

# --- the eyes: two thin discs on the face, skinned to the head ------------------------------------------------------
from mathutils.bvhtree import BVHTree
depsgraph = bpy.context.evaluated_depsgraph_get()
tree = BVHTree.FromObject(body, depsgraph)
eye_mat = bpy.data.materials.new('Eyes')
eye_mat.use_nodes = True
shader = eye_mat.node_tree.nodes['Principled BSDF']
shader.inputs['Base Color'].default_value = (.012, .008, .007, 1)   # sRGB about (0.11, 0.08, 0.075): Cairo's eye colour
shader.inputs['Roughness'].default_value = .45
ASPECT = 1.6    # Cairo's eyes are upright ovals: at least 1.6 times as tall as wide
discs = []
for cr, cc, rh, rw, core_w, core_cc in eye_ovals:
    hz = rh * CELL * .9; hy = min(core_w * CELL, hz / ASPECT)    # half height and half width (model units)
    zc, yc = z1 - cr * CELL, core_cc * CELL + y0
    rings, segs = 5, 32
    verts, faces = [], []
    for i in range(rings + 1):
        for j in range(segs if i else 1):
            t = i / rings; ang = 2 * math.pi * j / segs
            y, z = yc + hy * t * math.cos(ang), zc + hz * t * math.sin(ang)
            hit, normal_, _, _ = tree.ray_cast(Vector((1., y, z)), Vector((-1., 0., 0.)))
            assert hit is not None, ('no face under the eye', y, z)
            verts.append(hit + normal_ * .0012 * top)
    for j in range(segs):
        faces.append((0, 1 + j, 1 + (j + 1) % segs))
    for i in range(1, rings):
        for j in range(segs):
            a0 = 1 + (i - 1) * segs + j; a1 = 1 + (i - 1) * segs + (j + 1) % segs
            faces.append((a0, a0 + segs, a1 + segs, a1))
    mesh = bpy.data.meshes.new('Kaede eye')
    mesh.from_pydata([tuple(v) for v in verts], [], faces)
    mesh.materials.append(eye_mat)
    for poly in mesh.polygons:
        poly.use_smooth = True
    eye = bpy.data.objects.new('Kaede eye', mesh)
    scene.collection.objects.link(eye)
    eye.parent = arm
    group = eye.vertex_groups.new(name='mixamorig:Head')
    group.add(list(range(len(verts))), 1., 'REPLACE')
    mod = eye.modifiers.new('Armature', 'ARMATURE'); mod.object = arm
    eye['body_region'] = 'eye'
    discs.append({'half_size_mm': [round(hy * 1000 / top * 1.68, 1), round(hz * 1000 / top * 1.68, 1)]})
# Both discs as one object.
bpy.ops.object.select_all(action='DESELECT')
eyes_objects = [o for o in scene.objects if o.name.startswith('Kaede eye')]
for o in eyes_objects:
    o.select_set(True)
bpy.context.view_layer.objects.active = eyes_objects[0]
bpy.ops.object.join()
bpy.context.view_layer.objects.active.name = 'Kaede eyes'

# Front-view maps of the face for review: before (lightness), the found blobs, the repaint.
from_view = np.dstack([np.nan_to_num(grid_L, nan=0.) / 100.] * 3)
for e in eyes:
    from_view[e['cells'][:, 0], e['cells'][:, 1]] = (1, .2, .2)
for f in features:
    from_view[f['cells'][:, 0], f['cells'][:, 1]] = (.2, .6, 1) if f['kind'] == 'brow' else (.2, 1, .4)
for b in marks:
    from_view[b['cells'][:, 0], b['cells'][:, 1]] = (1., .9, .1)
save_map(out / 'face-map.png', from_view)

arm.data.pose_position = 'POSE'
for albedo in (False, True):
    render('after', albedo)
bpy.ops.wm.save_as_mainfile(filepath=str(out / f'{NAME}.blend'), compress=True)
for record in ('source-manifest.json',):
    if (src.parent / record).exists():
        manifest = json.loads((src.parent / record).read_text())
        import hashlib
        manifest['native'] = f'{NAME}.blend'
        manifest['native_sha256'] = hashlib.sha256((out / f'{NAME}.blend').read_bytes()).hexdigest()
        manifest['texture'] = f'{src.name}\'s texture with the baked light flattened (strength {a.strength}) and the face redrawn (texture.json)'
        (out / record).write_text(json.dumps(manifest, indent=2) + '\n')
report = {'from': src.name, 'normal_map': 'disconnected (it embossed the old drawing)' if normal_links else 'none', 'texture': [W, H], 'strength': a.strength, 'clusters': clusters, 'skin_cluster': skin_cluster,
          'face_cells': [GW, GH], 'cell_mm': round(CELL * 1000 / top * 1.68, 3), 'eyes': ovals,
          'features_kept': [f['kind'] for f in features], 'marks_wiped': len(marks), 'eye_discs': discs}
(out / 'texture.json').write_text(json.dumps(report, indent=2) + '\n')
print('TEXTURE OK', json.dumps({k: report[k] for k in ('eyes', 'eye_discs', 'features_kept', 'marks_wiped', 'skin_cluster')}))
