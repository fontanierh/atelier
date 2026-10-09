#!/usr/bin/env python3
"""Measure how the board rides different ground on the simulation offline QA session.

Imported worlds are game meshes, so the board must roll over what a real board rolls over: plank decks with gaps
between bevelled boards (the footbridge into the Mega Park), and seams and trim a few millimetres proud (the
mini-mega). Pushing across the planks must not catch a foot in a gap, and a curb must still stop the board. Each kind
of ground (ESkateSurface, packed per triangle as the plugin's snapshot does) rides as the session's surface profiles do:
concrete and wood smooth, asphalt and stone rough, dirt slow and grass very slow, and the session reports the surface
under the wheels. Requires the assembled simulation package (skate.runtime) and the explicitly built test-only gameplay-session-cli
(Tests/build_simulation_session_cli.py --compile, under the render lock and memory guard).
Results go to build/yorimichi/skate-simulation/terrain.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_skate_feel as feel  # noqa: E402

OUTPUT = feel.ROOT / 'build/yorimichi/skate-simulation/terrain'
DIFFICULTIES = ('easy', 'normal', 'hardcore')
# Packed as the plugin packs ESkateSurface: physics << 7 | surface. Physics 1 smooth, 2 rough, 3 slow, 5 very slow.
SURFACES = {'concrete': (1, 1), 'wood': (1, 2), 'asphalt': (2, 4), 'stone': (2, 5), 'dirt': (3, 6), 'grass': (5, 7)}


def quad(a, b, c, d):
    return [[a, b, c], [a, c, d]]


def box(cx, cy, cz, w, h, d, bevel=0.):
    """A box in simulation coordinates (x across, y up, z along the ride): w across, h high, d along. A bevel chamfers its
    vertical edges and top and bottom rims, as the game's Mesh.box(..., bevel) does."""
    if not bevel:
        x0, x1, y0, y1, z0, z1 = cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2, cz - d / 2, cz + d / 2
        return (quad([x0, y1, z0], [x0, y1, z1], [x1, y1, z1], [x1, y1, z0]) + quad([x0, y0, z0], [x1, y0, z0], [x1, y0, z1], [x0, y0, z1])
                + quad([x0, y0, z0], [x0, y1, z0], [x1, y1, z0], [x1, y0, z0]) + quad([x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1])
                + quad([x0, y0, z0], [x0, y0, z1], [x0, y1, z1], [x0, y1, z0]) + quad([x1, y0, z0], [x1, y1, z0], [x1, y1, z1], [x1, y0, z1]))
    b = min(bevel, w / 3, d / 3, h / 3)

    def ring(y, s):
        return [[cx + px * s, cy + y, cz + pz * s] for px, pz in
                [(-w/2+b, -d/2), (w/2-b, -d/2), (w/2, -d/2+b), (w/2, d/2-b), (w/2-b, d/2), (-w/2+b, d/2), (-w/2, d/2-b), (-w/2, -d/2+b)]]
    rings = [ring(-h / 2, .94), ring(-h / 2 + b, 1), ring(h / 2 - b, 1), ring(h / 2, .94)]
    tris = [[rings[-1][0], rings[-1][k + 1], rings[-1][k]] for k in range(1, 7)]
    tris += [[rings[0][0], rings[0][k], rings[0][k + 1]] for k in range(1, 7)]
    for lo, hi in zip(rings[:-1], rings[1:]):
        for k in range(8):
            p, q, r, s = lo[k], lo[(k + 1) % 8], hi[(k + 1) % 8], hi[k]
            tris += [[p, r, q], [p, s, r]]
    return tris


def planks(gap=.02, width=.22, thick=.06, bevel=.008):
    """The footbridge: bevelled boards across the ride with gaps between them over a subfloor 1 mm under their tops
    (zeppelin/build.py park_walk), after a run-up deck at the same height, over ground a metre down. It runs 60 m, past
    where a 5 s push or a 4 s coast at 7 m/s ends (at 20 m, Easy's push rode off its end and stopped in the ground
    below)."""
    tris = [[[p[0], p[1] - 1, p[2]] for p in t] for t in feel.FLAT] + box(0, -thick / 2, -4, 2.2, thick, 6)
    tris += quad([-1.1, -.001, -1], [-1.1, -.001, 60], [1.1, -.001, 60], [1.1, -.001, -1])
    z = -1.
    while z < 60:
        tris += box(0, -thick / 2, z + width / 2, 2.2, thick, width, bevel)
        z += width + gap
    return tris


def lips(height, spacing=1.5):
    """Strips across the ride every `spacing` metres, `height` proud of the ground: seams and trim."""
    tris = list(feel.FLAT)
    z = 1.
    while z < 20:
        tris += box(0, height / 2, z, 8, height, .008)
        z += spacing
    return tris


def quarter(radius=3., vert=.3, segments=32):
    """A quarter pipe ahead of the rider: flat ground, a transition of `radius` from z 10 rising to vertical in
    `segments` faces, `vert` of wall and a deck on top."""
    import math
    tris = quad([-4, 0, -40], [-4, 0, 10], [4, 0, 10], [4, 0, -40])
    pts = [(10 + radius * math.sin(a), radius - radius * math.cos(a)) for a in (i * math.pi / 2 / segments for i in range(segments + 1))]
    pts.append((10 + radius, radius + vert))
    for (za, ya), (zb, yb) in zip(pts, pts[1:]):
        tris += quad([-4, ya, za], [-4, yb, zb], [4, yb, zb], [4, ya, za])
    top, z = radius + vert, 10 + radius
    return tris + quad([-4, top, z], [-4, top, z + 3], [4, top, z + 3], [4, top, z])


def roll(binary, package, triangles, name, speed, frames=240, controls=None, surfaces=None, start=-3, difficulty='normal'):
    world = {'triangles': triangles, 'rails': [], 'spawn': [0, 0, start], 'heading': 0}
    if surfaces is not None:
        world['surfaces'] = surfaces
    session = feel.Session(binary, package, world, name)
    try:
        rows = session.ride(frames, controls or (lambda f: (0, [0, 0], [0, 0])), None, velocity=(0, 0, speed), spawn=(0, 0, start),
                            difficulty=difficulty)
    finally:
        session.close()
    speeds = [feel.speed(r) for r in rows]
    moving = next((k for k, v in enumerate(speeds) if v > 3), None)
    return dict(end_speed_mps=round(speeds[-1], 2), peak_m=round(max(session.deck_height(r) for r in rows), 2),
                distance_m=round(rows[-1]['root'][14] - rows[0]['root'][14], 2),
                slowest_once_moving_mps=round(min(speeds[moving:]), 2) if moving is not None else None,
                bailed=any('Wipeout' in r['state'] or 'Bail' in r['state'] for r in rows),
                surface=rows[min(60, len(rows) - 1)].get('surface'))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--binary', type=Path, default=feel.BINARY)
    parser.add_argument('--simulation-package', type=Path, default=feel.SIMULATION_PACKAGE)
    args = parser.parse_args()
    if not args.binary.exists():
        sys.exit(f'{args.binary} is missing: build it with Tests/build_simulation_session_cli.py --compile')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    feel.OUTPUT = OUTPUT
    report, failures = {}, []

    def check(name, ok, detail):
        print(('PASS ' if ok else 'FAIL ') + name, flush=True)
        if not ok:
            failures.append({'name': name, 'detail': detail})

    # Rolling over small edges: coasting across planks, 4 and 8 mm lips and a 2 cm lip keeps most of the speed a flat
    # coast keeps (it loses a little to the bumps) and never bails. A 3 cm curb, taller than an edge a wheel rolls over,
    # still stops the board.
    worlds = {'flat': feel.FLAT, 'planks': planks(), 'lip4mm': lips(.004), 'lip8mm': lips(.008), 'curb30mm': lips(.03, 40)}
    report['edges'] = {name: {str(v): roll(args.binary, args.simulation_package, tris, f'{name}_{v}', v) for v in (3, 5, 7)}
                       for name, tris in worlds.items()}
    edges = report['edges']
    for name in ('planks', 'lip4mm', 'lip8mm'):
        ok = all(edges[name][v]['end_speed_mps'] >= .8 * edges['flat'][v]['end_speed_mps'] and not edges[name][v]['bailed']
                 for v in edges[name])
        check(f'rolls_over_{name}', ok, {name: edges[name], 'flat': edges['flat']})
    check('stops_at_curb', all(r['distance_m'] < 4.5 for r in edges['curb30mm'].values()), edges['curb30mm'])
    # Pushing across the planks from a standstill: the pushing foot slides over the gaps rather than catching in one, so
    # once moving the board never falls back to a crawl (a caught foot stopped it dead, from 7 m/s to under 1).
    pushing = lambda f: (feel.PUSH, [0, 0], [0, 0])
    report['pushing'] = {d: {name: roll(args.binary, args.simulation_package, worlds[name], f'push_{name}_{d}', 0, 300, pushing, difficulty=d)
                             for name in ('flat', 'planks')} for d in DIFFICULTIES}
    # A ramp is not a small edge: going straight up a quarter pipe fast enough to air out of it, with no input, the
    # board comes back down into the transition and rides away. (Taking the transition's faces for small edges made
    # these landings bail.) Both on every difficulty the game offers.
    report['quarter'] = {d: {str(v): roll(args.binary, args.simulation_package, quarter(), f'quarter_{v}_{d}', v, 600, start=0, difficulty=d)
                             for v in (9, 10, 11)} for d in DIFFICULTIES}
    check('lands_back_in_transition', all(not r['bailed'] and r['peak_m'] > 3.6 for q in report['quarter'].values() for r in q.values()),
          report['quarter'])
    check('pushes_over_planks', all(p['planks']['distance_m'] >= .8 * p['flat']['distance_m'] and (p['planks']['slowest_once_moving_mps'] or 0) > 3
                                     and not p['planks']['bailed'] for p in report['pushing'].values()), report['pushing'])

    # Surfaces: a 4 s coast from 6 m/s and 6 s of pushing from a standstill on flat ground of each kind.
    report['surfaces'] = {}
    for name, (physics, sound) in SURFACES.items():
        packed = [physics << 7 | sound] * len(feel.FLAT)
        report['surfaces'][name] = {
            'coast': roll(args.binary, args.simulation_package, feel.FLAT, f'coast_{name}', 6, surfaces=packed),
            'push': roll(args.binary, args.simulation_package, feel.FLAT, f'push_{name}', 0, 360, lambda f: (feel.PUSH, [0, 0], [0, 0]), packed),
        }
    s = report['surfaces']
    check('reports_surface', all(s[n]['coast']['surface'][:2] == list(SURFACES[n]) for n in s), {n: s[n]['coast']['surface'] for n in s})
    coast = {n: s[n]['coast']['distance_m'] for n in s}
    check('smooth_rides_well', min(coast['concrete'], coast['wood']) > 20 and abs(coast['concrete'] - coast['wood']) < .1, coast)
    check('rough_rides_well', min(coast['asphalt'], coast['stone']) > .9 * coast['concrete'], coast)
    check('dirt_rides_poorly', coast['dirt'] < .6 * coast['concrete'] and s['dirt']['coast']['end_speed_mps'] < 1, coast)
    check('grass_rides_worst', coast['grass'] < coast['dirt'] and s['grass']['push']['distance_m'] < s['dirt']['push']['distance_m'], coast)
    check('pushing_still_moves', all(s[n]['push']['distance_m'] > 5 for n in s), {n: s[n]['push'] for n in s})

    report['passed'] = not failures
    report['failures'] = failures
    (OUTPUT / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('passed', 'failures')}, indent=2))
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
