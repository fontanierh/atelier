"""Where the outfit leaves the body bare: the green body key read back onto Cairo's own body and onto the Tripo model.

The key images (`<swap>/key/key-<view>.png`, made by `cairo_body_swap_sunburst.py --key`) are the dressed reference
views with every visible bit of bare mannequin painted flat green. The mannequin in those views is Cairo's base body
(the regions under the clothes, `mannequin()` below, shared with `cairo_body_swap_references.py`) seen by known
orthographic cameras (`references/envelope.json`), so the key lines up with the base body pixel for pixel.

`exposed_skin` marks the base-body faces the key shows bare. Green pixels count only where the dressed view is skin
toned or plain grey (`plausible`): Sunburst sometimes paints a whole cuff green, and a coloured garment under a green
pixel is no bare body. A face seen face-on by a view (and not hidden by the rest of the mannequin) takes that view's
vote from the 3x3 pixels under it; a green vote is dropped when the Tripo model stands more than 1 cm in front of the
face along the view ray (a wrist deep in a sleeve's mouth seen from the side, a neck behind a collar). A face is bare
when more than half of its views say green. Faces no view sees (under the arms, the top of the shoulders) take the
majority of their neighbours, wave by wave, and outfit islands under 2 cm2 inside bare skin close. Bare islands under
8 cm2 farther than 2 cm from the head and hands go back to covered (`_specks`): a bare neck ring or wrist can be a
handful of faces, a speck in the middle of a garment is green spilled past an opening. Faces below the top of the
sock region are never bare: the feet are always shod (Sunburst sometimes paints a tabi's ankle green in one view).

`tripo_body_faces` marks the faces of the aligned Tripo model that are mannequin, not outfit. Tripo's headless model
is hollow and only roughly on the base body (its chest often sits a few mm inside Cairo's), so:
- a face some view sees is judged by the key: body when the key is green there by majority (the green shrunk by
  3 px, about 2 mm, so garment edges lying on the skin keep their faces) and the face does not stand more than
  1 cm in front of the mannequin along the view ray (in front, the green belongs to the body behind a garment);
- a face lying on bare skin (its nearest base-body face is bare and it is within 6 mm of it, either side) is body
  too: Tripo's copy of a bare arm keeps the odd face the key missed at the silhouette;
- a face no view sees (the tops of bare shoulders, under bare arms, the floor of a collar) is also body when it lies
  inside the body under bare skin, however deep;
- with the baked colours given, and when the median colour of the key's faces is a skin tone (warm: red over green
  over blue) set by at least 30 faces, colour decides the rest. A face is skin-coloured when it is nearer that skin
  colour than the outfit faces within 6 cm (faces every view shows as outfit), and nearer than 0.3; never where that
  outfit is itself close to skin (tan, beige), and within 0.08 of the skin where no outfit is near. Colour is
  relative to the outfit around the face, so Tripo's shading does not matter. It is used twice:
  - Tripo faces lying on covered base body (within 6 mm) that no view shows as outfit, the side of the chest inside
    an armhole (the arm hides it from the side, the garment from the front), make the base face under them bare
    when skin-coloured faces cover more than half of it: the key could not see it, the neighbours only guessed;
  - a face within 2.5 cm of bare skin, or where the key is green but the face stands in front of the mannequin, is
    body when skin-coloured: the pale patches Tripo leaves beside a jersey's straps.
  (With only stumps bare, the key's faces are mostly cuff and collar insides, so their median is the garment's
  colour and the colour rules stay off.)
Tripo's neck stump and wrist caps end inside the kept head and hands and stay hidden there; a capped neck stump
is opened by the assembly as before.
The key and bare-skin labels are then opened (`_open`): strips one face wide and specks go back to outfit, because at
a garment edge a few faces of evidence are more often the key's edge than skin, and cutting them leaves ragged notches
in the cloth. The colour proofs are added after the opening (they are no key edge). Body islands under 1 cm2 go back
to outfit, and outfit islands under 8 cm2 enclosed by body close (loose pieces such as toggles stay).
Imported by `cairo_body_swap_assemble.py`; Blender only.
"""
import json
from pathlib import Path
import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

VIEWS = {'front': (1, 0, 0), 'back': (-1, 0, 0), 'left': (0, 1, 0), 'right': (0, -1, 0)}   # as in cairo_body_swap_references.py
MANNEQUIN_REGIONS = ('under_sweatshirt', 'under_shorts', 'lower_legs', 'under_socks', 'under_shoes')
IN_FRONT = .01    # m: a Tripo face this far in front of the mannequin is cloth over the edge of the green
ON_BODY = .006    # m: a Tripo face this close over bare skin (or inside the body) is the mannequin itself
SAME_COLOUR = .08  # RGB distance (0-1) to the skin colour where no outfit face is near to compare with
FAR = .3           # RGB distance: a face this far from the skin colour is not skin, however far the outfit is
LAST = {}          # the per-face proofs of the last tripo_body_faces call
REJECTED = {}      # green key pixels over a coloured garment in the dressed view, per view


def mannequin(objects):
    """The headless, handless reference mannequin as a world-space bmesh: the body regions under the clothes, welded,
    with the neck and wrist openings capped."""
    bm = bmesh.new()
    for o in objects:
        if o.type == 'MESH' and o.get('body_region') in MANNEQUIN_REGIONS:
            tmp = o.data.copy(); tmp.transform(o.matrix_world)
            bm.from_mesh(tmp); bpy.data.meshes.remove(tmp)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=.0005)
    caps = bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)   # cap the neck and wrist openings
    bmesh.ops.triangulate(bm, faces=caps['faces'])
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    return bm


def green(px):
    """Key pixels (floats 0-1): clearly green, whatever the shading Sunburst left at the edges."""
    r, g, b = px[..., 0], px[..., 1], px[..., 2]
    return (g > .55) & (g - np.maximum(r, b) > .3)


def plausible(px):
    """Dressed-view pixels (floats 0-1) that can show bare mannequin: skin tone (Sunburst paints the bare body as
    Cairo's skin) or plain grey (a stump left as the grey mannequin, or its shadow). Sunburst sometimes paints a whole
    cuff green in the key; a coloured garment under a green pixel is no bare body."""
    r = np.maximum(px[..., 0], 1e-3); gr = px[..., 1] / r; br = px[..., 2] / r
    skin = (px[..., 0] > .3) & (gr > .6) & (gr < .9) & (br > .4) & (br < .8)
    return skin | (px.max(-1) - px.min(-1) < .05)


def _image(path):
    img = bpy.data.images.load(str(path)); W, H = img.size
    px = np.array(img.pixels[:], dtype=np.float32).reshape(H, W, 4)[:, :, :3]   # row 0 is the bottom of the image
    bpy.data.images.remove(img)
    return px


def _keys(refs, key_dir):
    env = json.loads((Path(refs) / 'envelope.json').read_text())
    centre = np.array(env['center']); scale = env['ortho_scale']
    for view, d in VIEWS.items():
        path = Path(key_dir) / f'key-{view}.png'
        if not path.exists():
            continue
        px = _image(path); H, W = px.shape[:2]
        mask = green(px)
        dressed = Path(refs) / f'{view}.png'
        if dressed.exists():   # (same camera and size: the key is an edit of this view)
            ok = plausible(_image(dressed))
            REJECTED[view] = int((mask & ~ok).sum()); mask &= ok
        d = Vector(d); rot = (-d).to_track_quat('-Z', 'Y').to_matrix()
        right, up = np.array(rot.col[0]), np.array(rot.col[1])

        def pixel(C, W=W, H=H, right=right, up=up):
            return ((C - centre) @ right / scale + .5) * W, ((C - centre) @ up / scale + .5) * H
        yield view, d, mask, pixel


def shrink(mask, px):
    """Binary erosion by px pixels (4-neighbourhood, numpy only)."""
    m = mask.copy()
    for _ in range(px):
        m[1:, :] &= m[:-1, :]; m[:-1, :] &= m[1:, :]; m[:, 1:] &= m[:, :-1]; m[:, :-1] &= m[:, 1:]
    return m


def _vote(mask, x, y):
    x, y = int(x), int(y)
    if not (1 <= x < mask.shape[1] - 1 and 1 <= y < mask.shape[0] - 1):
        return None
    return mask[y - 1:y + 2, x - 1:x + 2].sum() >= 5   # majority of the 3x3 window


def _neighbours(polys, n):
    nbrs = [[] for _ in range(n)]
    edge_faces = {}
    for i, vs in enumerate(polys):
        for k in range(len(vs)):
            edge_faces.setdefault(tuple(sorted((vs[k], vs[(k + 1) % len(vs)]))), []).append(i)
    for fs in edge_faces.values():
        for a in fs:
            nbrs[a].extend(b for b in fs if b != a)
    return nbrs


def _spread(label, nbrs):
    """Unlabelled faces (-1) take the strict majority of their labelled neighbours, one wave at a time."""
    while (label < 0).any():
        wave = {}
        for i in np.where(label < 0)[0]:
            known = [label[j] for j in nbrs[i] if label[j] >= 0]
            if known:
                wave[i] = int(2 * sum(known) > len(known))
        if not wave:
            label[label < 0] = 0
            break
        for i, v in wave.items():
            label[i] = v
    return label


def _open(label, nbrs):
    """Morphological opening of the body label on the mesh: a body face survives only if it, or a neighbour, has
    every neighbour body. Removes strips one face wide and specks (a cuff rim the key's edge touched, bits of a
    strap edge) and keeps areas (an arm, a V of chest) whole. Returns the label and the number of faces removed."""
    core = np.array([label[i] == 1 and all(label[j] == 1 for j in nbrs[i]) for i in range(len(label))])
    kept = np.array([label[i] == 1 and (core[i] or any(core[j] for j in nbrs[i])) for i in range(len(label))])
    return kept.astype(int), int((label == 1).sum() - kept.sum())


def _islands(label, nbrs, area, body_min=1e-4, hole_max=2e-4):
    """Body islands under body_min m2 go back to outfit; outfit islands under hole_max m2 touching body close."""
    flipped = {0: 0, 1: 0}
    for value, limit in ((1, body_min), (0, hole_max)):
        done = np.zeros(len(label), bool)
        for s in np.where(label == value)[0]:
            if done[s]:
                continue
            comp = [s]; done[s] = True; k = 0
            while k < len(comp):
                for j in nbrs[comp[k]]:
                    if label[j] == value and not done[j]:
                        done[j] = True; comp.append(j)
                k += 1
            if area[comp].sum() < limit and (value == 1 or any(label[j] == 1 for c in comp for j in nbrs[c])):   # a loose piece (a toggle) is no hole
                label[comp] = 1 - value; flipped[value] += len(comp)
    return label, {'body_to_outfit': flipped[1], 'outfit_to_body': flipped[0]}


def _region_faces(objects):
    """World-space centres, normals, areas and vertex lists of every mannequin region face, with their owners."""
    regions = [o for o in objects if o.type == 'MESH' and o.get('body_region') in MANNEQUIN_REGIONS]
    C, N, A, V, owner = [], [], [], [], []
    offset = 0; verts = []
    for o in regions:
        M = o.matrix_world; R = M.to_3x3()
        verts.extend(M @ v.co for v in o.data.vertices)
        for p in o.data.polygons:
            C.append((M @ p.center)[:]); N.append((R @ p.normal).normalized()[:]); A.append(p.area)
            V.append([offset + v for v in p.vertices]); owner.append((o.name, p.index))
        offset += len(o.data.vertices)
    return regions, np.array(C), np.array(N), np.array(A), V, owner, verts


def exposed_skin(objects, refs, key_dir, floor_z, outfit=None):
    """{region object name: bool per polygon} of bare base-body faces, and a report. `outfit`: the aligned Tripo mesh
    (world coordinates), so green seen past a garment standing in front of the body does not count."""
    regions, C, N, A, V, owner, verts = _region_faces(objects)
    mbm = mannequin(objects); mann = BVHTree.FromBMesh(mbm); mbm.free()
    tripo = None if outfit is None else BVHTree.FromPolygons([v.co for v in outfit.vertices], [tuple(p.vertices) for p in outfit.polygons])
    n = len(C); seen = np.zeros(n, int); votes = np.zeros(n, int); views = {}; past_garment = 0
    for view, d, mask, pixel in _keys(refs, key_dir):
        X, Y = pixel(C); hits = 0
        for i in np.where(N @ np.array(d) > .2)[0]:
            loc = mann.ray_cast(Vector(C[i]) + d * 2, -d)[0]
            if loc is None or (loc - Vector(C[i])).length > .0015:
                continue   # the rest of the mannequin hides it in this view
            v = _vote(mask, X[i], Y[i])
            if v is None:
                continue
            if v and tripo is not None:
                front = tripo.ray_cast(Vector(C[i]) + d * 2, -d)[0]
                if front is not None and (front - Vector(C[i])).dot(d) > IN_FRONT:
                    past_garment += 1; continue   # a garment stands in front: the green is the body deeper in (a wrist in a sleeve)
            seen[i] += 1; votes[i] += int(v); hits += 1
        views[view] = hits
    label = np.full(n, -1)
    label[seen > 0] = (2 * votes[seen > 0] > seen[seen > 0]).astype(int)
    label[C[:, 2] < floor_z] = 0
    nbrs = _neighbours(V, n)
    unseen = int((label < 0).sum())
    label, flipped = _islands(_spread(label, nbrs), nbrs, A, body_min=0)
    specks = _specks(label, nbrs, A, C, objects)
    out = {o.name: np.zeros(len(o.data.polygons), bool) for o in regions}
    for i in np.where(label == 1)[0]:
        name, pi = owner[i]; out[name][pi] = True
    report = {'faces_seen_per_view': views, 'green_px_over_garment_ignored': dict(REJECTED), 'green_votes_past_a_garment': past_garment, 'bare_specks_dropped': specks, 'region_faces': n, 'unseen_filled': unseen, 'islands_flipped': flipped,
              'bare_faces': int(label.sum()), 'bare_area_cm2': round(float(A[label == 1].sum() * 1e4), 1),
              'bare_by_region': {o.get('body_region'): int(out[o.name].sum()) for o in regions}}
    return out, report


def _specks(label, nbrs, area, C, objects, most=8e-4, reach=.02):
    """Bare islands under `most` m2 farther than `reach` from the head and hands go back to covered: a bare neck ring
    or wrist can be a handful of faces, but a speck in the middle of a garment is green spilled past an opening in
    one view (a dark sleeve's mouth over a dark coat). Returns the number of faces."""
    from mathutils.kdtree import KDTree
    pins = [o.matrix_world @ v.co for o in objects if o.type == 'MESH' and o.get('body_region') in ('head', 'hands_forearms') for v in o.data.vertices]
    if not pins:
        return 0
    kd = KDTree(len(pins))
    for k, c in enumerate(pins):
        kd.insert(c, k)
    kd.balance()
    done = label != 1; dropped = 0
    for s0 in np.where(~done)[0]:
        if done[s0]:
            continue
        comp = [s0]; done[s0] = True; k = 0
        while k < len(comp):
            for j in nbrs[comp[k]]:
                if not done[j]:
                    done[j] = True; comp.append(j)
            k += 1
        if area[comp].sum() < most and all(kd.find(Vector(C[i]))[2] > reach for i in comp):
            label[comp] = 0; dropped += len(comp)
    return dropped


def tripo_body_faces(me, objects, exposed, refs, key_dir, colours=None):
    """Bool per polygon of `me` (world coordinates, as the fit leaves the Tripo model): mannequin, not outfit.
    `colours`: optional baked base colour per polygon (N x 3, 0-1)."""
    n = len(me.polygons)
    C = np.array([p.center[:] for p in me.polygons]); N = np.array([p.normal[:] for p in me.polygons])
    area = np.array([p.area for p in me.polygons])
    bvh = BVHTree.FromPolygons([v.co for v in me.vertices], [tuple(p.vertices) for p in me.polygons])
    mbm = mannequin(objects); mann = BVHTree.FromBMesh(mbm); mbm.free()
    # proof 1, the key
    seen = np.zeros(n, int); votes = np.zeros(n, int); front = np.zeros(n, int)
    for view, d, mask, pixel in _keys(refs, key_dir):
        X, Y = pixel(C); mask = shrink(mask, 3)
        for i in np.where(N @ np.array(d) > .2)[0]:
            loc, _, idx, _ = bvh.ray_cast(Vector(C[i]) + d * 2, -d)
            if idx != i and (loc is None or (loc - Vector(C[i])).length > .0015):
                continue   # something else is in front of it in this view
            v = _vote(mask, X[i], Y[i])
            if v is None:
                continue
            seen[i] += 1
            if not v:
                continue
            mloc = mann.ray_cast(Vector(C[i]) + d * 2, -d)[0]   # the mannequin surface this green pixel showed
            if mloc is None or (Vector(C[i]) - mloc).dot(d) > IN_FRONT:
                front[i] += 1; continue
            votes[i] += 1
    by_key = (seen > 0) & (2 * votes >= seen) & (votes > 0)
    green_in_front = (seen > 0) & (2 * (votes + front) >= seen) & (front > 0) & ~by_key
    regions, RC, RN, RA, RV, owner, verts = _region_faces(objects)
    bare = np.array([exposed[name][pi] for name, pi in owner])
    rbvh = BVHTree.FromPolygons(verts, RV)
    under = np.full(n, -1); height = np.zeros(n)   # the base-body face nearest each Tripo face, and the height over it
    for i in range(n):
        loc, nrm, idx, dist = rbvh.find_nearest(Vector(C[i]), .08)
        if idx is not None:
            under[i] = idx; height[i] = (Vector(C[i]) - loc).dot(Vector(RN[idx]))   # negative inside the body
    # the skin colour: the median of the key's faces, when that is a skin tone (warm) set by at least 30 faces
    skin_colour = None; skin_coloured = None; unseen_to_bare = 0
    if colours is not None and by_key.sum() >= 30:
        skin_colour = np.median(colours[by_key], axis=0)
        if not (skin_colour[0] > skin_colour[1] > skin_colour[2] and skin_colour[0] - skin_colour[2] > .15):
            skin_colour = None
    if skin_colour is not None:
        from mathutils.kdtree import KDTree
        cloth = np.where((seen > 0) & (votes + front == 0))[0]   # faces every view shows as outfit
        ckd = KDTree(len(cloth))
        for k, i in enumerate(cloth):
            ckd.insert(Vector(C[i]), k)
        ckd.balance()

        def skin_coloured(i):
            """Nearer the skin colour than the outfit around it (within 6 cm), so shading does not matter; never where
            that outfit is itself skin-coloured (tan, beige), and never far from both."""
            around = [cloth[j] for _, j, _ in ckd.find_range(Vector(C[i]), .06)]
            to_skin = np.linalg.norm(colours[i] - skin_colour)
            if not around:
                return to_skin < SAME_COLOUR
            local = np.median(colours[around], axis=0)
            return to_skin < min(np.linalg.norm(colours[i] - local), FAR) and np.linalg.norm(local - skin_colour) > FAR / 2
        # Tripo faces lying on covered body that no view shows as outfit (the side of the chest inside an armhole: the
        # arm hides it from the side, the garment from the front) are body when skin-coloured, and so is the base
        # face under them, when they cover most of it: the key could not see it, the neighbours' majority only guessed
        lying = np.where((under >= 0) & (np.abs(height) <= ON_BODY) & ~bare[np.maximum(under, 0)] & ((seen == 0) | (votes + front > 0)))[0]
        on_area = np.bincount(under[under >= 0], weights=area[under >= 0] * (np.abs(height[under >= 0]) <= ON_BODY), minlength=len(bare))
        skin_area = np.zeros(len(bare))
        for i in lying:
            if skin_coloured(i):
                skin_area[under[i]] += area[i]
        newly = (on_area > 0) & (skin_area > .5 * on_area)
        for k in np.where(newly)[0]:
            name, pi = owner[k]; exposed[name][pi] = True
        bare |= newly; unseen_to_bare = int(newly.sum())
    # proof 2, on or inside bare skin
    by_body = np.zeros(n, bool)
    for i in np.where(under >= 0)[0]:
        if bare[under[i]]:
            by_body[i] = abs(height[i]) <= ON_BODY or (not seen[i] and height[i] <= ON_BODY)
    # proof 3, skin colour near bare skin, or where the key is green in front of the mannequin
    by_colour = np.zeros(n, bool)
    if skin_colour is not None:
        kd = KDTree(int(bare.sum()))
        for k, c in enumerate(RC[bare]):
            kd.insert(Vector(c), k)
        kd.balance()
        for i in np.where(~by_key & ~by_body)[0]:
            if (green_in_front[i] or kd.find(Vector(C[i]))[2] < .025) and skin_coloured(i):
                by_colour[i] = True
    in_front = int(green_in_front.sum())
    LAST.update(by_key=by_key, by_body=by_body, by_colour=by_colour, seen=seen, votes=votes, front=front)   # for diagnostic renders
    label = (by_key | by_body).astype(int)
    nbrs = _neighbours([tuple(p.vertices) for p in me.polygons], n)
    label, thin = _open(label, nbrs)
    label[by_colour] = 1   # after the opening: a colour proof is no key edge
    label, flipped = _islands(label, nbrs, area, hole_max=8e-4)
    body = label == 1
    report = {'faces': n, 'seen': int((seen > 0).sum()), 'green_but_in_front_of_mannequin': in_front,
              'by_key': int(by_key.sum()), 'on_bare_skin': int(by_body.sum()), 'skin_coloured': int(by_colour.sum()),
              'skin_colour': None if skin_colour is None else [round(float(c), 3) for c in skin_colour],
              'hidden_base_faces_made_bare': unseen_to_bare,
              'thin_strips_removed': thin, 'islands_flipped': flipped,
              'body_faces': int(body.sum()), 'body_area_cm2': round(float(area[body].sum() * 1e4), 1)}
    return body, report
