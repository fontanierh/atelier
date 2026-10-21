"""Ferry berth sweep, terminal fit and deck-walk gates, on small fixtures: no Blender and no world build."""
import ast
import importlib.util
import json
import math
import re
import sys
from pathlib import Path
from unittest import mock

import numpy as np
import pytest

GAME = Path(__file__).resolve().parents[1]
FERRY = GAME / 'assets/vehicles/ferry'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); sys.modules[name] = mod; spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope='module')
def site():
    """terminals/site.py with bpy/mathutils stubbed only while it loads the ship's hull lines."""
    with mock.patch.dict(sys.modules):
        for name in ('bpy', 'mathutils', 'ferry_build', 'ferry_site'):
            sys.modules.pop(name, None)
        yield _load('ferry_site', FERRY / 'terminals/site.py')


@pytest.fixture(scope='module')
def walk():
    with mock.patch.dict(sys.modules):
        yield _load('ferry_walk', FERRY / 'walk.py')


def constants(path):
    """Module-level literal constants of a file that needs Blender to import."""
    out = {}
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.Assign):
            try:
                value = ast.literal_eval(node.value)
            except ValueError:
                continue
            for target in node.targets:
                names = target.elts if isinstance(target, ast.Tuple) else [target]
                values = value if isinstance(target, ast.Tuple) else [value]
                for n, v in zip(names, values):
                    if isinstance(n, ast.Name):
                        out[n.id] = v
    return out


def world(bounds, seabed=-10.0, solids=(), labels=('fixture',)):
    """A world probe fixture: flat seabed (two triangles) and solids given as plan boxes (x0, y0, x1, y1, label)."""
    x0, y0, x1, y1 = bounds
    ground = np.array([[[x0, y0, seabed], [x1, y0, seabed], [x1, y1, seabed]],
                       [[x0, y0, seabed], [x1, y1, seabed], [x0, y1, seabed]]], float)
    tris, lab = [], []
    for a, b, c, d, k in solids:
        for z in (0.0, 2.0):                           # top and bottom faces of a 2 m box
            tris += [[[a, b, z], [c, b, z], [c, d, z]], [[a, b, z], [c, d, z], [a, d, z]]]
            lab += [k, k]
    solid = np.array(tris, float).reshape(-1, 3, 3)
    return {'ground': ground, 'solid': solid, 'solid_label': np.array(lab, int), 'labels': list(labels),
            'bounds': bounds, 'meta': {'frame': 'fixture'}}


# A berth at the origin, bow east, starboard (south) side 0.6 m off a quay face at y -6.2, as at Brinecove/Hidamari.
BOUNDS = (-80.0, -40.0, 80.0, 60.0)


def berth_case(site, solids, labels=('fixture', 'quay'), zone_top=0.0):
    w = world(BOUNDS, solids=solids, labels=labels)
    face = -site.ship.BEAM - site.FENDER
    zone = [(-45.0, face - 4.0), (45.0, face - 4.0), (45.0, face + zone_top), (-45.0, face + zone_top)]
    hb = site.Harbour('fixture', w, (0.0, 0.0, 0.0), zone, [])
    # Arrival from 60 m east of the berth line and 13 m off, then a berthing crab onto the fenders.
    start = (0.0, 13.0, 0.0)
    return hb, hb.check('arrival', start, [('berth', -13.0)])[0]


def test_documented_clearance_is_the_code_rule(site):
    readme = (FERRY / 'README.md').read_text()
    assert site.STRUCTURE_CLEARANCE == 4.0
    rule = re.findall(r'keeps (\d+(?:\.\d+)?) m from every exported solid', readme)
    assert rule and all(float(r) == site.STRUCTURE_CLEARANCE for r in rule)
    assert f'{site.SEABED_MAX:.1f}'.replace('-', '−') in readme


def test_terminal_grounding_uses_region_owned_quay_limit(site):
    # Execute the real helper without importing the Blender-only terminal builder.
    tree = ast.parse((FERRY / 'terminals/build.py').read_text())
    helper = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'ground_under')
    namespace = {'FS': site, 'np': np}
    exec(compile(ast.Module(body=[helper], type_ignores=[]), '<terminal grounding>', 'exec'), namespace)
    ground = namespace['ground_under']
    assert ground(world((-2, -2, 2, 2), seabed=2.7), -1, -1, 1, 1) == pytest.approx(2.7)
    with pytest.raises(SystemExit, match='no exported ground'):
        ground(world((-2, -2, 2, 2), seabed=site.HD.QUAY_RAIL + 1), -1, -1, 1, 1)


def test_outlines_are_symmetric_and_the_wet_footprint_lies_inside_the_full_outline(site):
    xs, hw = site.ENV[id(site.FULL)]
    assert np.allclose(site.FULL[:161, 1], -site.FULL[161:, 1][::-1])
    wx, ww = site.ENV[id(site.WET)]
    assert (ww <= np.interp(wx, xs, hw) + 1e-9).all() and xs[0] <= wx[0] and wx[-1] <= xs[-1]


def test_poses_follow_each_move(site):
    ps = site.poses((0.0, 0.0, 90.0), [('ahead', 10.0), ('crab', 2.0), ('berth', -2.0), ('pivot', 90.0), ('move', 3.0, 4.0)])
    kinds = [p[3] for p in ps]
    assert kinds.count('ahead') == 20 and kinds.count('crab') == 4 and kinds.count('berth') == 4 and kinds.count('pivot') == 90
    x, y, h, _ = ps[20]; assert (round(x, 6), round(y, 6)) == (0.0, 10.0)
    x, y, h, _ = ps[24]; assert (round(x, 6), round(y, 6)) == (-2.0, 10.0)          # crab to port (west when heading north)
    x, y, h, _ = ps[-1]; assert (round(x, 6), round(y, 6), round(math.degrees(h), 6)) == (3.0, 14.0, 180.0)


def test_cover_marks_every_cell_a_sliver_triangle_crosses(site):
    g = site.Grid(0.0, 0.0, 10.0, 10.0)
    # A 2 cm wide diagonal sliver: no cell centre lies inside it, every cell it crosses must still be solid.
    t = np.array([[[0.1, 0.1, 0.0], [9.9, 9.9, 0.0], [9.9, 9.92, 1.0]]])
    m = g.cover(t)[0]
    for k in np.linspace(0.12, 9.88, 200):
        assert m[int(k / site.CELL), int(k / site.CELL)]
    assert m.sum() < 200


def test_surface_max_interpolates_the_exported_seabed(site):
    g = site.Grid(0.0, 0.0, 4.0, 4.0)
    tris = np.array([[[0, 0, -5.0], [4, 0, -1.0], [4, 4, -1.0]], [[0, 0, -5.0], [4, 4, -1.0], [0, 4, -5.0]]], float)
    z = g.surface_max(tris)
    assert np.allclose(z, -5.0 + g.X[None, :])
    assert np.isnan(g.surface_max(tris[:1])).any()                  # half the cells have no ground at all


def test_clear_water_and_a_berth_structure_pass(site):
    face = -site.ship.BEAM - site.FENDER
    hb, r = berth_case(site, [(-20.0, face - 3.0, 20.0, face, 1)])
    assert r['pass'], r
    assert 0.0 < r['alongside_berth_gap_m'] < 1.0 and r['min_structure_clearance_m'] >= site.STRUCTURE_CLEARANCE


def test_a_moored_boat_in_the_lane_fails(site):
    face = -site.ship.BEAM - site.FENDER
    boat = (30.0, 8.0, 39.6, 11.0, 0)                               # a 9.6 m rowboat beside the arrival line
    hb, r = berth_case(site, [(-20.0, face - 3.0, 20.0, face, 1), boat])
    assert not r['pass'] and r['conflict_count']
    hb, r = berth_case(site, [(-20.0, face - 3.0, 20.0, face, 1), (30.0, 30.0, 39.6, 33.0, 0)])
    assert r['pass'], r                                              # the same boat 20 m further off


def test_solids_outside_the_berth_zone_keep_the_full_clearance_alongside(site):
    face = -site.ship.BEAM - site.FENDER
    # A workboat off the bow, outside the berth zone and about 2 m from the stem at the berth: alongside does not
    # excuse it.
    hb, r = berth_case(site, [(-20.0, face - 3.0, 20.0, face, 1), (42.0, -3.0, 46.0, 3.0, 0)])
    assert not r['pass'] and any(c[3] in ('berth', 'start') for c in r['structure_conflicts'])


def test_the_hull_must_not_touch_its_own_berth(site):
    face = -site.ship.BEAM - site.FENDER
    hb, r = berth_case(site, [(-20.0, face - 3.0, 20.0, face + 1.0, 1)], zone_top=1.0)   # its own quay 1 m into the gap
    assert not r['pass'] and r['alongside_berth_gap_m'] == 0.0


def test_shallow_or_missing_seabed_under_the_keel_fails(site):
    w = world(BOUNDS, seabed=site.SEABED_MAX + 0.05)
    hb = site.Harbour('fixture', w, (0.0, 0.0, 0.0), [(0, 0), (1, 0), (1, 1)], [])
    r = hb.check('arrival', (0.0, 13.0, 0.0), [('berth', -13.0)])[0]
    assert not r['pass'] and r['grounding_count']
    w = world(BOUNDS); w['ground'] = w['ground'][:1]                # half the harbour has no exported ground
    hb = site.Harbour('fixture', w, (0.0, 0.0, 0.0), [(0, 0), (1, 0), (1, 1)], [])
    r = hb.check('arrival', (0.0, 13.0, 0.0), [('berth', -13.0)])[0]
    assert not r['pass'] and r['swept_cells_without_ground']


def test_site_json_refuses_changed_inputs(site, tmp_path):
    for n in ('hidamari', 'brinecove'):
        w = world(BOUNDS)
        np.savez_compressed(tmp_path / f'world_{n}.npz', ground=w['ground'], solid=w['solid'], solid_label=w['solid_label'],
                            meta=json.dumps({'labels': ['fixture'], 'bounds': BOUNDS, 'sources': {}, 'frame': 'fixture'}))
    worlds = {n: site.load_world(n, tmp_path) for n in ('hidamari', 'brinecove')}
    report = {'inputs': site.inputs(worlds)}
    assert site.stale_inputs(report, tmp_path) == []
    (tmp_path / 'world_brinecove.npz').write_bytes(b'changed')
    assert site.stale_inputs(report, tmp_path) == ['world_brinecove.npz']
    assert site.stale_inputs({}, tmp_path) == ['no inputs recorded']


def test_brow_fits_between_the_gate_posts_and_onto_the_landing_plate(site):
    """The brow (terminals/build.py) clears the ship's brass gate posts and its lip lands on the plate, inboard of
    the hull side and short of the plate's inner edge."""
    T = constants(FERRY / 'terminals/build.py')
    ship = site.ship
    gate_x, gate_w = ship.GATES[0]
    post_inner = gate_w / 2 + 0.05 - 0.11                        # post centre minus its widest lathe radius
    assert T['BROW_W'] / 2 + 0.05 <= post_inner
    assert T['HULL_GAP'] + T['LIP'] < ship.PLATE_DEPTH
    lo, hi = ship.landing_plate(gate_x, gate_w)
    for x in (gate_x - gate_w / 2, gate_x + gate_w / 2):
        assert lo < ship.deck_z(x) < hi                              # the level plate stands on the sheer everywhere
    assert 0 < T['LIP_GAP'] < 0.01 and T['FENDER_GAP'] > 0


def test_covering_board_stops_at_the_gates(site):
    edge = [(float(x), 5.5, 7.0) for x in np.linspace(-40, 40, 81)]
    runs = site.ship.gate_runs(edge)
    gate_x, gate_w = site.ship.GATES[0]
    assert len(runs) == 2
    assert math.isclose(runs[0][-1][0], gate_x - gate_w / 2) and math.isclose(runs[1][0][0], gate_x + gate_w / 2)
    assert not any(gate_x - gate_w / 2 < p[0] < gate_x + gate_w / 2 for r in runs for p in r)


def walk_report(**over):
    route = {'route': 'a -> b', 'connected': True, 'bottleneck_width_m': 1.3, 'bottleneck_at': [0, 0]}
    deck = {'routes': [route], 'pinch_points': [], 'trapping_pockets': []}
    report = {'decks': {'main deck': deck}, 'stair': {'min_headroom_m': 2.11},
              'fitting_seating': {'failures': []}, 'lifeboat_overlaps': {'FY_Hull': 0}}
    for k, v in over.items():
        if k in ('routes', 'pinch_points', 'trapping_pockets'):
            deck[k] = v
        elif k == 'headroom':
            report['stair']['min_headroom_m'] = v
        else:
            report[k] = v
    return report


def test_walk_verdict_passes_a_clean_report(walk):
    assert walk.verdict(walk_report()) == []


@pytest.mark.parametrize('fault', [
    {'routes': [{'route': 'a -> b', 'connected': False}]},
    {'routes': [{'route': 'a -> b', 'connected': True, 'bottleneck_width_m': 0.5, 'bottleneck_at': [1, 2]}]},
    {'pinch_points': [{'at': [1, 2], 'clear_width_m': 0.7, 'status': 'too narrow'}]},
    {'trapping_pockets': [{'at': [1, 2]}]},
    {'headroom': 1.9},
    {'fitting_seating': {'failures': [{'label': 'bollard', 'at': [1, 2]}]}},
    {'lifeboat_overlaps': {'FY_Hull': 3}},
])
def test_walk_verdict_fails_each_fault(walk, fault):
    assert walk.verdict(walk_report(**fault))


@pytest.fixture(scope='module')
def walkcheck():
    with mock.patch.dict(sys.modules):
        yield _load('ferry_walkcheck', FERRY / 'terminals/walkcheck.py')


def box(x0, y0, z0, x1, y1, z1):
    """The 12 triangles of an axis-aligned box."""
    v = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    quads = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    return np.array([[v[a], v[b], v[c]] for q in quads for a, b, c in ((q[0], q[1], q[2]), (q[0], q[2], q[3]))], float)


# The Hidamari jetty root: quay coping (top 2.475) on its wall, the timber rail's posts standing in it (2.45-3.55) and
# its top beam (3.455-3.545) running far past the jetty, all on y -126.
QUAY = 2.475
COPING, WALL = box(820, -127.7, 2.225, 860, -124.3, QUAY), box(820, -127.5, -1.0, 860, -124.5, 2.3)
POST = box(839.56, -126.065, 2.45, 839.69, -125.935, 3.55)
BEAM = box(781.65, -126.045, 3.455, 900.0, -125.955, 3.545)


def test_world_cut_takes_the_posts_with_the_rail_and_keeps_the_quay(site):
    cut = site.world_cut('rail', (831.8, 847.8), (-126.3, -125.7), QUAY - 0.1)
    for part, removed in ((POST, True), (BEAM, True), (COPING, False), (WALL, False),
                          (box(829.0, -126.065, 2.45, 829.13, -125.935, 3.55), False)):        # a post beside the jetty
        meets = (part[:, :, 0].max(1) >= cut['x'][0]) & (part[:, :, 0].min(1) <= cut['x'][1])      # crosses the jetty span
        assert (site.cut_mask(part, cut)[meets].all() if removed else not site.cut_mask(part, cut).any())


def walk_over_quay(walkcheck, site, extra):
    """The route at x 839.8 from the promenade over the coping onto the jetty, 0.11 m from the post."""
    floor = box(820, -140, 2.2, 860, -110, QUAY)
    tris = np.concatenate([floor] + extra)
    return walkcheck.audit([(839.8, -121.0, QUAY), (839.8, -131.0, QUAY)], walkcheck.TriangleCaster(tris))


def test_the_capsule_meets_a_post_beside_the_route_line(walkcheck, site):
    clear = walk_over_quay(walkcheck, site, [])
    assert clear['pass'], clear
    hit = walk_over_quay(walkcheck, site, [POST])
    assert not hit['pass'] and (hit['blocked'] or hit['min_side_clearance'] < walkcheck.RADIUS)


def test_cutting_the_rail_clears_the_route(walkcheck, site):
    cut = site.world_cut('rail', (831.8, 847.8), (-126.3, -125.7), QUAY - 0.1)
    parts = np.concatenate([POST, BEAM])
    kept = parts[~site.cut_mask(parts, cut)]
    assert walk_over_quay(walkcheck, site, [kept])['pass']
    assert not walk_over_quay(walkcheck, site, [BEAM])['pass']           # the beam alone blocks at waist height


def test_a_harbour_cannot_clip_the_hull_or_its_clearance_at_the_probe_edge(site):
    probe = world((-80., -40., 80., 60.))
    hb = site.Harbour('fixture', probe, (0., 0., 0.), [], [])
    result = hb.check('outside', (60., 0., 0.), [('ahead', 1.)])[0]
    assert not result['pass']
    assert result['probe_boundary_count'] == result['poses']
    assert result['conflict_count'] == result['grounding_count'] == 0
