"""A Tripo character's texture made game-ready: flat painted colour in place of Tripo's noise and baked light, the
chips of wrong colour gone, eyes and brows solid, a clean face (docs/TRIPO_CHARACTERS.md, "Eyes, light and noise").

    blender -b --python-exit-code 1 --python tripo_character_texture.py -- --input <rev>/<Name>-Rig-rNN.blend --output <out> --stage raster
    python tripo_character_texture.py --input ... --output <out> --face <character>/face.json --stage paint [--merge-l 10] [--chip 3000]
    blender -b --python-exit-code 1 --python tripo_character_texture.py -- --input ... --output <out> --face ... --stage pack

Three stages, each inside the small slot's 4 GiB: raster (Blender) writes <out>/work/raster.npz and pixels.npy, paint
(plain Python) writes work/colour.npy and paint.json, pack (Blender) writes <out>/<Name>-rMM.blend with the texture
packed (mesh, rig and clips untouched), renders of the head from seven angles and the body (after-*.png),
source-manifest.json and texture.json.

1. Raster: every texel's place on the body, its facing, its mesh piece and its UV chart, from the mesh's UV triangles
   at the texture's full size.
2. Colour groups: k-means in Lab (lightness at half weight); each texel then takes the group most of its neighbours in
   its own chart have, and the group most common round it in 3D within its piece.
3. Regions: the groups of each piece merged greedily by their merged colours (a, b within 9, lightness within
   --merge-l).
4. Chips: each region's patches, joined within a chart and across its seams; a small compact patch with half its
   border one other region becomes that region; then the regions' edges are rounded in each chart.
5. Flat colour: each region its median, keeping --shading (0.3) of its broad lightness.
6. The face (with --face): eye pieces painted as eyes (pupil, iris, catchlight), brow pieces solid, small hair pieces
   all hair, the sockets' walls and dark paint on the face's skin made skin, the spec's brows and mouth drawn.
7. Pack: colour carried 8 texels past every chart's edge; the normal map (Tripo embosses its drawing in it) disconnected.
"""
import argparse, hashlib, json, math, sys
from pathlib import Path
import numpy as np
try:
    import bpy
    from mathutils import Vector
except ImportError:   # the paint stage runs in plain Python
    bpy = None

ap = argparse.ArgumentParser()
ap.add_argument('--input', required=True)
ap.add_argument('--output', required=True)
ap.add_argument('--face', default=None)
ap.add_argument('--shading', type=float, default=.3)
ap.add_argument('--clusters', type=int, default=16)
ap.add_argument('--merge-l', type=float, default=10., help='regions of one piece within this lightness (and 9 in a, b) are one')
ap.add_argument('--chip', type=int, default=3000, help='largest patch (texels) taken into the colour round it')
ap.add_argument('--chip-size', type=float, default=.04, help='... and its largest size on the body (fraction of the height)')
ap.add_argument('--no-renders', action='store_true')
ap.add_argument('--stage', choices=['raster', 'paint', 'pack'], default='raster',
                help='raster (Blender): the mesh in texture space; paint (Python): the colour; pack (Blender): the revision')
a = ap.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:])
src = Path(a.input).resolve()
out = Path(a.output); out.mkdir(parents=True, exist_ok=True)
NAME = src.stem.rsplit('-r', 1)[0] + '-' + out.name.split('-')[-1]
WORK = out / 'work'
WORK.mkdir(exist_ok=True)

if a.stage in ('raster', 'pack'):
    bpy.ops.wm.open_mainfile(filepath=str(src))
    scene = bpy.context.scene
    arm = next(o for o in scene.objects if o.type == 'ARMATURE')
    body = next(o for o in scene.objects if o.type == 'MESH' and o.vertex_groups and len(o.data.vertices) > 1000)
    mat = body.data.materials[0]
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    color_node = bsdf.inputs['Base Color'].links[0].from_node
    image = color_node.image
    W, H = image.size
    arm.data.pose_position = 'REST'
    bpy.context.view_layer.update()
    normal_links = [l for l in nt.links if l.to_node == bsdf and l.to_socket.name == 'Normal']
    for link in normal_links:
        nt.links.remove(link)
    top = max((body.matrix_world @ v.co).z for v in body.data.vertices)




def render(tag):
    """The head from seven angles and the body, lit (no normal map, as in the game)."""
    if a.no_renders:
        return
    cam = scene.camera or bpy.data.objects.new('Review camera', bpy.data.cameras.new('Review camera'))
    if cam.name not in scene.objects:
        scene.collection.objects.link(cam)
    scene.camera = cam
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = scene.render.resolution_y = 1200
    cz = .86 * top
    shots = [('front', 0, 0, .26, cz), ('q_left', 40, 5, .3, cz), ('q_right', -40, 5, .3, cz), ('side_left', 90, 0, .3, cz),
             ('side_right', -90, 0, .3, cz), ('back', 180, 5, .3, cz), ('above', 20, 45, .32, cz), ('body', 0, 0, 1.1, .5 * top),
             ('body_back', 180, 0, 1.1, .5 * top)]
    for name, yaw, elev, scale, z in shots:
        r, e = math.radians(yaw), math.radians(elev)
        cam.data.type = 'ORTHO'; cam.data.ortho_scale = scale * top
        cam.location = Vector((3 * math.cos(r) * math.cos(e), 3 * math.sin(r) * math.cos(e), z + 3 * math.sin(e)))
        cam.rotation_euler = (Vector((0, 0, z)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
        scene.render.filepath = str(out / f'{tag}-{name}.png')
        bpy.ops.render.render(write_still=True)


# (the before renders are a separate run on the input: the renderer's memory and this script's arrays do not fit the
# small slot together)

if a.stage == 'raster':
    # --- 1. the mesh in texture space ---------------------------------------------------------------------------------
    mesh = body.data
    nv = len(mesh.vertices)
    co = np.empty(nv * 3, np.float32); mesh.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
    vn = np.empty(nv * 3, np.float32); mesh.vertices.foreach_get('normal', vn); vn = vn.reshape(-1, 3)
    # Pieces: the welded connected parts (the head and its hair, each strand, the eyes, the clothes...).
    keys = {}
    weld = np.array([keys.setdefault(tuple(np.round(v, 5)), len(keys)) for v in co])
    K = len(keys)
    edges = np.empty(len(mesh.edges) * 2, np.int64); mesh.edges.foreach_get('vertices', edges)
    ev = weld[edges.reshape(-1, 2)]; ev = ev[ev[:, 0] != ev[:, 1]]
    root = np.arange(K)
    def find(i):
        while root[i] != i:
            root[i] = root[root[i]]; i = root[i]
        return i
    for u, v in ev:
        ru, rv = find(u), find(v)
        if ru != rv:
            root[ru] = rv
    _, piece_of_weld = np.unique([find(i) for i in range(K)], return_inverse=True)
    vpiece = piece_of_weld[weld]
    mesh.calc_loop_triangles()
    nt_ = len(mesh.loop_triangles)
    tv = np.empty(nt_ * 3, np.int64); mesh.loop_triangles.foreach_get('vertices', tv); tv = tv.reshape(-1, 3)
    tl = np.empty(nt_ * 3, np.int64); mesh.loop_triangles.foreach_get('loops', tl); tl = tl.reshape(-1, 3)
    uvs = np.empty(len(mesh.loops) * 2, np.float32); mesh.uv_layers.active.data.foreach_get('uv', uvs); uvs = uvs.reshape(-1, 2)
    pos = np.zeros((H, W, 3), np.float32)
    nx = np.zeros((H, W), np.float16)
    piece = np.full((H, W), -1, np.int16)
    chart_tex = np.full((H, W), -1, np.int32)
    # UV charts: triangles joined where they share a corner (the same vertex at the same UV)
    corner = {}
    tri_root = np.arange(nt_)
    def tfind(i):
        while tri_root[i] != i:
            tri_root[i] = tri_root[tri_root[i]]; i = tri_root[i]
        return i
    for t in range(nt_):
        for k in range(3):
            key_ = (int(tv[t, k]), round(float(uvs[tl[t, k], 0]), 5), round(float(uvs[tl[t, k], 1]), 5))
            other = corner.setdefault(key_, t)
            if other != t:
                ra, rb = tfind(t), tfind(other)
                if ra != rb:
                    tri_root[ra] = rb
    _, chart_of_tri = np.unique([tfind(t) for t in range(nt_)], return_inverse=True)
    for t in range(nt_):
        uv = uvs[tl[t]] * np.array([W, H]) - .5   # texel centres at integers
        c0, c1 = int(np.floor(uv[:, 0].min())), int(np.ceil(uv[:, 0].max()))
        r0, r1 = int(np.floor(uv[:, 1].min())), int(np.ceil(uv[:, 1].max()))
        c0, r0 = max(c0, 0), max(r0, 0); c1, r1 = min(c1, W - 1), min(r1, H - 1)
        if c1 < c0 or r1 < r0:
            continue
        xs, ys = np.meshgrid(np.arange(c0, c1 + 1), np.arange(r0, r1 + 1))
        (x0, y0), (x1, y1), (x2, y2) = uv
        den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(den) < 1e-12:
            continue
        l0 = ((y1 - y2) * (xs - x2) + (x2 - x1) * (ys - y2)) / den
        l1 = ((y2 - y0) * (xs - x2) + (x0 - x2) * (ys - y2)) / den
        l2 = 1 - l0 - l1
        inside = (l0 >= -1e-4) & (l1 >= -1e-4) & (l2 >= -1e-4)
        if not inside.any():
            continue
        rr, cc = ys[inside], xs[inside]
        b = np.stack([l0[inside], l1[inside], l2[inside]], 1)
        pos[rr, cc] = b @ co[tv[t]]
        nx[rr, cc] = b @ vn[tv[t], 0]
        piece[rr, cc] = vpiece[tv[t, 0]]
        chart_tex[rr, cc] = chart_of_tri[t]
    cover = piece >= 0
    print('RASTER', int(cover.sum()), 'texels covered of', W * H, flush=True)

    px = np.empty(W * H * 4, np.float32); image.pixels.foreach_get(px)
    np.savez(WORK / 'raster.npz', pos=pos, nx=nx, piece=piece, chart=chart_tex, vpiece=vpiece, co=co, W=W, H=H, top=top)
    np.save(WORK / 'pixels.npy', (np.clip(px.reshape(H, W, 4), 0, 1) * 65535).astype(np.uint16))
    print('RASTER SAVED', flush=True)

if a.stage == 'paint':
    r_ = np.load(WORK / 'raster.npz')
    pos, nx, piece, chart, vpiece, co = r_['pos'], r_['nx'], r_['piece'], r_['chart'], r_['vpiece'], r_['co']
    W, H, top = int(r_['W']), int(r_['H']), float(r_['top'])
    cover = piece >= 0
    px = (np.load(WORK / 'pixels.npy').astype(np.float32) / 65535).reshape(-1)
    # --- 2. colour groups ------------------------------------------------------------------------------------------------


    def chunked(fn, x, rows=256):
        out_ = np.empty(x.shape, np.float32)
        for i in range(0, len(x), rows):
            out_[i:i + rows] = fn(x[i:i + rows])
        return out_


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


    lab = chunked(to_lab, px.reshape(H, W, 4)[..., :3])
    del px   # read again at the end; the arrays below do not fit the small slot beside it
    rng = np.random.default_rng(7)
    feat_w = np.array([.5, 1., 1.], np.float32)
    sample = lab[cover][rng.choice(int(cover.sum()), 200000, replace=False)] * feat_w
    centres = sample[rng.choice(len(sample), a.clusters, replace=False)]
    for _ in range(30):
        k = ((sample[:, None] - centres[None]) ** 2).sum(-1).argmin(1)
        centres = np.stack([sample[k == i].mean(0) if (k == i).any() else centres[i] for i in range(a.clusters)])
    labels = np.zeros((H, W), np.int8)
    for r in range(0, H, 256):
        labels[r:r + 256] = (((lab[r:r + 256, :, None, :] * feat_w) - centres) ** 2).sum(-1).argmin(-1)


    def box(x, n):
        """Sum over a (2n+1)^2 window (integral image), the edges clamped."""
        c = np.pad(x.astype(np.float32), ((n + 1, n), (n + 1, n)), mode='edge').cumsum(0, dtype=np.float32).cumsum(1, dtype=np.float32)
        return c[2 * n + 1:, 2 * n + 1:] - c[:-2 * n - 1, 2 * n + 1:] - c[2 * n + 1:, :-2 * n - 1] + c[:-2 * n - 1, :-2 * n - 1]


    def majority(lbl, n, passes):
        """Each covered texel takes the group most of its covered neighbours have (a (2n+1)^2 window)."""
        for _ in range(passes):
            best = np.zeros((H, W), np.float32); win = lbl.copy()
            for g in range(a.clusters):
                cnt = box(((lbl == g) & cover).astype(np.float32), n)
                better = cnt > best
                best[better] = cnt[better]; win[better] = g
            lbl = np.where(cover, win, lbl)
        return lbl


    del sample
    def chart_majority(lbl, n, passes):
        """Each texel takes the group most of its neighbours in its own UV chart have (a (2n+1)^2 window): specks,
        chips and thin pencil strokes dissolve, and nothing is voted across a seam from another part of the body."""
        rows, cols = np.nonzero(cover)
        ids = chart[rows, cols]
        order_c = np.argsort(ids, kind='stable')
        cut = np.searchsorted(ids[order_c], np.unique(ids))
        cut = list(cut) + [len(ids)]
        for _ in range(passes):
            out_l = lbl.copy()
            for ci in range(len(cut) - 1):
                sel = order_c[cut[ci]:cut[ci + 1]]
                if len(sel) < 20:
                    continue
                r, c = rows[sel], cols[sel]
                r0, r1, c0, c1 = max(r.min() - n, 0), min(r.max() + n + 1, H), max(c.min() - n, 0), min(c.max() + n + 1, W)
                mine = chart[r0:r1, c0:c1] == ids[sel[0]]
                sub = lbl[r0:r1, c0:c1]
                best = np.full(mine.shape, -1.); win = sub.copy()
                for g in np.unique(sub[mine]):
                    cnt = box_local(((sub == g) & mine).astype(np.float32), n)
                    better = mine & (cnt > best)
                    best[better] = cnt[better]; win[better] = g
                out_l[r0:r1, c0:c1] = np.where(mine, win, out_l[r0:r1, c0:c1])
            lbl = out_l
        return lbl

    def box_local(x, n):
        h, w = x.shape
        c = np.pad(x, ((n + 1, n), (n + 1, n))).cumsum(0, dtype=np.float32).cumsum(1, dtype=np.float32)
        return c[2 * n + 1:, 2 * n + 1:] - c[:-2 * n - 1, 2 * n + 1:] - c[2 * n + 1:, :-2 * n - 1] + c[:-2 * n - 1, :-2 * n - 1]

    labels = chart_majority(labels, 3, 2)

    def space_majority(lbl, cell, passes=1):
        """Each texel takes the group most common on the surface round it in 3D (its cell and the 26 next to it, cells
        of `cell` in fractions of the height), within its own piece: where the atlas cuts a patch into many charts (the
        temples, a collar), the chips at a colour boundary go, wherever their texels lie in the texture."""
        rr, cc = np.nonzero(cover)
        q = np.floor(pos[rr, cc] / (cell * top)).astype(np.int64)
        q -= q.min(0)
        span = q.max(0) + 3
        pc = piece[rr, cc].astype(np.int64)
        for _ in range(passes):
            lb = lbl[rr, cc].astype(np.int64)
            base = ((pc * span[0] + q[:, 0] + 1) * span[1] + q[:, 1] + 1) * span[2] + q[:, 2] + 1
            keys_, inv_ = np.unique(base, return_inverse=True)
            counts = np.zeros((len(keys_), a.clusters), np.int32)
            np.add.at(counts, (inv_, lb), 1)
            total = np.zeros((len(keys_), a.clusters), np.int32)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for dz in (-1, 0, 1):
                        nb = keys_ + (dx * span[1] + dy) * span[2] + dz
                        idx = np.searchsorted(keys_, nb)
                        idx = np.clip(idx, 0, len(keys_) - 1)
                        ok = keys_[idx] == nb
                        total[ok] += counts[idx[ok]]
            lbl = lbl.copy()
            lbl[rr, cc] = total.argmax(1)[inv_].astype(lbl.dtype)
        return lbl

    labels = space_majority(labels, .0008, 2)

    # --- 3. regions and their flat colour -----------------------------------------------------------------------------
    key = np.where(cover, piece.astype(np.int64) * 64 + labels, -1)
    groups, inv = np.unique(key[cover], return_inverse=True)
    med = np.zeros((len(groups), 3), np.float32)
    flat_lab = lab[cover]
    order = np.argsort(inv, kind='stable')
    bounds = np.searchsorted(inv[order], np.arange(len(groups) + 1))
    for g in range(len(groups)):
        idx = order[bounds[g]:bounds[g + 1]]
        med[g] = np.median(flat_lab[idx], 0) if len(idx) else 0
    # merge groups of one piece with nearly the same colour: greedily, the closest pair first, by the regions' current
    # colours (a chain of small steps, skin to shaded skin to brown to hair, must not make one region)
    gp = groups // 64
    counts = np.diff(bounds).astype(np.float64)
    reg = np.arange(len(groups))
    cur = {i: (med[i].astype(np.float64), counts[i]) for i in range(len(groups))}
    def dist(i, j):
        (mi, _), (mj, _) = cur[i], cur[j]
        return max(np.hypot(*(mi[1:] - mj[1:])) / 9., abs(mi[0] - mj[0]) / a.merge_l)
    while True:
        best = None
        alive = list(cur)
        for x in range(len(alive)):
            for y in range(x + 1, len(alive)):
                i, j = alive[x], alive[y]
                if gp[i] != gp[j]:
                    continue
                d = dist(i, j)
                if d < 1. and (best is None or d < best[0]):
                    best = (d, i, j)
        if best is None:
            break
        _, i, j = best
        (mi, ni), (mj, nj) = cur[i], cur[j]
        cur[i] = ((mi * ni + mj * nj) / (ni + nj), ni + nj)
        del cur[j]
        reg[reg == j] = i
    reg_med = np.zeros_like(med)
    for rgn in np.unique(reg):
        idx = np.concatenate([order[bounds[g]:bounds[g + 1]] for g in np.where(reg == rgn)[0]])
        reg_med[rgn] = np.median(flat_lab[idx], 0)
    texel_region = np.full((H, W), -1, np.int32); texel_region[cover] = reg[inv]

    def islands(rgn):
        """Connected patches of one region within one UV chart: each texel's patch label (4-neighbours, min-label
        propagation with pointer jumping), -1 off the islands."""
        k = np.where(cover, chart.astype(np.int64) * 256 + rgn, -1)
        lbl = np.where(cover, np.arange(H * W, dtype=np.int32).reshape(H, W), -1)
        while True:
            before = lbl.copy()
            for ax, sh in ((0, 1), (0, -1), (1, 1), (1, -1)):
                nb_k, nb_l = np.roll(k, sh, ax), np.roll(lbl, sh, ax)
                same = cover & (nb_k == k)
                np.minimum(lbl, np.where(same, nb_l, lbl), out=lbl)
            flat_l = lbl.reshape(-1)
            for _ in range(8):
                on = flat_l >= 0
                flat_l[on] = flat_l[flat_l[on]]
            if np.array_equal(before, lbl):
                return lbl
            del before

    L = np.where(cover, lab[..., 0], 0.).astype(np.float32)
    del lab, flat_lab

    # seams: the texels at a chart's edge, and the edge texels of the other charts lying at the same place on the body
    # (cells of .0006 of the height, the 27 round each, within one piece): a patch cut by the atlas is one patch
    inner = cover.copy()
    for ax, sh in ((0, 1), (0, -1), (1, 1), (1, -1)):
        inner &= np.roll(cover, sh, ax) & (np.roll(chart, sh, ax) == chart)
    er, ec = np.nonzero(cover & ~inner)
    del inner
    q = np.floor(pos[er, ec] / (.0006 * top)).astype(np.int64); q -= q.min(0)
    span = q.max(0) + 3
    ckey = ((piece[er, ec].astype(np.int64) * span[0] + q[:, 0] + 1) * span[1] + q[:, 1] + 1) * span[2] + q[:, 2] + 1
    cell_keys, cell_inv = np.unique(ckey, return_inverse=True)
    nbr = np.full((len(cell_keys), 27), -1, np.int32)
    o = 0
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                want = cell_keys + (dx * span[1] + dy) * span[2] + dz
                j = np.clip(np.searchsorted(cell_keys, want), 0, len(cell_keys) - 1)
                nbr[:, o] = np.where(cell_keys[j] == want, j, -1); o += 1
    del q, ckey

    def chips(rgn):
        """A small patch of one colour inside another (a skin chip on a strand, a fleck of hair on the temple, a patch of
        skin on the collar, a whole small chart of the wrong colour) takes the colour round it: each patch is a region's
        texels joined within a chart and across its seams; what borders it is counted over its edges in the chart and
        across the seams; a patch under --chip texels with half its border one other region becomes that region."""
        comp = islands(rgn)
        tr, tc = rgn[er, ec].astype(np.int64), comp[er, ec].astype(np.int64)
        # join the patches of one region across the seams (min-root propagation over the cells)
        parent = np.arange(H * W, dtype=np.int64)
        crk, crinv = np.unique(cell_inv * 4096 + tr, return_inverse=True)
        while True:
            cur = parent[tc]
            cmin = np.full(len(crk), np.iinfo(np.int64).max); np.minimum.at(cmin, crinv, cur)
            best = cur.copy()
            for o_ in range(27):
                n_ = nbr[cell_inv, o_]
                want = n_.astype(np.int64) * 4096 + tr
                j = np.clip(np.searchsorted(crk, want), 0, len(crk) - 1)
                ok = (n_ >= 0) & (crk[j] == want)
                best[ok] = np.minimum(best[ok], cmin[j[ok]])
            before = parent.copy()
            np.minimum.at(parent, cur, best)
            for _ in range(20):
                parent = parent[parent]
            if np.array_equal(before, parent):
                break
            del before
        patch = np.where(cover, parent[np.maximum(comp, 0)], -1)
        del comp, parent
        area = np.bincount(patch[cover], minlength=H * W)
        pair_c, pair_r = [], []
        for ax, sh in ((0, 1), (0, -1), (1, 1), (1, -1)):
            nb_r, nb_ch = np.roll(rgn, sh, ax), np.roll(chart, sh, ax)
            edge = cover & (nb_ch == chart) & (nb_r >= 0) & (nb_r != rgn) & (area[np.maximum(patch, 0)] < a.chip)
            pair_c.append(patch[edge]); pair_r.append(nb_r[edge])
            del nb_r, nb_ch, edge
        # across the seams: each edge texel counts the region most common round it in the other charts
        ids, rc = np.unique(tr, return_inverse=True)
        counts = np.zeros((len(cell_keys), len(ids)), np.int16)
        np.add.at(counts, (cell_inv, rc), 1)
        total = np.zeros_like(counts)
        for o_ in range(27):
            n_ = nbr[:, o_]
            total[n_ >= 0] += counts[n_[n_ >= 0]]
        del counts
        other = total[cell_inv]; other[np.arange(len(rc)), rc] = 0
        del total
        k_ = other.argmax(1); has = other[np.arange(len(k_)), k_] > 0
        small = area[patch[er, ec]] < a.chip
        pair_c.append(patch[er, ec][has & small]); pair_r.append(ids[k_][has & small])
        del other
        pair_c, pair_r = np.concatenate(pair_c).astype(np.int64), np.concatenate(pair_r).astype(np.int64)
        if not len(pair_c):
            return rgn, 0
        pk, pn = np.unique(pair_c * 4096 + pair_r, return_counts=True)
        pcomp, preg = pk // 4096, pk % 4096
        border = np.bincount(pcomp, weights=pn, minlength=H * W)
        order_p = np.lexsort((-pn, pcomp))
        first = np.ones(len(order_p), bool); first[1:] = pcomp[order_p][1:] != pcomp[order_p][:-1]
        top_c, top_r, top_n = pcomp[order_p][first], preg[order_p][first], pn[order_p][first]
        take = top_n > .5 * border[top_c]
        to = np.full(H * W, -1, np.int64); to[top_c[take]] = top_r[take]
        move = cover & (to[np.maximum(patch, 0)] >= 0)
        # only what is small on the body too: a strap or a seam line is a long thin patch and stays
        mr, mc = np.nonzero(move)
        mp = patch[mr, mc].astype(np.int64)
        ids_, mi = np.unique(mp, return_inverse=True)
        lo_ = np.full((len(ids_), 3), np.inf, np.float32); hi_ = np.full((len(ids_), 3), -np.inf, np.float32)
        np.minimum.at(lo_, mi, pos[mr, mc]); np.maximum.at(hi_, mi, pos[mr, mc])
        p_ = (pos[mr, mc] / top).astype(np.float64)
        n_ = np.bincount(mi).astype(np.float64)[:, None]
        mean_ = np.zeros((len(ids_), 3)); np.add.at(mean_, mi, p_); mean_ /= n_
        d_ = p_ - mean_[mi]
        cov_ = np.zeros((len(ids_), 3, 3)); np.add.at(cov_, mi, d_[:, :, None] * d_[:, None, :]); cov_ /= n_[:, :, None]
        ev_ = np.sort(np.linalg.eigvalsh(cov_), 1)
        long_ = np.sqrt(ev_[:, 2] / np.maximum(ev_[:, 1], 1e-12)) > 3.5
        diag_ = np.linalg.norm(hi_ - lo_, axis=1) / top
        big = (diag_ > a.chip_size) | (long_ & (diag_ > .015))
        to[ids_[big]] = -1
        move = cover & (to[np.maximum(patch, 0)] >= 0)
        return np.where(move, to[np.maximum(patch, 0)], rgn).astype(np.int32), int(move.sum())

    absorbed = 0
    for _ in range(3):
        texel_region, n_moved = chips(texel_region)
        absorbed += n_moved
        if not n_moved:
            break
    del nbr, cell_inv, cell_keys
    print('CHIPS absorbed', absorbed, 'texels', flush=True)
    # the regions' edges rounded in each chart: the 3D vote leaves them stepped like its cells (a collar, a lapel)
    texel_region = chart_majority(texel_region, 3, 2)
    # the region's colour, with a share of its broad lightness variation (folds read a little)
    n_cov = box(cover.astype(np.float32), 12)
    L_blur = box(L, 12) / np.maximum(n_cov, 1)
    new = np.zeros((H, W, 3), np.float32)
    new[cover] = reg_med[texel_region[cover]]
    new[..., 0] = np.where(cover, new[..., 0] + a.shading * (L_blur - new[..., 0]), 0)
    del L, L_blur, n_cov
    print('REGIONS', len(np.unique(reg)), 'from', len(groups), 'piece groups', flush=True)

    # --- 4. the face ---------------------------------------------------------------------------------------------------
    spec = json.loads(Path(a.face).read_text()) if a.face and Path(a.face).exists() else None
    report_face = {}
    if spec:
        colours = spec.get('colours', {})
        lab_of = lambda rgb: to_lab(np.array([rgb], np.float32))[0]
        eye_lab, brow_lab, mouth_lab = lab_of(colours.get('eyes', [.11, .08, .075])), lab_of(colours.get('brows', [.16, .11, .09])), lab_of(colours.get('mouth', [.42, .24, .19]))
        yv, zv = pos[..., 1] / top, pos[..., 2] / top
        # the head's piece: the piece most of the texels at the eyes' height on the front of the face belong to
        ez = np.mean([e['centre'][1] for e in spec['eyes']])
        at_face = cover & (np.abs(zv - ez) < .02) & (np.abs(yv) < .05) & (pos[..., 0] > 0) & (nx > .5)
        head = int(np.bincount(piece[at_face].astype(np.int64)).argmax())
        # small pieces in front at an eye or on a brow: Tripo's eyes and brows
        pc_n = np.bincount(vpiece)
        lo = np.full((pc_n.size, 3), np.inf); hi = np.full((pc_n.size, 3), -np.inf)
        np.minimum.at(lo, vpiece, co); np.maximum.at(hi, vpiece, co)
        eye_pieces, brow_pieces = [], []
        for p in range(pc_n.size):
            if p == head or pc_n[p] > 800 or lo[p, 0] < 0:
                continue
            cy, cz = ((lo[p] + hi[p]) / 2)[1:] / top
            if any(abs(cy - e['centre'][0]) < e['drawing_half'][0] and abs(cz - e['centre'][1]) < e['drawing_half'][1] for e in spec['eyes']):
                eye_pieces.append(p)
            elif any(np.min(np.hypot(np.array(b['points'])[:, 0] - cy, np.array(b['points'])[:, 1] - cz)) < .008 for b in spec['brows']):
                brow_pieces.append(p)
        new[cover & np.isin(piece, eye_pieces)] = eye_lab
        # the eyes: a dark iris, a darker pupil and a catchlight up and to the outside, in the eye's own frame
        iris_lab = lab_of(colours.get('iris', [.24, .15, .1]))
        for e in spec['eyes']:
            (ey, ezz), (hw, hh) = e['centre'], e['disc_half']
            on_eye = cover & np.isin(piece, eye_pieces) & (np.abs(yv - ey) < 2 * hw) & (np.abs(zv - ezz) < 2 * hh)
            er, ec = np.nonzero(on_eye)
            u, v = (yv[er, ec] - ey) / hw, (zv[er, ec] - ezz) / hh
            pupil = np.clip((np.hypot(u, v + .1) - .45) / .12, 0, 1)[:, None]   # 0 in the pupil, 1 in the iris
            col = eye_lab * (1 - pupil) + iris_lab * pupil
            out_ = 1. if ey > 0 else -1.
            glint = np.clip((.2 - np.hypot(u - .3 * out_, v - .38)) / .06 + .5, 0, 1)[:, None]
            new[er, ec] = col * (1 - glint) + np.array([97., 0., 2.]) * glint
        new[cover & np.isin(piece, brow_pieces)] = brow_lab
        # small pieces round the head that are mostly hair (a sideburn, a lock) but partly painted skin by Tripo: all hair
        hair_rgn = np.bincount(texel_region[cover & (piece == head) & (zv > ez + .08)].astype(np.int64)).argmax()
        hair_lab = reg_med[hair_rgn]
        hair_pieces = []
        for p in range(pc_n.size):
            if p == head or p in eye_pieces or p in brow_pieces or pc_n[p] > 800 or hi[p, 2] / top < .74:
                continue
            mask = cover & (piece == p)
            behind = (lo[p, 0] + hi[p, 0]) / 2 / top < -.01   # a tuft at the nape: hair, whatever Tripo painted it
            if mask.any() and (behind or np.mean(new[mask][:, 0] < hair_lab[0] + 15.) > .3):
                new[mask] = hair_lab; hair_pieces.append(p)
        report_face['hair_pieces'] = [int(p) for p in hair_pieces]
        # the face: the head's piece, facing forward, inside the spec's face (between the brows' top and the chin)
        on_head = cover & (piece == head) & (pos[..., 0] > 0) & (nx > .05)
        face_box = on_head & (zv > ez - .07) & (zv < ez + .04) & (np.abs(yv) < .055)
        skin_rgn = np.bincount(texel_region[face_box & (np.abs(zv - ez + .03) < .01) & (np.abs(yv) < .01)].astype(np.int64)).argmax()
        skin_lab = reg_med[skin_rgn]
        # dark paint on the face (scratches, painted hair, the old lashes): skin; the hair (its own regions far darker and
        # standing in front, or above the brows' line) stays
        # The skin's surface: a cubic fit of depth over the face's skin texels; paint lies on it, a strand stands in front.
        sk = face_box & (texel_region == skin_rgn)
        ys, zs, xs = yv[sk], zv[sk] - ez, pos[..., 0][sk] / top
        terms = lambda y, z: np.stack([np.ones_like(y), y, z, y * y, y * z, z * z, y ** 3, y * y * z, y * z * z, z ** 3], -1)
        coef = np.linalg.lstsq(terms(ys, zs), xs, rcond=None)[0]
        dark = face_box & (new[..., 0] < skin_lab[0] - 15.) & ~np.isin(piece, eye_pieces + brow_pieces)
        dr, dc = np.nonzero(dark)
        # on the skin's surface; below the eyes, clear of the face-framing strands that lie on the cheeks
        on_skin = (pos[dr, dc, 0] / top - terms(yv[dr, dc], zv[dr, dc] - ez) @ coef < .0022) & ((np.abs(yv[dr, dc]) < .042) | (zv[dr, dc] > ez + .004))
        hairline = np.array([max(p[1] for p in b['points']) for b in spec['brows']]).max() + .006
        # the sockets round Tripo's eye pieces: their walls face every way (so the face mask misses them) and carry the
        # old eye's brown painting, which shows as a line over each eye; the head's texels in each socket are skin
        for e in spec['eyes']:
            (ey, ezz), (hw, hh) = e['centre'], e['drawing_half']
            sock = cover & (piece == head) & (pos[..., 0] > 0) & (np.hypot((yv - ey) / hw, (zv - ezz) / hh) < 1.6)
            new[sock] = skin_lab
        # the old lashes: just above each eye, out past its sides, below the brow
        for e in spec['eyes']:
            (ey, ezz), (hw, hh) = e['centre'], e['drawing_half']
            lash = face_box & (np.abs(yv - ey) < 1.9 * hw) & (zv > ezz + .55 * hh) & (zv < ezz + 1.55 * hh) & ~np.isin(piece, eye_pieces + brow_pieces)
            lr, lc = np.nonzero(lash)
            flat_ = pos[lr, lc, 0] / top - terms(yv[lr, lc], zv[lr, lc] - ez) @ coef < .0022   # on the skin, not a strand
            new[lr[flat_], lc[flat_]] = skin_lab
        keep = on_skin & (zv[dr, dc] < hairline)
        new[dr[keep], dc[keep]] = skin_lab
        report_face['dark_texels_cleared'] = int(keep.sum())

        def stroke(points, thickness):
            """Coverage 0..1 of a stroke (centreline and thickness per point), anti-aliased over one texel."""
            pts = np.array(points, float); th = np.array(thickness, float)
            sel = np.nonzero(face_box)
            y, z = yv[sel], zv[sel]
            best = np.full(len(y), np.inf); half = np.zeros(len(y))
            for i in range(len(pts) - 1):
                p0, p1 = pts[i], pts[i + 1]; seg = p1 - p0; L2 = float(seg @ seg)
                t = np.clip(((y - p0[0]) * seg[0] + (z - p0[1]) * seg[1]) / L2, 0, 1)
                d = np.hypot(y - (p0[0] + t * seg[0]), z - (p0[1] + t * seg[1]))
                closer = d < best
                best[closer] = d[closer]; half[closer] = (th[i] + t[closer] * (th[i + 1] - th[i])) / 2
            texel = .0004   # about a texel on the face, in fractions of the height
            return sel, np.clip((half - best) / texel + .5, 0, 1)

        for b in spec['brows']:
            sel, cov = stroke(b['points'], b['thickness'])
            m = cov > 0
            new[sel[0][m], sel[1][m]] = new[sel[0][m], sel[1][m]] * (1 - cov[m, None]) + brow_lab * cov[m, None]
        m_ = spec['mouth']
        sel, cov = stroke(m_['points'], m_['thickness'])
        m = cov > 0
        new[sel[0][m], sel[1][m]] = new[sel[0][m], sel[1][m]] * (1 - cov[m, None]) + mouth_lab * cov[m, None]
        report_face.update(head_piece=head, eye_pieces=[int(p) for p in eye_pieces], brow_pieces=[int(p) for p in brow_pieces])

    # --- 5. back to colour, carried past the islands' edges -------------------------------------------------------------
    rgb = chunked(from_lab, new).astype(np.float32)
    del new
    filled = cover.copy()
    for _ in range(8):
        grow = np.zeros_like(filled)
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            src_f = np.roll(np.roll(filled, dr, 0), dc, 1)
            take = src_f & ~filled & ~grow
            rgb[take] = np.roll(np.roll(rgb, dr, 0), dc, 1)[take]
            grow |= take
        filled |= grow
    np.save(WORK / 'colour.npy', np.where(filled[..., None], np.clip(rgb, 0, 1), -1.).astype(np.float32))
    (WORK / 'paint.json').write_text(json.dumps({'regions': int(len(np.unique(reg))), **report_face}) + '\n')
    print('PAINT SAVED', flush=True)

if a.stage == 'pack':
    rgb = np.load(WORK / 'colour.npy')
    px = np.empty(W * H * 4, np.float32); image.pixels.foreach_get(px)
    rgba = px.reshape(H, W, 4)
    rgba[..., :3] = np.where(rgb[..., :1] >= 0, rgb, rgba[..., :3])
    del rgb
    image.pixels.foreach_set(px)
    image.update(); image.pack()
    del px, rgba
    render('after')
    arm.data.pose_position = 'POSE'
    bpy.ops.wm.save_as_mainfile(filepath=str(out / f'{NAME}.blend'), compress=True)
    manifest_src = src.parent / 'source-manifest.json'
    if manifest_src.exists():
        manifest = json.loads(manifest_src.read_text())
        manifest['native'] = f'{NAME}.blend'
        manifest['native_sha256'] = hashlib.sha256((out / f'{NAME}.blend').read_bytes()).hexdigest()
        manifest['texture'] = 'flat painted colour, solid eyes and brows, the face redrawn (tripo_character_texture.py, texture.json)'
        (out / 'source-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    report = {'from': src.name, 'texture': [W, H], 'clusters': a.clusters, 'shading': a.shading,
              'normal_map': 'disconnected' if normal_links else 'none', **json.loads((WORK / 'paint.json').read_text())}
    (out / 'texture.json').write_text(json.dumps(report, indent=2) + '\n')
    print('TEXTURE OK', json.dumps(report), flush=True)

