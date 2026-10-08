"""Three-bone fingers for a Tripo body rig, fitted from the mesh.

    from atelier.blender.tripo_fingers import add_fingers
    report = add_fingers(arm, body)      # in Blender, the rigged body in its T-pose, facing +X, palms forward

Tripo's auto-rig (Mixamo names) has no fingers. For each hand, the vertices its hand bone owns (weight over 0.5) are
sliced along the hand: the cut at which the far part splits into exactly four finger-height pieces gives the fingers
(index highest, little finger lowest; their middles below the top `thumb_band` of the hand's height above its bone,
0.2 by default, 0.35 for long claws), and the narrow piece standing up above them the thumb. Each piece's centreline
gives four joint centres, three bones per digit named mixamorig:<Side>Hand<Finger><1-3>, rolled so a positive turn
about local X curls toward the palm. Only the digits' vertices are reweighted: smoothly from the palm over the first
joint, then joint by joint, relaxed twice over their neighbours, four influences at most. Body bones and every other
vertex's weights are left exactly as they were (asserted).
"""
import math
import bpy
from mathutils import Vector

FINGERS = ['Thumb', 'Index', 'Middle', 'Ring', 'Pinky']


def _smooth(v):
    t = max(0., min(1., v))
    return t * t * (3 - 2 * t)


def add_fingers(arm, body, palm_axis=Vector((1, 0, 0)), thumb_band=.2):
    before_weights = [[(g.group, g.weight) for g in v.groups] for v in body.data.vertices]
    before_bones = {b.name: b.matrix_local.copy() for b in arm.data.bones}
    neighbors = [set() for _ in body.data.vertices]
    for e in body.data.edges:
        x, y = e.vertices; neighbors[x].add(y); neighbors[y].add(x)
    # The GLB mesh is split at every hard edge and UV seam: connectivity is taken over welded positions.
    key_of = [tuple(round(c, 5) for c in v.co) for v in body.data.vertices]
    verts_of = {}
    for i, k in enumerate(key_of):
        verts_of.setdefault(k, []).append(i)
    wadj = {k: set() for k in verts_of}
    for e in body.data.edges:
        ka, kb = key_of[e.vertices[0]], key_of[e.vertices[1]]
        if ka != kb:
            wadj[ka].add(kb); wadj[kb].add(ka)

    def components(keys):
        seen, comps = set(), []
        for s in keys:
            if s in seen:
                continue
            stack, comp = [s], []
            seen.add(s)
            while stack:
                v = stack.pop(); comp.append(v)
                for n in wadj[v]:
                    if n in keys and n not in seen:
                        seen.add(n); stack.append(n)
            comps.append(comp)
        return comps

    def centroid(keys):
        return sum((Vector(k) for k in keys), Vector()) / len(keys)

    def centreline(keys, hint):
        proj = {k: Vector(k).dot(hint) for k in keys}
        lo = sorted(keys, key=lambda k: proj[k]); n = max(4, len(keys) // 6)
        base, tip = centroid(lo[:n]), centroid(lo[-n:])
        axis = (tip - base).normalized()
        t = {k: (Vector(k) - base).dot(axis) for k in keys}
        tmin, tmax = min(t.values()), max(t.values())
        pts = []
        for q in range(4):
            a0, a1 = tmin + (tmax - tmin) * q / 4, tmin + (tmax - tmin) * (q + 1) / 4
            ids = [k for k in keys if a0 <= t[k] <= a1] or keys
            c = centroid(ids); on = base + axis * ((c - base).dot(axis))
            pts.append(on + (c - on) * .5)
        pts[0] = pts[0] - axis * (tmax - tmin) * .12
        pts[3] = base + axis * (tmax + (tmax - tmin) * .02)
        return pts, tmax - tmin

    def detect(side):
        hb = arm.data.bones[f'mixamorig:{side}Hand']
        gi = body.vertex_groups[hb.name].index
        hand = {key_of[v.index] for v in body.data.vertices if any(g.group == gi and g.weight > .5 for g in v.groups)}
        d = (hb.tail_local - hb.head_local).normalized()
        s = {k: (Vector(k) - hb.head_local).dot(d) for k in hand}
        smax = max(s.values()); zmax = max(k[2] for k in hand)
        z_split = zmax - thumb_band * (zmax - hb.head_local.z)   # the thumb stands above this; the fingers below
        finger_cut, finger_pieces = None, None
        for kk in range(59, 0, -1):
            cut = smax * kk / 60
            pieces = [c for c in components({k for k in hand if s[k] > cut}) if len(c) >= 4]
            fingers = [c for c in pieces if centroid(c).z < z_split]
            if len(fingers) == 4:
                finger_cut, finger_pieces = cut, fingers
            elif finger_pieces is not None and len(fingers) < 4:
                break
        if finger_pieces is None:
            raise RuntimeError(f'{side}: could not isolate four fingers')
        finger_keys = {k for c in finger_pieces for k in c}
        thumb, thumb_cut = None, None
        for kk in range(59, 0, -1):
            zc = hb.head_local.z + (zmax - hb.head_local.z) * kk / 60
            pieces = [c for c in components({k for k in hand if k[2] > zc and k not in finger_keys}) if len(c) >= 4]
            if not pieces:
                continue
            top = max(pieces, key=len)
            if max(s[k] for k in top) - min(s[k] for k in top) > .45 * smax or len(pieces) > 2:
                break
            thumb, thumb_cut = top, zc
        if thumb is None:
            raise RuntimeError(f'{side}: could not isolate the thumb')
        digits = {}
        order = sorted(((centroid(c).z, c) for c in finger_pieces), key=lambda zc: -zc[0])
        for name, (_, c) in zip(FINGERS[1:], order):
            pts, length = centreline(c, d)
            digits[name] = dict(keys=c, points=pts, length=length)
        pts, length = centreline(thumb, (Vector((0, 0, 1)) * .7 + d * .5).normalized())
        digits['Thumb'] = dict(keys=thumb, points=pts, length=length)
        for dg in digits.values():
            dg['ids'] = [i for k in dg['keys'] for i in verts_of[k]]
        return hb, digits, dict(finger_cut=round(finger_cut, 4), thumb_cut=round(thumb_cut, 4))

    detected = {side: detect(side) for side in ('Left', 'Right')}
    bpy.ops.object.select_all(action='DESELECT'); arm.select_set(True); bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    chains = {}
    for side, (hb, digits, _) in detected.items():
        for finger, dg in digits.items():
            pts, names = dg['points'], []
            for k in range(3):
                n = f'mixamorig:{side}Hand{finger}{k + 1}'
                eb = arm.data.edit_bones.new(n)
                eb.head, eb.tail = pts[k], pts[k + 1]
                eb.parent = arm.data.edit_bones[names[-1] if names else hb.name]
                eb.use_connect = k > 0
                eb.align_roll(palm_axis)
                names.append(n)
            chains[(side, finger)] = dict(points=pts, bones=names, ids=dg['ids'], length=dg['length'])
    bpy.ops.object.mode_set(mode='OBJECT')
    for n, m in before_bones.items():
        assert max(abs(arm.data.bones[n].matrix_local[i][j] - m[i][j]) for i in range(4) for j in range(4)) < 1e-6
    for c in chains.values():
        for n in c['bones']:
            body.vertex_groups.new(name=n)
    changed, per_chain = set(), {}
    for (side, finger), c in chains.items():
        pts, hand_name = c['points'], f'mixamorig:{side}Hand'
        lengths = [(b - a).length for a, b in zip(pts, pts[1:])]
        band = .08 * sum(lengths)
        for i in c['ids']:
            p = body.data.vertices[i].co
            best, off = None, 0.
            for k, (p0, p1, L) in enumerate(zip(pts, pts[1:], lengths)):
                t = (p - p0).dot(p1 - p0) / (L * L)
                near = p0 + (p1 - p0) * max(0., min(1., t))
                arc = off + L * (t if k == 0 and t < 0 else max(0., min(1., t)))
                if best is None or (p - near).length < best[0]:
                    best = ((p - near).length, arc)
                off += L
            arc = best[1]
            amount = _smooth((arc + band) / (2 * band))
            one = _smooth((arc - lengths[0] + .5 * band) / band)
            two = _smooth((arc - lengths[0] - lengths[1] + .5 * band) / band)
            w = {c['bones'][0]: amount * (1 - one), c['bones'][1]: amount * one * (1 - two), c['bones'][2]: amount * one * two, hand_name: 1 - amount}
            for g in [g.group for g in body.data.vertices[i].groups]:
                body.vertex_groups[g].remove([i])
            for n, ww in w.items():
                if ww > 1e-7:
                    body.vertex_groups[n].add([i], ww, 'REPLACE')
            changed.add(i)
        per_chain[side + finger] = len(c['ids'])
    for _ in range(2):
        cur = [{g.group: g.weight for g in v.groups} for v in body.data.vertices]; upd = {}
        for i in changed:
            adj = neighbors[i]
            if not adj:
                continue
            comb = {g: w * .7 for g, w in cur[i].items()}
            for o in adj:
                for g, w in cur[o].items():
                    comb[g] = comb.get(g, 0) + .3 * w / len(adj)
            top = sorted(comb.items(), key=lambda kv: -kv[1])[:4]; tot = sum(w for _, w in top)
            upd[i] = [(g, w / tot) for g, w in top if w / tot > 1e-7]
        for i, ws in upd.items():
            for g in [g.group for g in body.data.vertices[i].groups]:
                body.vertex_groups[g].remove([i])
            for g, w in ws:
                body.vertex_groups[g].add([i], w, 'REPLACE')
    assert all([(g.group, g.weight) for g in v.groups] == before_weights[v.index] for v in body.data.vertices if v.index not in changed)
    return dict(added_finger_bones=len(chains) * 3, detection={s: v[2] for s, v in detected.items()}, reweighted_vertices=len(changed),
                chains={s + f: dict(vertices=per_chain[s + f], length=round(c['length'], 4)) for (s, f), c in chains.items()})
