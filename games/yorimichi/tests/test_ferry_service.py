"""The single ferry's swept route, clock, boarding windows and stale-product refusal."""
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest

from test_ferry_site import site, world  # noqa: F401 (shared hull fixture)

WORLD = Path(__file__).resolve().parents[1] / 'world'
sys.path.insert(0, str(WORLD))
from regions.ferry import route, service, timetable as TT  # noqa: E402


def closed_cycle():
    outbound, end = TT.voyage((0., 0., 0.), [('departing', [('ahead', 50.)]),
                                           ('cruise', [('ahead', 200.)]), ('approach', [('ahead', 50.)])])
    returning, finish = TT.voyage(end, [('departing', [('pivot', 180.)]),
                                      ('cruise', [('ahead', 300.)]), ('approach', [('pivot', 180.)])])
    assert math.dist(finish[:2], (0., 0.)) < 1e-8
    return TT.Cycle([TT.Dwell((0., 0., 0.), TT.DWELL, 0), *outbound,
                     TT.Dwell(end, TT.DWELL, 1), *returning])


def test_filleted_crossings_join_the_audited_manoeuvre_poses(site):
    berths = {'hidamari': (855., -145., 180.), 'brinecove': (-251.2, 10., 90.)}
    origins = {'hidamari': (0., 0.), 'brinecove': (-1500., -120.)}
    moves = {'hidamari': site.hidamari_moves, 'brinecove': site.brinecove_moves}
    for spec in route.CROSSINGS.values():
        frm, to = spec['from'], spec['to']
        (_, _), (departure, leaving) = moves[frm](berths[frm])
        arrival, _ = moves[to](berths[to])[0]
        end = site.poses(departure, leaving)[-1]
        start = (end[0] + origins[frm][0], end[1] + origins[frm][1], math.degrees(end[2]))
        target = (arrival[0] + origins[to][0], arrival[1] + origins[to][1], arrival[2])
        pose, legs = route.crossing(start, target, spec)
        got = site.poses(pose, legs)[-1]
        assert math.dist(got[:2], target[:2]) < 1e-7
        assert abs((math.degrees(got[2]) - target[2] + 180) % 360 - 180) < 1e-7
        assert 3000 < route.length(legs) < 4000


def test_overlapping_turn_arcs_are_refused():
    with pytest.raises(ValueError, match='overlap'):
        route.fillet([(0, 0), (1, 0), (1, 1), (2, 1)], [5, 5])


def test_one_ship_cycle_has_contiguous_phases_and_stationary_boarding():
    cycle = closed_cycle()
    phases = cycle.phases()
    assert phases[0][0] == 0 and phases[-1][1] == cycle.duration
    assert all(a[1] == b[0] for a, b in zip(phases, phases[1:]))
    for berth, windows in TT.brows(cycle, 2).items():
        for lower, down, raise_, up in windows:
            assert lower < down < raise_ < up
            for time in np.linspace(lower, up, 25):
                state = cycle.state(time)
                assert state['berth'] == berth
                assert state['speed'] == state['vx'] == state['vy'] == 0
    data = service.line(cycle)
    assert len(data['ships']) == 1
    assert abs(data['step_s'] * len(data['samples']) - data['cycle_s']) < 1e-5


def test_runtime_interpolation_wraps_and_tracks_the_sailed_path():
    cycle = closed_cycle()
    step, states = TT.sample(cycle, .2)
    for time in np.linspace(-cycle.duration, cycle.duration * 2, 250):
        expected = cycle.state(time)
        x, y, heading = TT.hermite(states, step, time)
        assert math.dist((x, y), (expected['x'], expected['y'])) < .003
        assert abs((heading - expected['h'] + 180) % 360 - 180) < .01


@pytest.mark.parametrize('fault', ['none', 'solid', 'missing-seabed'])
def test_open_water_sweep_keeps_the_hull_rules_at_batch_boundaries(site, fault):
    solids = [(25., -8., 28., 8., 0)] if fault == 'solid' else ()
    probe = world((-100., -100., 100., 100.), solids=solids)
    if fault == 'missing-seabed':
        probe['ground'] = np.zeros((0, 3, 3))
    result = site.crossing_sweep(probe, (0., 0., 0.), [('ahead', 2.)], batch=3)
    assert result['poses'] == 5
    assert result['pass'] == (fault == 'none')
    if fault == 'solid':
        assert result['conflict_count'] > 0
    elif fault == 'missing-seabed':
        assert result['grounding_count'] > 0


def test_manifest_refuses_changed_code_exports_and_failed_audits(tmp_path):
    code, asset = tmp_path / 'code.py', tmp_path / 'ship.fbx'
    code.write_text('source'); asset.write_bytes(b'mesh')
    data = {'sources': {'code.py': service.sha(code)}, 'files': {'ship.fbx': service.sha(asset)}, 'failures': []}
    service.validate_manifest(data, tmp_path, tmp_path)
    asset.write_bytes(b'stale')
    with pytest.raises(ValueError, match='stale'):
        service.validate_manifest(data, tmp_path, tmp_path)
    asset.write_bytes(b'mesh'); code.write_text('changed')
    with pytest.raises(ValueError, match='stale'):
        service.validate_manifest(data, tmp_path, tmp_path)
    code.write_text('source'); data['failures'] = ['unsupported roof']
    with pytest.raises(ValueError, match='failed'):
        service.validate_manifest(data, tmp_path, tmp_path)


def test_normal_build_includes_the_whole_ferry_pipeline():
    from atelier import build
    from types import SimpleNamespace
    recipe = build.load_recipe('yorimichi')
    rows = {s.name: s for s in recipe.steps(SimpleNamespace(out=Path('/build'), uproject=None))}
    assert {'world.ferry_terminals', 'world.hidamari_ferry_cut'} <= set(rows['world.ferry_service'].needs)
    assert 'world.ferry_service' in rows['data.stage'].needs
    assert 'world.ferry_service' in rows['unreal.ferry'].needs
    assert 'world.hidamari_ferry_cut' in rows['unreal.world'].needs
    world_order = {s.name for s in build.order(list(rows.values()), ['unreal.world'])}
    assert {'world.ferry_probes', 'world.ferry_site', 'world.hidamari_ferry_cut'} <= world_order
    assert 'unreal.ferry' not in world_order
    assert Path('/build/ferry/terminals/assets/FT_HD_Brow.fbx') in rows['world.ferry_terminals'].outputs
    assert all(c.threads == 3 for key, step in rows.items() if 'ferry' in key
               for c in step.commands if isinstance(c, build.Blender))


@pytest.mark.parametrize('batch', [1, 200])
def test_a_clear_ship_cannot_pass_outside_the_exported_probe(site, batch):
    probe = world((-100., -100., 100., 100.))
    # Large triangles beyond the sampled box do not prove that unexported solids are absent.
    probe['ground'] = world((-200., -200., 200., 200.))['ground']
    result = site.crossing_sweep(probe, (80., 0., 0.), [('ahead', 2.)], batch=batch)
    assert not result['pass']
    assert result['probe_boundary_count'] == result['poses']
    assert result['probe_boundary_conflicts']
    assert result['conflict_count'] == result['grounding_count'] == 0


@pytest.mark.parametrize('fault', ['missing', 'checker', 'layout', 'failed', 'no-verdict'])
def test_ship_walk_refuses_missing_stale_and_failed_audit(tmp_path, fault):
    checker = tmp_path / 'walk.py'
    checker.write_text('original walking checker')
    layout = tmp_path / 'deck_layout.json'
    layout.write_text('{"deck": "original"}')
    report_path = tmp_path / 'review/walk_report.json'
    report_path.parent.mkdir()
    report = {'failures': [], 'inputs': {'checker_sha256': service.sha(checker),
                                        'deck_layout_sha256': service.sha(layout)}}
    report_path.write_text(json.dumps(report))
    service.validate_ship_walk(tmp_path, checker)
    if fault == 'missing':
        report_path.unlink()
    elif fault == 'checker':
        checker.write_text('changed walking rule')
    elif fault == 'layout':
        layout.write_text('{"deck": "changed collision"}')
    else:
        if fault == 'failed':
            report['failures'] = ['disconnected boarding route']
        else:
            del report['failures']
        report_path.write_text(json.dumps(report))
    with pytest.raises((ValueError, FileNotFoundError)):
        service.validate_ship_walk(tmp_path, checker)


@pytest.mark.parametrize('field', ['failures', 'meshes', 'seats', 'coplanar', 'carried', 'ship_clash', 'walk', 'audit_fixtures'])
@pytest.mark.parametrize('failed', [False, True])
def test_terminal_audits_refuse_missing_or_failed_proof(field, failed):
    import copy
    terminal = {'meshes': {'deck': {'open_edges': 0, 'flipped_parts': 0}},
                'seats': {'count': 1, 'failures': []}, 'coplanar': {'count': 0},
                'carried': {'groups': 1, 'islands': 1, 'uncarried_groups': 0,
                            'uncarried_islands': 0, 'failures': []},
                'ship_clash': {'pass': True, 'clashes': []}, 'walk': {'pass': True}}
    data = {'failures': [], 'audit_fixtures': [{'ok': True}],
            'terminals': {name: copy.deepcopy(terminal) for name in service.HARBOURS}}
    service.validate_terminal_audits(data)
    target = data if field in ('failures', 'audit_fixtures') else data['terminals']['hidamari']
    if failed:
        target[field] = {'failures':['bad'] ,'meshes':{'deck':{'open_edges':1,'flipped_parts':0}},
                         'seats':{'count':1,'failures':['floating']}, 'coplanar':{'count':1},
                         'carried':{'groups':1,'islands':1,'uncarried_groups':1,'uncarried_islands':1,'failures':[]},
                         'ship_clash':{'pass':False,'clashes':['hull']},'walk':{'pass':False},
                         'audit_fixtures':[{'ok':False}]}[field]
    else:
        del target[field]
    with pytest.raises(ValueError, match='audit'):
        service.validate_terminal_audits(data)


@pytest.mark.parametrize('quay', [1.8, 2.475])
def test_hidamari_landing_waypoints_match_the_two_flight_stair(quay):
    import ast
    from types import SimpleNamespace
    # Execute the production route declaration without Blender mesh generation.
    source = WORLD / 'regions/hidamari/ferry_terminal.py'
    tree = ast.parse(source.read_text())
    assemble = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'assemble')
    declaration = next(n for n in assemble.body if isinstance(n, ast.Assign)
                       and any(isinstance(t, ast.Name) and t.id == 'walk' for t in n.targets))
    scope = dict(dx=820.5, hy0=-122., hz=2.867, gx=839.8, QF=-127.7, quay=quay,
                 foot_y=-129.94, land_y1=-132.36, land_y0=-133.56, gal1=-135.8, gal0=-138.8,
                 face=-138.8, gy=-139.4, st={}, br={}, kit=SimpleNamespace(SILL=6.939))
    exec(compile(ast.Module(body=[declaration], type_ignores=[]), str(source), 'exec'), scope)
    route = service.walk_points(scope['walk']['route'], (0., 0.))
    # Ten lower-flight risers reach a level 1.2 m landing, followed by nine more.
    landing_cm = 100 * (quay + 10 * (6.939 - quay) / 19)
    assert route[6][2] == pytest.approx(landing_cm, abs=.005)
    assert route[7][2] == pytest.approx(landing_cm, abs=.005)
    assert abs(route[6][1] - route[7][1]) == pytest.approx(120.)
    assert list(reversed(route))[6][2] == pytest.approx(landing_cm, abs=.005)
