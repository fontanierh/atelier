#!/usr/bin/env python3
"""A dry run of a Ride playtest on the island, with the player's own pad inputs (atelier play yorimichi).

Run against the running game:  atelier qa yorimichi ride_e2e        (after quitting:  ... ride_e2e --post)
The game starts on foot at the island's start. Every input goes through the pad keys a player presses (InputKey on the
player controller: the face buttons, the D-pad, the sticks, the triggers); on foot the stick is mirrored through the
bridge's stick verb (live.drive), as the game's own move action does. Nothing is placed, launched or scripted on the
board. No console command is used; the character switch calls the Esc menu's own function (live.L.switch_character). A "travel cut" (a teleport on foot) takes
the rider to the sailboat's beach, and recovers a ride that got stuck; the report lists every one.

The run, in order: the first mounts at the start (stand, run, sprint) and a dismount; the road (a carve, a brake, a push
from rest, an ollie, a kickflip) and the access path down to Sunset Pier; on the pier's promenade lanes Flick-It tricks,
a manual, a grab, a grind on the red flatbar and two powerslides (the pad's down-diagonal, then the C key); an air on
the east return quarter; a stand dismount, the board carried past its hold time, recalled, put away for the sword and
an interaction; a slam at speed; dismounts into a run, fast, from a grab in the air and a kick-out, each followed by a
mount from the run; a caveman; a bail off a grind on the long flatbar; Modori's mount, ride, bail and dismount; the
sailboat from the beach. Every frame records the skate state, the camera, the frame time and the
board's sound loops; the sound log records the one-shots.

Writes build/yorimichi/skateqa/ride_e2e.json and ride_e2e.md (the step table, the numbers, the screenshots in
skateqa/ride_e2e/), every frame in skateqa/ride_e2e/rows.json and the sounds in skateqa/ride_e2e/audio.json.
--post (after the game has quit) adds the guard's memory peak and the whole game log's counts.
"""
import argparse
import bisect
import calendar
import json
import math
import re
import time
from pathlib import Path

import skate as qa

# In-game code this scenario sends to the running game, kept as real files so it can be read, linted and diffed.
INGAME = Path(__file__).resolve().parent / 'ingame'

OUT = qa.yori.OUT / 'skateqa'
DIR = OUT / 'ride_e2e'
PARK = json.loads((qa.GAME / 'world/regions/skatepark/park.json').read_text())
OX, OY, OZ = PARK['origin']

# The road from the island's start to the access path (world.json 'road', every 4th point, UE cm), a rounded junction,
# and the access path down to the pier entrance (skatepark layout.py path_layout's filleted route, every 4 m).
ROAD = [(-25526, 9951), (-25127, 9981), (-24728, 10005), (-24328, 10021), (-23928, 10029), (-23528, 10026),
        (-23129, 10009), (-22730, 9975), (-22333, 9924), (-21939, 9860), (-21546, 9783), (-21156, 9695),
        (-20768, 9598), (-20382, 9494), (-19997, 9383), (-19614, 9269), (-19231, 9151), (-18849, 9033),
        (-18467, 8915), (-18084, 8800), (-17700, 8688), (-17315, 8581), (-16927, 8482), (-16540, 8381),
        (-16154, 8276)]
JUNCTION = [(-15920, 8215), (-15720, 8200), (-15585, 8265)]
PATH = [(-15504, 8362), (-15409, 8750), (-15387, 9148), (-15363, 9546), (-15190, 9903), (-14892, 10165),
        (-14515, 10291), (-14119, 10350), (-13723, 10408), (-13328, 10467), (-12936, 10545), (-12565, 10694),
        (-12232, 10915), (-11950, 11197), (-11729, 11529), (-11565, 11894), (-11407, 12261), (-11248, 12629),
        (-11090, 12996), (-10932, 13364), (-10774, 13731), (-10616, 14098), (-10483, 14475), (-10412, 14869),
        (-10400, 15268), (-10400, 15668), (-10400, 16068), (-10400, 16468), (-10400, 16800)]
BEACH = ((-21600, 16900), 80.0)    # the sailboat QA's mainland beach
TURN, TIGHT = 330.0, 250.0         # cm/s through the U-turns, and the junction's right angle


def ue(px, py):
    """Park-local metres (park.json: x east, y north) -> UE cm."""
    return ((OX + px) * 100.0, -(OY + py) * 100.0)


def park(x, y):
    return (x / 100.0 - OX, -y / 100.0 - OY)


def line(a, b, step=2.0):
    n = max(1, int(math.dist(a, b) / step))
    return [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(1, n + 1)]


def arc(c, r, a0, a1, step=1.2):
    n = max(2, int(abs(math.radians(a1 - a0)) * r / step))
    return [(c[0] + r * math.cos(math.radians(a0 + (a1 - a0) * k / n)),
             c[1] + r * math.sin(math.radians(a0 + (a1 - a0) * k / n))) for k in range(1, n + 1)]


def route(*parts):
    """Park-local pieces (lists of points, or (points, cap) for a speed cap) -> (UE points, caps)."""
    pts, caps = [], []
    for part in parts:
        points, cap = part if isinstance(part, tuple) else (part, None)
        for p in points:
            q = ue(*p)
            if pts and math.dist(q, pts[-1]) < 50:
                continue
            pts.append(q)
            caps.append(cap)
    return pts, caps


# Sunset Pier (park.json, layout.py): the promenade lanes y = 58 (between the manual pads and the gardens), y = 48
# (between the rails and the pads) and y = 50.5; the rails on y = 43 (red x -28..-10, square 4..24, long 41..61); the
# east return quarter at x 68..73, y 18..34 (coping x = 70.025, 2.15 m), approached along y = 27.
ENTRY = [(6, 66), (6, 64), (5.6, 61.6), (4.4, 59.6), (2.6, 58.4), (0.5, 58.0)]
W1 = line((0.5, 58), (-62, 58))
WT1 = arc((-67, 53), 5.0, 90, 270)                      # west U-turn, y 58 -> y 48
E1 = (line((-67, 48), (-58, 48)) + [(-54, 47.2), (-50, 45.2), (-46.5, 43.5), (-44, 43.0)] + line((-44, 43), (-6, 43))
      + [(-3, 44.0), (0, 46.0), (3, 47.6), (6, 48.0)] + line((6, 48), (30, 48)))
QUARTER = [(34, 46.6), (38, 42.4), (42, 36.6), (46, 31.6), (50.5, 28.6), (55, 27.4), (59, 27.0)] + line((59, 27), (75, 27))
W2 = [(40, 46.8), (36, 48)] + line((36, 48), (-62, 48))
WT2 = arc((-67, 53), 5.0, 270, 90)                      # west U-turn, y 48 -> y 58
E2 = (line((-67, 58), (6, 58)) + [(10, 57.4), (14, 55.6), (18, 52.4), (21, 48.6), (24, 45.6), (27, 43.8), (30, 43.1)]
      + line((30, 43), (66, 43)))
ET2 = arc((66, 46.75), 3.75, -90, 90)                   # east U-turn, y 43 -> y 50.5
W3 = line((66, 50.5), (-60, 50.5))
RAIL_RED = (-28.0, -10.0)
RAIL_LONG = (41.0, 61.0)
COPING_X = 70.025
LOOP_SOUNDS = ('roll', 'grind', 'slide', 'skid', 'scrape')


# ---------------------------------------------------------------------------------------------------------------
# In the game: one per-frame behaviour records the frame and plays the pad: a timeline of presses, triggers on the skate
# state, and a pilot that steers with the left stick and pushes (A) or brakes (B), or walks with the stick on foot.
GAME = (INGAME / 'ride_e2e' / 'game.py').read_text()


# ---------------------------------------------------------------------------------------------------------------
# The driver: waits on the game's clock, keeps every frame, and checks.
ROWS, EVENTS, ERRORS, CHECKS, CUTS = [], [], [], [], []
STATE = {'T': 0.0, 'done': {}, 'step': 'setup', 'log': None}


def g(code):
    return qa.py(code)


def drain():
    out = g("import json\nprint(json.dumps({'rows': live.E2E.ROWS, 'ev': live.E2E.EV, 'err': live.E2E.ERR, 'T': live.E2E.T, "
            "'done': live.E2E.DONE}))\nlive.E2E.ROWS = []; live.E2E.EV = []; live.E2E.ERR = []")
    d = json.loads(out.strip().splitlines()[-1])
    ROWS.extend(d['rows'])
    EVENTS.extend(d['ev'])
    ERRORS.extend(d['err'])
    STATE['T'], STATE['done'] = d['T'], d['done']
    return d


def now():
    return STATE['T']


def last():
    return ROWS[-1] if ROWS else {'f': {}, 'at': [0, 0, 0], 'n': 0, 'T': 0, 'wdt': .016, 'dt': .016, 's': '-'}


def wait(seconds=None, until=None, timeout=20.0, poll=.25):
    """Wait on the game's clock: `seconds` of its time, or until `until(row)` holds for a recorded frame (every frame is
    checked), at most `timeout` game seconds (and four times that on the wall clock). Returns the frame, or None."""
    drain()
    start, wall, seen = now(), time.monotonic(), len(ROWS)
    while True:
        if until:
            for r in ROWS[seen:]:
                if until(r):
                    return r
            seen = len(ROWS)
        if seconds is not None and now() - start >= seconds:
            return last()
        if now() - start >= timeout or time.monotonic() - wall > timeout * 4 + 10:
            return None
        time.sleep(poll)
        drain()


def stalled(seconds=5.0):
    """An `until` that holds when the rider has been under 40 cm/s for `seconds` of game time."""
    since = {'t': None}

    def test(r):
        if speed(r) > 40:
            since['t'] = None
            return False
        since['t'] = r['T'] if since['t'] is None else since['t']
        return r['T'] - since['t'] > seconds
    return test


def mark():
    drain()
    return last()['n'] + 1 if ROWS else 0


def seg(n0, n1=None):
    return [r for r in ROWS if r['n'] >= n0 and (n1 is None or r['n'] < n1)]


def step(name):
    """Label the frames from now on with a playtest step (the brief's 1..9)."""
    STATE['step'] = name
    g(f"live.E2E.STEP = {name!r}")


def check(name, ok, note, **numbers):
    shots = numbers.pop('shots', [])
    CHECKS.append({'step': STATE['step'], 'name': name, 'ok': None if ok is None else bool(ok), 'note': note,
                   'numbers': numbers, 'shots': shots, 'T': round(now(), 2)})
    print(('SKIP' if ok is None else 'PASS' if ok else 'FAIL') + f' [{STATE["step"]}] {name}: {note}', flush=True)


def shot(name):
    g(f"live.E2E.shot({name!r})")
    return f'ride_e2e/{name}.png'


def f(r, key, default=''):
    return r['f'].get(key, default)


def num(r, key, default=0.0):
    try:
        return float(r['f'].get(key, default))
    except (TypeError, ValueError):
        return default


def vec(text):
    try:
        return tuple(float(x) for x in str(text).strip().strip('()').split(','))
    except ValueError:
        return None


def speed(r):
    v = vec(f(r, 'vel', '0,0,0')) or (0, 0, 0)
    return math.hypot(v[0], v[1])


def heading(r):
    v = vec(f(r, 'vel', '0,0,0')) or (0, 0, 0)
    return math.degrees(math.atan2(v[1], v[0]))


def mode(r):
    return f(r, 'mode', '0')


def riding(r):
    return mode(r) in ('1', '2', '3')


def px(r):
    return park(r['at'][0], r['at'][1])


def counter(r, key):
    try:
        return int(r['f'].get(key, 0))
    except ValueError:
        return 0


def combos(rows):
    return list(dict.fromkeys(f(r, 'combo') for r in rows if f(r, 'combo')))


def clips(rows):
    seen = []
    for r in rows:
        c = (f(r, 'foot', '-'), f(r, 'clip', '-'))
        if c[1] not in ('-', '') and (not seen or seen[-1] != c):
            seen.append(c)
    return seen


def clip_of(rows, foot):
    return next((c for ft, c in clips(rows) if ft == foot), '-')


def clip_line(rows, limit=8):
    return ' > '.join(f'{ft}:{c}' for ft, c in clips(rows)[:limit]) or '(no clips)'


def board_line(rows):
    """The board's places in order, its fading frames, frames hidden while somewhere, and pops (shown changing > .5 in
    one frame)."""
    places = []
    for r in rows:
        b = f(r, 'board', '?')
        if not places or places[-1] != b:
            places.append(b)
    sh = [num(r, 'shown') for r in rows]
    fading = sum(1 for s in sh if 0 < s < 1)
    pops = sum(1 for a, b in zip(sh, sh[1:]) if abs(b - a) > .5)
    hidden = sum(1 for r in rows if f(r, 'board') in ('ride', 'hand', 'world') and num(r, 'shown') > 0 and f(r, 'vis') != '1')
    return {'places': '>'.join(places), 'fading': fading, 'pops': pops, 'hidden': hidden}


def where(r):
    return f"T={r['T']:.2f} {r['s']} mode={mode(r)} foot={f(r, 'foot', '-')} clip={f(r, 'clip', '-')}@{f(r, 't', '-')}"


def shot_frames():
    """The frames a screenshot stalls: the one that takes it and the next (a 0.1-0.25 s tick); the QA's, not the game's."""
    out = set()
    for e in EVENTS:
        if e[3] == 'shot':
            out.update((e[0], e[0] + 1))
    return out


def jumps(rows):
    """The worst frame-to-frame jumps: the character beyond its speed's travel, the hips beyond that (not in a bail),
    the camera's move (raw, and beyond the character's), the camera's turn, per tick of the game. Left out: frames after
    a travel cut or a character switch, the screenshots' frames, and ticks over 0.1 s (a hitch, counted by frame_stats)."""
    w = {'move_cm': 0.0, 'hip_cm': 0.0, 'cam_raw_cm': 0.0, 'cam_cm': 0.0, 'cam_deg': 0.0, 'cam_over30': 0, 'hip_over12': 0}
    worst = {}
    skip = shot_frames()
    for a, b in zip(rows, rows[1:]):
        if b.get('x') or a.get('x') or b['n'] != a['n'] + 1 or b['n'] in skip or a['n'] in skip or b['wdt'] > .1:
            continue
        travel = max(speed(a), speed(b), 1.0) * b['wdt']
        moved = math.dist(a['at'], b['at'])
        w['move_cm'] = max(w['move_cm'], moved - travel - 2.0)
        ha, hb = vec(f(a, 'hip', '')), vec(f(b, 'hip', ''))
        if ha and hb and mode(a) != '4' and mode(b) != '4':
            hip = math.dist(ha, hb) - travel
            if hip > w['hip_cm']:
                w['hip_cm'] = hip
                worst['hip'] = where(b)
            w['hip_over12'] += hip > 12
        cam = math.dist(a['cam'][:3], b['cam'][:3])
        if cam > w['cam_raw_cm']:
            w['cam_raw_cm'] = cam
            worst['cam'] = where(b)
        w['cam_over30'] += cam > 30
        w['cam_cm'] = max(w['cam_cm'], cam - max(moved, travel))
        pa, ya, pb, yb = (math.radians(x) for x in (a['cam'][3], a['cam'][4], b['cam'][3], b['cam'][4]))
        da = (math.cos(pa) * math.cos(ya), math.cos(pa) * math.sin(ya), math.sin(pa))
        db = (math.cos(pb) * math.cos(yb), math.cos(pb) * math.sin(yb), math.sin(pb))
        w['cam_deg'] = max(w['cam_deg'], math.degrees(math.acos(max(-1.0, min(1.0, sum(x * y for x, y in zip(da, db)))))))
    out = {k: round(v, 1) if isinstance(v, float) else v for k, v in w.items()}
    out['worst_at'] = worst
    return out


def smooth(j):
    return j['cam_over30'] == 0 and j['cam_cm'] <= 30 and j['hip_cm'] <= 12


def frame_stats(rows):
    """Frame times without the screenshots' frames (their stall is the QA's)."""
    skip = shot_frames()
    rows = [r for r in rows if r['n'] not in skip]
    ms = sorted(r['dt'] * 1000 for r in rows)
    if not ms:
        return {}
    pick = lambda p: ms[min(len(ms) - 1, round((len(ms) - 1) * p))]
    slow = [r for r in rows if r['dt'] > .025]
    return {'frames': len(ms), 'p50_ms': round(pick(.5), 1), 'p99_ms': round(pick(.99), 1), 'worst_ms': round(ms[-1], 1),
            'over_25ms': len(slow),
            'slow': [f"{r['dt'] * 1000:.0f} ms at {where(r)} board={f(r, 'board', '-')} {speed(r):.0f} cm/s"
                     + (' (after a cut/switch)' if r.get('x') else '') for r in sorted(slow, key=lambda r: -r['dt'])[:8]]}


def air_height(rows):
    """Height of the deck's highest point above where it left the ground, and the air frames."""
    air = [i for i, r in enumerate(rows) if mode(r) == '2']
    if not air:
        return 0.0, 0
    start = rows[max(0, air[0] - 1)]
    base = (vec(f(start, 'deck', '')) or start['at'])[2]
    top = max((vec(f(r, 'deck', '')) or r['at'])[2] for r in rows[air[0]:air[-1] + 1])
    return top - base, len(air)


def sounds(rows, audio):
    """The board's sounds in these frames: one-shots from the sound log (by cue), loops by their top volume."""
    if not rows:
        return {'one_shots': {}, 'loop_top_volume': dict.fromkeys(LOOP_SOUNDS, 0.0)}
    n0, n1 = rows[0]['n'], rows[-1]['n'] + 1
    shots = {}
    for e in audio:
        if n0 <= e.get('frame', -1) < n1:
            name = e.get('sound', '?').rsplit('.', 1)[-1]
            key = re.sub(r'[_\d]+$', '', name) or name
            shots[key] = shots.get(key, 0) + 1
    top = dict.fromkeys(LOOP_SOUNDS, 0.0)
    loops = next((r['loops'] for r in reversed(ROWS) if r['n'] < n0 and 'loops' in r), None)
    for r in rows:
        loops = r.get('loops', loops)
        if loops:
            vals = loops.split()
            for i, name in enumerate(LOOP_SOUNDS):
                if 2 * i < len(vals):
                    top[name] = max(top[name], float(vals[2 * i]))
    return {'one_shots': shots, 'loop_top_volume': {k: round(v, 2) for k, v in top.items()}}


# ---- the player's actions (all through the pad) ----

def tap(key, dt=0.0):
    g(f"live.E2E.tap({key!r}, {dt})")


def pilot(kind, pts, caps=None, **kw):
    args = ''.join(f', {k}={v!r}' for k, v in kw.items())
    g(f"live.E2E.set_pilot({kind!r}, {[(round(p[0], 1), round(p[1], 1)) for p in pts]!r}, {caps!r}{args})")


def pset(**kw):
    g('P = live.E2E.PILOT\nif P: P.update(' + ', '.join(f'{k}={v!r}' for k, v in kw.items()) + ')')


def stop_pilot():
    g("live.E2E.PILOT = None\nfor k in ('A','B','LX','LY','L3','RX','RY','LT','RT','C'): live.E2E.pad(k, 0)\nlive.drive(0)")


def bail_combo(hold=.5):
    """Both stick clicks with both triggers held: the deliberate bail."""
    g(f"live.E2E.at(0, ('L3', 1), ('R3', 1), ('LT', 1), ('RT', 1), lambda: live.E2E.ev('bail_combo'))\n"
      f"live.E2E.at({hold}, ('L3', 0), ('R3', 0), ('LT', 0), ('RT', 0))")


def flick(name, dt=0.0):
    g(f"live.E2E.flick({name!r}, {dt})")


def brake_to_stop(limit=60.0, timeout=6.0, keep=False):
    pset(brake=True)
    r = wait(until=lambda r: (riding(r) and speed(r) < limit) or not riding(r), timeout=timeout)
    if not keep:
        pset(brake=False)
    return r


def travel_cut(why, x, y, yaw):
    """A teleport on foot (listed in the report); the rider is first taken off the board with the top face button."""
    stop_pilot()
    if riding(last()):
        tap('Y')
        wait(until=lambda r: mode(r) == '0', timeout=6)
    g(f"live.E2E.SKIPTO = live.E2E.N + 60; live.drive(0); live.teleport(live.L.ground_at(live.v({x}, {y}, 300)), {yaw})")
    wait(1.5)
    CUTS.append({'step': STATE['step'], 'why': why, 'to': [round(x), round(y)], 'T': round(now(), 2)})
    print(f'TRAVEL CUT [{STATE["step"]}] {why}', flush=True)


def ensure_on_foot():
    if mode(last()) == '4':
        wait(until=lambda r: mode(r) in ('0', '1'), timeout=10)
    if riding(last()):
        if speed(last()) > 140:
            pset(brake=True)
            wait(until=lambda r: speed(r) < 60 or not riding(r), timeout=6)
        stop_pilot()
        tap('Y')
        wait(until=lambda r: mode(r) == '0', timeout=5)
        wait(1.0)
    stop_pilot()


def ride_on(pts, caps, **kw):
    """After a bail the rider gets up and rides on; if he stands instead, the top face button gets him back on."""
    if not riding(last()):
        wait(until=lambda r: mode(r) == '1', timeout=7)
    if not riding(last()):
        stop_pilot()
        tap('Y')
        wait(until=lambda r: mode(r) == '1', timeout=4)
    pilot('ride', pts, caps, **kw)
    return riding(last())


def mount(name, expect, gait=None, seconds=1.8):
    """Get on with the top face button: from a stand, or after `seconds` of `gait` along the walk pilot's path (the stick
    is held through the hop on and let go once on the board, as a player would)."""
    n0 = mark()
    if gait:
        pset(gait=gait)
        wait(seconds)
    entry = speed(last())
    g("live.E2E.when('onboard', lambda f: f.get('mode') in ('1', '2', '3'), live.E2E.stop_walk)")
    tap('Y')
    r = wait(until=lambda r: mode(r) == '1', timeout=4)
    wait(.8)
    g("live.E2E.unwhen('onboard'); live.E2E.stop_walk()")
    rows = seg(n0)
    clip = clip_of(rows, 'mount')
    i = next((k for k, x in enumerate(rows) if mode(x) == '1'), None)
    near = rows[max(0, i - 6):i + 10] if i is not None else []
    worst_dt = max((x['dt'] for x in near), default=0) * 1000
    frozen = sum(1 for a, b in zip(near, near[1:]) if speed(b) > 100 and math.dist(a['at'], b['at']) < .2)
    j, b = jumps(rows), board_line(rows)
    ok = r is not None and clip.startswith(expect) and b['pops'] == 0 and b['hidden'] == 0 and smooth(j) and frozen == 0
    check(name, ok, f"{clip} from {entry:.0f} cm/s, riding {(rows[i]['T'] - rows[0]['T']) if i is not None else -1:.2f} s after "
          f"the start; ride start: worst frame {worst_dt:.0f} ms, {frozen} frozen frames; "
          f"{speed(rows[-1]):.0f} cm/s after; jumps {j}; board {b}", clip=clip, entry_cm_s=round(entry),
          start_worst_ms=round(worst_dt, 1), frozen_frames=frozen, jumps=j, board=b)
    return r is not None


def dismount(name, expect, run=0.0, path=None):
    """Off with the top face button (no push, no brake held), then `run` seconds running along `path` (the stick held)."""
    n0 = mark()
    g('live.E2E.coast(True)')
    wait(.1)
    before = speed(last())
    tap('Y')
    r = wait(until=lambda r: mode(r) == '0', timeout=4)
    if r is not None and run and path:
        pilot('walk', path[0], path[1], name='run-off', gait='run')
    wait(max(1.4, run))
    rows = seg(n0)
    clip = clip_of(rows, 'dismount')
    i = next((k for k, x in enumerate(rows) if mode(x) == '0'), None)
    after = speed(rows[i]) if i is not None else 0.0
    carry = sum(1 for x in rows if f(x, 'foot') == 'carry')
    j, b = jumps(rows), board_line(rows)
    ok = r is not None and (expect is None or (clip == expect and carry > 0)) and b['pops'] == 0 and smooth(j)
    check(name, ok, f"{clip} at {before:.0f} cm/s -> {after:.0f} on foot, {carry} carry frames, {speed(rows[-1]):.0f} cm/s "
          f"after {rows[-1]['T'] - rows[0]['T']:.1f} s; {clip_line(rows)}; board {b}; jumps {j}",
          clip=clip, before_cm_s=round(before), after_cm_s=round(after), carry_frames=carry, jumps=j, board=b)
    return r is not None


def trick(name, kind, want, x_at=None, coast_before=.35, seconds=2.0):
    """A Flick-It trick (or 'manual', 'grab') while riding, when the rider passes park x `x_at` (or now)."""
    if x_at is not None:
        ux = ue(x_at, 0)[0]
        r = last()
        v = vec(f(r, 'vel', '0,0,0')) or (1, 0, 0)
        sign = 1 if v[0] >= 0 else -1
        if (r['at'][0] - ux) * sign > 100:
            check(name, None, f'the lane ran out before it (at x={px(r)[0]:.1f}, wanted {x_at})')
            return None
        if not wait(until=lambda r: (r['at'][0] - ux) * sign >= 0, timeout=20):
            check(name, False, f'never reached x={x_at} (at {px(last())[0]:.1f}, {px(last())[1]:.1f}, mode {mode(last())})')
            return False
    n0 = mark()
    g('live.E2E.coast(True)')
    wait(coast_before)
    before = last()
    if kind == 'manual':
        g("live.E2E.at(0, ('RY', .5)); live.E2E.at(1.8, ('RY', 0))")
    elif kind == 'grab':
        flick('ollie')
        g("live.E2E.when('grab', lambda f: live.E2E.AIR > .08, lambda: (live.E2E.pad('RT', 1), "
          "live.E2E.later(.32, lambda: live.E2E.pad('RT', 0))))")
    else:
        flick(kind)
    g(f"live.E2E.later({seconds}, lambda: live.E2E.coast(False))\n"
      f"live.E2E.when('peak', lambda f: f.get('mode') == '2' and (live.E2E.vec(f.get('vel', '')) or (0, 0, 1))[2] < 0, "
      f"lambda: live.E2E.shot({name!r}))\n"
      f"t0 = live.E2E.T\nlive.E2E.when('hud', lambda f, t0=t0: live.E2E.LAND > t0, "
      f"lambda: live.E2E.later(.3, lambda: live.E2E.shot({name + '_hud'!r})))"
      + (f"\nlive.E2E.later(1.2, lambda: live.E2E.shot({name!r}))" if kind == 'manual' else ''))
    wait(seconds + .4)
    g("live.E2E.unwhen('peak', 'grab', 'hud')")
    rows = seg(n0)
    after = last()
    height, air = air_height(rows)
    seen = combos(rows)
    bails = counter(after, 'bails') - counter(before, 'bails')
    manual = sum(1 for r in rows if f(r, 'manual') == '1')
    landed = mode(after) == '1' and bails == 0
    named = bool(seen) if kind == 'grab' else any(want.lower() in c.lower() for c in seen + [f(after, 'last')])
    ok = landed and named and (kind != 'manual' or manual > 30)
    hud = any(e[3] == 'shot' and e[4] == name + '_hud' for e in EVENTS if e[0] >= n0)
    check(name, ok, f"{' / '.join(seen) or '(no trick line)'}; last={f(after, 'last', '-')}; {speed(before):.0f} cm/s, "
          f"{height:.0f} cm high, {air} air frames, {manual} manual frames, bails {bails}, mode {mode(after)} after",
          combos=seen, height_cm=round(height), air_frames=air, manual_frames=manual, bails=bails,
          shots=([f'ride_e2e/{name}.png'] if air or kind == 'manual' else []) + ([f'ride_e2e/{name}_hud.png'] if hud else []))
    return ok


def bail_check(name, rows, ride_on_after=True):
    """A bail's numbers: the slide, the get-up where the body lay, the board's fade or step, riding on."""
    bail = [i for i, r in enumerate(rows) if mode(r) == '4']
    if not bail:
        check(name, False, f'no bail (mode 4 never seen; {clip_line(rows)})')
        return
    b0, b1 = bail[0], bail[-1]
    v0 = speed(rows[max(0, b0 - 1)])
    hip0, hip1 = vec(f(rows[b0], 'hip', '')), vec(f(rows[b1], 'hip', ''))
    slide = math.dist(hip0[:2], hip1[:2]) if hip0 and hip1 else -1
    up = next((i for i in range(b1 + 1, len(rows)) if mode(rows[i]) in ('0', '1')), None)
    near = math.dist(rows[up]['at'][:2], hip1[:2]) if up is not None and hip1 else -1
    board = board_line(rows[b0:])
    stepped = 'away' not in board['places'] and board['fading'] == 0
    tumble = max((math.dist(vec(f(a, 'hip', '')) or (0, 0, 0), vec(f(b, 'hip', '')) or (0, 0, 0)) / max(b['wdt'], 1e-3)
                  for a, b in zip(rows[b0:b1], rows[b0 + 1:b1 + 1])), default=0)
    j = jumps(rows[b1:])
    end = rows[-1]
    rode = mode(end) == '1' and speed(end) > 150
    ok = (up is not None and 0 <= near < 60 and slide > 50 and board['pops'] == 0 and board['hidden'] == 0
          and (rode or not ride_on_after))
    check(name, ok, f"from {v0:.0f} cm/s: {(rows[b1]['T'] - rows[b0]['T']):.2f} s down, the hips slid {slide:.0f} cm "
          f"(fastest {tumble:.0f} cm/s), up {near:.0f} cm from where the body lay"
          f"{' (mode ' + mode(rows[up]) + ')' if up is not None else ' (never up)'}; board {board} -> "
          f"{'stepped onto' if stepped else 'faded out and back'}; then mode {mode(end)} at {speed(end):.0f} cm/s; "
          f"{clip_line(rows[b0:])}; after the get-up {j}",
          from_cm_s=round(v0), down_s=round(rows[b1]['T'] - rows[b0]['T'], 2), slide_cm=round(slide), tumble_cm_s=round(tumble),
          up_from_body_cm=round(near), stepped=stepped, rode_on=rode, end_mode=mode(end), end_cm_s=round(speed(end)),
          jumps=j, board=board, shots=[f'ride_e2e/{name}_down.png', f'ride_e2e/{name}_up.png'])


def bail_now(name):
    n0 = mark()
    g(f"live.E2E.when('down', lambda f: f.get('mode') == '4', lambda: live.E2E.later(.45, lambda: live.E2E.shot('{name}_down')))\n"
      f"live.E2E.when('up', lambda f: f.get('mode') in ('0', '1') and live.E2E.PREV == '4', "
      f"lambda: live.E2E.later(.3, lambda: live.E2E.shot('{name}_up')))")
    bail_combo()
    if not wait(until=lambda r: mode(r) == '4', timeout=3):
        check(name, False, f'the bail input gave no bail (mode {mode(last())}, {speed(last()):.0f} cm/s)')
        g("live.E2E.unwhen('down', 'up')")
        return False
    wait(until=lambda r: mode(r) in ('0', '1'), timeout=12)
    wait(2.4)
    g("live.E2E.unwhen('down', 'up')")
    bail_check(name, seg(n0))
    return True


def hold_check(name, n_carry):
    """The board in the hand dissolves after its hold time (BoardHoldTime 6 s)."""
    r = wait(until=lambda r: f(r, 'board') != 'hand', timeout=9)
    wait(1.2)
    rows = seg(n_carry)
    held = max((num(x, 'hold') for x in rows if f(x, 'board') == 'hand'), default=0.0)
    b = board_line(rows)
    gone = f(last(), 'board') == 'away' and f(last(), 'vis') == '0'
    check(name, r is not None and gone and b['pops'] == 0 and b['fading'] >= 4,
          f"held {held:.2f} s, then {b}; board {f(last(), 'board')}, vis {f(last(), 'vis')}",
          held_s=round(held, 2), board=b, shots=[shot(name)])


def recall(name):
    n0 = mark()
    tap('DR')
    r = wait(until=lambda r: f(r, 'board') == 'hand' and num(r, 'shown') >= 1, timeout=3)
    wait(.4)
    rows = seg(n0)
    b = board_line(rows)
    took = (r['T'] - rows[0]['T']) if r else None
    check(name, r is not None and b['pops'] == 0 and b['hidden'] == 0,
          f"board {f(last(), 'board')} (shown {f(last(), 'shown')}), foot {f(last(), 'foot')}, "
          f"{'in the hand after ' + format(took, '.2f') + ' s' if r else 'never in the hand'}; {b}", seconds=took, board=b)
    return r is not None


def sword_drawn():
    out = g('print(live.E2E.sword())').strip().splitlines()[-1]
    return {'True': True, 'False': False}.get(out)


def hands(name, key, works, settle=1.2, shot_after=.6):
    """With the board in the hand, an action that needs the hands: the board must go without a pop, the action work."""
    if f(last(), 'board') != 'hand':
        recall(name + '_recall_first')
    n0 = mark()
    tap(key)
    g(f"live.E2E.later({shot_after}, lambda: live.E2E.shot({name!r}))")
    r = wait(until=lambda r: f(r, 'board') != 'hand', timeout=3)
    wait(settle)
    rows = seg(n0)
    b = board_line(rows)
    worked, how = works()
    went = r is not None
    check(name, went and worked and b['pops'] == 0 and b['hidden'] == 0,
          f"board {'went after ' + format(r['T'] - rows[0]['T'], '.2f') + ' s' if went else 'stayed in the hand'} ({b}); {how}",
          board_went=went, worked=worked, board=b, shots=[f'ride_e2e/{name}.png'])


# ---------------------------------------------------------------------------------------------------------------

def run():
    qa.py((qa.GAME / 'scenarios/skate_live_skate.py').read_text())
    qa.settle(minimum=50, seconds=3, limit=150)
    DIR.mkdir(parents=True, exist_ok=True)
    g(GAME)
    STATE['goofy'] = goofy()
    g(f"live.E2E.SHOTDIR = {str(DIR)!r}; live.E2E.GOOFY = {STATE['goofy']}; live.L.audio_log('start')")
    STATE['log'] = newest_log()
    step('1_first_mount')
    wait(1.0)
    r0 = last()
    road_d = min(math.dist(r0['at'][:2], p) for p in ROAD)
    check('start_on_foot', mode(r0) == '0' and f(r0, 'board') in ('away', 'hand'),
          f"mode {mode(r0)}, mm {f(r0, 'mm')}, board {f(r0, 'board')}, at UE ({r0['at'][0]:.0f}, {r0['at'][1]:.0f}), "
          f"{road_d:.0f} cm from the road", road_cm=round(road_d), shots=[shot('start')])
    if road_d > 1500:
        travel_cut('the game did not start at the island start', ROAD[0][0], ROAD[0][1], 2.0)
    road_path = ROAD + JUNCTION + PATH
    road_caps = [None] * len(ROAD) + [TIGHT] * len(JUNCTION) + [TIGHT] * 2 + [None] * (len(PATH) - 2)
    road = (road_path, road_caps)

    # 1. Walk, then the first mounts (stand, run, sprint) with the top face button; a stand and a run dismount.
    n0 = mark()
    pilot('walk', road_path, name='walk', gait='walk', mag=.5)
    wait(2.5)
    g('live.E2E.stop_walk()')
    rows = seg(n0)
    walked = math.dist(rows[0]['at'][:2], rows[-1]['at'][:2])
    top = max(map(speed, rows))
    check('walk', walked > 50 and top > 20 and all(mode(r) == '0' for r in rows),
          f"walked {walked:.0f} cm in {rows[-1]['T'] - rows[0]['T']:.1f} s, top {top:.0f} cm/s (stick .5, walk gait)",
          walked_cm=round(walked), top_cm_s=round(top))
    wait(.8)
    first = mount('mount_stand_first', 'BR_STAND_0_INTO_MOUNT')
    first_ride = next((r for r in ROWS if riding(r)), None)
    check('first_mount_rides', first_ride is not None,
          f"first riding frame at {first_ride['T']:.2f} s" if first_ride else 'never rode',
          shots=[shot('first_mount')])
    if first:
        pilot('ride', *road, name='road', v=380)
        wait(2.0)
        brake_to_stop(keep=True)
        stop_pilot()
        dismount('dismount_stand_road', 'BR_DISMOUNT_HI_INTO_STAND_0')
    pilot('walk', *road, name='road-walk', gait='run')
    mount('mount_run', 'BR_RUN_FWD_', gait='run', seconds=1.8)
    pilot('ride', *road, name='road', v=420)
    wait(until=lambda r: speed(r) > 380, timeout=4)
    dismount('dismount_run_road', 'BR_DISMOUNT_HI_INTO_RUN_FWD', run=1.0, path=road)
    pilot('walk', *road, name='road-walk', gait='sprint')
    mount('mount_sprint', 'BR_SPRINT_FWD_', gait='sprint', seconds=2.4)

    # 2. The road: a carve, a brake to a stop, a push from rest, an ollie, a kickflip.
    step('2_riding')
    pilot('ride', *road, name='road', v=560)
    wait(1.5)
    n0 = mark()
    pset(carve=[140.0, 2.6])
    g("live.E2E.later(1.4, lambda: live.E2E.shot('carve'))")
    wait(4.0)
    pset(carve=None)
    rows = [r for r in seg(n0) if speed(r) > 150]
    heads = [heading(r) for r in rows]
    rates = [((b - a + 180) % 360 - 180) / max(r['wdt'], 1e-3) for a, b, r in zip(heads, heads[1:], rows[1:])]
    bails = counter(rows[-1], 'bails') - counter(rows[0], 'bails') if rows else 0
    check('carve', bool(rates) and max(rates) > 15 and min(rates) < -15 and bails == 0,
          f"yaw rate {min(rates or [0]):.0f}..{max(rates or [0]):.0f} deg/s at {sum(map(speed, rows)) / max(1, len(rows)):.0f} cm/s, "
          f"bails {bails}", yaw_rate_min=round(min(rates or [0])), yaw_rate_max=round(max(rates or [0])), shots=['ride_e2e/carve.png'])
    n0 = mark()
    v0, t0 = speed(last()), now()
    r = brake_to_stop(limit=40, timeout=7, keep=True)
    rows = seg(n0)
    dist, dur = math.dist(rows[0]['at'][:2], rows[-1]['at'][:2]), now() - t0
    snd = sounds(rows, [])
    check('brake', r is not None and riding(rows[-1]) and speed(rows[-1]) < 60,
          f"{v0:.0f} -> {speed(rows[-1]):.0f} cm/s in {dur:.2f} s over {dist:.0f} cm "
          f"({(v0 - speed(rows[-1])) / max(dur, .01):.0f} cm/s2), the foot-brake loop's top volume {snd['loop_top_volume']['scrape']}",
          from_cm_s=round(v0), seconds=round(dur, 2), distance_cm=round(dist), scrape=snd['loop_top_volume']['scrape'])
    # The push from that stop (the junction's 250 cm/s cap is ahead, so only the push's direction and first metres count).
    n0 = mark()
    pset(brake=False, v=950)
    r = wait(until=lambda r: speed(r) > 200, timeout=3.5)
    wait(.3)
    rows = seg(n0)
    end = rows[-1]
    off = abs((heading(end) - num(end, 'yaw') + 180) % 360 - 180)
    creep = max((speed(x) for x in rows if f(x, 'push') == '1' and speed(x) < 60), default=0.0)
    check('push_from_rest', r is not None and f(end, 'fakie') == '0' and off < 45
          and counter(end, 'bails') == counter(rows[0], 'bails'),
          f"{speed(rows[0]):.0f} -> {speed(end):.0f} cm/s, over 200 cm/s "
          f"{format(r['T'] - rows[0]['T'], '.2f') + ' s' if r else 'never'} after A; the travel {heading(end):.0f} deg against "
          f"the nose {num(end, 'yaw'):.0f} deg ({off:.0f} off, {'fakie' if f(end, 'fakie') == '1' else 'nose first'}); "
          f"the board crept {creep:.0f} cm/s during the push's wind-up",
          after_cm_s=round(speed(end)), travel_off_nose_deg=round(off), fakie=f(end, 'fakie'), creep_cm_s=round(creep))
    pset(v=480)
    wait(until=lambda r: abs(speed(r) - 480) < 80, timeout=5)
    trick('ollie_road', 'ollie', 'Ollie')
    trick('kickflip_road', 'kickflip', 'Kickflip')

    # The path down to the pier (to 9 %, 4 m wide), then the promenade: y 58 west, the U-turn, y 48 east, the quarter.
    n0 = mark()
    pts, pcaps = route((ENTRY, TURN), (W1, None), (WT1, TURN), (E1, None), (QUARTER, None))
    pier = (road_path + pts, road_caps + pcaps)
    pilot('ride', *pier, name='pier', v=470, over=120.0)
    stuck = stalled(6.0)
    r = wait(until=lambda r: (px(r)[0] < 0 and abs(px(r)[1] - 58) < 3) or stuck(r), timeout=110)
    rows = seg(n0)
    arrived = r is not None and px(r)[0] < 0 and abs(px(r)[1] - 58) < 3
    xt = max((x['pilot'][2] for x in rows if x.get('pilot') and x['pilot'][0] == 'pier'), default=-1)
    bails = counter(rows[-1], 'bails') - counter(rows[0], 'bails')
    check('ride_to_pier', arrived and bails == 0,
          f"{'on the promenade' if arrived else 'stuck at ' + str(tuple(round(c) for c in rows[-1]['at']))} after "
          f"{rows[-1]['T'] - rows[0]['T']:.1f} s, top {max(map(speed, rows)):.0f} cm/s, off the line by at most {xt:.0f} cm, "
          f"bails {bails}", seconds=round(rows[-1]['T'] - rows[0]['T'], 1), top_cm_s=round(max(map(speed, rows))),
          cross_track_cm=round(xt), bails=bails, shots=[shot('pier_arrival')])
    if not arrived:
        travel_cut('the ride to the pier got stuck', *ue(-1, 58), 180.0)
        tap('Y')
        wait(until=lambda r: mode(r) == '1', timeout=4)
        pilot('ride', *pier, name='pier', v=470)
    pset(v=500)
    trick('heelflip', 'heelflip', 'Heelflip', x_at=-3)
    trick('shove_it', 'shove', 'Shove', x_at=-19)
    trick('manual', 'manual', 'Manual', x_at=-34, seconds=2.2)
    trick('grab_flat', 'grab', '', x_at=-50, seconds=1.6)

    # The red flatbar (y 43, x -28..-10): the line drifts onto the rail's line; an ollie ~3 m before it.
    pset(v=470)
    r = wait(until=lambda r: px(r)[1] < 44 and -45 < px(r)[0] < -35 and riding(r), timeout=40)
    n0 = mark()
    if r:
        g(f"live.E2E.when('rail', lambda f: f.get('mode') == '1' and live.E2E.AT[0] >= {ue(RAIL_RED[0] - 3.0, 0)[0]} "
          "- max(0.0, (float(f.get('speed', 470)) - 470.0) * .6), lambda: (live.E2E.coast(True), live.E2E.flick('ollie'), "
          "live.E2E.later(3.0, lambda: live.E2E.coast(False))))\n"
          "live.E2E.when('railshot', lambda f: f.get('mode') == '3', lambda: live.E2E.later(.4, lambda: live.E2E.shot('grind_red')))")
        wait(until=lambda r: px(r)[0] > RAIL_RED[1] + 3 or mode(r) == '4', timeout=14)
        wait(until=lambda r: mode(r) == '1', timeout=8)
        g("live.E2E.unwhen('rail', 'railshot')")
    rows = seg(n0)
    grind = [r for r in rows if mode(r) == '3']
    bails = counter(rows[-1], 'bails') - counter(rows[0], 'bails') if rows else 0
    snd = sounds(rows, [])
    check('grind_red_flatbar', bool(grind) and bails == 0 and bool(rows) and riding(rows[-1]),
          f"{len(grind)} grind frames over {math.dist(grind[0]['at'][:2], grind[-1]['at'][:2]) if grind else 0:.0f} cm "
          f"({' / '.join(combos(rows)) or 'no trick line'}), bails {bails}, mode {mode(rows[-1]) if rows else '-'} after; "
          f"grind loop top {snd['loop_top_volume']['grind']}", grind_frames=len(grind), combos=combos(rows),
          bails=bails, shots=['ride_e2e/grind_red.png'] if grind else [])
    if not riding(last()):
        ride_on(*pier, name='pier', v=470)

    # Powerslides on y 48: the pad's down-diagonal (the HUD's hint, the README), then the keyboard's C, both to the left.
    for name, items, back, x0 in (('powerslide_pad', "('LX', -.6), ('LY', -.8)", "('LX', 0), ('LY', 0)", 1.0),
                                  ('powerslide_c_key', "('C', 1), ('LX', -.6)", "('C', 0), ('LX', 0)", 13.0)):
        pset(v=640)
        wait(until=lambda r: px(r)[0] > x0 and speed(r) > 500 and abs(px(r)[1] - 48) < 1.2, timeout=6)
        n0 = mark()
        g(f"live.E2E.coast(True); live.E2E.steer(-.6)\nlive.E2E.at(0, {items})\n"
          f"live.E2E.at(.9, {back}, lambda: live.E2E.coast(False), lambda: live.E2E.steer(None))\n"
          f"live.E2E.later(.45, lambda: live.E2E.shot({name!r}))")
        wait(1.4)
        rows = seg(n0)
        slide = sum(1 for r in rows if f(r, 'slide') == '1')
        ps = sum(1 for r in rows if f(r, 'ps') == '1')
        snd = sounds(rows, [])
        heads = [heading(r) for r in rows if speed(r) > 100]
        turned = ((heads[-1] - heads[0] + 180) % 360 - 180) if len(heads) > 1 else 0.0
        check(name, slide > 10 and counter(rows[-1], 'bails') == counter(rows[0], 'bails'),
              f"{slide} powerslide frames (the input's slide flag on {ps}), {speed(rows[0]):.0f} -> {speed(rows[-1]):.0f} cm/s, "
              f"the path turned {turned:.0f} deg, skid loop top {snd['loop_top_volume']['skid']}", slide_frames=slide,
              input_frames=ps, from_cm_s=round(speed(rows[0])), to_cm_s=round(speed(rows[-1])), turned_deg=round(turned),
              shots=[f'ride_e2e/{name}.png'])

    # 3. The east return quarter (coping x 70.025, 2.15 m) at speed, an air with a grab: does it come back in?
    step('3_transition')
    pset(v=860)
    g(f"live.E2E.when('ramp', lambda f: live.E2E.AT[0] > {ue(64.5, 0)[0]} and live.E2E.AT[1] > {ue(0, 34)[1]}, "
      "lambda: live.E2E.PILOT and live.E2E.PILOT.update(nosteer=True, coast=True))\n"
      "live.E2E.when('qgrab', lambda f: live.E2E.AIR > .08, lambda: (live.E2E.pad('RT', 1), live.E2E.later(.5, lambda: live.E2E.pad('RT', 0))))\n"
      "live.E2E.when('qpeak', lambda f: f.get('mode') == '2' and (live.E2E.vec(f.get('vel', '')) or (0, 0, 1))[2] < 0, "
      "lambda: live.E2E.shot('quarter_air'))")
    n0 = mark()
    r = wait(until=lambda r: mode(r) == '2' and px(r)[0] > 62, timeout=25)
    if r:
        wait(until=lambda r: mode(r) in ('1', '4') and px(r)[0] < 72, timeout=6)
        g("live.E2E.later(.35, lambda: live.E2E.shot('quarter_landing'))")
        wait(1.6)
    g("live.E2E.unwhen('ramp', 'qgrab', 'qpeak')")
    rows = seg(n0)
    air = [k for k, x in enumerate(rows) if mode(x) == '2' and px(x)[0] > 60]
    if air:
        a0, a1 = air[0], air[-1]
        top = max(rows[a0:a1 + 1], key=lambda x: x['at'][2])
        out = max(px(x)[0] for x in rows[a0:a1 + 1]) - COPING_X
        land = next((x for x in rows[a1 + 1:] if mode(x) != '2'), rows[-1])
        back_in = mode(land) == '1' and px(land)[0] < COPING_X and (vec(f(land, 'vel')) or (0,))[0] < 0
        check('quarter_air', back_in,
              f"took off at {speed(rows[max(0, a0 - 1)]):.0f} cm/s (vertical {(vec(f(rows[a0], 'vel')) or (0, 0, 0))[2]:.0f}), "
              f"the capsule's peak {top['at'][2] / 100 - OZ:.2f} m above the deck, {out:+.2f} m past the coping at most, "
              f"{a1 - a0 + 1} air frames ({' / '.join(combos(rows)) or 'no trick line'}); landed mode {mode(land)} at "
              f"x={px(land)[0]:.2f} {'heading back down' if back_in else 'NOT back in the transition'}, {speed(land):.0f} cm/s; "
              f"{clip_line(rows[a1:])}",
              takeoff_cm_s=round(speed(rows[max(0, a0 - 1)])), past_coping_m=round(out, 2), air_frames=a1 - a0 + 1,
              landing_mode=mode(land), landing_x=round(px(land)[0], 2), combos=combos(rows),
              shots=['ride_e2e/quarter_air.png', 'ride_e2e/quarter_landing.png'])
    else:
        check('quarter_air', False, f"no air off the quarter (top {max(map(speed, rows), default=0):.0f} cm/s, reached "
              f"x={max((px(x)[0] for x in rows), default=0):.1f}, mode {mode(rows[-1]) if rows else '-'})")
    if mode(last()) == '4':
        wait(until=lambda r: mode(r) in ('0', '1'), timeout=10)
        wait(1.0)

    # 5a. A stand dismount, the carry past the hold time (it dissolves), recalled to the hand.
    step('5_dismounts')
    if riding(last()):
        brake_to_stop(timeout=6, keep=True)
        stop_pilot()
        n_carry = mark()
        dismount('dismount_stand', 'BR_DISMOUNT_HI_INTO_STAND_0')
        hold_check('board_hold_time', n_carry)
    recall('recall_to_hand')

    # 6. Hands needed: the sword (D-pad Left), an interaction (D-pad Down); each time the board goes, then comes back.
    step('6_hands')
    hands('hands_sword', 'DL', lambda: (sword_drawn() is True, f'sword drawn: {sword_drawn()}'))
    tap('DL')
    wait(1.4)
    check('sword_sheathed', sword_drawn() is False, f'sword drawn after D-pad Left again: {sword_drawn()}')
    recall('recall_after_sword')
    hands('hands_interact', 'DD', lambda: (True, 'interaction played (see the screenshot)'), settle=1.6)
    wait(1.0)
    recall('recall_after_interact')
    check('hands_climb_glide_swim', None, 'not on this build: no climb or glide (the adventure move set is unmerged), and the '
          'island has no swimmable water (the sea and the forest lake are recovery teleports)')

    # Back to the lane y 48 heading west, on foot around the quarter and between the rails, then a mount from the carry.
    here = px(last())
    lead = ([(77, 37), (64, 38)] if here[0] > 71 else []) + [(52, 36), (38, 36), (36, 44), (36, 48), (32, 48)]
    walk_pts, walk_caps = route(([here] + lead, None))
    pilot('walk', walk_pts, walk_caps, name='to_lane', gait='run', end_r=90.0)
    r = wait(until=lambda r: px(r)[0] < 33.5 and abs(px(r)[1] - 48) < 1.5, timeout=25)
    if r is None:
        travel_cut('the walk to the lane got stuck', *ue(33, 48), 180.0)
    stop_pilot()
    wait(.6)
    lane = route((W2, None), (WT2, TURN), (E2, None), (ET2, TURN), (W3, None))
    mount('mount_carry_stand', 'BR_STAND_0_INTO_MOUNT')
    pilot('ride', *lane, name='lane', v=780)

    # 4. A slam at speed: the deliberate bail (both stick clicks, both triggers) at 7+ m/s; up where he lay; rides on.
    step('4_bails')
    if wait(until=lambda r: speed(r) > 700, timeout=8):
        bail_now('slam_at_speed')
    else:
        check('slam_at_speed', False, f'never reached 700 cm/s ({speed(last()):.0f})')
    ride_on(*lane, name='lane', v=420)

    # 5b. Dismounts at speed: into a run, fast, from a grab in the air, a kick-out; mounts from the run after each.
    step('5_dismounts')
    wait(until=lambda r: abs(speed(r) - 420) < 60, timeout=5)
    if dismount('dismount_run', 'BR_DISMOUNT_HI_INTO_RUN_FWD', run=1.2, path=lane):
        pilot('walk', *lane, name='lane-walk', gait='run')
        mount('mount_carry_run', 'BR_RUN_FWD_', gait='run', seconds=.4)
    ride_on(*lane, name='lane', v=780)
    if wait(until=lambda r: speed(r) > 650, timeout=7):
        if dismount('dismount_fast', 'BR_DISMOUNT_FAST_HI_INTO_RUN_FWD', run=1.2, path=lane):
            pilot('walk', *lane, name='lane-walk', gait='run')
            mount('mount_carry_run_after_fast', 'BR_RUN_FWD_', gait='run', seconds=.4)
    else:
        check('dismount_fast', False, f'never reached 650 cm/s ({speed(last()):.0f})')
    for name, grab, expect in (('dismount_air_grab', True, 'BR_DISMOUNT_'), ('kick_out', False, 'BR_KICKOUT_HI_INTO_NB_AIR')):
        ride_on(*lane, name='lane', v=480)
        wait(until=lambda r: abs(speed(r) - 480) < 80 and mode(r) == '1', timeout=6)
        n0 = mark()
        g('live.E2E.coast(True)')
        wait(.3)
        before = speed(last())
        flick('ollie')
        if grab:
            g("live.E2E.when('agrab', lambda f: live.E2E.AIR > .08, lambda: (live.E2E.pad('RT', 1), live.E2E.tap('Y', .1), "
              "live.E2E.later(.5, lambda: live.E2E.pad('RT', 0))))")
        else:
            g("live.E2E.when('akick', lambda f: live.E2E.AIR > .12, lambda: live.E2E.tap('Y'))")
        g(f"live.E2E.when('ashot', lambda f: f.get('foot') == 'air', lambda: live.E2E.later(.12, lambda: live.E2E.shot({name!r})))")
        wait(until=lambda r: mode(r) == '0' and f(r, 'foot') != 'air', timeout=4)
        wait(1.4)
        g("live.E2E.unwhen('agrab', 'akick', 'ashot'); live.E2E.coast(False)")
        rows = seg(n0)
        seen = clips(rows)
        off = next((c for ft, c in seen if ft == 'air'), '-')
        land = next((c for ft, c in seen if ft == 'land'), '-')
        b, j = board_line(rows), jumps(rows)
        end = rows[-1]
        if grab:
            ok = off.startswith(expect) and off.endswith('_INTO_BR_AIR') and land.startswith('BR_LAND_') and f(end, 'board') == 'hand'
            how = f"the board in the hand at the end: {f(end, 'board') == 'hand'}"
        else:
            flew = any(f(r, 'loose') == 'flying' for r in rows)
            ok = off == expect and flew and f(end, 'board') == 'world'
            how = f"the board {'flew on' if flew else 'never flew'}, {f(end, 'board')} at the end ({f(end, 'loose', '-')})"
        check(name, ok and b['pops'] == 0 and b['hidden'] == 0 and smooth(j),
              f"{clip_line(rows)}; {before:.0f} cm/s; {how}; board {b}; jumps {j}",
              clips=[c for _, c in seen], board=b, jumps=j, shots=[f'ride_e2e/{name}.png'])
        if grab and mode(last()) == '0':
            pilot('walk', *lane, name='lane-walk', gait='run')
            mount('mount_after_air_dismount', 'BR_', gait='run', seconds=.4)
    stop_pilot()
    wait(.5)
    if f(last(), 'board') != 'hand':
        recall('recall_lying_board')

    # 7. Caveman: run, jump (A), the top face button in the air, land riding.
    step('7_caveman')
    pilot('walk', *lane, name='lane-walk', gait='run')
    wait(1.6)
    n0 = mark()
    before = speed(last())
    g("live.E2E.when('onboard', lambda f: f.get('mode') in ('1', '2', '3'), live.E2E.stop_walk)\n"
      "live.E2E.at(0, ('A', 1)); live.E2E.at(.16, ('A', 0)); live.E2E.tap('Y', .26); live.E2E.later(.45, lambda: live.E2E.shot('caveman'))")
    r = wait(until=lambda r: riding(r) and f(r, 'board') == 'ride', timeout=3)
    if r:
        pilot('ride', *lane, name='lane', v=500)
    wait(1.8)
    g("live.E2E.unwhen('onboard')")
    rows = seg(n0)
    cave = clip_of(rows, 'airmount')
    b, j = board_line(rows), jumps(rows)
    check('caveman', 'AIR_INTO_MOUNT' in cave and mode(rows[-1]) in ('1', '2') and b['pops'] == 0 and smooth(j),
          f"{clip_line(rows)}; {before:.0f} cm/s running, mode {mode(rows[-1])} at {speed(rows[-1]):.0f} cm/s after; "
          f"board {b}; jumps {j}", clip=cave, board=b, jumps=j, shots=['ride_e2e/caveman.png'])
    ride_on(*lane, name='lane', v=500)

    # 4b. A bail off a grind: the long flatbar (y 43, x 41..61), the bail input once grinding.
    step('4_bails')
    pset(v=470)
    r = wait(until=lambda r: abs(px(r)[1] - 43) < 1.0 and 28 < px(r)[0] < 36 and riding(r), timeout=70)
    if r:
        n0 = mark()
        g(f"live.E2E.when('rail', lambda f: f.get('mode') == '1' and live.E2E.AT[0] >= {ue(RAIL_LONG[0] - 3.0, 0)[0]} "
          "- max(0.0, (float(f.get('speed', 470)) - 470.0) * .6), lambda: (live.E2E.coast(True), live.E2E.flick('ollie'), "
          "live.E2E.later(3.0, lambda: live.E2E.coast(False))))\n"
          "live.E2E.when('railbail', lambda f: f.get('mode') == '3', lambda: live.E2E.later(.35, lambda: (live.E2E.ev('bail_combo'), "
          "[live.E2E.pad(k, 1) for k in ('L3', 'R3', 'LT', 'RT')], "
          "live.E2E.later(.5, lambda: [live.E2E.pad(k, 0) for k in ('L3', 'R3', 'LT', 'RT')]))))\n"
          "live.E2E.when('down', lambda f: f.get('mode') == '4', lambda: live.E2E.later(.45, lambda: live.E2E.shot('bail_off_grind_down')))\n"
          "live.E2E.when('up', lambda f: f.get('mode') in ('0', '1') and live.E2E.PREV == '4', "
          "lambda: live.E2E.later(.3, lambda: live.E2E.shot('bail_off_grind_up')))")
        wait(until=lambda r: mode(r) == '4' or px(r)[0] > RAIL_LONG[1] + 2, timeout=12)
        wait(until=lambda r: mode(r) in ('0', '1'), timeout=12)
        wait(2.4)
        g("live.E2E.unwhen('rail', 'railbail', 'down', 'up')")
        rows = seg(n0)
        grind = sum(1 for x in rows if mode(x) == '3')
        check('grind_long_flatbar', grind > 0, f"{grind} grind frames on the long flatbar ({' / '.join(combos(rows)) or 'no trick line'})",
              grind_frames=grind)
        runout = clip_of(rows, 'runout')
        bails = counter(rows[-1], 'bails') - counter(rows[0], 'bails')
        if not any(mode(x) == '4' for x in rows) and runout.startswith('RUNOUT_'):
            k = next(i for i, x in enumerate(rows) if f(x, 'foot') == 'runout')
            b, j = board_line(rows[k:]), jumps(rows[k:])
            check('bail_off_grind', bails == 1 and mode(rows[-1]) == '0' and b['pops'] == 0 and b['hidden'] == 0 and smooth(j),
                  f"a run-out (by design under RunOutSpeed 450 cm/s): {runout} from {speed(rows[max(0, k - 1)]):.0f} cm/s, "
                  f"the run-out clip for {sum(x['wdt'] for x in rows if f(x, 'foot') == 'runout'):.2f} s, then mode {mode(rows[-1])}, "
                  f"bails +{bails}; board {b}; jumps {j}",
                  kind='runout', clip=runout, from_cm_s=round(speed(rows[max(0, k - 1)])), board=b, jumps=j)
        else:
            bail_check('bail_off_grind', rows)
    else:
        check('bail_off_grind', False, f'never lined up on the long flatbar (at {tuple(round(c, 1) for c in px(last()))})')

    # 8. Modori through the Esc menu's character switch: mount, ride, bail, dismount; then back to Cairo.
    step('8_character')
    ensure_on_foot()
    g('live.E2E.SKIPTO = live.E2E.N + 150')
    switched = g("print(live.L.switch_character('Modori'))").strip().splitlines()[-1]
    wait(3.0)
    check('switch_to_link', switched == 'Modori', f'the switch returned {switched!r}', shots=[shot('modori')])
    w3 = route((W3, None))
    if switched == 'Modori':
        pilot('walk', *w3, name='modori-walk', gait='walk', mag=.5)
        wait(1.0)
        stop_pilot()
        wait(.5)
        if mount('link_mount_stand', 'BR_STAND_0_INTO_MOUNT'):
            pilot('ride', *w3, name='modori', v=650)
            wait(3.2)
            shot('link_riding')
            bail_now('link_bail')
            ride_on(*w3, name='modori', v=380)
            wait(until=lambda r: abs(speed(r) - 380) < 80, timeout=5)
            dismount('link_dismount_run', 'BR_DISMOUNT_HI_INTO_RUN_FWD', run=1.0, path=w3)
        ensure_on_foot()
        g('live.E2E.SKIPTO = live.E2E.N + 150')
        back = g("print(live.L.switch_character('Cairo'))").strip().splitlines()[-1]
        wait(3.0)
        check('switch_back_to_cairo', back == 'Cairo', f'the switch returned {back!r}')

    # 6c. The sailboat (D-pad Up) needs open water: from the mainland beach (a travel cut, as the sailboat QA does).
    step('6_hands')
    travel_cut('the sailboat needs a beach; the pier has railings', BEACH[0][0], BEACH[0][1], BEACH[1])
    if f(last(), 'board') != 'hand':
        recall('recall_on_beach')
    hands('hands_sailboat', 'DU', lambda: (f(last(), 'mm').startswith('5/'), f"movement {f(last(), 'mm')} (5/ is the boat)"),
          settle=1.6, shot_after=1.2)
    if f(last(), 'mm').startswith('5/'):
        tap('DU')
        wait(2.0)
        check('sailboat_step_off', not f(last(), 'mm').startswith('5/'), f"movement {f(last(), 'mm')} after D-pad Up again",
              shots=[shot('sailboat_off')])
        recall('recall_after_sailboat')
    g("live.E2E.release()")
    wait(.5)


def goofy():
    """The stance the game loaded: Saved/settings.txt's goofy (JapanPreferences; no file or no key is regular)."""
    path = qa.GAME / 'unreal/Saved/settings.txt'
    m = re.search(r'^goofy=([0-9.]+)', path.read_text(), re.M) if path.exists() else None
    return bool(m and float(m.group(1)) > .5)


def newest_log():
    logs = sorted((qa.yori.OUT / 'logs').glob('play-*/game.log'), key=lambda p: p.stat().st_mtime)
    return logs[-1] if logs else None


LOG_IGNORE = re.compile(r'UnifiedErrorTest|FError that has been')
LOG_PATTERNS = {'error': r'\bError\b', 'warning': r'\bWarning\b', 'ensure': r'[Ee]nsure', 'assert': r'Assert',
                'bone_data': r'Failed to find bone data', 'unstable': r'[Uu]nstable', 'nan': r'\bNaN\b|\bnan\b'}


def log_by_step(log, rows):
    """The game log's flagged lines (errors, warnings, ensures...) during the run, by step (the line's UTC time -> the
    recorded frame's wall time)."""
    if not log or not log.exists() or not rows:
        return {}, []
    times = [r['w'] for r in rows]
    out, lines = {}, []
    for text in log.read_text(errors='replace').splitlines():
        m = re.match(r'\[(\d{4}\.\d\d\.\d\d-\d\d\.\d\d\.\d\d):(\d{3})\]', text)
        if not m:
            continue
        t = calendar.timegm(time.strptime(m.group(1), '%Y.%m.%d-%H.%M.%S')) + int(m.group(2)) / 1000
        if t < times[0] - .5 or t > times[-1] + 1:
            continue
        hit = [k for k, p in LOG_PATTERNS.items() if re.search(p, text)] if not LOG_IGNORE.search(text) else []
        if not hit:
            continue
        name = rows[max(0, bisect.bisect_right(times, t) - 1)]['s']
        s = out.setdefault(name, dict.fromkeys(LOG_PATTERNS, 0))
        for k in hit:
            s[k] += 1
        lines.append(f'{name}: {text[:260]}')
    return out, lines


def report():
    try:
        drain()
    except Exception as error:
        print('drain:', error)
    audio_path = DIR / 'audio.json'
    try:
        g(f"live.L.audio_log('stop', {str(audio_path)!r}); live.stop('e2e')")
    except Exception as error:
        print('audio log:', error)
    audio = json.loads(audio_path.read_text()) if audio_path.exists() else []
    DIR.mkdir(parents=True, exist_ok=True)
    (DIR / 'rows.json').write_text(json.dumps(ROWS))
    (DIR / 'events.json').write_text(json.dumps({'events': EVENTS, 'errors': ERRORS}))
    log = STATE['log'] or newest_log()
    by_step, lines = log_by_step(log, ROWS)
    steps = {}
    for name in sorted({r['s'] for r in ROWS}):
        rows = [r for r in ROWS if r['s'] == name]
        steps[name] = {'frames': frame_stats(rows), 'camera': jumps(rows), 'sounds': sounds(rows, audio),
                       'log': by_step.get(name, {}), 'travel_cuts': [c['why'] for c in CUTS if c['step'] == name],
                       'hud_trick_lines': combos(rows)[:16]}
    result = {'stance': 'goofy' if STATE.get('goofy') else 'regular', 'checks': CHECKS, 'steps': steps,
              'all': {'frames': frame_stats(ROWS), 'camera': jumps(ROWS), 'sounds': sounds(ROWS, audio)},
              'travel_cuts': CUTS, 'bridge_errors': ERRORS[:40], 'log': str(log) if log else None, 'log_lines': lines[:400],
              'audio_events': len(audio)}
    (OUT / 'ride_e2e.json').write_text(json.dumps(result, indent=1) + '\n')
    (OUT / 'ride_e2e.md').write_text(markdown(result))
    passed = sum(1 for c in CHECKS if c['ok'])
    failed = sum(1 for c in CHECKS if c['ok'] is False)
    print(f'{passed} passed, {failed} failed, {len(CHECKS) - passed - failed} skipped -> {OUT / "ride_e2e.json"}')
    return 0 if failed == 0 else 1


def markdown(result):
    lines = ['# Ride end-to-end dry run', '', f"Stance: {result.get('stance', '-')}. "
             f"Game log: `{Path(result['log']).parent.name if result.get('log') else '-'}`. "
             f"Travel cuts: {len(result['travel_cuts'])}. Sound log events: {result['audio_events']}.", '',
             '| Step | Check | Result | Numbers |', '| --- | --- | --- | --- |']
    for c in result['checks']:
        res = 'skip' if c['ok'] is None else 'PASS' if c['ok'] else 'FAIL'
        note = c['note'].replace('|', '/').replace('\n', ' ')
        shots = ' '.join(f'[{Path(s).stem}]({s})' for s in c.get('shots', []))
        lines.append(f"| {c['step']} | {c['name']} | {res} | {note} {shots} |")
    lines += ['', '## Per step', '', '| Step | Frames | p50 / p99 / worst ms | > 25 ms | Camera: worst cm/frame, frames > 30 cm, '
              'worst cm beyond the character, worst deg | Hips: worst cm, frames > 12 | One-shot sounds | Loops (top volume) '
              '| Log: errors, warnings, ensures, bone data, NaN |', '| --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for name, s in result['steps'].items():
        fr, cam, snd, log = s['frames'], s['camera'], s['sounds'], s['log']
        lines.append(f"| {name} | {fr.get('frames', 0)} | {fr.get('p50_ms')} / {fr.get('p99_ms')} / {fr.get('worst_ms')} | "
                     f"{fr.get('over_25ms')} | {cam.get('cam_raw_cm')}, {cam.get('cam_over30')}, {cam.get('cam_cm')}, {cam.get('cam_deg')} | "
                     f"{cam.get('hip_cm')}, {cam.get('hip_over12')} | {snd.get('one_shots')} | {snd.get('loop_top_volume')} | "
                     f"{log.get('error', 0)}, {log.get('warning', 0)}, {log.get('ensure', 0)}, {log.get('bone_data', 0)}, {log.get('nan', 0)} |")
    if result.get('memory'):
        lines += ['', f"Memory (the guard's report): peak {result['memory']}."]
    if result.get('log_totals'):
        lines += ['', f"The whole game log: {result['log_totals']}."]
    if result['travel_cuts']:
        lines += ['', '## Travel cuts', ''] + [f"- {c['step']}: {c['why']}" for c in result['travel_cuts']]
    slow = [x for s in result['steps'].values() for x in s['frames'].get('slow', [])]
    if slow:
        lines += ['', '## Slowest frames', ''] + [f'- {x}' for x in slow[:24]]
    if result.get('log_lines'):
        lines += ['', '## Flagged log lines during the run (first 60)', ''] + [f'- `{x}`' for x in result['log_lines'][:60]]
    return '\n'.join(lines) + '\n'


def post():
    """After the game quit: the guard's memory peak and the whole log's counts go into the report."""
    out = OUT / 'ride_e2e.json'
    result = json.loads(out.read_text())
    log = Path(result['log']) if result.get('log') else newest_log()
    health = log.parent / 'memory-health.json' if log else None
    if health and health.exists():
        h = json.loads(health.read_text())
        result['memory'] = f"{h['peak_bytes'] / 2 ** 30:.2f} GiB of {h['limit_bytes'] / 2 ** 30:.0f} GiB"
    if log and log.exists():
        text = log.read_text(errors='replace')
        text = '\n'.join(x for x in text.splitlines() if not LOG_IGNORE.search(x))
        result['log_totals'] = {k: len(re.findall(p, text)) for k, p in LOG_PATTERNS.items()}
    out.write_text(json.dumps(result, indent=1) + '\n')
    (OUT / 'ride_e2e.md').write_text(markdown(result))
    print(result.get('memory'), result.get('log_totals'))
    return 0


def release_controls():
    try:
        qa.py("live.stop('e2e'); live.drive(0); live.skate_release()\n"
              "for k in ('Gamepad_FaceButton_Bottom', 'Gamepad_FaceButton_Right', 'Gamepad_FaceButton_Top', 'Gamepad_LeftThumbstick', "
              "'Gamepad_RightThumbstick', 'Gamepad_DPad_Left', 'Gamepad_DPad_Right', 'Gamepad_DPad_Up', 'Gamepad_DPad_Down', 'C'): "
              "live.L.input_key(k, 'release', 0)\n"
              "for k in ('Gamepad_LeftX', 'Gamepad_LeftY', 'Gamepad_RightX', 'Gamepad_RightY', 'Gamepad_LeftTriggerAxis', "
              "'Gamepad_RightTriggerAxis'): live.L.input_key(k, 'axis', 0)")
    except Exception as error:
        print('release:', error)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8830)
    parser.add_argument('--post', action='store_true', help='after the game quit: add the memory peak and the whole log')
    args = parser.parse_args()
    if args.post:
        return post()
    qa.bridge.URL = f'http://127.0.0.1:{args.port}'
    try:
        run()
    except Exception as error:
        import traceback
        traceback.print_exc()
        check('run', False, f'the run stopped: {error!r}')
    finally:
        release_controls()
    return report()


if __name__ == '__main__':
    raise SystemExit(main())
