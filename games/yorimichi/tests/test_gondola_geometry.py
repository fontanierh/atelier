"""Fast checks of the gondola kit's pure geometry and gate decisions: no Blender, no world build.

The rope path (straight, sagging, over a tower, round a station), the plumb hang of the cabin, the grip's clearance
from its dimensions, and the decisions in checks.py and walk.py that make the build fail. Fixtures marked MUST FAIL
are faults the gates exist to catch: a hanger 0.05 m from the rope, a jaw contact 3 mm off the rope radius, and a
tilted cabin floor.
"""
import math

import pytest

from gondola_kit_fixture import gondola_modules, load

KIT = load('rope', 'checks', 'params', 'walk')              # pure: importing bpy or mathutils would raise here
R, C, W = KIT.rope, KIT.checks, KIT.walk
RR = KIT.params.DEFAULTS['rope_radius']


@pytest.fixture(scope='module')
def grip():
    with gondola_modules('cabin', pure=False) as kit:        # cabin.py uses mathutils inside its builders only
        return dict(kit.cabin.GRIP)


def apply(M, q):
    return tuple(M[i][0] * q[0] + M[i][1] * q[1] + M[i][2] * q[2] + M[i][3] for i in range(3))


def column(M, j):
    return tuple(M[i][j] for i in range(3))


def paths():
    yield 'level', R.straight((-5, 0, 0), (5, 0, 0), RR)
    yield 'grade 40%', R.straight((-5, 0, -2), (5, 0, 2), RR)
    yield 'grade 75%', R.straight((-5, 0, -3.75), (5, 0, 3.75), RR)
    yield 'grade 100%', R.straight((-5, 0, -5), (5, 0, 5), RR)
    yield 'sagging span', R.sagging_span(40.0, 4.0, RR)
    yield 'tower pass', R.over_tower(16.0, 3.0, RR, span=6.0)
    yield 'station loop', R.station_loop(3.0, 3.77, 3.62, 8.2, RR)


# ------------------------------------------------------------------ rope geometry
def test_pure_kit_modules_import_without_blender():
    with gondola_modules('rope', 'checks', 'params', 'walk', pure=True) as kit:
        assert kit.rope.RopePath and kit.checks.ROPE_CLEARANCE and kit.walk.STEP


def test_grip_frame_follows_the_rope_with_the_door_side_outward():
    path = R.straight((-5, 0, -2), (5, 0, 2), RR)
    for out in ((0, -1, 0), (0, 1, 0)):
        G = path.grip_frame(path.length / 2, out)
        x, y, z = column(G, 0), column(G, 1), column(G, 2)
        t = path.rope_tangent(path.length / 2)
        assert abs(abs(sum(a * b for a, b in zip(x, t))) - 1) < 1e-9          # x along the rope
        assert z[2] > 0 and abs(sum(a * b for a, b in zip(x, z))) < 1e-9      # z up, square to the rope
        assert sum(a * b for a, b in zip(y, out)) < 0                           # door side (-y) faces outward


def test_sagging_span_is_the_small_sag_catenary():
    half, sag = 40.0, 4.0
    path = R.sagging_span(half, sag, RR)
    assert path.pts[0][2] == pytest.approx(sag) and path.pts[-1][2] == pytest.approx(sag)
    assert min(p[2] for p in path.pts) == pytest.approx(0.0, abs=1e-9)
    t = path.rope_tangent(path.length, h=0.5)
    assert t[2] / t[0] == pytest.approx(2 * sag / half, rel=0.02)              # end slope of the parabola
    lo, hi = 1.0, 1e5                                                           # the catenary through the same supports
    for _ in range(200):
        a = (lo + hi) / 2
        lo, hi = (a, hi) if a * (math.cosh(half / a) - 1) > sag else (lo, a)
    worst = max(abs(p[2] - a * (math.cosh(p[0] / a) - 1)) for p in path.pts)
    assert worst < 0.02 * sag                                                   # within 2 % of the sag everywhere


def test_tower_pass_is_level_over_the_train_and_smooth():
    H, half_train, defl = 16.0, 1.6, 3.0
    path = R.over_tower(H, 3.0, RR, half_train=half_train, deflection_deg=defl, span=8.0)
    for p in path.pts:
        assert p[1] == 3.0
        if abs(p[0]) <= half_train:
            assert p[2] == pytest.approx(H)
        assert p[2] <= H + 1e-12
    t_end = path.rope_tangent(0.0, h=0.2)
    assert math.degrees(math.atan2(-t_end[2], -t_end[0])) == pytest.approx(-defl, abs=0.05) or \
        math.degrees(math.atan2(t_end[2], t_end[0])) == pytest.approx(defl, abs=0.05)
    turns = []
    for i in range(1, len(path.pts) - 1):
        a, b, c = path.pts[i - 1], path.pts[i], path.pts[i + 1]
        u = [b[k] - a[k] for k in range(3)]; v = [c[k] - b[k] for k in range(3)]
        cos = sum(x * y for x, y in zip(u, v)) / (math.hypot(*u) * math.hypot(*v))
        turns.append(math.degrees(math.acos(max(-1.0, min(1.0, cos)))))
    assert max(turns) < 0.1                                                     # filleted: no kink over the end sheaves


def test_station_loop_drops_inside_the_mouth_and_rounds_the_bullwheel():
    Rb, z_line, drop, mouth = 3.0, 3.77, 0.15, 8.2
    path = R.station_loop(Rb, z_line, z_line - drop, mouth, RR)
    for p in path.pts:
        if p[0] >= mouth:
            assert p[2] == pytest.approx(z_line)
        elif p[0] <= mouth - 1.6:
            assert p[2] == pytest.approx(z_line - drop)
        if p[0] < -1e-6:
            assert math.hypot(p[0], p[1]) == pytest.approx(Rb, abs=1e-6)       # on the bullwheel's rope circle


# ------------------------------------------------------------------ hanging plumb
def test_cabin_hangs_plumb_on_every_path(grip):
    for name, path in paths():
        for k in range(1, 8):
            s = path.length * k / 8
            G = path.grip_frame(s, (0, -1, 0))
            H = R.hang_frame(G, grip['pivot'])
            assert C.floor_tilt_deg(H) < 1e-6, name
            assert C.hanging_ok(H), name
            pg, ph = apply(G, grip['pivot']), apply(H, grip['pivot'])
            assert math.dist(pg, ph) < 1e-9, name                              # the pivot pin is shared
            hx, gx = column(H, 0), column(G, 0)
            assert hx[2] == 0.0 and (hx[0] * gx[1] - hx[1] * gx[0]) == pytest.approx(0.0, abs=1e-9), name   # same heading


def test_tilted_cabin_floor_fails():
    """MUST FAIL: a cabin that takes the rope's frame (pitched with the grip) on a 40 % grade, and a 0.02 deg tilt."""
    path = R.straight((-5, 0, -2), (5, 0, 2), RR)
    G = path.grip_frame(path.length / 2, (0, -1, 0))
    assert C.floor_tilt_deg(G) == pytest.approx(math.degrees(math.atan(0.4)), abs=1e-6)
    assert not C.hanging_ok(G)
    a = math.radians(2 * C.FLOOR_TILT_TOL_DEG)
    slight = [[math.cos(a), 0, math.sin(a), 0], [0, 1, 0, 0], [-math.sin(a), 0, math.cos(a), 0], [0, 0, 0, 1]]
    assert not C.hanging_ok(slight)


# ------------------------------------------------------------------ rope contacts and clearance
def test_contact_categories():
    for tag in ('jaw', 'clamp', 'sheave', 'bullwheel groove'):
        assert C.category(tag) == C.INTENTIONAL
    for tag in ('hanger', 'wheel', 'rail', 'roof', None):
        assert C.category(tag) == C.UNRELATED


def test_seated_contacts_pass():
    for off in (0.0, 0.0019, -0.0019):
        for tag in ('jaw', 'sheave', 'bullwheel groove'):
            row = C.classify(tag, RR + off, RR)
            assert row['ok'] and row['category'] == C.INTENTIONAL, (tag, off)


@pytest.mark.parametrize('off', [0.003, -0.003])
def test_contact_three_mm_off_the_rope_radius_fails(off):
    """MUST FAIL: a jaw (or sheave, or bullwheel groove) 3 mm off the rope radius, lifted off or pressed in."""
    for tag in ('jaw', 'sheave', 'bullwheel groove'):
        row = C.classify(tag, RR + off, RR)
        assert row['category'] == C.INTENTIONAL and not row['ok'], (tag, off)


def test_contact_that_never_meets_the_rope_fails():
    assert not C.contact_ok(None, RR)


def test_unrelated_hardware_clearance_rule():
    need = C.required_clearance(RR)
    assert need == pytest.approx(RR + C.ROPE_CLEARANCE)
    assert C.clearance_ok(need, RR) and C.clearance_ok(None, RR) and C.clearance_ok(0.5, RR)
    assert not C.clearance_ok(need - 0.001, RR) and not C.clearance_ok(0.0, RR)


def test_hanger_five_cm_from_the_rope_fails():
    """MUST FAIL: a hanger post whose face runs 0.05 m from the rope axis (inside the rope radius + 0.05 m)."""
    path = R.straight((-5, 0, 0), (5, 0, 0), RR)
    post = [(x * 0.05, -0.05, z * 0.05) for x in range(-4, 5) for z in range(0, 20)]   # the face nearest the rope
    d = C.point_clearance(post, path)
    assert d == pytest.approx(0.05, abs=1e-9)
    row = C.classify('hanger', d, RR)
    assert row['category'] == C.UNRELATED and not row['ok']
    clear = [(x, y - 0.15, z) for x, y, z in post]
    assert C.classify('hanger', C.point_clearance(clear, path), RR)['ok']


def test_grip_wheels_and_pivot_clear_the_rope(grip):
    res = C.grip_clearances(grip, RR)
    assert res['ok'], res
    assert res['wheel_m'] == pytest.approx(abs(grip['wheel_y']) - grip['wheel_width'] / 2, abs=1e-4)
    assert res['pivot_point_m'] == pytest.approx(math.hypot(grip['pivot'][1], grip['pivot'][2]), abs=1e-4)


def test_grip_wheel_against_the_rope_fails(grip):
    """MUST FAIL: running wheels pulled in so their tyres come within the rope clearance."""
    tight = dict(grip, wheel_y=-0.12)
    assert not C.grip_clearances(tight, RR)['ok']


# ------------------------------------------------------------------ other gates
def test_budgets():
    assert C.budget_failures('cabin', C.BUDGET['cabin']) == []
    assert C.budget_failures('station', C.BUDGET['station'] + 1)


def test_collision_proxies_must_be_convex_hulls():
    box = {'name': 'box', 'poly': [[0, 0], [1, 0], [1, 1], [0, 1]], 'z0': [0] * 4, 'z1': [1] * 4}
    ell = {'name': 'ell', 'poly': [[0, 0], [2, 0], [2, 1], [1, 1], [1, 2], [0, 2]], 'z0': [0] * 6, 'z1': [1] * 6}
    flat = dict(box, name='flat', z1=[0] * 4)
    assert C.proxy_failures([box]) == []
    assert C.proxy_failures([ell]) and C.proxy_failures([flat]) and C.proxy_failures([])


def piece(**kw):
    good = {'routes': [{'route': 'a -> b', 'connected': True, 'meets_0.9': True, 'bottleneck_width_m': 1.4}],
            'pinch_points': [], 'trapping_pockets': [], 'stairs': [], 'boarding': []}
    return good | kw


def test_walk_verdict_passes_a_clean_piece():
    assert W.verdict(piece()) == []


def test_walk_verdict_fails_each_fault():
    assert W.verdict(piece(routes=[{'route': 'a -> b', 'connected': False}]))
    assert W.verdict(piece(routes=[{'route': 'a -> b', 'connected': True, 'meets_0.9': False, 'bottleneck_width_m': 0.7}]))
    assert W.verdict(piece(pinch_points=[{'status': 'too narrow', 'clear_width_m': 0.6, 'at': [0, 0]}]))
    assert W.verdict(piece(trapping_pockets=[{'at': [0, 0]}]))
    steep = {'x': [0, 1], 'y': [0, 1], 'riser_m': W.RISER_MAX + 0.05, 'tread_m': 0.3, 'width_m': 1.2,
             'riser_ok': False, 'tread_ok': True, 'width_ok': True}
    assert W.verdict(piece(stairs=[steep]))
    assert W.verdict(piece(door={'clear_width_m': 0.8, 'clear_height_m': 2.0, 'ok': False}))
    assert W.verdict(piece(boarding=[{'side': 1, 'door_within_gate': False}]))


def test_walk_exits_nonzero_on_failure(monkeypatch):
    monkeypatch.setattr(W, 'audit', lambda quiet=False: ({}, ['valley: route a -> b: not connected']))
    with pytest.raises(SystemExit) as e:
        W.main()
    assert e.value.code == 1
    monkeypatch.setattr(W, 'audit', lambda quiet=False: ({}, []))
    W.main()


# ------------------------------------------------------------------ per-part, signed contact gates
def box(x0, x1, y0, y1, z0, z1):
    V = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    F = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    return C.triangles(V, F)


ROPE = [(x * 0.01, 0.0, 0.0) for x in range(-200, 201)]           # a level rope axis along x, sampled every 10 mm


def rows_for(parts, tag):
    return [{'tag': tag, 'part': f'{tag} {k}', 'per_pose': [C.part_minimum(t, ROPE, RR)]} for k, t in enumerate(parts)]


def sheave(x, drop=0.0):
    """A sheave block under the rope: its top face RR below the rope axis (seated), lowered by `drop`."""
    return box(x - 0.1, x + 0.1, -0.06, 0.06, -0.3 - drop, -RR - drop)


def test_seated_sheave_train_passes():
    rows = rows_for([sheave(x) for x in (-1.35, -0.6, 0.6, 1.35)], 'sheave')
    assert C.part_verdicts(rows, RR, {'sheave': 4}) == []


def test_one_sheave_off_the_rope_fails_although_the_train_minimum_is_seated():
    """MUST FAIL: one sheave of four dropped 5 mm; the minimum over the train would still read seated."""
    rows = rows_for([sheave(-1.35), sheave(-0.6, drop=0.005), sheave(0.6), sheave(1.35)], 'sheave')
    assert C.contact_ok(min(r['per_pose'][0] for r in rows), RR)          # the old, train-wide minimum passes
    bad = C.part_verdicts(rows, RR, {'sheave': 4})
    assert len(bad) == 1 and 'sheave 1' in bad[0]


def test_sheave_missing_from_the_train_fails():
    """MUST FAIL: a sheave lifted clear of the rope (beyond the search) is missing, not passing."""
    rows = rows_for([sheave(-1.35), sheave(-0.6, drop=0.5), sheave(0.6), sheave(1.35)], 'sheave')
    assert any('expected 4' in b for b in C.part_verdicts(rows, RR, {'sheave': 4}))


def jaw(side, lift=0.0):
    """A jaw block beside the rope: its inner face RR from the axis (seated), moved off by `lift`."""
    y0 = side * (RR + lift)
    return box(-0.2, 0.2, min(y0, y0 + side * 0.05), max(y0, y0 + side * 0.05), -0.03, 0.03)


def test_seated_jaw_pair_passes():
    assert C.part_verdicts(rows_for([jaw(1), jaw(-1)], 'jaw'), RR, {'jaw': 2}) == []


def test_one_jaw_half_lifted_three_mm_fails():
    """MUST FAIL: the movable jaw 3 mm off the rope while the fixed jaw is seated."""
    rows = rows_for([jaw(1), jaw(-1, lift=0.003)], 'jaw')
    bad = C.part_verdicts(rows, RR, {'jaw': 2})
    assert len(bad) == 1 and 'jaw 1' in bad[0] and 'off the seat' in bad[0]


def test_attach_zone_allows_the_rope_off_the_jaws_but_not_into_them():
    lifted = rows_for([jaw(1), jaw(-1, lift=0.1)], 'jaw')
    assert C.part_verdicts(lifted, RR, {'jaw': 2}, seated=False) == []
    pressed = rows_for([jaw(1), jaw(-1, lift=-0.01)], 'jaw')
    assert C.part_verdicts(pressed, RR, {'jaw': 2}, seated=False)


def test_rope_axis_buried_a_radius_deep_fails():
    """MUST FAIL: the rope axis inside a part, one radius from its nearest face. Unsigned, it would read seated."""
    block = box(-0.3, 0.3, -RR, 0.5, -0.5, 0.5)
    assert C.point_distance((0, 0, 0), block) == pytest.approx(RR)
    assert C.signed_distance((0, 0, 0), block) == pytest.approx(-RR)
    for tag in ('jaw', 'sheave', 'bullwheel groove'):
        bad = C.part_verdicts(rows_for([block], tag), RR, {tag: 1})
        assert bad and 'inside the part' in bad[0], tag


def test_clamp_may_sit_beside_the_rope_but_not_cut_into_it():
    beside = box(-0.2, 0.2, -0.05, 0.05, RR + 0.03, 0.2)
    assert C.part_verdicts(rows_for([beside], 'clamp'), RR) == []
    cutting = box(-0.2, 0.2, -0.05, 0.05, RR - 0.01, 0.2)
    assert C.part_verdicts(rows_for([cutting], 'clamp'), RR)


# ------------------------------------------------------------------ station loop margin and boarding
def test_cabin_body_near_a_post_fails_the_loop_margin():
    """MUST FAIL: a cabin body passing 0.05 m from a canopy post."""
    body = box(-1.1, 0.95, -0.8, 0.8, 0.3, 2.4)
    post = [(x, y, z) for x in (1.0, 1.3) for y in (-0.15, 0.15) for z in (0.5, 2.0)]   # a post's corners beside the wall
    d = min(C.point_distance(q, body) for q in post)
    assert d == pytest.approx(0.05)
    assert not C.loop_margin_ok(d)
    assert C.loop_margin_ok(C.STATION_LOOP_MARGIN) and not C.loop_margin_ok(None)


def berth(gap=0.1, sill=0.02, centre=3.4, width=1.0, gate=(2.6, 4.2)):
    lo, hi = gate
    return {'side': -1, 'door_within_gate': lo <= centre - width / 2 and centre + width / 2 <= hi,
            'gap_door_to_edge_m': gap, 'sill_above_platform_m': sill,
            'gap_ok': W.BOARDING_GAP_MIN <= gap <= W.BOARDING_GAP_MAX, 'sill_ok': W.SILL_MIN <= sill <= W.SILL_MAX}


def test_boarding_gap_and_sill_in_range_pass():
    assert W.verdict(piece(boarding=[berth()])) == []


@pytest.mark.parametrize('kw', [{'gap': 0.2}, {'gap': 0.0}, {'sill': 0.06}, {'sill': -0.02}, {'width': 1.8}])
def test_boarding_gap_sill_or_door_out_of_range_fails(kw):
    """MUST FAIL: a boarding gap or sill outside its range, or a door wider than the gate opening."""
    assert W.verdict(piece(boarding=[berth(**kw)]))


# ------------------------------------------------------------------ walkable slabs stand on collision
PLAZA = [(-20.4, -20.0), (9.6, -20.0), (9.6, -5.0), (-20.4, -5.0)]


def floor_hull(poly, top=0.0):
    tops = [top(x, y) if callable(top) else top for x, y in poly]
    return {'name': 'floor', 'poly': [list(p) for p in poly], 'z0': [t - 0.3 for t in tops], 'z1': tops}


def test_slab_on_its_own_floor_hull_passes():
    assert C.floor_support_failures([('plaza', PLAZA)], [floor_hull(PLAZA)]) == []


def test_slab_split_across_abutting_hulls_passes():
    west = [(-20.4, -20.0), (-5.0, -20.0), (-5.0, -5.0), (-20.4, -5.0)]
    east = [(-5.0, -20.0), (9.6, -20.0), (9.6, -5.0), (-5.0, -5.0)]
    assert C.floor_support_failures([('plaza', PLAZA)], [floor_hull(west), floor_hull(east)]) == []


def test_slab_without_collision_fails():
    """MUST FAIL: a walkable plaza drawn in the render mesh with no floor hull under it."""
    bad = C.floor_support_failures([('plaza', PLAZA)], [])
    assert len(bad) == 1 and bad[0].startswith('plaza:')


def test_slab_half_on_collision_fails():
    """MUST FAIL: a ramp whose hulls stop part way along it."""
    half = [(-20.4, -20.0), (-5.0, -20.0), (-5.0, -5.0), (-20.4, -5.0)]
    assert C.floor_support_failures([('plaza', PLAZA)], [floor_hull(half)])


def test_hull_displaced_below_the_slab_fails():
    """MUST FAIL: the plaza's hull exported a metre below the paving: in plan it covers the slab, but nothing holds a
    player at the slab's height."""
    assert C.floor_support_failures([('plaza', PLAZA)], [floor_hull(PLAZA, top=-1.0)])


def test_roof_hull_over_the_slab_fails():
    """MUST FAIL: a canopy hull 3 m up covers the slab in plan but is not its floor."""
    assert C.floor_support_failures([('plaza', PLAZA)], [floor_hull(PLAZA, top=3.0)])


def test_hull_a_little_off_the_slab_height_fails():
    """MUST FAIL: a floor hull 3 cm under the paving (over the 1 cm seat rule): the player would sink."""
    assert C.floor_support_failures([('plaza', PLAZA)], [floor_hull(PLAZA, top=-0.03)])


def test_sloped_slab_on_its_sloped_hull_passes():
    ramp = lambda x, y: -0.08 * (y + 20.0)
    assert C.floor_support_failures([('ramp', PLAZA, ramp)], [floor_hull(PLAZA, top=ramp)]) == []


def test_sloped_slab_on_a_flat_hull_fails():
    """MUST FAIL: a ramp whose hull is flat at the ramp's top: most of the ramp has no floor at its height."""
    ramp = lambda x, y: -0.08 * (y + 20.0)
    assert C.floor_support_failures([('ramp', PLAZA, ramp)], [floor_hull(PLAZA, top=0.0)])


# ------------------------------------------------------------------ cabin bench seats and first-person look clamp
def test_gondola_bench_seats_lie_on_cabin_benches_face_inward_and_clear_walls():
    """Verify every C++ bench seat in AGondolaService::BuildCabinSeats lies on a cabin.py bench top (+-2 cm),
    faces into the cabin, and keeps the seated rider body capsule clear of all cabin walls and the ceiling."""
    from pathlib import Path
    import re

    p = KIT.params.DEFAULTS
    d = KIT.params.derived(p)
    with gondola_modules('cabin', pure=False) as kit:
        cab = kit.cabin.Cabin(p, d)
        layout = cab.layout()
        wall_t_cm = kit.cabin.T * 100.0
        seat_d_cm = kit.cabin.SEAT_D * 100.0
        seat_h_cm = kit.cabin.SEAT_H * 100.0
        wall_top_cm = kit.cabin.WALL_TOP * 100.0

    cpp = (Path(__file__).resolve().parents[1] / 'unreal/Source/Yorimichi/GondolaService.cpp').read_text()
    assert 'const float WallT=7.5f,BenchD=40.f,BenchH=46.f;' in cpp
    assert wall_t_cm == pytest.approx(7.5)
    assert seat_d_cm == pytest.approx(40.0)
    assert seat_h_cm == pytest.approx(46.0)

    size_x_cm = p['cabin_length'] * 100.0
    size_y_cm = p['cabin_width'] * 100.0
    floor_z_cm = layout['floor_z'] * 100.0
    xi = size_x_cm * 0.5 - wall_t_cm
    yi = size_y_cm * 0.5 - wall_t_cm
    seat_z = floor_z_cm + seat_h_cm
    seats = [
        ('back_left', (-28.0, -(yi - 0.5 * seat_d_cm), seat_z), 90.0, 'back'),
        ('back_right', (28.0, -(yi - 0.5 * seat_d_cm), seat_z), 90.0, 'back'),
        ('west', (-(xi - 0.5 * seat_d_cm), 0.0, seat_z), 0.0, 'west'),
        ('east', (xi - 0.5 * seat_d_cm, 0.0, seat_z), 180.0, 'east'),
    ]
    expected_cpp_lines = [
        'OutSeats.Add({TEXT("back_left"),FVector(-28.f,-(Yi-0.5f*BenchD),SeatZ),90.f});',
        'OutSeats.Add({TEXT("back_right"),FVector(28.f,-(Yi-0.5f*BenchD),SeatZ),90.f});',
        'OutSeats.Add({TEXT("west"),FVector(-(Xi-0.5f*BenchD),0.f,SeatZ),0.f});',
        'OutSeats.Add({TEXT("east"),FVector(Xi-0.5f*BenchD,0.f,SeatZ),180.f});',
    ]
    for line in expected_cpp_lines:
        assert line in cpp, line

    benches = layout['benches']
    expected_top_cm = (layout['floor_z'] + benches['seat_height']) * 100.0
    for name, (x_ue, y_ue, z_ue), yaw_deg, which in seats:
        # Convert Unreal cm (y_ue = -y_m * 100) back to cabin.py metres (x_m, y_m).
        x_m, y_m = x_ue / 100.0, -y_ue / 100.0
        assert abs(z_ue - expected_top_cm) <= 2.0, (name, z_ue, expected_top_cm)
        if which == 'back':
            y0, y1 = benches['back_y']
            assert y0 <= y_m <= y1 and benches['west'][1] <= x_m <= benches['east'][0]
            inward_ue = (0.0, 1.0)
        elif which == 'west':
            x0, x1 = benches['west']
            assert x0 <= x_m <= x1 and -yi / 100.0 <= y_m <= yi / 100.0
            inward_ue = (1.0, 0.0)
        else:
            x0, x1 = benches['east']
            assert x0 <= x_m <= x1 and -yi / 100.0 <= y_m <= yi / 100.0
            inward_ue = (-1.0, 0.0)
        facing_ue = (math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg)))
        assert facing_ue[0] * inward_ue[0] + facing_ue[1] * inward_ue[1] == pytest.approx(1.0), name
        # Seated body cylinder (r = 18 cm) clears the cabin interior walls (xi, yi) and ceiling (wall_top_cm).
        radius_cm = 18.0
        assert xi - abs(x_ue) - radius_cm > 0.0, name
        assert yi - abs(y_ue) - radius_cm > 0.0, name
        assert (floor_z_cm + wall_top_cm) - (z_ue + 95.0) > 0.0, name


def test_gondola_seat_scenario_and_first_person_clamp_contract():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    view_cpp = (root / 'unreal/Source/Yorimichi/TrainPassengerView.cpp').read_text()
    char_cpp = (root / 'unreal/Source/Yorimichi/WandererCharacter.cpp').read_text()
    scen = (root / 'scenarios/gondola_seat.py').read_text()
    assert 'FMath::Clamp(float(FRotator::NormalizeAxis(Look.Yaw - BaseYaw)), -100.f, 100.f)' in view_cpp
    assert 'FMath::Clamp(float(FRotator::NormalizeAxis(Look.Pitch)), -60.f, 60.f)' in view_cpp
    assert 'bSlowBlend ? 2.5f : 4.f' in char_cpp
    for key in ('seated_on_board', 'first_person_active', 'head_hidden', 'look_clamped_pos',
                'look_clamped_neg', 'cabin_plumb', 'no_wall_clip', 'stood_on_arrival', 'third_person_restored'):
        assert key in scen
