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


def test_atomic_ship_preserves_original_runtime_component_order_through_sorted_json():
    order = ['FY_Hull', 'FY_Superstructure', 'FY_Funnel', 'FY_Lifeboats', 'FY_Rails', 'FY_Masts', 'FY_Fittings', 'FY_BoardingGate']
    original = dict(dimensions=dict(min=[-40., -6., -2.6], max=[40., 6., 25.]), boarding_openings=[],
                    meshes={key: {} for key in order})
    atomic = dict(original, meshes={key: dict(logical_parent=key) for key in sorted(order)}, mesh_order=order,
                  logical_meshes=original['meshes'])
    assert service.ship_data(original) == service.ship_data(atomic)
    del atomic['mesh_order']
    with pytest.raises(ValueError, match='order'): service.ship_data(atomic)


def test_atomic_terminal_preserves_original_runtime_component_order():
    order = ['FT_BC_Landing', 'FT_BC_Brow', 'FT_BC_Pavilion', 'FT_BC_TicketHut', 'FT_BC_Fenders', 'FT_BC_Props']
    original = dict(meshes={key: {} for key in order}, anchor=[-244.5, 25., 0.],
        brow=dict(**{'from': [-244.5, 25., 6.9], 'to': [-245.1, 25., 6.9]}),
        board=dict(position=[-230., 40., 7.], yaw=180., text_size_m=.09))
    atomic = dict(original, meshes={key: dict(logical_parent=key) for key in sorted(order)}, mesh_order=order)
    walks = dict(brinecove=dict(route=[[-235., 45., 5.2], [-235., 40., 5.2]]))
    expected = service.terminal_data('brinecove', 1, dict(terminals=dict(brinecove=original)), walks, (0., 0.))
    actual = service.terminal_data('brinecove', 1, dict(terminals=dict(brinecove=atomic)), walks, (0., 0.))
    assert actual == expected


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
    assert Path('/build/ferry/terminals/atomic-assets') in rows['world.ferry_terminals'].products[0].paths
    assert 'ferry_terminals.source.FT_HD_Brow' in rows['world.ferry_terminals.geometry.FT_HD_Brow'].reads
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


@pytest.mark.parametrize('fault', ['missing', 'checker', 'raster', 'layout', 'failed', 'no-verdict'])
def test_ship_walk_refuses_missing_stale_and_failed_audit(tmp_path, fault):
    checker = tmp_path / 'walk.py'
    checker.write_text('original walking checker')
    raster=tmp_path/'walk_raster.py'
    raster.write_text('original raster core')
    layout = tmp_path / 'deck_layout.json'
    layout.write_text('{"deck": "original"}')
    report_path = tmp_path / 'review/walk_report.json'
    report_path.parent.mkdir()
    report = {'failures': [], 'inputs': {'checker_sha256': service.sha(checker), 'raster_sha256':service.sha(raster),
                                        'deck_layout_sha256': service.sha(layout)}}
    report_path.write_text(json.dumps(report))
    service.validate_ship_walk(tmp_path, checker, raster)
    if fault == 'missing':
        report_path.unlink()
    elif fault == 'checker':
        checker.write_text('changed walking rule')
    elif fault == 'raster':
        raster.write_text('changed capsule raster')
    elif fault == 'layout':
        layout.write_text('{"deck": "changed collision"}')
    else:
        if fault == 'failed':
            report['failures'] = ['disconnected boarding route']
        else:
            del report['failures']
        report_path.write_text(json.dumps(report))
    with pytest.raises((ValueError, FileNotFoundError)):
        service.validate_ship_walk(tmp_path, checker, raster)


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
    assemble = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'walk_plan')
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


def test_harbour_and_sea_paths_obey_natural_motion_constraints(site):
    """Pin the natural boat-motion rules for Hidamari, Brinecove and both sea crossings."""
    hull_length = 80.0
    berths = {'hidamari': (855., -145., 180.), 'brinecove': (-251.2, 10., 90.)}
    origins = {'hidamari': (0., 0.), 'brinecove': (-1500., -120.)}
    move_fns = {'hidamari': site.hidamari_moves, 'brinecove': site.brinecove_moves}
    harbours = {}
    for name, fn in move_fns.items():
        (arr_start, arr_moves), (dep_start, dep_moves) = fn(berths[name])
        arr_end = site.poses(arr_start, arr_moves)[-1]
        dep_end = site.poses(dep_start, dep_moves)[-1]
        harbours[name] = {
            'origin_m': list(origins[name]),
            'arrival': {'start': list(arr_start), 'moves': arr_moves,
                        'end': [arr_end[0], arr_end[1], math.degrees(arr_end[2])]},
            'departure': {'start': list(dep_start), 'moves': dep_moves,
                          'end': [dep_end[0], dep_end[1], math.degrees(dep_end[2])]},
        }
        # No pivoting in place or pure sideways moves; final approach is >= 15 m straight and aligned.
        for mv in arr_moves + dep_moves:
            assert mv[0] in ('ahead', 'arc', 'berth')
            if mv[0] == 'berth':
                assert len(mv) == 3 and abs(mv[1]) >= 15.0
            if mv[0] == 'arc':
                assert abs(mv[1]) >= hull_length
        assert arr_moves[-1][0] == 'berth' and arr_moves[-1][1] >= 15.0
        # Astern portion is <= 1.5 hull lengths (120 m) and includes a curved arc.
        astern_legs = [mv for mv in dep_moves if mv[1] < 0]
        astern_len = route.length(astern_legs)
        assert 0.0 < astern_len <= 1.5 * hull_length
        assert any(mv[0] == 'arc' for mv in astern_legs)

    crossings = {}
    for cname, spec in route.CROSSINGS.items():
        frm, to = spec['from'], spec['to']
        oa, ob = origins[frm], origins[to]
        de = harbours[frm]['departure']['end']
        as_ = harbours[to]['arrival']['start']
        start = (de[0] + oa[0], de[1] + oa[1], de[2])
        end = (as_[0] + ob[0], as_[1] + ob[1], as_[2])
        pose, c_moves = route.crossing(start, end, spec)
        for mv in c_moves:
            if mv[0] == 'arc':
                assert abs(mv[1]) >= 3.0 * hull_length
        crossings[cname] = {'start': list(pose), 'moves': c_moves, 'end': list(end), 'pass': True}

    cycle = service.cycle_from({**harbours, 'crossings': crossings})
    _, states = TT.sample(cycle, 0.25)
    prev_long = 0.0
    stopped_since_astern = True
    for s in states:
        h_rad = math.radians(s['h'])
        v_long = s['vx'] * math.cos(h_rad) + s['vy'] * math.sin(h_rad)
        v_lat = -s['vx'] * math.sin(h_rad) + s['vy'] * math.cos(h_rad)
        # Yaw rate <= 3 deg/s everywhere, and no yaw while |speed| < 0.5 m/s.
        assert abs(s['w']) <= 3.0 + 1e-6
        if abs(s['speed']) < 0.5:
            assert abs(s['w']) == pytest.approx(0.0, abs=1e-6)
        # Lateral (crab) speed <= 0.3 m/s everywhere (and <= 0.5 m/s in the last 10 m).
        assert abs(v_lat) <= 0.3 + 1e-6
        # Harbour speed <= 2.0 m/s; astern speed <= 1.5 m/s.
        if s['phase'] in ('departing', 'approach'):
            assert s['speed'] <= 2.0 + 1e-6
        if v_long < -1e-6:
            assert abs(v_long) <= 1.5 + 1e-6
            stopped_since_astern = False
        if s['speed'] == 0.0 and s['w'] == 0.0:
            stopped_since_astern = True
        if v_long > 1e-6 and prev_long < -1e-6:
            assert stopped_since_astern
        if abs(v_long) > 1e-6:
            prev_long = v_long
