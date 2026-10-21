"""Walkability audit of the ferry's decks, from the same collision proxies that build.py exports for Unreal.

uv run python games/yorimichi/assets/vehicles/ferry/walk.py
Reads build/yorimichi/ferry/deck_layout.json (written by build.py) and writes, under build/yorimichi/ferry/review/:
walk_report.json and one top-down layout image per deck (walk_main_deck.png, walk_boat_deck.png,
walk_monkey_island.png). It exits 1 when verdict() finds a failure: a route that does not connect or narrows below
HARD_MIN, a pinch under MIN_WIDTH that is not isolated, a trapping pocket, stair headroom under HEAD, an unseated
fitting or a lifeboat overlap.

For each deck, a cell is blocked when any proxy covers it in plan, with any part of its height between 0.30 m (the
step limit) and 2.0 m (required headroom) above the deck. The player capsule's centre (radius 0.22 m) may stand where
the clearance to the nearest blocked cell is at least the radius. Clear width at a point is twice that clearance, and
the routes report their bottleneck (max-min) width. Trapping pockets are free cells, reachable from the open deck,
that the capsule cannot sweep. Unswept slots no wider than 0.3 m are listed separately as slivers: the 0.44 m capsule
cannot enter them.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402
import json
import hashlib
import math
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[5]
OUT = yori.OUT / 'ferry'
REVIEW = OUT / 'review'
CELL = 0.05
RADIUS = 0.22
STEP, HEAD = 0.30, 2.0
MIN_WIDTH, HARD_MIN = 0.9, 0.6
SLIVER = 0.3                  # unswept slots up to this width are reported as slivers, not trapping pockets

from walk_raster import edt_1d,edt,label,bfs_path,inside_poly,plane,bottlenecks,pinch_points,pockets
import walk_raster as _raster


class Deck(_raster.Deck):
    def __init__(self,name,x0,x1,y0,y1,region,surface,own):
        super().__init__(name,x0,x1,y0,y1,region,surface,own,cell=CELL,radius=RADIUS,step=STEP,head=HEAD,
                         min_width=MIN_WIDTH,hard_min=HARD_MIN,sliver=SLIVER,record_routes=False)


def draw(deck,pinches,routes,marks,path,pockets_=(),scale=40):
    from PIL import Image,ImageDraw
    return _raster.draw(deck,pinches,routes,marks,path,pockets_,scale,image=Image,image_draw=ImageDraw)


def verdict(report):
    """Every failure in a walk report, as readable lines (empty when the decks pass)."""
    out = []
    for name, dk in report['decks'].items():
        for r in dk['routes']:
            if not r.get('connected'):
                out.append(f"{name}: route {r['route']} does not connect")
            elif r['bottleneck_width_m'] < HARD_MIN:
                out.append(f"{name}: route {r['route']} narrows to {r['bottleneck_width_m']} m at {r.get('bottleneck_at')}")
        out += [f"{name}: pinch {p['clear_width_m']} m at {p['at']} is too narrow" for p in dk['pinch_points'] if p['status'] == 'too narrow']
        out += [f"{name}: trapping pocket at {p['at']}" for p in dk['trapping_pockets']]
    head = report['stair']['min_headroom_m']
    if head != 'open sky' and head < HEAD:
        out.append(f'stair headroom {head} m is under {HEAD} m')
    out += [f"unseated fitting {s['label']} at {s.get('at', '')}" for s in report['fitting_seating']['failures']]
    out += [f'lifeboat overlap {k}: {v}' for k, v in report['lifeboat_overlaps'].items() if v]
    return out


def main():
    REVIEW.mkdir(parents=True, exist_ok=True)
    L = json.loads((OUT / 'deck_layout.json').read_text())
    proxies = L['proxies']; md = L['main_deck']; mx, mw, mz = (np.array(md[k]) for k in ('x', 'half_width', 'z'))
    bz = L['boat_deck']['z']; bx_, bz_ = np.array(bz['x']), np.array(bz['z'])
    st = L['stair']; ymid = sum(st['y']) / 2
    main = Deck('main deck', mx[0], mx[-1], -6.3, 6.3, lambda X, Y: np.abs(Y) <= np.interp(X, mx, mw) - 0.02,
                lambda X, Y: np.interp(X, mx, mz), {'main deck'}).rasterise(proxies)
    so = L['boat_deck']['outline']
    boat = Deck('boat deck', min(p[0] for p in so) - 0.2, max(p[0] for p in so) + 0.2, -4.4, 4.4, lambda X, Y: inside_poly(X, Y, so),
                lambda X, Y: np.interp(X, bx_, bz_), {'boat deck'}).rasterise(proxies)
    ro = L['monkey_island']['outline']; off = L['monkey_island']['z_offset_from_boat_deck']
    roof = Deck('monkey island (climb-only)', min(p[0] for p in ro) - 0.2, max(p[0] for p in ro) + 0.2, -3.4, 3.4,
                lambda X, Y: inside_poly(X, Y, ro), lambda X, Y: np.interp(X, bx_, bz_) + off, {'monkey island', 'wheelhouse'}).rasterise(proxies)
    hw = lambda x: float(np.interp(x, mx, mw))
    gx = L['boarding_openings'][0]['x']
    main_pts = {'boarding starboard': (gx, -(hw(gx) - 0.6)), 'boarding port': (gx, hw(gx) - 0.6), 'foredeck': (28.8, 0.0),
                'stern deck': (-31.8, 0.0), 'stair foot': (st['foot_x'] - 0.45, ymid), 'starboard walk aft': (-15.0, -4.4), 'port walk aft': (-15.0, 4.4)}
    main_routes = [('boarding starboard -> boarding port', main_pts['boarding starboard'], main_pts['boarding port']),
                   ('boarding starboard -> foredeck', main_pts['boarding starboard'], main_pts['foredeck']),
                   ('boarding port -> foredeck', main_pts['boarding port'], main_pts['foredeck']),
                   ('boarding starboard -> starboard walk aft', main_pts['boarding starboard'], main_pts['starboard walk aft']),
                   ('boarding port -> port walk aft', main_pts['boarding port'], main_pts['port walk aft']),
                   ('starboard walk aft -> stern deck', main_pts['starboard walk aft'], main_pts['stern deck']),
                   ('port walk aft -> stern deck', main_pts['port walk aft'], main_pts['stern deck']),
                   ('stern deck -> stair foot', main_pts['stern deck'], main_pts['stair foot'])]
    boat_pts = {'stair head': (st['top_x'] + 0.55, ymid), 'starboard midships': (0.0, -2.9), 'port midships': (0.0, 2.9),
                'forward boat deck': (23.8, 0.0), 'aft boat deck': (-17.0, 0.0)}
    boat_routes = [('stair head -> aft boat deck', boat_pts['stair head'], boat_pts['aft boat deck']),
                   ('stair head -> starboard midships', boat_pts['stair head'], boat_pts['starboard midships']),
                   ('stair head -> port midships', boat_pts['stair head'], boat_pts['port midships']),
                   ('starboard midships -> forward boat deck', boat_pts['starboard midships'], boat_pts['forward boat deck']),
                   ('port midships -> forward boat deck', boat_pts['port midships'], boat_pts['forward boat deck'])]
    report = {'capsule': L['capsule'], 'rules': {'min_clear_width_m': MIN_WIDTH, 'hard_min_isolated_m': HARD_MIN, 'headroom_m': HEAD,
                                                 'step_m': STEP, 'cell_m': CELL}, 'decks': {}}
    for deck, pts, routes in ((main, main_pts, main_routes), (boat, boat_pts, boat_routes), (roof, {}, [])):
        lab, n = label(deck.walk)
        comps = {int(lab[deck.snap(*p)]) for p in pts.values() if deck.snap(*p)} or set(range(1, n + 1))
        rts = bottlenecks(deck, routes); pin = pinch_points(deck, comps, lab); poc, sliv = pockets(deck)
        report['decks'][deck.name] = {'walkable_area_m2': round(float(deck.walk.sum() * CELL * CELL), 1), 'components': n,
                                      'routes': rts, 'pinch_points': pin, 'trapping_pockets': poc,
                                      'slivers': sliv}
        marks = [(k, x, y, (220, 110, 0)) for k, (x, y) in pts.items()]
        draw(deck, pin, rts, marks, REVIEW / f"walk_{deck.name.split(' (')[0].replace(' ', '_')}.png", poc)
    # Stair: geometry, headroom above every tread and the clear landings.
    head = []
    for x0, x1, z in st['treads']:
        xm = (x0 + x1) / 2; over = []
        for pr in proxies:
            if pr['name'] in ('stair', 'stair rail', 'main deck', 'boat deck'):
                continue
            if inside_poly(np.array([[xm]]), np.array([[ymid]]), pr['poly'])[0, 0]:
                (a0, b0, c0), _ = plane(pr); zb = a0 + b0 * xm + c0 * ymid
                if zb > z:
                    over.append(zb - z)
        head.append(round(min(over), 2) if over else None)
    def run(deck, x, y, dx):
        i, j = deck.cell(x, y); k = 0
        while 0 <= j < deck.walk.shape[1] and deck.free[i, j]:
            j += dx; k += 1
        return round(k * CELL, 2)
    report['stair'] = {'risers': st['risers'], 'rise_m': st['rise'], 'tread_m': st['tread'], 'angle_deg': st['angle_deg'],
                       'width_between_handrails_m': st['width'], 'treads': len(st['treads']),
                       'headroom_above_treads_m': [h if h is not None else 'open sky' for h in head],
                       'min_headroom_m': min([h for h in head if h is not None], default='open sky'),
                       'top_landing_clear_depth_m': run(boat, st['top_x'] + 0.05, ymid, 1),
                       'foot_landing_clear_depth_m': run(main, st['foot_x'] - 0.05, ymid, -1),
                       'handrails': 'both sides', 'treads_closed': True, 'top_gate': 'opening in the boat-deck rail with brass gate posts'}
    report['ladder'] = {'where': 'wheelhouse aft face to the monkey island', 'mode': 'climb-only',
                        'rail_gate': 'opening in the roof rail at the ladder head', 'side_rails_above_roof_m': 1.0}
    seats = L['seating']; bad = [s for s in seats if s['status'] != 'ok']
    report['fitting_seating'] = {'checked': len(seats), 'failures': bad, 'by_label': {}}
    for s in seats:
        b = report['fitting_seating']['by_label'].setdefault(s['label'], {'count': 0, 'max_gap_m': -1e9, 'min_gap_m': 1e9})
        b['count'] += 1
        if 'gap_m' in s:
            b['max_gap_m'] = max(b['max_gap_m'], s['gap_m']); b['min_gap_m'] = min(b['min_gap_m'], s['gap_m'])
    report['lifeboat_overlaps'] = L['lifeboat_overlaps']
    report['failures'] = verdict(report)
    report['inputs'] = {
        'checker_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'raster_sha256':hashlib.sha256(Path(_raster.__file__).read_bytes()).hexdigest(),
        'deck_layout_sha256': hashlib.sha256((OUT / 'deck_layout.json').read_bytes()).hexdigest(),
    }
    (REVIEW / 'walk_report.json').write_text(json.dumps(report, indent=2) + '\n')
    for name, dk in report['decks'].items():
        print(name, 'area', dk['walkable_area_m2'], 'components', dk['components'])
        for r in dk['routes']:
            print('  ', r['route'], r.get('bottleneck_width_m'), r.get('bottleneck_at'), 'OK' if r.get('meets_0.9') else 'CHECK')
        for p in dk['pinch_points']:
            print('   pinch', p)
        for p in dk['trapping_pockets']:
            print('   pocket', p)
        print('   slivers', dk['slivers']['count'], 'max width', dk['slivers']['max_width_m'])
    print('stair', {k: v for k, v in report['stair'].items() if k != 'headroom_above_treads_m'})
    print('seating failures', len(bad), 'lifeboat overlaps', L['lifeboat_overlaps'])
    for f in report['failures']:
        print('FAIL', f)
    print('WALK', 'FAIL' if report['failures'] else 'PASS')
    return 1 if report['failures'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
