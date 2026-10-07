"""The came-back rival's Tripo body texture: the hair and the face cleaned of each other's colour, then his eyes, brows
and mouth painted on the blank face (Tripo Studio's Smart UV model from the body references of
games/yorimichi/tools/came_back_tpose.py).

    blender -b --python-exit-code 1 --python came_back_texture.py -- --input <model.fbx> --output <out> --stage raster
    python came_back_texture.py --input <model.fbx> --output <out> --stage paint [--variant redo]
    blender -b --python-exit-code 1 --python came_back_texture.py -- --input <model.fbx> --output <out> --stage pack [--variant redo]

Run the Blender stages under the guard (python -m atelier.safety.guarded --small 3 ...).

1. Raster (Blender): every texel's place on the body and its normal, from the mesh's UV triangles, in the model's
   world frame (Z up, the face toward -Y, 1 m tall as Tripo exports it), and its UV chart.
2. Paint (plain Python): on the head, each texel is called skin, hair or cloth by its colour; a texel whose colour
   disagrees with the surface round it in 3D (a small patch of skin colour on a lock, hair colour on the cheek, the
   ear or the nape) takes the colour of that surface. Then the face is drawn from FACE (below): two half-lidded pill
   eyes, the brows and a lopsided small mouth, projected from the front onto the skin only, so a lock in front of the
   face keeps its hair colour. With --variant redo, Tripo's colours on the head are dropped instead: only the labels
   stay (skin, hair, the white streak), and the skin and hair are painted fresh from REDO with soft shading taken from
   the geometry (basecolor-redo.png), for comparison.
3. Pack (Blender): the new texture beside the model (<out>/basecolor.png), a blend with it applied, and renders of the
   head from five angles and the body (before and after).
"""
import argparse, json, math, sys
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
ap.add_argument('--stage', choices=['raster', 'paint', 'pack'], required=True)
ap.add_argument('--variant', choices=['clean', 'redo'], default='clean')
a = ap.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:])
src = Path(a.input).resolve()
out = Path(a.output).resolve(); out.mkdir(parents=True, exist_ok=True)
WORK = out / 'work'; WORK.mkdir(exist_ok=True)

# The face, in metres of the model as exported (x to his left, z up; he faces -Y; the chin at z 0.794, the hair's top
# at 0.998). Measured on the concept's front T-pose face (chin to hair top 745 px of a 4x crop = 0.204 m), its widths
# scaled by 0.87 because the model's head is narrower than the concept's (ear to ear), and checked on
# review/before-face.png (ortho 0.14 m over 900 px at z 0.845).
THIN = 8      # texels: the reach of the thin-line check on the skin

# --variant redo: the head's colours painted fresh (CIE Lab), not cleaned
REDO = {
    'skin': [77, 14, 21], 'skin_shade': [63, 19, 24], 'blush': [70, 26, 20],
    'hair_deep': [17, 1, -5], 'hair': [23, 1, -6], 'hair_light': [38, 0, -9],
    'streak': [88, 0, -3], 'streak_shade': [68, 0, -5],
    'head_centre': [.002, .0, .885],
}

FACE = {
    'eyes': [{'centre': [.025, .8616], 'half': [.0072, .0142]},     # his left eye, the one the fringe leaves bare
             {'centre': [-.025, .8616], 'half': [.0072, .0142]}],   # his right eye, mostly under the fringe
    'lid': .4,           # the heavy upper lid: the top of each pill is cut flat this far down from its top (of the height)
    'brows': [{'points': [[.0145, .8795], [.025, .8806], [.0345, .8800]], 'thickness': [.0040, .0044, .0036]},
              {'points': [[-.0145, .8795], [-.025, .8806], [-.0345, .8800]], 'thickness': [.0040, .0044, .0036]}],
    'mouth': {'points': [[-.0095, .8137], [-.002, .8129], [.004, .8134], [.0093, .8164]],
              'thickness': [.0011, .0015, .0015, .0010]},
    'colours': {'eyes': [.075, .065, .07], 'brows': [.11, .1, .105], 'mouth': [.50, .30, .25]},
}

def mesh_object():
    return next(o for o in bpy.context.scene.objects if o.type == 'MESH')


def load():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(src))
    body = mesh_object()
    nt = body.data.materials[0].node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    return body, nt, bsdf, bsdf.inputs['Base Color'].links[0].from_node.image


def render(tag):
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = scene.render.resolution_y = 900
    world = bpy.data.worlds.new('review'); scene.world = world; world.use_nodes = True
    world.node_tree.nodes['Background'].inputs[0].default_value = (.6, .6, .62, 1)
    cam = bpy.data.objects.new('review', bpy.data.cameras.new('review')); scene.collection.objects.link(cam)
    scene.camera = cam; cam.data.type = 'ORTHO'
    for name, yaw, scale, z in [('front', -90, .3, .88), ('q_left', -50, .3, .88), ('q_right', -130, .3, .88),
                                ('side_left', 0, .3, .88), ('side_right', 180, .3, .88), ('back', 90, .3, .88),
                                ('face', -90, .14, .845), ('body', -90, 1.1, .5)]:
        r = math.radians(yaw)
        cam.data.ortho_scale = scale
        cam.location = Vector((3 * math.cos(r), 3 * math.sin(r), z))
        cam.rotation_euler = (Vector((0, 0, z)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
        scene.render.filepath = str(out / 'review' / f'{tag}-{name}.png')
        bpy.ops.render.render(write_still=True)


if a.stage == 'raster':
    body, nt, bsdf, image = load()
    W, H = image.size
    mesh = body.data
    mw = body.matrix_world
    co = np.array([tuple(mw @ v.co) for v in mesh.vertices], np.float32)
    rot = mw.to_3x3().normalized()
    vn = np.array([tuple((rot @ v.normal).normalized()) for v in mesh.vertices], np.float32)
    mesh.calc_loop_triangles()
    nt_ = len(mesh.loop_triangles)
    tv = np.empty(nt_ * 3, np.int64); mesh.loop_triangles.foreach_get('vertices', tv); tv = tv.reshape(-1, 3)
    tl = np.empty(nt_ * 3, np.int64); mesh.loop_triangles.foreach_get('loops', tl); tl = tl.reshape(-1, 3)
    uvs = np.empty(len(mesh.loops) * 2, np.float32); mesh.uv_layers.active.data.foreach_get('uv', uvs)
    uvs = uvs.reshape(-1, 2)
    # UV charts: triangles joined where they share a corner (the same vertex at the same UV)
    root = np.arange(nt_)

    def find(i):
        while root[i] != i:
            root[i] = root[root[i]]; i = root[i]
        return i
    corner = {}
    for t in range(nt_):
        for k in range(3):
            other = corner.setdefault((int(tv[t, k]), round(float(uvs[tl[t, k], 0]), 5), round(float(uvs[tl[t, k], 1]), 5)), t)
            ra, rb = find(t), find(other)
            if ra != rb:
                root[ra] = rb
    _, chart_of_tri = np.unique([find(t) for t in range(nt_)], return_inverse=True)
    pos = np.zeros((H, W, 3), np.float32)
    nrm = np.zeros((H, W, 3), np.float16)
    chart = np.full((H, W), -1, np.int32)
    for t in range(nt_):
        uv = uvs[tl[t]] * np.array([W, H]) - .5
        c0, c1 = max(int(np.floor(uv[:, 0].min())), 0), min(int(np.ceil(uv[:, 0].max())), W - 1)
        r0, r1 = max(int(np.floor(uv[:, 1].min())), 0), min(int(np.ceil(uv[:, 1].max())), H - 1)
        if c1 < c0 or r1 < r0:
            continue
        xs, ys = np.meshgrid(np.arange(c0, c1 + 1), np.arange(r0, r1 + 1))
        (x0, y0), (x1, y1), (x2, y2) = uv
        den = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(den) < 1e-12:
            continue
        l0 = ((y1 - y2) * (xs - x2) + (x2 - x1) * (ys - y2)) / den
        l1 = ((y2 - y0) * (xs - x2) + (x0 - x2) * (ys - y2)) / den
        inside = (l0 >= -1e-4) & (l1 >= -1e-4) & (1 - l0 - l1 >= -1e-4)
        if not inside.any():
            continue
        rr, cc = ys[inside], xs[inside]
        b = np.stack([l0[inside], l1[inside], 1 - l0[inside] - l1[inside]], 1)
        # rows counted from the image's top, as PIL reads it (Blender's v runs up)
        pos[H - 1 - rr, cc] = b @ co[tv[t]]
        nrm[H - 1 - rr, cc] = b @ vn[tv[t]]
        chart[H - 1 - rr, cc] = chart_of_tri[t]
    print('RASTER', int((chart >= 0).sum()), 'texels covered of', W * H, 'charts', int(chart.max()) + 1, flush=True)
    np.savez(WORK / 'raster.npz', pos=pos, nrm=nrm, chart=chart, W=W, H=H)
    render('before')
    print('RASTER SAVED', flush=True)


def to_lab(rgb):
    """sRGB 0..1 -> CIE Lab (D65)."""
    lin = np.where(rgb > .04045, ((rgb + .055) / 1.055) ** 2.4, rgb / 12.92)
    xyz = lin @ np.array([[.4124, .2126, .0193], [.3576, .7152, .1192], [.1805, .0722, .9505]], np.float32)
    xyz = xyz / np.array([.95047, 1., 1.08883], np.float32)
    f = np.where(xyz > .008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def from_lab(lab):
    fy = (lab[..., 0] + 16) / 116; fx = fy + lab[..., 1] / 500; fz = fy - lab[..., 2] / 200
    f = np.stack([fx, fy, fz], -1)
    xyz = np.where(f > .2069, f ** 3, (f - 16 / 116) / 7.787) * np.array([.95047, 1., 1.08883], np.float32)
    lin = xyz @ np.array([[3.2406, -.9689, .0557], [-1.5372, 1.8758, -.2040], [-.4986, .0415, 1.0570]], np.float32)
    lin = np.clip(lin, 0, 1)
    return np.where(lin > .0031308, 1.055 * lin ** (1 / 2.4) - .055, 12.92 * lin)


if a.stage == 'paint':
    from PIL import Image
    r_ = np.load(WORK / 'raster.npz')
    pos, nrm, chart = r_['pos'], r_['nrm'].astype(np.float32), r_['chart']
    tex = next(src.parent.glob('*.fbm/*basecolor*'))
    rgb = np.asarray(Image.open(tex).convert('RGB')).astype(np.float32) / 255
    H, W = chart.shape
    cover = chart >= 0
    x, y, z = pos[..., 0], pos[..., 1], pos[..., 2]
    # the head: above the high collar (its top is at 0.80 at the front, a little higher at the back)
    head = cover & (z > .785) & (np.abs(x) < .16)
    lab = to_lab(rgb)
    L, A, B = lab[..., 0], lab[..., 1], lab[..., 2]
    chroma = np.hypot(A, B)
    # skin is warm and saturated; hair and cloth are near-grey (the white streak too)
    skin = head & (chroma > 22) & (B > 12) & (L > 35)
    report = {'head_texels': int(head.sum()), 'skin_texels_before': int(skin.sum())}

    # The surface's own label from its neighbourhood in 3D: cells of 4 mm, each cell's skin share, widened over its 26
    # neighbours, voted only among texels whose normals point the same main way (a lock lying over the cheek faces
    # another way and keeps its own vote). The vote is taken twice: over every texel, and over the texel's own UV island
    # only. The island's vote wins where the island has enough texels round it: a thin skin-coloured streak along the
    # edge of a lock lies millimetres from the cheek behind it, but its own island round it is all hair.
    hr, hc = np.nonzero(head)
    P, N = pos[hr, hc], nrm[hr, hc]
    S = skin[hr, hc].astype(np.float32)
    # the black collar and cloth do not vote: the neck just above the collar is still all skin round it
    V = (L[hr, hc] >= 18).astype(np.float32)
    cell = 0.004
    key = np.floor(P / cell).astype(np.int64) + 512
    axis = np.argmax(np.abs(N), 1)
    nb = axis * 2 + (N[np.arange(len(N)), axis] > 0)

    def vote(group, groups, S=S, V=V):
        k = ((key[:, 0] * 1024 + key[:, 1]) * 1024 + key[:, 2]) * groups + group
        uk, inv = np.unique(k, return_inverse=True)
        vs, vn = np.bincount(inv, weights=S), np.bincount(inv, weights=V)
        cg = uk % groups; ck = uk // groups
        cz_, rest = ck % 1024, ck // 1024
        cy_, cx_ = rest % 1024, rest // 1024
        acc = np.zeros(len(uk)); cnt = np.zeros(len(uk))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    nk = (((cx_ + dx) * 1024 + (cy_ + dy)) * 1024 + (cz_ + dz)) * groups + cg
                    j = np.minimum(np.searchsorted(uk, nk), len(uk) - 1)
                    ok = uk[j] == nk
                    acc[ok] += vs[j[ok]]; cnt[ok] += vn[j[ok]]
        return (acc / np.maximum(cnt, 1))[inv], cnt[inv]

    share_all, _ = vote(nb, 6)
    share_own, own = vote(nb * 4096 + chart[hr, hc], 6 * 4096)
    share = np.where(own >= 200, share_own, share_all)   # the share of skin round each head texel, among skin and hair
    is_skin = skin[hr, hc]
    greyish = (L[hr, hc] > 18) & (L[hr, hc] < 62)    # hair-coloured: not the white streak, not the black collar
    wrong_skin = is_skin & (share < .35)              # a skin-coloured patch on a lock
    warm = ~is_skin & (chroma[hr, hc] > 10) & (B[hr, hc] > 6) & (L[hr, hc] > 18)
    wrong_skin |= warm & (share < .15)               # the darker, brownish edge of such a patch
    wrong_hair = ~is_skin & (share > .65) & greyish   # hair colour or dark paint on the cheek, the ear, the nape
    skin_lab = np.median(lab[hr, hc][is_skin & (share > .8)], 0)
    # (the dark skin behind the ears and under the hair is Tripo's baked shadow, not a smear: it stays)
    report.update(skin_to_hair=int(wrong_skin.sum()), hair_to_skin=int(wrong_hair.sum()))
    hair_lab = np.median(lab[hr, hc][~is_skin & (share < .2) & greyish], 0)
    new = lab.copy()
    keepL = .3    # each repainted texel keeps a little of its lightness variation, so it does not read as a sticker
    fs = (hr[wrong_skin], hc[wrong_skin]); fh = (hr[wrong_hair], hc[wrong_hair])
    new[fs] = hair_lab; new[fs[0], fs[1], 0] = hair_lab[0] + keepL * (L[fs] - L[fs].mean())
    new[fh] = skin_lab; new[fh[0], fh[1], 0] = skin_lab[0] + keepL * (L[fh] - L[fh].mean())
    skin_now = np.zeros((H, W), bool); skin_now[hr, hc] = (is_skin & ~wrong_skin) | wrong_hair
    report.update(skin_lab=[round(float(v), 1) for v in skin_lab], hair_lab=[round(float(v), 1) for v in hair_lab])

    # Thin dark lines on the skin (the lock's edge painted onto the cheek beside it, small ticks): a skin texel much darker
    # than the skin of its own island within THIN texels takes that skin's colour. Broad baked shadow (behind the ears,
    # under the hair) is as dark as its surroundings and stays.
    def box(v, r):
        c = np.pad(v, ((r + 1, r), (r + 1, r))).cumsum(0).cumsum(1)
        return c[2 * r + 1:, 2 * r + 1:] - c[:-2 * r - 1, 2 * r + 1:] - c[2 * r + 1:, :-2 * r - 1] + c[:-2 * r - 1, :-2 * r - 1]
    near = np.zeros((H, W), np.float32); mean = np.zeros((H, W, 3), np.float32)
    for c_ in np.unique(chart[skin_now]):
        m = (skin_now & (chart == c_)).astype(np.float32)
        r0, r1 = np.nonzero(m.any(1))[0][[0, -1]]; c0, c1 = np.nonzero(m.any(0))[0][[0, -1]]
        sl = (slice(max(r0 - THIN, 0), r1 + THIN + 1), slice(max(c0 - THIN, 0), c1 + THIN + 1))
        n = box(m[sl], THIN)
        near[sl] = np.where(m[sl] > 0, n, near[sl])
        for ch in range(3):
            mean[sl + (ch,)] = np.where(m[sl] > 0, box(new[sl + (ch,)] * m[sl], THIN) / np.maximum(n, 1), mean[sl + (ch,)])
    thin = skin_now & (near > .4 * (2 * THIN + 1) ** 2) & (new[..., 0] < mean[..., 0] - 10)
    new[thin] = mean[thin]
    report.update(thin_dark=int(thin.sum()))

    if a.variant == 'redo':
        # Tripo's colours dropped on the head: only the labels stay (skin, hair, the white streak; the black collar keeps
        # its texels), and the skin and hair are painted fresh, in flat anime colours with soft shading from the geometry.
        # the collar is where black cloth is most of the surface round a texel; other near-black texels (shadow behind
        # the ears, at the nape, under the chin) are skin or hair like the surface round them
        dark = (L[hr, hc] < 18).astype(np.float32)
        cloth_share, _ = vote(nb, 6, S=dark, V=np.ones_like(dark))
        collar = np.zeros((H, W), bool); collar[hr, hc] = (cloth_share > .6) & (z[hr, hc] < .83)
        # skin or hair by the surface round the texel first; only where it is mixed does its own colour decide (warm
        # brown shadow behind the ears is skin, a grey lock edge is hair)
        warm1 = (chroma[hr, hc] > 10) & (B[hr, hc] > 6)
        skin_now = np.zeros((H, W), bool); skin_now[hr, hc] = (share > .6) | ((share >= .3) & warm1)
        skin_now &= ~collar
        hair_now = head & ~skin_now & ~collar
        streak = hair_now & (L > 62) & (chroma < 15)
        lab_ = lambda v: np.array(v, np.float32)
        share2 = np.zeros((H, W), np.float32); share2[hr, hc] = share_all

        def blur(v, mask, r):
            out_ = np.zeros_like(v)
            for c_ in np.unique(chart[mask]):
                m = (mask & (chart == c_)).astype(np.float32)
                r0, r1 = np.nonzero(m.any(1))[0][[0, -1]]; c0, c1 = np.nonzero(m.any(0))[0][[0, -1]]
                sl = (slice(max(r0 - r, 0), r1 + r + 1), slice(max(c0 - r, 0), c1 + r + 1))
                b = box(v[sl] * m[sl], r) / np.maximum(box(m[sl], r), 1e-6)
                out_[sl] = np.where(m[sl] > 0, b, out_[sl])
            return out_
        # skin: shaded where hair is close round it (under the fringe, at the hairline, behind the ears) and under the chin
        shade = np.clip((.95 - share2) / .45, 0, 1) * .85
        chin = np.clip((.801 - z) / .008, 0, 1) * (np.abs(x) < .05) * (y > -.06)
        shade = np.maximum(shade, .7 * chin)
        shade = blur(blur(shade.astype(np.float32), skin_now, 8), skin_now, 8)   # the 4 mm vote cells, smoothed away
        skin_col = lab_(REDO['skin']) * (1 - shade[..., None]) + lab_(REDO['skin_shade']) * shade[..., None]
        blush = sum(np.exp(-(((x - cx) / .009) ** 2 + ((z - .836) / .005) ** 2)) for cx in (.034, -.034))
        blush = (blush * (nrm[..., 1] < -.3) * .35)[..., None]
        skin_col = skin_col * (1 - blush) + lab_(REDO['blush']) * blush
        new[skin_now] = skin_col[skin_now]
        # hair: dark toward the scalp, lighter toward the tips, lit from above, dark under each lock
        r = np.linalg.norm(pos - np.array(REDO['head_centre'], np.float32), axis=2)
        t = np.clip((r - .065) / .045, 0, 1)[..., None]
        up = np.clip(nrm[..., 2:3], 0, 1); down = np.clip(-nrm[..., 2:3], 0, 1)
        for mask, deep, mid, light in ((hair_now & ~streak, 'hair_deep', 'hair', 'hair_light'),
                                       (streak, 'streak_shade', 'streak', 'streak')):
            c_ = lab_(REDO[deep]) * (1 - t) + lab_(REDO[mid]) * t
            c_ = c_ * (1 - .55 * up * t) + lab_(REDO[light]) * (.55 * up * t)
            c_ = c_ * (1 - .5 * down) + lab_(REDO[deep]) * (.5 * down)
            new[mask] = c_[mask]
        report.update(redo_skin=int(skin_now.sum()), redo_hair=int(hair_now.sum()), redo_streak=int(streak.sum()))

    # --- the face: projected from the front (-Y) onto the skin that faces forward ---------------------------------------
    front = skin_now & (nrm[..., 1] < -.25)
    fr, fc = np.nonzero(front)
    fx, fz = x[fr, fc], z[fr, fc]
    texel = .00035    # about one texel on the face, in metres

    def stroke(points, thickness):
        """Coverage 0..1 of a stroke of varying thickness, anti-aliased over a texel."""
        pts = np.array(points, float); th = np.array(thickness, float)
        best = np.full(len(fx), np.inf); half = np.zeros(len(fx))
        for i in range(len(pts) - 1):
            p0, seg = pts[i], pts[i + 1] - pts[i]
            t = np.clip(((fx - p0[0]) * seg[0] + (fz - p0[1]) * seg[1]) / float(seg @ seg), 0, 1)
            d = np.hypot(fx - p0[0] - t * seg[0], fz - p0[1] - t * seg[1])
            closer = d < best
            best[closer] = d[closer]; half[closer] = (th[i] + t[closer] * (th[i + 1] - th[i])) / 2
        return np.clip((half - best) / texel + .5, 0, 1)

    def pill(e):
        """A vertical pill (a stadium) with its top cut flat by the heavy lid; coverage 0..1."""
        (cx, cz), (hw, hh) = e['centre'], e['half']
        u, v = np.abs(fx - cx), fz - cz
        core = hh - hw
        d = np.where(np.abs(v) <= core, u - hw, np.hypot(u, np.abs(v) - core) - hw)
        lid = cz + hh - FACE['lid'] * 2 * hh
        d = np.maximum(d, fz - lid)                 # nothing above the lid line
        return np.clip(-d / texel + .5, 0, 1)

    def lid_line(e):
        """The upper lid: a flat stroke along the cut, wider than the pill, tipped down at the outside."""
        (cx, cz), (hw, hh) = e['centre'], e['half']
        lid = cz + hh - FACE['lid'] * 2 * hh
        o = 1 if cx > 0 else -1
        return stroke([[cx - o * 1.35 * hw, lid + .0004], [cx + o * .4 * hw, lid + .0008], [cx + o * 1.6 * hw, lid - .0008]],
                      [.0026, .0032, .0022])

    col = lambda name: to_lab(np.array(FACE['colours'][name], np.float32))
    paint = new[fr, fc]
    for e in FACE['eyes']:
        for cov in (pill(e), lid_line(e)):
            paint = paint * (1 - cov[:, None]) + col('eyes') * cov[:, None]
    for b in FACE['brows']:
        cov = stroke(b['points'], b['thickness'])
        paint = paint * (1 - cov[:, None]) + col('brows') * cov[:, None]
    cov = stroke(FACE['mouth']['points'], FACE['mouth']['thickness'])
    paint = paint * (1 - cov[:, None]) + col('mouth') * cov[:, None]
    new[fr, fc] = paint

    out_rgb = np.where(head[..., None], from_lab(new.astype(np.float32)), rgb)   # nothing below the head changes
    # pad round every island with its own edge colour (8 texels), so filtering and mipmaps never pull in other colours
    filled = chart >= 0
    for _ in range(8):
        acc = np.zeros_like(out_rgb); n = np.zeros(filled.shape, np.float32)
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            f = np.roll(filled, (dr, dc), (0, 1)); acc += np.roll(out_rgb, (dr, dc), (0, 1)) * f[..., None]; n += f
        grow = ~filled & (n > 0)
        out_rgb[grow] = acc[grow] / n[grow, None]; filled |= grow
    name = 'basecolor.png' if a.variant == 'clean' else f'basecolor-{a.variant}.png'
    Image.fromarray((np.clip(out_rgb, 0, 1) * 255 + .5).astype(np.uint8)).save(out / name)
    (out / name.replace('basecolor', 'paint').replace('.png', '.json')).write_text(json.dumps({**report, 'face': FACE}, indent=2) + '\n')
    print('PAINT', json.dumps(report), flush=True)


if a.stage == 'pack':
    body, nt, bsdf, image = load()
    tag = '' if a.variant == 'clean' else f'-{a.variant}'
    new = bpy.data.images.load(str(out / f'basecolor{tag}.png'))
    bsdf.inputs['Base Color'].links[0].from_node.image = new
    for link in [l for l in nt.links if l.to_node == bsdf and l.to_socket.name == 'Normal']:
        nt.links.remove(link)
    render('after' + tag)
    new.pack()
    bpy.ops.wm.save_as_mainfile(filepath=str(out / f'CameBack-Body{tag}.blend'), compress=True)
    print('PACK OK', flush=True)
