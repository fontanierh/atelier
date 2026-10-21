"""The ferry terminal's world change at Hidamari: the quay's rail opened where the terminal's jetty meets it.

blender --background --factory-startup --threads 3 --python-exit-code 1 -P ferry_cut.py
Reads hidamari/assets/HD_Harbor.fbx (this region's export, build.py harbor()) and the cuts recorded in
ferry/terminals/site.json (berth.world_cuts, from site.py hidamari_layout; the terminal's walk audit was run without
them). Writes hidamari/ferry/HD_Harbor.fbx, the harbour the game imports (exports.py), and cut.json.

A world cut is the rail of the quay wall across the jetty root: in plan inside the cut's y band, from z_from up, and
meeting its x span. That rail is a long beam and posts every few metres. The beam is cut a post's half-width outside
the span at each end and the piece between removed, with its ends closed; posts inside (or straddling) the span go;
and a post is copied onto each new rail end, as at every other opening in the rail (build.py: a post at every
endpoint). The copy keeps the post's colours; its UVs are the harbour's own dominant-plane projection.

Checks (any failure exits 1): every cut removes something, no triangle the cut describes is left (site.cut_mask),
nothing outside the cut's band is touched (the triangle count and the bounds of everything else are unchanged), and
the result is closed where it was cut.
"""
import importlib.util
import json
import hashlib
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
import yori  # noqa: E402

OUT = yori.OUT / 'hidamari'
SOURCE = OUT / 'assets' / 'HD_Harbor.fbx'
SITE = yori.OUT / 'ferry' / 'terminals' / 'site.json'
TARGET = OUT / 'ferry' / 'HD_Harbor.fbx'
POST = 0.13                   # the rail's posts (build.py harbor(): .13 x .13 x 1.1 boxes)
EPS = 1e-4


def islands(bm):
    """Connected face groups as lists of faces."""
    seen, out = set(), []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, group = [f], []
        seen.add(f.index)
        while stack:
            g = stack.pop(); group.append(g)
            for e in g.edges:
                for h in e.link_faces:
                    if h.index not in seen:
                        seen.add(h.index); stack.append(h)
        out.append(group)
    return out


def box_of(faces):
    vs = {v for f in faces for v in f.verts}
    co = np.array([tuple(v.co) for v in vs])
    return co.min(0), co.max(0)


def in_band(lo, hi, cut):
    return lo[1] >= cut['y'][0] - EPS and hi[1] <= cut['y'][1] + EPS and lo[2] >= cut['z_from'] - EPS


def project_uv(bm, faces):
    uv = bm.loops.layers.uv.active
    if uv is None:
        return
    for f in faces:
        drop = max(range(3), key=lambda i: abs(f.normal[i]))
        axes = [i for i in range(3) if i != drop]
        for loop in f.loops:
            loop[uv].uv = (loop.vert.co[axes[0]], loop.vert.co[axes[1]])


def apply_cut(bm, cut):
    """Opens one cut. Returns what it did."""
    x0, x1 = cut['x']
    c0, c1 = x0 - POST / 2 - 0.001, x1 + POST / 2 + 0.001        # the new rail ends, each inside its new post
    # The region's FBX has separate vertices for each hard-edged face. Restore
    # adjacency only in this rail band before finding solids and filling caps.
    # Coincident vertices move by at most 0.01 mm; other harbour geometry is untouched.
    rail_faces = []
    for face in bm.faces:
        lo, hi = box_of([face])
        if in_band(lo, hi, cut) and hi[0] >= x0 - 2 * POST and lo[0] <= x1 + 2 * POST:
            rail_faces.append(face)
    # Include all split copies of those positions: a beam's original end caps
    # lie outside the opening, but must reconnect to its selected long faces.
    positions = {tuple(v.co) for face in rail_faces for v in face.verts}
    rail = [v for v in bm.verts if tuple(v.co) in positions]
    bmesh.ops.remove_doubles(bm, verts=rail, dist=1e-5)
    bm.faces.ensure_lookup_table(); bm.faces.index_update()
    groups = [(g, *box_of(g)) for g in islands(bm)]
    band = [(g, lo, hi) for g, lo, hi in groups if in_band(lo, hi, cut) and hi[0] >= c0 - POST and lo[0] <= c1 + POST]
    posts = [(g, lo, hi) for g, lo, hi in band if hi[0] - lo[0] < POST + 0.01]
    beams = [(g, lo, hi) for g, lo, hi in band if hi[0] - lo[0] >= POST + 0.01]
    if not posts or not beams:
        raise SystemExit(f'cut {cut["what"]}: no rail posts ({len(posts)}) or beam ({len(beams)}) in its band')
    template = posts[0]
    # A post to copy onto each new end, before the posts in the way go.
    copies = []
    for at in (c0, c1):
        dup = bmesh.ops.duplicate(bm, geom=list(template[0]))
        faces = [e for e in dup['geom'] if isinstance(e, bmesh.types.BMFace)]
        verts = [e for e in dup['geom'] if isinstance(e, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, verts=verts, vec=Vector((at - (template[1][0] + template[2][0]) / 2, 0.0, 0.0)))
        copies.append(faces)
    bmesh.ops.delete(bm, geom=[f for g, _, _ in posts for f in g], context='FACES')
    removed_beam = 0
    for g, lo, hi in beams:
        geom = list({v for f in g for v in f.verts}) + list({e for f in g for e in f.edges}) + list(g)
        for at in (c0, c1):
            if lo[0] < at < hi[0]:
                res = bmesh.ops.bisect_plane(bm, geom=geom, plane_co=(at, 0.0, 0.0), plane_no=(1.0, 0.0, 0.0))
                geom = list({*geom, *res['geom']})
                geom = [e for e in geom if e.is_valid]
        faces = [e for e in geom if isinstance(e, bmesh.types.BMFace) and e.is_valid]
        inside = [f for f in faces if c0 + EPS < f.calc_center_median().x < c1 - EPS]
        removed_beam += len(inside)
        bmesh.ops.delete(bm, geom=inside, context='FACES')
    # Close the beam's new ends: each boundary loop lies in one of the cut planes.
    open_edges = [e for e in bm.edges if e.is_boundary and all(abs(v.co.x - c0) < EPS or abs(v.co.x - c1) < EPS for v in e.verts)]
    filled = bmesh.ops.holes_fill(bm, edges=open_edges, sides=0)['faces'] if open_edges else []
    bmesh.ops.recalc_face_normals(bm, faces=filled)
    for f in filled:      # surviving left/right beams face +X/-X into the opening
        if (f.normal.x > 0) != (f.calc_center_median().x < (c0 + c1) / 2):
            f.normal_flip()
    cap_normals = [{'x': round(f.calc_center_median().x, 4), 'normal_x': round(f.normal.x, 6),
                    'expected_x': 1 if abs(f.calc_center_median().x-c0) < abs(f.calc_center_median().x-c1) else -1}
                   for f in filled]
    caps_pass = bool(cap_normals) and all(c['normal_x'] * c['expected_x'] > .99 for c in cap_normals)
    project_uv(bm, filled + [f for c in copies for f in c])
    return {'what': cut['what'], 'x': cut['x'], 'rail_ends_x': [round(c0, 4), round(c1, 4)], 'posts_removed': len(posts),
            'beam_faces_removed': removed_beam, 'ends_closed': len(filled), 'posts_added': len(copies),
            'cap_normals': cap_normals, 'cap_normals_pass': caps_pass}


def open_cut_edges(bm, cuts):
    """Count real holes in a normalized inspection copy; retain the output's hard-edge vertices."""
    check = bm.copy()
    try:
        vertices = [v for v in check.verts if any(c['x'][0] - 2 <= v.co.x <= c['x'][1] + 2 and
                                                  c['y'][0] - 1 <= v.co.y <= c['y'][1] + 1 for c in cuts)]
        bmesh.ops.remove_doubles(check, verts=vertices, dist=1e-5)
        return sum(e.is_boundary and any(c['x'][0] - 1 <= v.co.x <= c['x'][1] + 1 and
                                        c['y'][0] - .5 <= v.co.y <= c['y'][1] + .5
                                        for c in cuts for v in e.verts) for e in check.edges)
    finally:
        check.free()


def audit_split_rail():
    """A hard-edge FBX-style rail must cut into closed solids with outward caps."""
    bm = bmesh.new()
    try:
        def box(lo, hi):
            corners = [(lo[0], lo[1], lo[2]), (hi[0], lo[1], lo[2]),
                       (hi[0], hi[1], lo[2]), (lo[0], hi[1], lo[2]),
                       (lo[0], lo[1], hi[2]), (hi[0], lo[1], hi[2]),
                       (hi[0], hi[1], hi[2]), (lo[0], hi[1], hi[2])]
            # Each face owns its vertices, as in the actual imported harbour.
            for face in ((3, 2, 1, 0), (4, 5, 6, 7), (0, 1, 5, 4),
                         (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
                bm.faces.new([bm.verts.new(corners[i]) for i in face])
        box((-5, -.045, 3.455), (5, .045, 3.545))
        box((-.065, -.065, 2.45), (.065, .065, 3.55))
        # A neighbouring split solid must retain its original topology/coordinates.
        box((-1, 2, 0), (1, 3, 1))
        # The quay corner contains coincident duplicate posts. Welding the whole
        # Y band would silently remove one, outside this opening's allowed area.
        box((-10, -.065, 2.45), (-9.87, .065, 3.55))
        box((-10, -.065, 2.45), (-9.87, .065, 3.55))
        box((1, -.065, 2.45), (1.13, .065, 3.55))
        untouched = [v for v in bm.verts if v.co.y >= 2 or v.co.x < -9 or 1 <= v.co.x <= 1.13]
        coordinates = [tuple(v.co) for v in untouched]
        cut = {'what': 'split-rail regression', 'x': [-.5, .5], 'y': [-.1, .1], 'z_from': 2.4}
        result = apply_cut(bm, cut)
        assert result['posts_removed'] == 1 and result['posts_added'] == 2
        assert result['ends_closed'] == 2 and result['cap_normals_pass'], result
        assert all(v in untouched for e in bm.edges if e.is_boundary for v in e.verts)
        assert [tuple(v.co) for v in untouched] == coordinates
        assert sum(e.is_boundary for e in bm.edges) == 96
        assert open_cut_edges(bm, [cut]) == 0
        # Inspection must still refuse a real hole after normalizing split vertices.
        cap = next(f for f in bm.faces if abs(f.calc_center_median().x + .566) < EPS and f.normal.x > .99)
        bmesh.ops.delete(bm, geom=[cap], context='FACES_ONLY')
        assert open_cut_edges(bm, [cut]) == 4
        return {'split_rail_closed': True, 'outward_caps': True, 'neighbour_untouched': True,
                'missing_cap_refused': True}
    finally:
        bm.free()


def triangles(obj):
    me = obj.data; me.calc_loop_triangles()
    v = np.array([tuple(p.co) for p in me.vertices]); t = np.array([tuple(lt.vertices) for lt in me.loop_triangles], int)
    return v[t]


def main():
    fixtures = audit_split_rail()
    site = json.loads(SITE.read_text())
    cuts = site['hidamari']['berth']['world_cuts']
    S = load_site()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(SOURCE))
    objs = [o for o in bpy.data.objects if o.type == 'MESH']
    if len(objs) != 1:
        raise SystemExit(f'{SOURCE.name}: expected one mesh object, got {len(objs)}')
    obj = objs[0]
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    before = triangles(obj)
    bm = bmesh.new(); bm.from_mesh(obj.data)
    done = [apply_cut(bm, c) for c in cuts]
    bm.to_mesh(obj.data); bm.free(); obj.data.update()
    after = triangles(obj)
    failures = []
    for c, d in zip(cuts, done):
        if not d['cap_normals_pass']:
            failures.append(f'{c["what"]}: inward or missing new rail caps')
        left = int(S.cut_mask(after, c).sum())
        d['triangles_cut_left'] = left
        d['triangles_cut_before'] = int(S.cut_mask(before, c).sum())
        if left or not d['triangles_cut_before']:
            failures.append(f'{c["what"]}: {left} triangles left of {d["triangles_cut_before"]}')
    # Everything outside the cuts' bands (with a post's margin) is untouched.
    def outside(t):
        keep = np.ones(len(t), bool)
        for c in cuts:
            lo, hi = t.min(1), t.max(1)
            keep &= ~((hi[:, 0] >= c['x'][0] - 2 * POST) & (lo[:, 0] <= c['x'][1] + 2 * POST) & (lo[:, 1] >= c['y'][0] - EPS)
                      & (hi[:, 1] <= c['y'][1] + EPS) & (lo[:, 2] >= c['z_from'] - EPS))
        return t[keep]
    ob, oa = outside(before), outside(after)
    same = len(ob) == len(oa) and np.allclose(np.sort(ob.reshape(-1, 9), 0), np.sort(oa.reshape(-1, 9), 0), atol=1e-4)
    if not same:
        failures.append(f'triangles outside the cuts changed: {len(ob)} before, {len(oa)} after')
    bm = bmesh.new(); bm.from_mesh(obj.data)
    boundary = open_cut_edges(bm, cuts)
    bm.free()
    if boundary:
        failures.append(f'{boundary} open edges where the rail was cut')
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action='DESELECT'); obj.select_set(True)
    obj.name = 'HD_Harbor'
    bpy.ops.export_scene.fbx(filepath=str(TARGET), use_selection=True, apply_unit_scale=True, apply_scale_options='FBX_SCALE_ALL',
                             axis_forward='-Y', axis_up='Z', object_types={'MESH'}, mesh_smooth_type='FACE', bake_anim=False,
                             use_custom_props=False)
    report = {'source': str(SOURCE.relative_to(yori.OUT)), 'site': str(SITE.relative_to(yori.OUT)), 'cuts': done,
              'triangles': {'before': len(before), 'after': len(after)}, 'untouched_outside_cuts': bool(same),
              'failures': failures, 'fixtures': fixtures, 'open_cut_edges': boundary,
              'inputs': {str(p.relative_to(yori.REPO)) if p.is_relative_to(yori.REPO) else p.name:
                         hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__), SOURCE, SITE)},
              'output_sha256': hashlib.sha256(TARGET.read_bytes()).hexdigest()}
    (TARGET.parent / 'cut.json').write_text(json.dumps(report, indent=1) + '\n')
    for f in failures:
        print('FAIL', f)
    print('HIDAMARI FERRY CUT', 'FAIL' if failures else 'PASS', json.dumps(done))
    if failures:
        raise SystemExit(1)


def load_site():
    """site.py's cut_mask, the same test the terminal walk audit ran (site.py stubs bpy only outside Blender)."""
    path = yori.REPO / 'games/yorimichi/assets/vehicles/ferry/terminals/site.py'
    spec = importlib.util.spec_from_file_location('ferry_site', path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


if __name__ == '__main__':
    main()
