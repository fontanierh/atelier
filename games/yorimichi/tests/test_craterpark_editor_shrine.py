"""The start tower's shrine balcony (concept C): textured Tripo models on a balcony off the deck's back edge, clear of
the deck, every run-in and every other piece's riding surfaces; drawn only, with their own textures."""
import json
from pathlib import Path
import shutil
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'world' / 'regions'))
from craterpark.v2 import dsl, editor_supports as es, shrine  # noqa: E402
from test_craterpark_editor_supports import FLAT, GRID, box_deck, sheet  # noqa: E402

GAME = Path(__file__).resolve().parents[1]
APP = GAME / 'tools' / 'craterpark_editor'


def tower_with_drop_in():
    """The supports test's tower: a 16 x 22 m deck 60 m up, a roll-in leaving its +x side (so the back is -x)."""
    ramp = sheet('ramp', 60., length=60., z0=0., x0=0.)
    ramp.metadata['type'] = 'rollin'
    for st in ramp.metadata['stations']:
        st['x'] += 8.
    ramp.mesh.V[:, 0] += 8.
    return [box_deck('t', 60.), ramp]


def frame(piece):
    c, fwd, acr, a, w, top = es._rect(np.asarray(piece.mesh.V, 'f8'))
    return c, fwd, acr, a, w, top


def clearance(pieces, k, parts, info):
    """Independently of the build: every shrine model vertex's plan distance to the nearest point of any other piece's
    faces near the shrine's height, to the run-ins, and whether any other piece lies under the balcony."""
    c, fwd, acr, a, w, top = frame(pieces[k])
    model = np.concatenate([p.V for p in parts])
    y0, y1 = info['floor_y'] - es.SHRINE_BELOW, info['top_y'] + 1.
    plan = es.Plan(pieces)
    near = es._surface_points(plan, k, model[:, [0, 2]].mean(0), 80., y0, y1, step=.2)
    def nearest(P, Q, reach=10.):          # min plan distance from P to Q, or `reach` if nothing is that near
        Q = Q[((Q >= P.min(0) - reach) & (Q <= P.max(0) + reach)).all(1)]
        if not len(Q) or not len(P):
            return reach
        best_sq = reach * reach
        qx, qy = Q[:, 0], Q[:, 1]
        for i in range(0, len(P), 256):
            chunk = P[i:i + 256]
            dx = chunk[:, 0, None] - qx[None, :]
            dy = chunk[:, 1, None] - qy[None, :]
            best_sq = min(best_sq, float((dx * dx + dy * dy).min()))
        return float(np.sqrt(best_sq))
    sub = model[::7, [0, 2]]
    runs = [a + f * (e - a) for a, e in es._runways(pieces[k], pieces, k) for f in np.linspace(0, 1, 49)]
    u0, u1, v0, v1 = info['rect_uv']
    under = [plan.heights(*(c + u * n_ + v * t_)) for u in np.linspace(u0, u1, 13) for v in np.linspace(v0, v1, 13)
             for n_, t_ in [(info['n'], info['t'])]]
    return (nearest(sub, near), nearest(sub, np.array(runs).reshape(-1, 2)),
            sum(int(((who != k) & (y < y1)).sum()) for who, y in under))


def shrine_of(parts, summary, tower_id):
    info = dict(summary['shrines'][tower_id])
    return [p for p in parts if p.features[0] == f'{tower_id}_shrine'], info


def test_models_fit_their_sizes_and_turn_without_mirroring():
    for slug, (material, size, measure) in shrine.MODELS.items():
        V, N, UV, F = shrine.model(slug)
        ext = V.max(0) - V.min(0)
        assert abs((ext[1] if measure == 'height' else max(ext[0], ext[2])) - size) < 1e-6, slug
        assert abs(V[:, 1].min()) < 1e-9 and np.isfinite(UV).all() and F.max() < len(V)
    V, F, N, UV, material = shrine.place('torii', (10., 2., 5.), (0., 1.))
    ext = V.max(0) - V.min(0)
    assert ext[0] > 4. * ext[2], 'the torii faces +z, so it spans x'
    assert abs(V[:, 1].min() - 2.) < 1e-9 and material == 'material_048'
    # a rotation, never a mirror: the faces keep their winding against their normals
    V0, N0, _, F0 = shrine.model('torii')
    for facing in ((1., 0.), (0., 1.), (-.6, .8)):
        V1, F1, N1, _, _ = shrine.place('torii', (0., 0., 0.), facing)
        a0 = np.cross(V0[F0[:, 1]] - V0[F0[:, 0]], V0[F0[:, 2]] - V0[F0[:, 0]])
        a1 = np.cross(V1[F1[:, 1]] - V1[F1[:, 0]], V1[F1[:, 2]] - V1[F1[:, 0]])
        assert np.sign((a0 * N0[F0[:, 0]]).sum(1)).sum() == np.sign((a1 * N1[F1[:, 0]]).sum(1)).sum()


def test_the_shrine_materials_follow_the_steel_and_carry_their_own_textures():
    assert dsl.MATERIALS.index('coping_steel') == 46, 'older material indices never move'
    specs = {m['id']: m for m in json.loads((GAME / 'assets' / 'craterpark' / 'materials.json').read_text())}
    for slug, (material, _, _) in shrine.MODELS.items():
        assert material in dsl.MATERIALS and specs[material]['texture'] == f'shrine/{slug}/{slug}.glb'
        assert shrine.texture(slug)[:3] == b'\xff\xd8\xff', 'a JPEG base colour'
        record = json.loads((shrine.SOURCE / slug / 'job.json').read_text())
        assert record['settings']['texture_quality'] == 'detailed' and record['task_id']


def test_the_tower_shrine_stands_off_the_back_edge_drawn_only():
    pieces = tower_with_drop_in()
    parts, summary = es.build(pieces, FLAT, GRID)
    models, info = shrine_of(parts, summary, 't')
    assert {dsl.MATERIALS[p.material[0]] for p in models} == set(shrine.MATERIALS)
    assert all((p.role == dsl.ROLE[dsl.COPING]).all() for p in models), 'drawn only: no collision'
    V = np.concatenate([p.V for p in models])
    u0, u1, v0, v1 = info['rect_uv']
    # the back is -x (the roll-in leaves +x): everything beyond the deck and its rim, inside the balcony
    assert V[:, 0].max() < -(8. + es.RIM) + 1e-6 and V[:, 0].min() > -(8. + es.RIM + es.SHRINE_DEPTH) - 1e-6
    assert info['deck_gap_m'] == es.RIM and info['models'] >= 5 and info['posts'] >= 2
    assert abs(V[:, 1].min() - info['floor_y']) < 1e-6, 'standing on its floor'
    assert info['runin_m'] >= es.RUNWAY_CLEAR
    tower = np.concatenate([p.V for p in parts if p.features[0] == 't_tower'])
    assert tower[:, 1].min() < 0., 'its posts reach the ground'


def test_the_balcony_narrows_clear_of_a_piece_beside_it():
    pieces = tower_with_drop_in() + [sheet('beside', 60., length=14., width=8., x0=-26., z0=-16.)]
    parts, summary = es.build(pieces, FLAT, GRID)
    models, info = shrine_of(parts, summary, 't')
    assert info['clear_m'] >= es.SHRINE_CLEAR
    lo, hi = pieces[-1].mesh.V[:, [0, 2]].min(0), pieces[-1].mesh.V[:, [0, 2]].max(0)     # a flat rectangle
    P = np.concatenate([p.V for p in models])[:, [0, 2]]
    gap = np.hypot(*np.maximum(np.maximum(lo - P, P - hi), 0.).T).min()
    assert gap >= es.SHRINE_CLEAR - 1e-6, gap
    assert info['rect_uv'][3] - info['rect_uv'][2] < 2 * (11. + es.RIM), 'it narrowed'


@pytest.fixture(scope='module')
def shipped(tmp_path_factory):
    """The shipped editor park's lines, compiled by the pinned editor compiler as the build does."""
    if shutil.which('node') is None:
        pytest.skip('editor compiler needs Node.js')
    from craterpark.v2 import editor_generate as eg, v4_config
    from craterpark.v2.editor import frontend
    tmp = tmp_path_factory.mktemp('shrine')
    doc = json.loads((APP / 'shipped.json').read_text())
    chosen = eg.select(doc, set(v4_config.SHIPPED_LINES.split(',')))
    (tmp / 'src').mkdir()
    (tmp / 'src' / 'park.json').write_text(json.dumps(chosen))
    snap = frontend.snapshot(tmp / 'src' / 'park.json', tmp / 'snap', terrain_dir=APP / 'data')
    scene = frontend.compile_snapshot(snap, tmp / 'mesh')
    scene.metadata['_dir'] = str(tmp / 'mesh')
    params = {p['id']: p.get('params') or {} for p in chosen['pieces']}
    for piece in scene.pieces:
        piece.metadata['params'] = params.get(piece.metadata['id'], {})
    terrain = json.loads((APP / 'data' / 'terrain.json').read_text())['inner']
    base = np.fromfile(APP / 'data' / terrain['layers'][doc['terrain']], '<f4')
    heights, _ = eg.ground_grid(scene, np.concatenate([p.mesh.V for p in scene.pieces]),
                                base.reshape(terrain['nz'], terrain['nx']).astype('f8'))
    grid = {k: scene.metadata['ground_grid'][k] for k in ('x0', 'z0', 'G', 'nx', 'nz')}
    parts, summary = es.build(scene.pieces, heights, grid)
    return scene.pieces, parts, summary


def test_the_shipped_tower_shrine_is_clear_of_the_deck_every_run_in_and_every_ride(shipped):
    pieces, parts, summary = shipped
    assert summary['shrines'], 'the shipped start tower has its shrine'
    for tower_id, info in summary['shrines'].items():
        k = next(i for i, p in enumerate(pieces) if p.metadata['id'] == tower_id)
        models, info = shrine_of(parts, summary, tower_id)
        c, fwd, acr, a, w, top = frame(pieces[k])
        V = np.concatenate([p.V for p in models])
        P = V[:, [0, 2]] - c
        uv = np.stack([P @ fwd, P @ acr], 1)
        # its side (n) is whichever of +-fwd, +-acr the balcony lies beyond
        back = max(((fwd, acr, a), (-fwd, acr, a), (acr, fwd, w), (-acr, fwd, w)),
                   key=lambda s: float((P @ s[0]).min() - s[2]))
        info['n'], info['t'] = back[0], back[1]
        assert (P @ back[0]).min() >= back[2] + es.RIM - 1e-6, 'nothing over the deck or its rim'
        assert not ((np.abs(uv[:, 0]) <= a) & (np.abs(uv[:, 1]) <= w)).any()
        near, runin, under = clearance(pieces, k, models, info)
        print(f'{tower_id}: shrine clear of other pieces by {near:.2f} m, of run-ins by {runin:.2f} m, '
              f'{under} faces under it; build says {info}')
        assert near >= es.SHRINE_CLEAR - .05 and runin >= es.RUNWAY_CLEAR and under == 0
        assert info['clear_m'] >= es.SHRINE_CLEAR and info['runin_m'] >= es.RUNWAY_CLEAR
        assert {dsl.MATERIALS[p.material[0]] for p in models} == set(shrine.MATERIALS)
