"""Crater Park v2 geometry step (world.craterpark_geometry): compile the layout, split it, write the arrays export.py
turns into FBX (plan/pipeline.md 2.2, 10). Pure numpy, no Blender.

The layout is v2/layout_line1.py when it exists, else the M0 smoke layout (layout_m0.py); `--layout NAME` overrides.
Writes OUT/v2/geometry.npz, OUT/v2/geometry-report.json and one OUT/v2/lines/<name>.npz per designed line.
"""
import argparse
import hashlib
import importlib
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))        # world/regions: the craterpark package
sys.path.insert(0, str(HERE.parents[2]))        # world: yori

import numpy as np  # noqa: E402

from craterpark.v2 import dsl, split  # noqa: E402


def default_layout():
    """D's park (v2/layout.py) once it defines park(); else the M0 smoke layout."""
    text = (HERE / 'layout.py').read_text() if (HERE / 'layout.py').exists() else ''
    return 'layout' if '\ndef park(' in text else 'layout_m0'


def compile_park(layout):
    module = importlib.import_module(f'craterpark.v2.{layout}')
    park = module.park()
    if not isinstance(park, dsl.Park):
        raise TypeError(f'{layout}.park() must return a dsl.Park')
    return park, module


def line_spawns(park, module):
    """park.json `lines` (spawns.entries): each line's start, ground-checked on the collidable mesh; a layout's
    SPAWN_DECK_Y (default the tower deck) is the deck every start must stand on (None: no deck rule)."""
    if not park.lines:
        return []
    from craterpark import placement
    from craterpark.v2 import spawns
    deck_y = getattr(module, 'SPAWN_DECK_Y', spawns.TOWER_DECK_Y)
    return spawns.entries(park.mesh, park.lines, placement, deck_y=deck_y, labels=getattr(module, 'LINE_LABELS', None))


SAFETY = ('topology', 'topology_collision', 'buried', 'overlaps', 'overlaps_collision', 'thin_walls', 'plan_width',
          'protrusions', 'airs', 'terrain', 'budgets', 'ownership', 'dressing')
COSMETIC = ('outlines', 'facets', 'uv_stretch', 'slivers')
PREVIEW = 'PREVIEW'     # a file of this name in the output folder (build/yorimichi/craterpark/v2) opts into a preview


def run_validators(park, out):
    """validate.validate_park(park, path) -> (report, ok); a failed check fails the step. Preview gate: when only
    COSMETIC checks fail and out/PREVIEW exists, the step passes with validation.json {ok: false, preview: true} (for
    screenshots, never for a release: packaging requires ok true). Any SAFETY (or unclassified) failure still fails."""
    try:
        from craterpark.v2 import validate
    except ImportError:
        return {'ran': False}
    if not hasattr(validate, 'validate_park'):
        return {'ran': False, 'why': 'validate.validate_park not defined yet'}
    path = out / 'validation.json'
    report, ok = validate.validate_park(park, path)
    if ok:
        return {'ran': True, 'ok': True}
    failed = sorted(k for k, v in report.get('checks', {}).items() if isinstance(v, dict) and not v.get('ok', True))
    cosmetic_only = bool(failed) and all(k in COSMETIC for k in failed)
    if cosmetic_only and (out / PREVIEW).exists():
        report.update(ok=False, preview=True, cosmetic_failures=failed)
        path.write_text(json.dumps(report, indent=1, default=str) + '\n')
        n = sum(int(report['checks'][k].get('bad_faces', report['checks'][k].get('faceted_edges',
                report['checks'][k].get('zigzag_points', 1)))) for k in failed)
        print('!' * 78 + f'\nPREVIEW BUILD: {n} cosmetic failures in {", ".join(failed)} (validation.json ok: false)\n'
              + '!' * 78, flush=True)
        return {'ran': True, 'ok': False, 'preview': True, 'failed': failed}
    raise SystemExit(f'Crater Park v2 validation failed ({", ".join(failed) or "?"}): see {path}'
                     + ('' if not cosmetic_only else f' (only cosmetic: create {out / PREVIEW} for a preview build)'))


def declare_scenery(park):
    """A feature made only of ground, side and base faces with ground among them (ground.ground's landform) is
    scenery, not a useless block: declare it for validate's ownership check unless the layout already did."""
    m = park.mesh
    declared = {c.get('feature') for c in park.checks if isinstance(c, dict) and c.get('kind') == 'scenery'}
    plain = {dsl.ROLE[dsl.GROUND], dsl.ROLE[dsl.SIDE], dsl.ROLE[dsl.BASE]}
    for i, name in enumerate(m.features):
        roles = set(np.unique(m.role[m.feature == i]).tolist())
        if name not in declared and dsl.ROLE[dsl.GROUND] in roles and roles <= plain:
            park.checks.append({'kind': 'scenery', 'feature': name})


def bundle(park, lines=(), trees=None):
    """The arrays geometry.npz holds: render meshes r<i>_*, collision sections c<i>, rails rail<i>, and a JSON index
    (with park.json's `lines` entries)."""
    arrays, index = {}, {'render': [], 'collision': [], 'rails': [], 'lines': list(lines), 'trees': trees or {}}
    folded = 0
    for i, (name, role, mesh) in enumerate(split.render_meshes(park.mesh)):
        # no degenerate face may reach the importer's triangle check (build.py FOLDED)
        area2 = 2 * mesh.areas()
        t = mesh.triangles()
        # Unreal's FBX reader welds points under about 1e-5 cm apart: an edge under 0.1 mm would lose its face
        bad = (area2 <= 2e-7) | (np.linalg.norm(t - np.roll(t, 1, 1), axis=2).min(1) < 1e-4)
        if bad.any():
            folded += int(bad.sum()); mesh = mesh.subset(~bad)
        arrays.update(mesh.to_arrays(f'r{i}_'))
        index['render'].append({'name': name, 'role': role, 'materials': [dsl.MATERIALS[int(m)] for m in
                                                                          np.unique(mesh.material)],
                                'features': list(mesh.features)})
    for i, (name, role, t) in enumerate(split.collision_sections(park.mesh)):
        a = t[:, 1] - t[:, 0]; b = t[:, 2] - t[:, 0]
        ok = (np.linalg.norm(np.cross(a, b), axis=1) > 2e-7) & (np.linalg.norm(t - np.roll(t, 1, 1), axis=2).min(1) >= 1e-4)
        folded += int((~ok).sum())
        arrays[f'c{i}'] = t[ok]
        index['collision'].append({'name': name, 'role': role})
    for i, rail in enumerate(park.rails):
        arrays[f'rail{i}'] = rail.points
        index['rails'].append({'closed': bool(rail.closed), 'feature': rail.feature})
    index['folded_left_out'] = folded
    arrays['index'] = np.asarray(json.dumps(index))
    return arrays, index


def report(park, index, seconds):
    m = park.mesh
    roles = {r: int((m.role == dsl.ROLE[r]).sum()) for r in dsl.ROLES}
    return {'features': list(m.features), 'faces': int(len(m.F)), 'faces_by_role': roles,
            'render_meshes': len(index['render']), 'collision_sections': len(index['collision']),
            'render_triangles': int(sum((m.role == dsl.ROLE[r]).sum() for r in dsl.RENDER_ROLE)),
            'collision_triangles': int(sum((m.role == dsl.ROLE[r]).sum() for r in dsl.COLLISION_ROLE)),
            'rails': len(park.rails), 'lines': [ln.name for ln in park.lines], 'checks': park.checks,
            'folded_left_out': index['folded_left_out'], 'seconds': round(seconds, 2)}


def ground_spots(m, limit=30.):
    """ground.steep_spots for the park's ground, each with the nearest other feature and its plan gap: the places
    where fixed heights force ground steeper than `limit` (a foot too near a much lower edge or foot)."""
    from craterpark.v2 import ground
    spots = ground.steep_spots(m, limit=limit)
    other = np.flatnonzero(m.role != dsl.ROLE[dsl.GROUND])
    other = other[np.isin(m.role[other], [dsl.ROLE[r] for r in (dsl.RIDING, dsl.SIDE, dsl.COPING)])]
    if not len(other):
        return spots
    C = m.triangles()[other].mean(1)
    for s in spots:
        d = np.linalg.norm(C[:, [0, 2]] - np.asarray(s['where'])[[0, 2]], axis=1); k = int(np.argmin(d))
        s['near'] = m.features[int(m.feature[other[k]])]; s['gap_m'] = round(float(d[k]), 1)
    return spots


def main(argv=None):
    import yori
    parser = argparse.ArgumentParser()
    parser.add_argument('--layout', default=None)
    parser.add_argument('--out', default=str(yori.OUT / 'craterpark' / 'v2'))
    args = parser.parse_args(argv)
    start = time.time()
    layout = args.layout or default_layout()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    park, module = compile_park(layout)
    declare_scenery(park)
    lines = line_spawns(park, module)
    from craterpark import placement
    from craterpark.v2 import dressing
    dressing.check(park.mesh, placement)          # every drawn face on the block, riding clear of the island's dressing
    trees = dressing.plant(park.mesh, airs=park.checks)
    from craterpark.v2 import ao
    ao.bake_mesh(park.mesh, drawn=(dsl.RIDING, dsl.SIDE, dsl.GROUND, dsl.COPING, dsl.RAIL))
    validation = run_validators(park, out)
    arrays, index = bundle(park, lines, trees)
    np.savez(out / 'geometry.npz', **arrays)
    from craterpark.v2 import export
    (out / 'lines').mkdir(exist_ok=True)
    for line in park.lines:
        export.line_npz(park.mesh, line, out / 'lines' / f'{line.name}.npz')
    rep = report(park, index, time.time() - start)
    rep['layout'] = layout
    rep['validation'] = validation
    rep['ground_steep_spots'] = ground_spots(park.mesh)
    for s in rep['ground_steep_spots'][:8]:
        print('ground over 30 deg:', s, flush=True)
    rep['geometry_sha256'] = hashlib.sha256((out / 'geometry.npz').read_bytes()).hexdigest()
    (out / 'geometry-report.json').write_text(json.dumps(rep, indent=1) + '\n')
    print('CRATERPARK V2 GEOMETRY COMPLETE', layout, rep['render_triangles'], 'render',
          rep['collision_triangles'], 'collision', flush=True)


if __name__ == '__main__':
    main()
