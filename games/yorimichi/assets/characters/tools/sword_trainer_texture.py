"""Kaede's texture made game-ready: Tripo's baked lighting taken out, her eyes and brows solid, her face redrawn clean.

    blender -b --python-exit-code 1 --python games/yorimichi/assets/characters/tools/sword_trainer_texture.py -- \\
        --input <revision>/SwordTrainer-Rig-rNN.blend --output <asset>/rig-rMM [--face face.json] [--strength 0.35]

The method, and why each step is there, is in docs/TRIPO_CHARACTERS.md ("Eyes and light"). In short: every texel's
place, facing and mesh piece are baked; the light is flattened within each material's colour group; Tripo's small eye
(and brow) pieces are recoloured solid; on the head's piece, the face's skin layer takes one smooth skin colour except
the hair; the brows and the mouth are redrawn from the face spec (`assets/characters/<id>/face.json`); the normal map
is disconnected. Writes the revision (mesh, rig and clips untouched), before/after renders (face three-quarter and
straight on, body; lit and albedo), the face maps and texture.json.
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
ap.add_argument('--face', default=str(Path(__file__).resolve().parents[1] / 'sword-trainer' / 'face.json'),
                help='the face spec: eyes, brows and mouth in front-view fractions of the height')
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
    for shot, loc, at, scale in (('face', (3, .9, .87 * top), (0, 0, .87 * top), .3 * top), ('front', (3, 0, .86 * top), (0, 0, .86 * top), .2 * top),
                                 ('body', (3, 0, .5 * top), (0, 0, .5 * top), 1.1 * top)):
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
# The mesh's islands (its welded pieces: the head and face, each hair strand, the clothes...): baked per texel as a
# colour attribute, so the face's repaint touches only the head's own piece, never a strand lying on the skin.
nv = len(body.data.vertices)
co = np.empty(nv * 3, np.float32); body.data.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
keys = {}
weld = np.array([keys.setdefault(tuple(np.round(v, 5)), len(keys)) for v in co])
K = len(keys)
edges = np.empty(len(body.data.edges) * 2, np.int64); body.data.edges.foreach_get('vertices', edges)
ev = weld[edges.reshape(-1, 2)]
ev = ev[ev[:, 0] != ev[:, 1]]
root = np.arange(K)
def find(i):
    while root[i] != i:
        root[i] = root[root[i]]; i = root[i]
    return i
for u, v in ev:
    ru, rv = find(u), find(v)
    if ru != rv:
        root[ru] = rv
piece = np.array([find(i) for i in range(K)])
_, piece = np.unique(piece, return_inverse=True)
vertex_piece = piece[weld]
attr = body.data.color_attributes.new('kaede_piece', 'FLOAT_COLOR', 'POINT')
code = np.zeros((nv, 4), np.float32); code[:, 0] = (vertex_piece % 256 + .5) / 256; code[:, 1] = (vertex_piece // 256 + .5) / 256; code[:, 3] = 1
attr.data.foreach_set('color', code.ravel())
attr_node = nt.nodes.new('ShaderNodeAttribute'); attr_node.attribute_name = 'kaede_piece'
coded = bake(attr_node.outputs['Color'])
piece_half = np.floor(coded[..., 0] * 256).astype(np.int32) + 256 * np.floor(coded[..., 1] * 256).astype(np.int32)
nt.nodes.remove(attr_node)
body.data.color_attributes.remove(body.data.color_attributes['kaede_piece'])
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
# Groups of one material: a lit and a shaded patch of the same skin or cloth split into two clusters (their lightness
# differs), and flattening each toward its own median would leave a step where they meet. Clusters of nearly the same
# colour (a, b within 9) and lightness within 25 are merged first.
cl = centres / np.array([.5, 1., 1.])
group = list(range(a.clusters))
def gfind(i):
    while group[i] != i:
        i = group[i]
    return i
for i in range(a.clusters):
    for j in range(i + 1, a.clusters):
        if np.hypot(cl[i, 1] - cl[j, 1], cl[i, 2] - cl[j, 2]) < 9. and abs(cl[i, 0] - cl[j, 0]) < 25.:
            group[gfind(j)] = gfind(i)
merged = np.array([gfind(i) for i in range(a.clusters)])
labels = merged[labels]
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
skin_cluster = int(merged[(((centres / np.array([.5, 1., 1.])) - skin_ref) ** 2 * np.array([.25, 1, 1])).sum(1).argmin()])
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
lines = inface[head_rows, head_cols] & (head_before[:, 0] > 36.) & (head_before[:, 0] < skin_before - 18.)   # lines, not shading
lab[head_rows[lines], head_cols[lines]] = head_before[lines]
del head_before
ty, tx = np.nonzero(inface)
gx = ((P[ty, tx, 1] - y0) / CELL).astype(int); gz = ((z1 - P[ty, tx, 2]) / CELL).astype(int)   # columns along y, rows down z
depth = np.full((GH, GW), -1e9, np.float32)
np.maximum.at(depth, (gz, gx), P[ty, tx, 0])
front = P[ty, tx, 0] >= depth[gz, gx] - .004 * top   # the texels on the visible surface of each cell
tex_piece = piece_half[ty // (H // BH), tx // (W // BW)]
head_piece = int(np.bincount(tex_piece[(labels.reshape(H, W)[ty, tx] == skin_cluster) & front]).argmax())   # the face's piece
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

# --- the face rebuilt, as a painter would: one smooth skin, solid brows, a clean mouth, geometry eyes ---------------
yy, xx = np.mgrid[0:GH, 0:GW]
ovals, eye_ovals = [], []
# Each eye's whole drawing (its outline and rim too, lighter than its core): the mid-dark region round the core.
drawn = grid_any & (np.nan_to_num(grid_L, nan=100.) < skin_L - 12.)
drawn_parts = components(drawn)
for e in eyes:
    core = {(int(r), int(c)) for r, c in e['cells']}
    whole = next((p for p in drawn_parts if any((int(r), int(c)) in core for r, c in p[:200])), None)
    cells = whole if whole is not None and len(whole) < 4 * e['n'] else e['cells']
    r, c = cells[:, 0], cells[:, 1]
    cr, cc = (r.min() + r.max()) / 2, (c.min() + c.max()) / 2
    rh, rw = (r.max() - r.min() + 1) / 2 * .94, (c.max() - c.min() + 1) / 2 * .9
    core_c = e['cells'][:, 1]
    core_w = (core_c.max() - core_c.min() + 1) / 2 * .9   # the dark core's half width: the eye's own width
    eye_ovals.append((cr, cc, rh, rw, core_w, (core_c.min() + core_c.max()) / 2))   # the drawing's oval, and the core's middle
    ovals.append({'centre_mm': [round((cc * CELL + y0) * 1000 / top * 1.68, 1), round((z1 - cr * CELL) * 1000 / top * 1.68, 1)],
                  'size_mm': [round(2 * rw * CELL * 1000 / top * 1.68, 1), round(2 * rh * CELL * 1000 / top * 1.68, 1)]})


face_spec = json.loads(Path(a.face).read_text()) if Path(a.face).exists() else None
disc_sizes = None
if face_spec:
    # The spec's eyes (checked by eye on a grid over the face) take the place of the found ones.
    eye_ovals, disc_sizes = [], []
    for e in face_spec['eyes']:
        (ey, ez), (hw, hh), dh = e['centre'], e['drawing_half'], e['disc_half']
        cr, cc = (z1 - ez * top) / CELL, (ey * top - y0) / CELL
        eye_ovals.append((cr, cc, hh * top / CELL, hw * top / CELL, dh[0] * top / CELL, cc))
        disc_sizes.append((dh[0] * top, dh[1] * top))


def grow(mask, n):
    out = mask.copy()
    for _ in range(n):
        out = np.max([np.roll(np.roll(out, dr, 0), dc, 1) for dr in (-1, 0, 1) for dc in (-1, 0, 1)], 0)
    return out


def box_blur(x, n, passes=3):
    for _ in range(passes):
        x = sum(np.roll(np.roll(x, dr, 0), dc, 1) for dr in range(-n, n + 1) for dc in range(-n, n + 1)) / (2 * n + 1) ** 2
    return x


here = front | isskin
on_head = tex_piece == head_piece
# Hair: the texels of a dark colour group (hair, the brows' and eyes' ink): never repainted as skin outside the eyes
# and brows, so a strand across the face (even one of the head's own piece) stays.
group_L = {g: float(np.median(lab[used.reshape(H, W) & (labels.reshape(H, W) == g)][:, 0])) for g in np.unique(labels[used])}
hair_groups = [g for g, l in group_L.items() if l < 38.]
is_hair = np.isin(labels.reshape(H, W)[ty, tx], hair_groups)
# The face: the skin's cells in the front view, their holes (eyes, brows, mouth) closed.
skin_cells = np.zeros((GH, GW), bool); skin_cells[gz[isskin & front], gx[isskin & front]] = True
hull = ~grow(~grow(skin_cells, 10), 10)
# The skin's surface in each cell (its frontmost skin texel), carried under what hides it: the brows and the mouth are
# drawn on that layer only, never on a strand of hair lying in front of it.
surface = np.full((GH, GW), -1e9, np.float32)
np.maximum.at(surface, (gz[isskin], gx[isskin]), P[ty, tx, 0][isskin])
known = surface > -1e8
filled = np.where(known, surface, 0.); w = known.astype(float)
for _ in range(400):
    nb = sum(np.roll(np.roll(filled * w, dr, 0), dc, 1) for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)))
    nw = sum(np.roll(np.roll(w, dr, 0), dc, 1) for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)))
    upd = (w == 0) & (nw > 0)
    if not upd.any():
        break
    filled[upd] = nb[upd] / nw[upd]; w[upd] = 1.
# within 3 mm in front of the skin (a brow sculpted proud of it, the lids) or behind it; a strand stands further out
skin_layer = (P[ty, tx, 0] - filled[gz, gx] < .0035 * top) & (P[ty, tx, 0] - filled[gz, gx] > -.004 * top)
face_t = skin_layer & on_head & hull[gz, gx]
# One smooth skin: the skin texels' colour per cell, averaged widely (normalised, so the holes do not darken it).
sk = face_t & isskin & ~is_hair
sum_ = np.zeros((GH, GW, 3)); n_ = np.zeros((GH, GW))
np.add.at(sum_, (gz[sk], gx[sk]), lab[ty[sk], tx[sk]]); np.add.at(n_, (gz[sk], gx[sk]), 1)
field = box_blur(sum_, 5) / np.maximum(box_blur(n_, 5), 1e-6)[..., None]
cy, cx = (z1 - P[ty, tx, 2]) / CELL, (P[ty, tx, 1] - y0) / CELL
f_here = field[gz, gx].astype(np.float32)
# The eyes' old drawings (core, outline, lashes) under the discs: all skin.
eye_zone = np.zeros(len(ty), bool)
for cr, cc, rh, rw, core_w, core_cc in eye_ovals:
    q = np.sqrt(((cy - cr) / rh) ** 2 + ((cx - cc) / rw) ** 2)
    qx = np.sqrt(((cy - cr) / rh) ** 2 + ((cx - cc) / (rw * 1.5)) ** 2)
    eye_zone |= (q <= 1.75) | (qx <= 1.5)   # the lashes reach out to the sides
eye_zone &= skin_layer & on_head
yv, zv = P[ty, tx, 1] / top, P[ty, tx, 2] / top


def stroke(points, thickness):
    """Texels within a stroke: the distance to its centreline under half the thickness there (fractions of height)."""
    pts = np.array(points, float); th = np.array(thickness, float)
    best = np.full(len(yv), np.inf); half = np.zeros(len(yv))
    for i in range(len(pts) - 1):
        p0, p1 = pts[i], pts[i + 1]; seg = p1 - p0; L2 = float(seg @ seg)
        t = np.clip(((yv - p0[0]) * seg[0] + (zv - p0[1]) * seg[1]) / L2, 0, 1)
        d = np.hypot(yv - (p0[0] + t * seg[0]), zv - (p0[1] + t * seg[1]))
        closer = d < best
        best[closer] = d[closer]; half[closer] = (th[i] + t[closer] * (th[i + 1] - th[i])) / 2
    return best < half, best - half


brow_t = np.zeros(len(ty), bool); mouth_t = np.zeros(len(ty), bool)
features = []
if face_spec:
    for b in face_spec['brows']:
        inside_b, gap = stroke(b['points'], b['thickness'])
        brow_t |= inside_b & skin_layer & on_head
        eye_zone |= (gap < .004) & ~inside_b & skin_layer & on_head   # its old scratchy edges: skin
        features.append({'kind': 'brow', 'side': b['side']})
    m = face_spec['mouth']
    inside_m, gap = stroke(m['points'], m['thickness'])
    mouth_t = inside_m & skin_layer & on_head
    eye_zone |= (gap < .003) & ~inside_m & skin_layer & on_head
    features.append({'kind': 'mouth'})
    colours = face_spec.get('colours', {})
    feature_lab = to_lab(np.array([colours.get('brows', [.16, .11, .09])], np.float32))[0]
    mouth_lab = to_lab(np.array([colours.get('mouth', [.42, .24, .19])], np.float32))[0]
else:
    mouth_lab = to_lab(np.array([[.42, .24, .19]], np.float32))[0]
# Paint: the skin (everything on the face's piece that is not hair, and the eyes' and brows' surroundings), then the
# brows and the mouth over it.
# Hair painted onto the skin itself (a streak on a cheek beside a strand), well inside the face: skin too; real strands
# stand in front of the skin layer and the hairline is at the face's edge, so neither is touched.
inner = ~grow(~hull, 5)
painted_hair = face_t & is_hair & skin_layer & inner[gz, gx] & ~brow_t
skin_paint = (face_t & ~is_hair) | eye_zone | painted_hair
lab[ty[skin_paint], tx[skin_paint]] = f_here[skin_paint]
lab[ty[brow_t], tx[brow_t]] = feature_lab
lab[ty[mouth_t], tx[mouth_t]] = mouth_lab
# Tripo models the eyes (and often the brows) as small pieces of their own, set into the face, their texture the same
# muddy painting. Such a piece, small and in front, at an eye or a brow, is recoloured solid: the eye pieces Cairo's
# eye colour (Tripo's own crisp oval, its rim and highlight gone), a brow piece the brows' colour.
eye_lab = to_lab(np.array([(face_spec or {}).get('colours', {}).get('eyes', [.11, .08, .075])], np.float32))[0]
piece_n = np.bincount(vertex_piece)
piece_lo = np.full((piece_n.size, 3), np.inf); piece_hi = np.full((piece_n.size, 3), -np.inf)
np.minimum.at(piece_lo, vertex_piece, co); np.maximum.at(piece_hi, vertex_piece, co)
eye_pieces, brow_pieces = [], []
for pid in range(piece_n.size):
    if pid == head_piece or piece_n[pid] > 800 or piece_lo[pid, 0] < 0:
        continue
    cyz = ((piece_lo[pid] + piece_hi[pid]) / 2)[1:] / top
    for cr, cc, rh, rw, *_ in eye_ovals:
        ey, ez = (cc * CELL + y0) / top, (z1 - cr * CELL) / top
        if abs(cyz[0] - ey) < rw * CELL / top and abs(cyz[1] - ez) < rh * CELL / top:
            eye_pieces.append(pid)
    if face_spec and pid not in eye_pieces:
        for b in face_spec['brows']:
            pts = np.array(b['points'])
            if np.min(np.hypot(pts[:, 0] - cyz[0], pts[:, 1] - cyz[1])) < .008:
                brow_pieces.append(pid)
whole_piece = piece_half[np.arange(H)[:, None] // (H // BH), np.arange(W)[None, :] // (W // BW)]
for pids, colour in ((eye_pieces, eye_lab), (brow_pieces, feature_lab)):
    if pids:
        m = cover & np.isin(whole_piece, pids)
        lab[m] = colour
del whole_piece
marks = []
del P
rgba[..., :3] = np.where(cover[..., None], chunked(from_lab, lab), rgba[..., :3])
image.pixels.foreach_set(rgba.reshape(-1))
image.update()
image.pack()

# --- the eyes: two thin discs on the face, skinned to the head ------------------------------------------------------
# Only when Tripo gave no eye pieces: then the eyes are drawn as discs fitted to the face (and its carved sockets
# smoothed first).
discs, smoothing = [], {}
if len(eye_pieces) < 2:
    from mathutils.bvhtree import BVHTree
    # Tripo carved the painted eyes into the mesh: a socket with a ledge under each eye, which shades as the old eye under
    # any light. The head's piece is smoothed there (Laplacian, the welded vertices moving together, fading out round
    # the eye) before the discs are fitted to it.
    vn = np.empty(nv * 3, np.float32); body.data.vertices.foreach_get('normal', vn); vn = vn.reshape(-1, 3)
    pos = np.zeros((K, 3)); np.add.at(pos, weld, co); pos /= np.bincount(weld, minlength=K)[:, None]
    nrm = np.zeros((K, 3)); np.add.at(nrm, weld, vn)
    vcy, vcx = (z1 - pos[:, 2]) / CELL, (pos[:, 1] - y0) / CELL
    weight = np.zeros(K)
    for cr, cc, rh, rw, core_w, core_cc in eye_ovals:
        q = np.sqrt(((vcy - cr) / (rh * 1.15)) ** 2 + ((vcx - cc) / (rw * 1.15)) ** 2)
        weight = np.maximum(weight, np.clip((2.1 - q) / .7, 0., 1.))   # the lids' ridges round the socket too
    weight[(piece != head_piece) | (nrm[:, 0] <= .1) | (pos[:, 0] <= 0)] = 0.
    moved = pos.copy()
    deg = np.bincount(ev.ravel(), minlength=K).astype(np.float64)
    for _ in range(100):
        nb = np.zeros((K, 3)); np.add.at(nb, ev[:, 0], moved[ev[:, 1]]); np.add.at(nb, ev[:, 1], moved[ev[:, 0]])
        moved += (.5 * weight)[:, None] * (nb / np.maximum(deg, 1)[:, None] - moved)
    shift = np.linalg.norm(moved - pos, axis=1)
    body.data.vertices.foreach_set('co', (co + (moved - pos)[weld]).astype(np.float32).ravel())
    body.data.update()
    smoothing = {'vertices_moved': int((shift > 1e-6).sum()), 'max_shift_mm': round(float(shift.max()) * 1000 / top * 1.68, 2)}
    # The discs land on the head's own piece only: a strand lying across the face must not catch them.
    head_polys = [list(poly.vertices) for poly in body.data.polygons if vertex_piece[poly.vertices[0]] == head_piece]
    tree = BVHTree.FromPolygons([tuple(v.co) for v in body.data.vertices], head_polys)
    eye_mat = bpy.data.materials.new('Eyes')
    eye_mat.use_nodes = True
    shader = eye_mat.node_tree.nodes['Principled BSDF']
    shader.inputs['Base Color'].default_value = (.012, .008, .007, 1)   # sRGB about (0.11, 0.08, 0.075): Cairo's eye colour
    shader.inputs['Roughness'].default_value = .45
    ASPECT = 1.6    # Cairo's eyes are upright ovals: at least 1.6 times as tall as wide
    discs = []
    for k, (cr, cc, rh, rw, core_w, core_cc) in enumerate(eye_ovals):
        hz = rh * CELL * .9; hy = min(core_w * CELL, hz / ASPECT)    # half height and half width (model units)
        if disc_sizes:
            hy, hz = disc_sizes[k]
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
from_view[hull & ~(~grow(~hull, 1))] = (.9, .9, .9)   # the face's outline
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
report = {'from': src.name, 'eye_pieces': [int(p) for p in eye_pieces], 'brow_pieces': [int(p) for p in brow_pieces], 'normal_map': 'disconnected (it embossed the old drawing)' if normal_links else 'none', 'texture': [W, H], 'strength': a.strength, 'clusters': clusters, 'skin_cluster': skin_cluster,
          'face_cells': [GW, GH], 'cell_mm': round(CELL * 1000 / top * 1.68, 3), 'eyes': ovals,
          'features': features, 'marks_wiped': len(marks), 'eye_discs': discs, 'socket_smoothing': smoothing}
(out / 'texture.json').write_text(json.dumps(report, indent=2) + '\n')
print('TEXTURE OK', json.dumps({k: report[k] for k in ('eyes', 'eye_discs', 'features', 'skin_cluster')}))
