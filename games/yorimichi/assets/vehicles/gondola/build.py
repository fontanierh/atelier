"""Gondola ropeway pieces: cabin, parametric towers and three station shells. Procedural Blender build.

blender --background --factory-startup --threads 3 --python-exit-code 1 -P games/yorimichi/assets/vehicles/gondola/build.py
Metres, z up. Writes into build/yorimichi/gondola/: one FBX per mesh and one UCX collision FBX per piece under
assets/, a .blend per piece, layout_<piece>.json (walk layouts for walk.py) and manifest.json (parameters, triangle
counts, attachment points and audit results). $GONDOLA_PIECES limits a run to some pieces (comma separated: cabin,
towers, valley, rim, crater); only a full run writes manifest.json.

Every mesh is checked before export, and the build exits non-zero on any failed gate (thresholds and decisions in
checks.py): an open or misoriented edge or a degenerate face, coplanar overlapping faces of different parts
(z-fighting), an unseated fitting, a cabin touching a tower as it passes over the sheaves or a station as it runs
round the loop, a jaw groove off the rope, an intentional rope contact (jaws, sheaves, bullwheel groove) off the rope
radius, unrelated hardware within the rope clearance, a cabin floor off level, a grip wheel or pivot near the rope, a
collision proxy that is not a convex hull, a triangle-budget overrun, or (on a full run) a failed walk audit.
$GONDOLA_SOFT_FAIL=1 lets a review render run on a failing build: the failures are still listed and recorded in the
manifest (soft_fail: true), but the exit code is 0.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402,F401
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import time  # noqa: E402

import bpy  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

import checks  # noqa: E402
import params as P  # noqa: E402
import rope as R  # noqa: E402
import solid  # noqa: E402
import textures  # noqa: E402
from cabin import GRIP, Cabin, pose as cabin_pose  # noqa: E402
from tower import Tower  # noqa: E402

OUT = yori.OUT / 'gondola'
ASSETS = OUT / 'assets'
HERE = _Path(__file__).resolve().parent
BUDGET = checks.BUDGET
TEXTURES = {}
GROOVE_TOL = checks.CONTACT_TOL


def log(*a):
    print(*a, flush=True)


def source_hash():
    return P.source_hash()

def fresh_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return solid.make_materials(TEXTURES)


def groove_check(cab, path, frames):
    """The rope axis to the jaw groove, at every placement: must equal the rope radius within GROOVE_TOL."""
    rr = path.r; worst = 0.0; bad = []
    for label, M, s in frames:
        G = solid.matrix_for(M, 'GD_CabinGrip')          # the jaws belong to the grip, which follows the rope
        for q in cab['cabin'].groove:
            dist = path.nearest_distance(tuple(G @ Vector(q)), near=s)
            err = dist - rr; worst = max(worst, abs(err))
            if abs(err) > GROOVE_TOL:
                bad.append((label, [round(c, 3) for c in q], round(dist, 4)))
    return {'placements': len(frames), 'points_per_placement': len(cab['cabin'].groove), 'rope_radius': rr,
            'max_error_mm': round(worst * 1000, 3), 'tolerance_mm': GROOVE_TOL * 1000, 'failures': bad[:6], 'ok': not bad}


def audit_meshes(meshes):
    """Closed/oriented check per mesh and the coplanar-overlap check across all the piece's meshes."""
    rows = {}
    for name, m in meshes.items():
        rows[name] = solid.closed(m) | {'triangles': m.tris()}
    t0 = time.time()
    n, samples = solid.coplanar_overlaps(list(meshes.values()))
    log(f'  coplanar check: {n} overlaps ({time.time() - t0:.1f} s)')
    for smp in samples:
        log(f'    coplanar {smp["parts"][0][2]} / {smp["parts"][1][2]} at {smp["at"]} ({smp["area_m2"]} m2)')
    return rows, {'count': n, 'samples': samples}


def export_piece(piece, meshes, mats, proxies, sharp=None):
    objs = []
    for name, m in meshes.items():
        obj, names = solid.to_object(m, mats, sharp_degrees=(sharp or {}).get(name, 38))
        objs.append(obj)
        solid.export_fbx([obj], ASSETS / f'{name}.fbx')
    hulls = solid.export_collision(proxies, ASSETS / f'GD_{piece}_Collision.fbx', f'GD_{piece}_Collision')
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / f'{piece.lower()}.blend'))
    return hulls


def bounds(meshes):
    vs = [v for m in meshes.values() for v in m.verts]
    return [[round(min(v[i] for v in vs), 3) for i in range(3)], [round(max(v[i] for v in vs), 3) for i in range(3)]]


def failures_of(rows, cop, seats, extra=()):
    bad = []
    for name, r in rows.items():
        if r['open_edges'] or r['misoriented_edges'] or r['degenerate_faces']:
            bad.append(f'{name}: open {r["open_edges"]}, misoriented {r["misoriented_edges"]}, degenerate {r["degenerate_faces"]}')
    if cop['count']:
        bad.append(f'{cop["count"]} coplanar overlaps, e.g. {cop["samples"][:3]}')
    bs = [s for s in seats if s['status'] != 'ok']
    if bs:
        bad.append(f'{len(bs)} unseated fittings, e.g. {bs[:4]}')
    bad += list(extra)
    return bad


# ------------------------------------------------------------------ pieces
def build_cabin(p, d):
    mats = fresh_scene(); c = Cabin(p, d)
    meshes, door_info = c.build()
    rows, cop = audit_meshes(meshes)
    seats = solid.seats(list(meshes.values()), c.seats)
    proxies = c.proxies()
    tris = sum(m.tris() for m in meshes.values())
    extra = [f'cabin {b}' for b in checks.budget_failures('cabin', tris)] + checks.proxy_failures(proxies)
    grip_clear = checks.grip_clearances(GRIP, p['rope_radius'])
    if not grip_clear['ok']:
        extra.append(f'grip wheel or pivot within {grip_clear["required_m"]} m of the rope axis: {grip_clear}')
    hulls = export_piece('Cabin', meshes, mats, proxies)
    G = d['grip_to_floor']; W = p['cabin_width']
    # Jaw groove on the rope on a level rope, a 40 % grade and a sagging span (rope.py frames, as in the stations).
    span = R.sagging_span(40.0, 4.0, p['rope_radius'])
    tests = {'level': R.straight((-5, 0, 0), (5, 0, 0), p['rope_radius']), 'grade 40%': R.straight((-5, 0, -2), (5, 0, 2), p['rope_radius']),
             'grade 75% (steepest: the crater-floor line in the reviews)': R.straight((-5, 0, -3.75), (5, 0, 3.75), p['rope_radius']),
             'sagging span': span}
    groove = {}
    for name, path in tests.items():
        frames = [(f'{name} s {s_:.1f}', Matrix(path.grip_frame(s_, (0, -1, 0))), s_) for s_ in (path.length * k / 8 for k in range(1, 8))]
        groove[name] = groove_check({'cabin': c}, path, frames)
        if not groove[name]['ok']:
            extra.append(f'jaw groove off the rope ({name}): {groove[name]["failures"]}')
    # Rope clearance on the spans, both directions of travel (the cabin hangs plumb; only the grip pitches).
    cab = {'cabin': c, 'meshes': meshes}; rope_clear = {}; hang = {}; jaw = {}
    for name, path in tests.items():
        poses = []
        for way, out in (('down', (0, -1, 0)), ('up', (0, 1, 0))):
            ks = range(2, 7) if path.length < 20 else range(1, 8)
            poses += [(f'{name}, {way}, s {s_:.1f}', cabin_pose(path.grip_frame(s_, out)), s_) for s_ in (path.length * k / 8 for k in ks)]
        rope_clear[name] = rope_check(cab, path, poses)
        jaw[name] = jaw_contact(cab, path, poses)
        if not rope_clear[name]['ok']:
            extra.append(f'rope within {rope_clear[name]["required_m"]} m of the cabin ({name}): {rope_clear[name]["where"]}')
        if not jaw[name]['ok']:
            extra.append(f'rope not seated in the jaws ({name}): {jaw[name]["failures"]}')
        tilt = max(checks.floor_tilt_deg(Q.C) for _, Q, _ in poses)
        hang[name] = {'grip_pitch_deg': round(max(abs(checks.grip_pitch_deg(Q.G)) for _, Q, _ in poses), 2),
                      'cabin_floor_tilt_deg': round(tilt, 4), 'tolerance_deg': checks.FLOOR_TILT_TOL_DEG,
                      'ok': all(checks.hanging_ok(Q.C) for _, Q, _ in poses)}
        if not hang[name]['ok']:
            extra.append(f'cabin floor tilted {tilt:.3f} deg from level ({name}); it must hang plumb')
    layout = c.layout() | {'proxies': proxies}
    (OUT / 'layout_cabin.json').write_text(json.dumps(layout) + '\n')
    entry = {
        'meshes': rows, 'triangles': tris, 'bounds': bounds(meshes), 'collision': {'file': 'assets/GD_Cabin_Collision.fbx', 'convex_hulls': hulls},
        'frame': 'origin at the grip point on the rope axis; +x along the rope; door on the -y face; z up',
        'placement': ('GD_CabinGrip takes the grip frame (rope.grip_frame: x along the rope tangent); GD_Cabin, GD_CabinHanger '
                      'and the doors take rope.hang_frame(grip frame, grip.pivot.point): the same heading, no pitch or roll, '
                      'the pivot point shared, so the floor stays level on every grade (cabin.pose)'),
        'grip_point': [0.0, 0.0, 0.0], 'hanger_length': p['hanger_length'], 'grip_to_floor': round(G, 3),
        'floor_top_z': round(-G, 3), 'roof_deck_z': round(-p['hanger_length'], 3),
        'door_frame': {'centre': [0.0, round(-W / 2, 3), round(-G, 3)], 'clear_width': p['door_clear_width'], 'clear_height': p['door_clear_height'],
                       'sill_z': round(-G, 3), 'outward': [0, -1, 0], 'leaves': door_info},
        'interior': {'floor_size': [round(p['cabin_length'] - 2 * 0.075, 3), round(W - 2 * 0.075, 3)], 'headroom': 2.08, 'benches': 3, 'seat_height': 0.46},
        'exterior_size': [p['cabin_length'], W, round(p['cabin_floor_to_roof'] + p['cabin_floor_depth'], 3)],
        'grip': c.grip_info | {'jaw_groove_on_rope': groove, 'clear_of_the_rope': grip_clear},
        'rope_clearance': rope_clear, 'rope_in_jaws': jaw, 'hanging': hang,
        'coplanar_overlaps': cop, 'seating': {'checked': len(seats), 'failures': [s for s in seats if s['status'] != 'ok']},
    }
    return entry, failures_of(rows, cop, seats, extra), cab


def cabin_movers(cab):
    return [cab['meshes'][k] for k in ('GD_Cabin', 'GD_CabinHanger', 'GD_CabinGrip', 'GD_CabinDoorLeft', 'GD_CabinDoorRight')]


def part_contacts(meshes, path, poses, tags, expected, reach=0.4, seated=True):
    """Each contact part on its own (solid.rope_contact_parts, signed): its least and greatest per-pose minimum, and
    the per-part gate (checks.part_verdicts)."""
    rows = solid.rope_contact_parts(meshes, path, poses, tags, reach=reach)
    bad = checks.part_verdicts(rows, path.r, expected, seated=seated)
    parts = []
    for r in rows:
        vals = [v for v in r['per_pose'] if v is not None]
        if vals:
            parts.append({'tag': r['tag'], 'part': r['part'], 'mesh': r['mesh'], 'min_signed_m': min(vals), 'max_signed_m': max(vals), 'poses': len(vals)})
    return parts, bad


def jaw_contact(cab, path, poses, seated=True):
    """Intentional contact: the rope axis to each jaw half (seated within checks.CONTACT_TOL at every pose) and the
    clamp body over them (must not cut into the rope), part by part and signed. seated=False: the station's attach
    zone, where the rope ramps down from the jaws; there no part may cut into the rope."""
    parts, bad = part_contacts([cab['meshes']['GD_CabinGrip']], path, poses, ('jaw', 'clamp'), {'jaw': checks.EXPECTED_PARTS['jaw']}, seated=seated)
    halves = [q for q in parts if q['tag'] == 'jaw']
    d = min((q['min_signed_m'] for q in halves), default=None)
    return {'category': checks.INTENTIONAL, 'contact': 'rope seated in each jaw half' if seated else 'rope ramping off the jaws: no part cuts into it',
            'rule': 'seated within the tolerance at every pose' if seated else 'no intrusion', 'min_distance_from_rope_axis_m': d,
            'rope_radius_m': path.r, 'gap_m': None if d is None else round(d - path.r, 4), 'where': {'parts': parts}, 'poses': len(poses),
            'tolerance_m': checks.CONTACT_TOL, 'per_part': parts, 'failures': bad, 'ok': not bad}


def static_rope_check(meshes, path, contact_tags, contact_name, label):
    """The rope against a static piece (tower or station), whole path: each part tagged contact_tags (each sheave, the
    bullwheel groove) is the rope's intentional contact, gated on its own and signed; every other part (the piece's
    own rope mesh aside) must stay rope radius + checks.ROPE_CLEARANCE from the rope axis."""
    I = Matrix.Identity(4); pose = [(label, I, path.length / 2)]; reach = path.length / 2 + 0.05
    parts, bad = part_contacts(meshes, path, pose, contact_tags, {t: checks.EXPECTED_PARTS[t] for t in contact_tags}, reach=None)
    k, _ = solid.rope_clearance(meshes, path, pose, exclude_tags=tuple(contact_tags) + ('rope',), reach=reach)
    need = checks.required_clearance(path.r); dk = k['distance_m']
    dc = min((q['min_signed_m'] for q in parts), default=None)
    return {'intentional': {'category': checks.INTENTIONAL, 'contact': contact_name, 'min_distance_from_rope_axis_m': dc,
                            'rope_radius_m': path.r, 'gap_m': None if dc is None else round(dc - path.r, 4), 'where': {'parts': parts},
                            'tolerance_m': checks.CONTACT_TOL, 'per_part': parts, 'failures': bad, 'ok': not bad},
            'clearance': {'category': checks.UNRELATED, 'min_distance_from_rope_axis_m': dk, 'required_m': round(need, 3),
                          'gap_to_rope_surface_m': None if dk is None else round(dk - path.r, 4), 'where': k, 'poses': 1,
                          'ok': checks.clearance_ok(dk, path.r)}}


def rope_summary(pieces):
    """Every rope-clearance result in the manifest, flattened (check name, minimum, where)."""
    rows = []
    def walk(node, name):
        if isinstance(node, dict):
            if 'min_distance_from_rope_axis_m' in node:
                cat = node.get('category', 'clearance to unrelated hardware (cabin, hanger, grip outside the jaws)')
                rows.append({'check': name, 'category': cat, **{k: node.get(k) for k in ('contact', 'min_distance_from_rope_axis_m', 'required_m',
                             'gap_to_rope_surface_m', 'gap_m', 'where', 'poses', 'failures', 'ok')}})
                return
            for k, v in node.items():
                walk(v, f'{name}/{k}' if name else k)
    walk(pieces, '')
    return rows


def rope_check(cab, path, poses):
    """Rope centreline to the cabin, hanger and grip (jaw zone excluded) over the poses: must be at least the rope
    radius plus checks.ROPE_CLEARANCE everywhere."""
    t0 = time.time()
    best, per_pose = solid.rope_clearance(cabin_movers(cab), path, poses)
    need = checks.required_clearance(path.r); d = best['distance_m']
    return {'min_distance_from_rope_axis_m': d, 'required_m': round(need, 3),
            'gap_to_rope_surface_m': None if d is None else round(d - path.r, 4), 'where': best, 'poses': len(poses),
            'tightest_poses': sorted(per_pose, key=lambda t: t[1])[:3], 'seconds': round(time.time() - t0, 1),
            'excluded': 'grip parts tagged jaw and clamp (where the jaws close on the rope)', 'ok': checks.clearance_ok(d, path.r)}


def build_towers(p, d, cab):
    mats = fresh_scene(); out = {}; bad = []; movers = cabin_movers(cab)
    for H in p['tower_heights']:
        t = Tower(p, H); m = t.build(); meshes = {m.name: m}
        rows, cop = audit_meshes(meshes)
        seats = solid.seats([m], t.seats)
        # The cabin passing over the tower on either rope, door side outward, along the whole sheave train.
        # Placements come from the rope path over the sheave train (rope.over_tower): the grip frame follows the
        # rope's tangent, and the jaw groove must stay on the rope at every one of them.
        g = p['gauge']; places = []; gcs = {}; rcs = {}
        for side, y in (('-g/2', -g / 2), ('+g/2', g / 2)):
            path = R.over_tower(H, y, p['rope_radius'], span=4.0)
            mid = path.length / 2; frames = []
            for k in range(-24, 25):
                s = mid + 0.1 * k; M = cabin_pose(path.grip_frame(s, (0, 1 if y > 0 else -1, 0)))
                frames.append((f'x {0.1 * k:+.1f}, y {side}', M, s))
            places += [(lbl, M) for lbl, M, _ in frames]
            gc = gcs[side] = groove_check(cab, path, frames)
            if not gc['ok']:
                bad.append(f'{m.name}: jaw groove off the rope on {side}: {gc["failures"]}')
            rc = rcs[side] = rope_check(cab, path, frames[::2])
            jc = rcs[side + ' rope in the jaws'] = jaw_contact(cab, path, frames[::2])
            if not jc['ok']:
                bad.append(f'{m.name}: rope not seated in the jaws on {side}: {jc["failures"]}')
            st_ = rcs[side + ' rope and tower'] = static_rope_check([m], path, ('sheave',), 'rope on the sheave grooves', f'tower {side}')
            for part in ('intentional', 'clearance'):
                if not st_[part]['ok']:
                    bad.append(f'{m.name}: rope {part} on {side}: {st_[part].get("failures") or st_[part]["min_distance_from_rope_axis_m"]} at {st_[part]["where"]}')
            if not rc['ok']:
                bad.append(f'{m.name}: rope within {rc["required_m"]} m of the cabin on {side}: {rc["where"]}')
        hits = solid.clearance([m], movers, places)
        env = envelope(p, d, checks.TOWER_BODY_MARGIN)
        env_hits = solid.clearance([m], [env], places)
        tris = m.tris()
        extra = []
        if hits:
            extra.append(f'{m.name}: cabin touches the tower at {hits[:4]}')
        if env_hits:
            extra.append(f'{m.name}: cabin body within 0.3 m of the tower at {env_hits[:4]}')
        extra += [f'{m.name}: {b}' for b in checks.budget_failures('tower', tris)]
        proxies = t.proxies()
        extra += [f'{m.name}: {b}' for b in checks.proxy_failures(proxies)]
        obj, _ = solid.to_object(m, mats); solid.export_fbx([obj], ASSETS / f'{m.name}.fbx')
        hulls = solid.export_collision(proxies, ASSETS / f'{m.name}_Collision.fbx', f'{m.name}_Collision')
        if H != p['review_tower_height']:          # towers.blend keeps the review height only
            bpy.data.objects.remove(obj)
        out[m.name] = {'mesh': rows[m.name], 'triangles': tris, 'bounds': bounds(meshes), **t.attachment(),
                       'collision': {'file': f'assets/{m.name}_Collision.fbx', 'convex_hulls': hulls},
                       'cabin_pass': {'positions': len(places), 'contacts': hits, 'body_within_0.3m': env_hits,
                                      'jaw_groove_on_rope': gcs, 'rope_clearance': rcs},
                       'coplanar_overlaps': cop, 'seating': {'checked': len(seats), 'failures': [s for s in seats if s['status'] != 'ok']}}
        bad += failures_of(rows, cop, seats, extra)
        log(f'  {m.name}: {tris} triangles, {rows[m.name]}, pass contacts {len(hits)}, envelope {len(env_hits)}')
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'towers.blend'))
    return out, bad


def envelope(p, d, margin, top=False):
    """The cabin body's bounding prism grown by margin on every side but the top (the hanger is checked exactly), or
    on the top too (top=True: the stations, where headers pass over the roof)."""
    G = d['grip_to_floor']; m = solid.Mesh('envelope')
    L, W = p['cabin_length'] + 2 * margin, p['cabin_width'] + 2 * margin
    z1 = -p['hanger_length'] + (margin if top else -0.02)
    m.prism(solid.rect(-L / 2, -W / 2, L / 2, W / 2), -G - p['cabin_floor_depth'] - margin, z1, solid.CONCRETE)
    return m


def main():
    t0 = time.time()
    ASSETS.mkdir(parents=True, exist_ok=True)
    p = P.load(); d = P.derived(p)
    TEXTURES.update(textures.generate(OUT / 'textures'))
    log(f'textures: {len(TEXTURES)} maps ({time.time() - t0:.1f} s)')
    wanted = [w.strip() for w in os.environ.get('GONDOLA_PIECES', 'cabin,towers,valley,rim,crater').split(',') if w.strip()]
    log('gondola build:', wanted, 'params', p)
    manifest = {'units': 'metres, z up', 'source_hash': source_hash(), 'parameters': p, 'derived': {k: round(v, 4) for k, v in d.items()},
                'budgets': BUDGET, 'pieces': {}}
    failures = []
    cab_entry, bad, cab = build_cabin(p, d)
    log(f'cabin: {cab_entry["triangles"]} triangles; seats {cab_entry["seating"]}; failures {bad}')
    manifest['pieces']['cabin'] = cab_entry; failures += [f'cabin: {b}' for b in bad]
    if 'towers' in wanted:
        towers, bad = build_towers(p, d, cab)
        manifest['pieces']['towers'] = towers; failures += [f'towers: {b}' for b in bad]
    for key in ('valley', 'rim', 'crater'):
        if key in wanted:
            import stations
            mats = fresh_scene()
            ctx = {'audit': audit_meshes, 'movers': cabin_movers, 'groove': groove_check, 'rope_check': rope_check, 'jaw_contact': jaw_contact,
                   'static_rope': static_rope_check, 'budget': BUDGET, 'bounds': bounds, 'envelope': lambda mg: envelope(p, d, mg, top=True),
                   'failures': failures_of, 'out': OUT, 'export': lambda piece, meshes, proxies, mats=mats: export_piece(piece, meshes, mats, proxies)}
            t1 = time.time()
            entry, bad = stations.build(key, p, d, cab, ctx)
            log(f'station {key}: {entry["triangles"]} triangles, loop contacts {len(entry["cabin_loop"]["contacts"])}, '
                f'seats {entry["seating"]["checked"]} ({len(entry["seating"]["failures"])} failing), {time.time() - t1:.1f} s')
            manifest['pieces'][f'station_{key}'] = entry; failures += [f'station {key}: {b}' for b in bad]
    summary = rope_summary(manifest['pieces'])
    manifest['rope_clearance'] = summary
    manifest['materials'] = solid.MATERIALS
    manifest['textured_materials'] = solid.TEXTURED
    for row in summary:
        w = row['where'] or {}
        if 'parts' in w:                       # intentional contact, part by part (signed minimum over the poses)
            where = ', '.join(f'{q["tag"]} {q["part"]} {q["min_signed_m"]}..{q["max_signed_m"]}' for q in w['parts'])
        else:
            where = f'{w.get("at")} [{w.get("mesh")} {w.get("part")}]'
        log(f'  rope {row["category"]}: {row["check"]}: {row["min_distance_from_rope_axis_m"]} m from the rope axis '
            f'(needs {row["required_m"]}, gap {row["gap_m"]}) at {where} {"ok" if row["ok"] else "FAIL"}')
    bad_rows = [r for r in summary if not r['ok']]
    failures += [f'rope check {r["check"]} ({r["category"]}): {r["min_distance_from_rope_axis_m"]} m at {r["where"]}' for r in bad_rows
                 if not any(r['check'] in f for f in failures)]
    for key, entry in manifest['pieces'].items():
        (OUT / f'piece_{key}.json').write_text(json.dumps(entry, indent=1) + '\n')
    full = set(wanted) >= {'cabin', 'towers', 'valley', 'rim', 'crater'}
    if full:                                   # the walk audit reads the layouts this run has just written
        import walk
        rep, walk_bad = walk.audit(quiet=True)
        manifest['walk'] = {'all_pass': rep['all_pass'], 'report': 'review/walk_report.json', 'rules': rep['rules']}
        log(f'walk audit: {"PASS" if not walk_bad else "FAIL"} ({len(walk_bad)} failures)')
        failures += [f'walk: {w}' for w in walk_bad]
    manifest['failures'] = failures
    manifest['soft_fail'] = bool(os.environ.get('GONDOLA_SOFT_FAIL'))
    manifest['build_seconds'] = round(time.time() - t0, 1)
    if full:
        (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    log('GONDOLA BUILD', 'FAILED' if failures else 'COMPLETE', f'{time.time() - t0:.0f} s', 'manifest written' if full else 'partial run, manifest not written')
    for f in failures:
        log('FAIL', f)
    if failures and not os.environ.get('GONDOLA_SOFT_FAIL'):     # review runs may render a failing build
        raise SystemExit(1)


if __name__ == '__main__':
    main()
