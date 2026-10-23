"""The ferry service the game runs: build/yorimichi/ferry/service/service.json (pure Python).

uv run python games/yorimichi/world/regions/ferry/service.py
Reads terminals/site.json (site.py: each harbour's berth and its swept arrival and departure manoeuvres, the swept sea
crossings and the ship's plan outline, every manoeuvre recorded as the moves that were checked), terminals/manifest.json
and walk.json (terminals/build.py: each terminal's anchor, meshes, brow and audited walk), and the ship's manifest.json
(build.py). Refuses any of them with a failure, and creates exactly one shuttling passenger ferry. Writes what AFerryService needs, in Unreal units (centimetres, y flipped, yaw clockwise from +x):
- the timetable (timetable.py): one ship's cycle sampled every half second, its phases and the brows' windows, and the
  ships on the line with their offsets;
- the ship's meshes and collision (/Game/Ferry/Ship), the deck volume that counts as aboard and its boarding gates;
- each terminal's meshes, collision and brow (/Game/Ferry/Terminals) at its anchor, the brow's hinge, and the audited
  walk from the shore over the brow onto the deck (live drives follow it).
"""
import hashlib
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from regions.ferry import timetable as TT  # noqa: E402
import yori  # noqa: E402

REPO = HERE.parents[4]
FERRY = yori.OUT / 'ferry'
OUT = FERRY / 'service'
SHIPS = (('Ferry', 0),)                  # one ship shuttles between the two harbours
HARBOURS = ('hidamari', 'brinecove')      # berth indices 0 and 1
BROW_RAISED = 75.0                        # degrees the brow swings up about its shore hinge, clear of the hull
CLOCK_LEAD = 90.0                         # at service time 0 ship A is this many seconds from coming alongside Hidamari
DECK_Z = (5.2, 17.0)                      # metres above the waterline that count as aboard, inside the hull's plan
GATE_HEIGHT = 1.2                         # the closed boarding gate's stop, above the sill
SHIP_ROOT = '/Game/Ferry/Ship'
TERMINAL_ROOT = '/Game/Ferry/Terminals'
SHIP_WALK = yori.ASSETS / 'vehicles/ferry/walk.py'
SHARED_WALK = yori.WORLD / 'walk_raster.py'
CODE = (HERE/'service.py',HERE/'timetable.py',HERE.parent/'hidamari/ferry_source.py',
        HERE/'site_inputs.py',yori.WORLD/'region_plan_files.py',SHIP_WALK,SHARED_WALK)


def ue(x, y, z=0.0):
    return [round(x * 100.0, 2), round(-y * 100.0, 2), round(z * 100.0, 2)]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def asset(root, name):
    return f'{root}/{name}.{name}'


def refuse(problems):
    for p in problems:
        print('FERRY SERVICE REFUSED', p)
    raise SystemExit(1)


def origins(site):
    return {n: tuple(site[n].get('origin_m', (0.0, 0.0))) for n in HARBOURS}


def world(pose, origin):
    return (pose[0] + origin[0], pose[1] + origin[1], *pose[2:])


def cycle_from(site):
    """Ship A's cycle: alongside at Hidamari, the voyage west, alongside at Brinecove, the voyage east, each manoeuvre
    and crossing exactly the moves site.py swept."""
    o = origins(site)
    h, b = site['hidamari'], site['brinecove']
    west, east = site['crossings']['westbound'], site['crossings']['eastbound']
    hb = world(tuple(h['departure']['start']), o['hidamari'])
    bb = world(tuple(b['departure']['start']), o['brinecove'])
    for name, leg, frm, to in (('westbound', west, 'hidamari', 'brinecove'), ('eastbound', east, 'brinecove', 'hidamari')):
        # The swept crossings join the manoeuvres they were swept between.
        if (math.dist(leg['start'][:2], world(tuple(site[frm]['departure']['end']), o[frm])[:2]) > 0.05 or
                math.dist(leg['end'][:2], world(tuple(site[to]['arrival']['start']), o[to])[:2]) > 0.05):
            raise SystemExit(f'the {name} crossing does not join the {frm} departure to the {to} arrival')
    out, end_w = TT.voyage(hb, [('departing', h['departure']['moves']), ('cruise', west['moves']),
                                ('approach', b['arrival']['moves'])])
    back, end_e = TT.voyage(bb, [('departing', b['departure']['moves']), ('cruise', east['moves']),
                                 ('approach', h['arrival']['moves'])])
    for got, want, what in ((end_w, bb, 'Brinecove'), (end_e, hb, 'Hidamari')):
        if math.hypot(got[0] - want[0], got[1] - want[1]) > 0.05 or abs((got[2] - want[2] + 180) % 360 - 180) > 0.05:
            raise SystemExit(f'the voyage to {what} ends at {got}, its berth is {want}')
    return TT.Cycle([TT.Dwell(hb, TT.DWELL, 0), *out, TT.Dwell(bb, TT.DWELL, 1), *back])


def walk_points(route, origin):
    """walk.json's route in Unreal cm, every missing z filled in along it from its neighbours."""
    pts = [(p[0] + origin[0], p[1] + origin[1], p[2]) for p in route]
    known = [i for i, p in enumerate(pts) if p[2] is not None]
    out = []
    for i, (x, y, z) in enumerate(pts):
        if z is None:
            a = max([k for k in known if k < i], default=known[0]); b = min([k for k in known if k > i], default=known[-1])
            z = pts[a][2] if a == b else pts[a][2] + (pts[b][2] - pts[a][2]) * (i - a) / (b - a)
        out.append(ue(x, y, z))
    return out


def offsets(cycle):
    """Each ship's offset into the cycle (seconds): where it comes alongside its starting berth."""
    alongside = {berth: start for berth, start, _ in cycle.dwells()}
    return [alongside[berth] for _, berth in SHIPS]


def line(cycle):
    step, states = TT.sample(cycle)
    brows = TT.brows(cycle, len(HARBOURS))
    samples = [[round(s['x'] * 100, 2), round(-s['y'] * 100, 2), round(-s['h'], 4), round(s['vx'] * 100, 3),
                round(-s['vy'] * 100, 3), round(-s['w'], 5), round(s['throttle'], 3), round(s['thruster'], 3)] for s in states]
    alongside = [d for d in cycle.dwells() if d[0] == 0][0][1]
    return {'cycle_s': round(cycle.duration, 10), 'step_s': round(step, 10),
            'clock_start_s': round((alongside - CLOCK_LEAD) % cycle.duration, 3),
            'ships': [{'name': n, 'offset_s': round(o, 4)} for (n, _), o in zip(SHIPS, offsets(cycle))],
            'phases': [[round(a, 3), round(b, 3), p, -1 if berth is None else berth] for a, b, p, berth in cycle.phases()],
            'brows': [[[round(t, 3) for t in w] for w in brows[i]] for i in range(len(HARBOURS))],
            'samples': samples}


def ship_data(ferry):
    x0, y0, _ = ferry['dimensions']['min']; x1, y1, _ = ferry['dimensions']['max']
    gates = []
    for g in ferry['boarding_openings']:
        cx, cy, cz = g['centre']
        gates.append({'side': g['side'], 'centre_cm': ue(cx, cy, cz + GATE_HEIGHT / 2),
                      'extent_cm': [round(g['width'] * 50.0, 2), 8.0, round(GATE_HEIGHT * 50.0, 2)],
                      'hinge_cm': ue(cx - (g['width'] - .2) / 2, cy, cz),
                      'open_yaw': 90 if g['side'] == 'starboard' else -90})
    lo, hi = ue(x0, y1, DECK_Z[0]), ue(x1, y0, DECK_Z[1])
    return {'body': asset(SHIP_ROOT, 'FY_Collision'),
            'gate_mesh': asset(SHIP_ROOT, 'FY_BoardingGate'),
            'parts': [{'name': n.removeprefix('FY_'), 'mesh': asset(SHIP_ROOT, n), 'cull_cm': 15000 if n == 'FY_Masts' else 0} for n in ferry['meshes'] if n != 'FY_BoardingGate'],
            'deck_box_cm': [*lo, *hi], 'gates': gates}


def terminal_data(name, i, terminals, walks, origin):
    t = terminals['terminals'][name]
    prefix = 'FT_HD' if name == 'hidamari' else 'FT_BC'
    brow = t['brow']
    walk = walk_points(walks[name]['route'], origin)
    yaw = math.degrees(math.atan2(walk[1][1] - walk[0][1], walk[1][0] - walk[0][0]))
    return {'key': name, 'name': name.title(), 'berth': i, 'side': 'starboard',
            'anchor_cm': ue(*world(tuple(t['anchor']), origin)),
            'parts': [{'name': n.removeprefix(prefix + '_'), 'mesh': asset(TERMINAL_ROOT, n)}
                      for n in t['meshes'] if n != f'{prefix}_Brow'],
            'collision': asset(TERMINAL_ROOT, f'{prefix}_Collision'),
            'brow': {'mesh': asset(TERMINAL_ROOT, f'{prefix}_Brow'), 'hinge_cm': ue(*world(tuple(brow['from']), origin)),
                     'to_cm': ue(*world(tuple(brow['to']), origin)), 'raised_deg': BROW_RAISED},
            'board': {'location_cm': ue(*world(tuple(t['board']['position']), origin)),
                      'yaw': 90 - t['board']['yaw'], 'text_size_cm': t['board']['text_size_m'] * 100},
            'walk_cm': walk, 'walk_yaw': round(yaw, 2)}


def timing(cycle):
    """When each voyage leaves and arrives, how long the crossings and the brows' boarding windows last (seconds)."""
    (_, h_on, h_off), (_, b_on, b_off) = cycle.dwells()
    brows = TT.brows(cycle, len(HARBOURS))
    return {'cycle_s': round(cycle.duration, 1), 'westbound_s': round(b_on - h_off, 1),
            'eastbound_s': round(cycle.duration - b_off + h_on, 1), 'dwell_s': TT.DWELL,
            'brow_down_s': [round(brows[i][0][2] - brows[i][0][1], 1) for i in range(len(HARBOURS))],
            'departures_s': {h: sorted(round((off - o) % cycle.duration, 1) for berth, _, off in cycle.dwells() if berth == i
                                       for o in offsets(cycle)) for i, h in enumerate(HARBOURS)}}


def validate_manifest(data, root, repo=REPO):
    """Refuse missing proof, bad audits and stale source/export bytes before any Unreal mutation."""
    if not data.get('sources') or not data.get('files'):
        raise ValueError('ferry manifest is missing source/export identities; rebuild it')
    for base, hashes in ((repo, data['sources']), (root, data['files'])):
        for rel, wanted in hashes.items():
            path = base / rel
            if not path.is_file() or sha(path) != wanted:
                raise ValueError(f'ferry manifest is stale: {rel}')
    if data.get('failures') or data.get('soft_fail'):
        raise ValueError('ferry manifest contains failed or soft audits')


def validate_terminal_audits(data):
    """Require complete explicit passing terminal proof, independently of hashes."""
    try:
        if data['failures'] != [] or set(data['terminals']) != set(HARBOURS):
            raise ValueError('ferry terminal audit verdict failed')
        if not data['audit_fixtures'] or not all(row['ok'] is True for row in data['audit_fixtures']):
            raise ValueError('ferry terminal audit fixture failed')
        for terminal in data['terminals'].values():
            meshes = terminal['meshes']
            if not meshes or any(mesh['open_edges'] != 0 or mesh['flipped_parts'] != 0 for mesh in meshes.values()):
                raise ValueError('ferry terminal closure audit failed')
            if terminal['seats']['count'] <= 0 or terminal['seats']['failures'] != []:
                raise ValueError('ferry terminal seating audit failed')
            if terminal['coplanar']['count'] != 0:
                raise ValueError('ferry terminal coplanar audit failed')
            carried = terminal['carried']
            if (carried['groups'] <= 0 or carried['islands'] <= 0 or carried['failures'] != [] or
                    carried['uncarried_groups'] != 0 or carried['uncarried_islands'] != 0):
                raise ValueError('ferry terminal carried audit failed')
            if terminal['ship_clash']['pass'] is not True or terminal['ship_clash']['clashes'] != []:
                raise ValueError('ferry terminal ship clash audit failed')
            if terminal['walk']['pass'] is not True:
                raise ValueError('ferry terminal walking audit failed')
    except (KeyError, TypeError) as exc:
        raise ValueError('ferry terminal audit proof is incomplete') from exc


def validate_ship_walk(root=FERRY, checker=SHIP_WALK, raster=SHARED_WALK):
    """Require a passing ship walk bound to this checker and the exact deck."""
    report = json.loads((root / 'review/walk_report.json').read_text())
    expected = {'checker_sha256': sha(checker), 'raster_sha256': sha(raster),
                'deck_layout_sha256': sha(root / 'deck_layout.json')}
    if report.get('inputs') != expected:
        raise ValueError('ferry ship walk is stale; rebuild the deck walking audit')
    if report.get('failures') != []:
        raise ValueError('ferry ship walk failed or has no verdict')
    return report


def preflight(root=FERRY):
    """@cc [owner:fontanierh,label:correctness] ferry-stale-input-refusal
    Service generation and Unreal import MUST refuse failed/missing sweeps and audits or mismatched
    source/product hashes before creating assets. The ship MUST be the approved single shuttle, and
    its runtime manoeuvres MUST be exactly the source-bound moves the sweep checked.
    """
    site = json.loads((root / 'terminals/site.json').read_text())
    terminals = json.loads((root / 'terminals/manifest.json').read_text())
    walks = json.loads((root / 'terminals/walk.json').read_text())
    ferry = json.loads((root / 'manifest.json').read_text())
    from regions.hidamari.ferry_source import validated_atomic_harbor
    validated_atomic_harbor(yori.OUT, REPO)
    crossings = site.get('crossings') or {}
    if set(crossings) != {'eastbound', 'westbound'} or not all(c.get('pass') for c in crossings.values()):
        raise ValueError('a swept ferry sea crossing is missing or failed')
    if terminals.get('site_inputs') != site['inputs']:
        raise ValueError('ferry terminals were built against a different world/site')
    validate_manifest(terminals, root / 'terminals')
    validate_terminal_audits(terminals)
    validate_manifest(ferry, root)
    validate_ship_walk(root)
    audit = ferry['deck_audit']
    if any(m['open_edges'] for m in ferry['meshes'].values()) or audit['failures'] or any(audit['lifeboat_overlaps'].values()) or audit['fitting_rail_contacts']:
        raise ValueError('ferry mesh/deck audits failed')
    if set(walks) != set(HARBOURS) or not all(w['audit']['pass'] for w in walks.values()):
        raise ValueError('ferry terminal walk failed or is missing')
    return site, terminals, walks, ferry


def source_records(root=FERRY):
    from regions.hidamari.ferry_source import validated_atomic_harbor
    harbor = validated_atomic_harbor(yori.OUT, REPO)
    return {'code': {str(p.relative_to(REPO)): sha(p) for p in CODE},
            'products': harbor | {str(p.relative_to(yori.OUT)): sha(p) for p in
                         (root / 'terminals/site.json', root / 'terminals/manifest.json',
                          root / 'terminals/walk.json', root / 'manifest.json',
                          root / 'review/walk_report.json')}}


def validate_service(data, root=FERRY):
    if data != build_data(*preflight(root)):
        raise ValueError('ferry service is stale or differs from the single-shuttle timetable')


def build_data(site, terminals, walks, ferry):

    cycle = cycle_from(site)
    crossings = site['crossings']
    o = origins(site)
    data = {'units': 'Unreal: centimetres, y flipped from Blender, yaw degrees clockwise from +x; time seconds',
            'line': line(cycle), 'ship': ship_data(ferry),
            'terminals': [terminal_data(n, i, terminals, walks, o[n]) for i, n in enumerate(HARBOURS)],
            'checks': {'ship_count': len(SHIPS), 'crossings': {k: {'length_m': v['length_m'], 'min_clearance_m': v['min_structure_clearance_m'],
                                         'deepest_seabed_under_keel_m': v['deepest_seabed_under_keel_m']}
                                     for k, v in crossings.items()}},
            'timing': timing(cycle),
            'sources': source_records()}
    return data


def main():
    data = build_data(*preflight())
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'service.json').write_text(json.dumps(data, separators=(',', ':')) + '\n')
    print('FERRY SERVICE', json.dumps(data['timing']), 'ships', len(SHIPS))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
