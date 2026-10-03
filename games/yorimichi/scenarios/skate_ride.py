#!/usr/bin/env python3
"""In-game checks for the Ride skating backend (Skate plugin, Private/Ride, RIDE.md) on the skate pier park.

Run against a running game (atelier play yorimichi):  atelier qa yorimichi skate_ride [--only name,name]
Mounts with skate.Backend Ride, then checks a ride's first frame (it moves like every later one), a start inside the
floor (it starts on it), pushing (from rest, nose-first), steering, braking, the ollie's height, every Flick-It trick,
a grab, a 360, a grind, a manual, a bail and its recovery, the hands clear of the body and the pushing foot out of
the ground (Cairo regular and goofy, Link), lip airs
back into the transition (straight, 180 and 360 on the pier's quarter; straight and across on Mega Park's pool wall)
and a coasting back-and-forth in the bowl (`--only vert`), every wheel on the ground through carves, a pump, a
powerslide and a manual (`--only wheels`), frame pacing (including mounting and switching character), Mega Park's
roll-in from the upper deck (over the crest without leaving it, through the concave at the bottom without a bail) and a
grind into
the parapet's corner (it flies off the end, never stalling), and the physical rider (skate.RidePhysical, on by
default): how closely it holds the animation riding and landing, bails on flat (at 6 and 11 m/s) and on a quarter
that go limp at once, lie down within a second and travel as far as the reference's for their speed, its skin never
under the ground in any group of bodies (riding, falling, lying or getting up), and its frame cost in Mega Park. Over
every frame recorded, the rider's pose (the clips through Unreal's animation graph) must keep both feet on the deck
where the clip stands on it, carry no NaN and never pop between clips, in both stances, and the standing rider matches
the reference's stand.
The cost check (`--only cost`) measures the frame, the animator and the session with the physical rider off and on.
Writes build/yorimichi/skateqa/ride.json, and ride-pose.json: every frame of the pose checks and each pop with the
frames around it.
"""
import argparse
import json
import math
import os
import time
import skate as qa

# live.FLICKS name -> the trick name Ride shows.
FLIPS = {
    'ollie': 'Ollie', 'nollie': 'Nollie', 'kickflip': 'Kickflip', 'heelflip': 'Heelflip', 'shove': 'Pop Shove-it',
    'fs_shove': 'FS Pop Shove-it', '360_shove': '360 Shove-it', 'fs_360_shove': 'FS 360 Shove-it',
    'varial_kickflip': 'Varial Kickflip', 'varial_heelflip': 'Varial Heelflip', 'hardflip': 'Hardflip',
    'inward_heelflip': 'Inward Heelflip', '360_flip': '360 Flip', 'laser_flip': 'Laser Flip',
    '360_hardflip': '360 Hardflip', '360_inward_heelflip': '360 Inward Heelflip',
}
# Park-local metres on the Sunset Pier (world/regions/skatepark/layout.py).
FLAT = (-28, 38)       # the pier's long flat run, heading east between flatbar_red (y 43) and long_ledge (y 25-28)
# The steering turns start a metre apart: the left turn starts a metre further from flatbar_red.
STEER = {1: FLAT, -1: (FLAT[0], FLAT[1] - 1)}
RAIL = (-36, 43)       # an ollie at .98 s onto flatbar_red, along it (it starts 8 m ahead, x -28 to -10)
RAIL_FAST = (-38, 43)  # the same take-off at 700 cm/s
QUARTER = (57, 25)     # east_return's quarter (lip at x 70, 2 m radius, 0.15 m vert), launched east at 950 cm/s
QUARTER_OUT = (-1, 0)  # its face's level normal, Unreal x, y: back into the ramp, west
OPEN = (0, 52)         # an open run east between the bars (y 43) and the north gardens (y 61), for hard carves
BOWL = (29, -10)       # the bowl's floor; its walls (3 m radius, 0.2 m vert) east and west of it


def position(row):
    return tuple(float(x) for x in row['pos'].strip('()').split(','))


def speed(row):
    return float(row['speed'])


def recorded():
    return [qa.parse(r) for r in json.loads(qa.py("live.stop('rec'); print(json.dumps(live.REC))").strip().splitlines()[-1])]


def record_while(code, seconds):
    """Record every frame's state while `code` runs in the game for `seconds`."""
    qa.py("live.REC=[]; live.behave('rec', lambda dt: live.REC.append(live.skate_state()))\n" + code)
    time.sleep(seconds)
    return recorded()


def mount_ride():
    qa.py("unreal.SystemLibrary.execute_console_command(live.L.game_world(), 'skate.Backend Ride')")
    qa.py('live.L.skate_goofy(False); live.skate_park(); live.skate_input()')
    for _ in range(40):
        state = qa.py('print(live.skate_state())')
        if 'backend=Ride' in state and 'retail=PhysicsGround' in state:
            return state
        time.sleep(.5)
    raise RuntimeError('Ride did not mount: ' + state.strip())


# User 19:46: at rest on the board Cairo's hands sank into his thighs (the idle clip on his wider hips and thighs). The
# retarget swings each arm out until its hand and forearm clear the rider's own body (skate.ArmClear), and lifts a foot
# whose sole goes under the ground (skate.FootGround). hand_gap= is each hand's skin against the pelvis, spine, chest and
# thigh bodies (cm, below 0 inside), skin_groups= the skin under the ground (skate.RideSkinCheck).
HAND_GAP = -1.   # cm: no hand deeper inside the rider's own body than this, at rest, rolling or carving
HAND_RIDERS = (('cairo_regular', 'Cairo', False), ('cairo_goofy', 'Cairo', True), ('link', 'Link', False))
# The rest close-up shows the right hand from the rider's right side (out from the hips through the hand), frozen at
# the idle loop's worst phase for that hand: a watcher reads hand_gap= every frame for 1.6 s (more than the loop), then
# stops time (global time dilation) when the right hand is back within 0.3 cm of the deepest it went.
REST_AIM = """
import unreal
st = dict(kv.split('=', 1) for kv in live.skate_state().split() if '=' in kv)
P = unreal.Vector(*[float(v) for v in st.get('hips', st.get('hip')).split(',')])
H = P
try:
    _m = live.L.player().get_editor_property('mesh')
    _b = next((n for n in ('hand_R', 'Wrist_R', 'hand_r') if _m.get_bone_index(n) != -1), None)
    H = _m.get_socket_location(_b) if _b else P
except Exception as e:
    print('no right hand:', e)
_out = unreal.Vector(H.x - P.x, H.y - P.y, 0)
_out = _out * (1 / _out.length()) if _out.length() > 1 else live.L.player().get_actor_right_vector()
unreal.MegaParkValidation.review_camera(H + _out * 85 + unreal.Vector(0, 0, 8), H, 40)
"""
WORST_PHASE = """
import unreal
live.HW = {'t': 0., 'min': 99., 'done': False, 'at': None}
def _hw(dt):
    s = live.HW
    if s['done']:
        return
    st = dict(kv.split('=', 1) for kv in live.skate_state().split() if '=' in kv)
    if 'hand_gap' not in st:
        return
    r = float(st['hand_gap'].split(',')[1])
    s['t'] += dt
    if s['t'] < 1.6:
        s['min'] = min(s['min'], r)
    elif r <= s['min'] + .3 or s['t'] > 4.5:
        unreal.GameplayStatics.set_global_time_dilation(live.L.game_world(), .0001)
        s['done'], s['at'] = True, r
live.behave('handworst', _hw)
"""


def hand_rows(record):
    """Each hand against the rider's own body (hand_gap=) and the feet's skin under the ground (skin_groups= feet) at
    rest for a second, then through a push, rolling and carving both ways, for Cairo regular and goofy and Link; a
    close-up at rest (build/yorimichi/skateqa/ride-hands-<rider>.png)."""
    qa.py("unreal.SystemLibrary.execute_console_command(live.L.game_world(), 'skate.RideSkinCheck 1')")
    who_now = 'Cairo'
    try:
        for tag, who, goofy in HAND_RIDERS:
            if who != who_now:
                qa.py(f"print(live.L.switch_character({who!r}))")
                who_now = who
                time.sleep(3)
                mount_ride()
            qa.py(f'live.L.skate_goofy({goofy})')
            rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,0,[(1,{{'push':True}}),(2.2,{{'left':(.6,0)}}),"
                                   f"(3.2,{{'left':(-.6,0)}}),(4.2,{{}})],duration=4.4", 4.4)
            clock, rest, moving = 0., [], []
            for r in rows:
                if 'hand_gap' in r:
                    # The deeper hand this frame, which body, when and in which clip.
                    gaps, near = [float(v) for v in r['hand_gap'].split(',')], r.get('hand_near', '-').split(',')
                    side = min(range(len(gaps)), key=gaps.__getitem__)
                    (rest if clock < 1 else moving).append(
                        (gaps[side], f"{'LR'[side]} hand, {near[min(side, len(near) - 1)]}, {clock:.2f} s, {r.get('clip', '-')}"))
                clock += float(r.get('dt', 16.7)) / 1000
            feet = max((float(part.partition(':')[2]) for r in rows for part in r.get('skin_groups', '').split(',')
                        if part.startswith('feet:')), default=float('nan'))
            qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,0,[],duration=1.5", 1.5)
            shot = qa.yori.OUT / 'skateqa' / f'ride-hands-{tag}.png'
            qa.py(REST_AIM)
            qa.py(WORST_PHASE)
            frozen = None
            for _ in range(40):
                time.sleep(.2)
                got = qa.py("import json; print(json.dumps(live.HW))").strip().splitlines()[-1]
                if json.loads(got)['done']:
                    frozen = json.loads(got)
                    break
            try:
                qa.py(REST_AIM)
                time.sleep(.6)
                qa.py(f"live.L.screenshot({str(shot)!r})")
                time.sleep(1.2)
            finally:
                qa.py("live.stop('handworst'); unreal.GameplayStatics.set_global_time_dilation(live.L.game_world(), 1.)")
                qa.py("unreal.MegaParkValidation.restore_player_camera()")
            phase = (f"right hand at {frozen['at']:.1f} cm (deepest {frozen['min']:.1f} in the loop)" if frozen and frozen['at'] is not None
                     else 'right hand phase not caught')
            worst = min(rest + moving, default=(float('nan'), '-'))
            text = lambda seen: f'{min(seen)[0]:.1f}' if seen else '-'
            record(f'hands_clear_{tag}', rows, bool(rest) and bool(moving) and worst[0] >= HAND_GAP,
                   f'hand gap (cm, below 0 inside the body) at rest {text(rest)}, pushing, rolling and carving '
                   f'{text(moving)} (worst: {worst[1]}); close-up from the right side, {phase}: {shot}')
            record(f'push_foot_{tag}', rows, feet <= SKIN_DEPTH,
                   f'feet skin {feet:.1f} cm under the ground at worst through a push and two carves')
    finally:
        qa.py("unreal.SystemLibrary.execute_console_command(live.L.game_world(), 'skate.RideSkinCheck 0')")
        qa.py('live.L.skate_goofy(False)')
        if who_now != 'Cairo':
            qa.py("print(live.L.switch_character('Cairo'))")
            time.sleep(3)
            mount_ride()


def frame_sampler():
    qa.py('''
import time
live.FRAMES=[]
live.behave('frames', lambda dt: live.FRAMES.append(time.perf_counter()))
''')


def frame_report():
    stamps = json.loads(qa.py("live.stop('frames'); print(json.dumps(live.FRAMES))").strip().splitlines()[-1])
    intervals = sorted((b - a) * 1000 for a, b in zip(stamps, stamps[1:]))
    if not intervals:
        return {'frames': 0}
    pick = lambda p: intervals[min(len(intervals) - 1, round((len(intervals) - 1) * p))]
    return {'frames': len(intervals), 'fps': 1000 * len(intervals) / sum(intervals), 'p50_ms': pick(.5),
            'p95_ms': pick(.95), 'p99_ms': pick(.99), 'worst_ms': intervals[-1],
            'over_33ms': sum(t > 33.4 for t in intervals), 'over_50ms': sum(t > 50 for t in intervals)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8830)
    parser.add_argument('--only', default='', help='comma-separated check names (prefixes) to run')
    args = parser.parse_args()
    qa.bridge.URL = f'http://127.0.0.1:{args.port}'
    only = [o for o in args.only.split(',') if o]
    wanted = lambda name: not only or any(name.startswith(o) for o in only)
    qa.py((qa.GAME / 'scenarios/skate_live_skate.py').read_text())
    results = {}

    seen = {}

    def record(name, rows, passed, note):
        results[name] = {'ok': bool(passed), 'note': note, 'frames': len(rows)}
        if rows:
            seen[name] = rows
        print(('PASS' if passed else 'FAIL') + ' ' + name + ': ' + note, flush=True)

    mounted = mount_ride()
    record('mount', [], True, mounted.strip().split(' | ')[0])
    qa.settle(minimum=50, seconds=2, limit=60)

    if wanted('ride_start'):
        # Placed and launched at 5 m/s, the ride's first frame shows a frame's travel like every later frame (with the
        # session's step clock starting empty, it showed the start again for a frame).
        qa.py("import unreal\nlive.skate_input()\n"
              f"live.park.place({FLAT[0]},{FLAT[1]},0); live.park.launch(500)\n"
              "live.REC=[(unreal.SystemLibrary.get_frame_count(), live.skate_state())]\n"
              "live.behave('rec', lambda dt: live.REC.append((unreal.SystemLibrary.get_frame_count(), live.skate_state())))")
        time.sleep(.6)
        raw = json.loads(qa.py("live.stop('rec'); print(json.dumps(live.REC))").strip().splitlines()[-1])
        rows = [qa.parse(state) for _, state in raw]
        steps = [math.dist(position(a)[:2], position(b)[:2]) for a, b in zip(rows, rows[1:])]
        later = sorted(steps[1:13])
        typical = later[len(later) // 2] if later else 0.
        record('ride_start', rows[1:], len(steps) > 6 and typical > 4 and steps[0] >= .5 * typical,
               f'first frame {steps[0] if steps else 0:.1f} cm, then {typical:.1f} cm a frame '
               f'(frames {raw[0][0]} -> {raw[1][0] if len(raw) > 1 else "-"})')
    if wanted('ride_start_low'):
        # A start 12 cm inside the pier's deck (where the caveman hand-off started one) starts on the deck, not in the
        # air under it.
        ground = f"live.L.ground_at(live.park.ue({FLAT[0]},{FLAT[1]},3.0))"
        qa.py(f"live.skate_input(); live.skate_place({ground}, 0)")
        time.sleep(.4)
        deck = float(qa.parse(qa.py('print(live.skate_state())'))['z'])
        rows = record_while(f"import unreal\nlive.skate_place({ground} - unreal.Vector(0, 0, 12), 0)", 1.2)
        zs = [float(r['z']) for r in rows[3:]]
        ok = len(zs) > 20 and min(zs) > deck - 3 and abs(zs[-1] - deck) < 3 and rows[-1]['mode'] == '1' and not qa.count(rows, 'bails')
        record('ride_start_low', rows, ok, f"placed at z {deck - 12:.0f}, 12 cm under the deck (z {deck:.0f}): rode at z "
               f"{min(zs) if zs else 0:.0f} to {max(zs) if zs else 0:.0f}, last mode {rows[-1]['mode'] if rows else '-'}")
    if wanted('push'):
        rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,0,[(0,{{'push':True}}),(3.5,{{}})],duration=4", 4)
        first = next((float(r['speed']) for r in rows if float(r['speed']) > 150), 0)
        top = max(map(speed, rows))
        record('push_cruise', rows, top > 750 and rows[-1]['mode'] == '1' and not qa.count(rows, 'bails'),
               f'top speed {top:.0f} cm/s after 3.5 s of pushing')
    if wanted('push_from_rest'):
        # A push from rest goes nose-first, even with the board creeping tail-first as it does down a slope after a
        # stop: it stands still through the wind-up and leaves nose-first (the e2e's push from a stop on the road crept
        # back 9-10 cm/s through the wind-up and left fakie). Placed facing +x, creeping back at 20 cm/s.
        rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,-20,[(0,{{'push':True}}),(1.2,{{}})],duration=1.6", 1.6)
        x0 = position(rows[0])[0]
        back = min(position(r)[0] - x0 for r in rows)
        ahead = position(rows[-1])[0] - x0
        ok = back > -3 and ahead > 50 and rows[-1].get('fakie') == '0' and speed(rows[-1]) > 150 and not qa.count(rows, 'bails')
        record('push_from_rest', rows, ok, f"crept back at most {-back:.1f} cm, then {ahead:.0f} cm forward at {speed(rows[-1]):.0f} cm/s, "
               f"fakie={rows[-1].get('fakie')}")
    if wanted('steer'):
        for direction in (1, -1):
            x, y = STEER[direction]
            rows = qa.run_scenario(f"{x},{y},0,500,[(.2,{{'left':({direction * .8},0)}}),(1.4,{{}})],duration=1.6", 1.6)
            dy = position(rows[-1])[1] - position(rows[0])[1]
            turned = (float(rows[-1]['yaw']) - float(rows[0]['yaw']) + 180) % 360 - 180
            record(f'steer_{"right" if direction > 0 else "left"}', rows, dy * direction > 40 and turned * direction > 30 and rows[-1]['mode'] == '1',
                   f'sideways {dy:.0f} cm, turned {turned:.0f} degrees')
    if wanted('brake'):
        rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,600,[(.3,{{'brake':True}}),(2.6,{{}})],duration=2.8", 2.8)
        record('brake', rows, speed(rows[-1]) < 60 and not qa.count(rows, 'bails'), f'{speed(rows[0]):.0f} -> {speed(rows[-1]):.0f} cm/s')
    if wanted('powerslide'):
        rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,700,[(.3,{{'slide':True,'left':(.6,0)}}),(1.3,{{}})],duration=2", 2)
        record('powerslide', rows, qa.ever(rows, 'slide', '1') and speed(rows[-1]) < 600 and not qa.count(rows, 'bails'),
               f'{speed(rows[0]):.0f} -> {speed(rows[-1]):.0f} cm/s')
        # A pad's powerslide (native's slide intents): the left stick pushed out to a rear diagonal, no key, on either
        # side in either stance; the stick pulled straight back does not slide.
        for goofy in (False, True):
            qa.py(f'live.L.skate_goofy({goofy})')
            for side in (1, -1):
                rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,700,[(.3,{{'left':({side * .6},-.8)}}),(1.3,{{}})],duration=2", 2)
                record(f'powerslide_pad_{"goofy" if goofy else "regular"}_{"right" if side > 0 else "left"}', rows,
                       qa.ever(rows, 'slide', '1') and speed(rows[-1]) < 600 and not qa.count(rows, 'bails'),
                       f'{speed(rows[0]):.0f} -> {speed(rows[-1]):.0f} cm/s')
        qa.py('live.L.skate_goofy(False)')
        rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,700,[(.3,{{'left':(0,-1)}}),(1.3,{{}})],duration=2", 2)
        record('powerslide_pad_straight_back', rows, not qa.ever(rows, 'slide', '1') and not qa.count(rows, 'bails'),
               f'no slide; {speed(rows[0]):.0f} -> {speed(rows[-1]):.0f} cm/s')
    if wanted('ollie'):
        rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,400,[(.4,('flick','ollie'))],duration=2.2", 2.2)
        base = position(rows[0])[2]
        height = max(position(r)[2] for r in rows) - base
        air = sum(1 for r in rows if r['mode'] == '2')
        # The reference rises 0.98 m after a 10-tick load (the flick's .16 s), 1.31 m after a long one.
        record('ollie_height', rows, 75 < height < 125 and 'Ollie' in qa.combos(rows) and rows[-1]['mode'] == '1' and not qa.count(rows, 'bails'),
               f'{height:.0f} cm high, {air} air frames; {qa.combos(rows)}')
    for key, name in FLIPS.items():
        if not wanted('flip') and not wanted('flip_' + key):
            continue
        rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,450,[(.4,('flick','{key}'))],duration=2.3", 2.3)
        combos = qa.combos(rows)
        landed = rows[-1]['mode'] == '1' and not qa.count(rows, 'bails')
        # The line reads "Kickflip" (or "Fakie Kickflip" and so on); "360 Flip" must not pass for "Laser Flip".
        tricks = [t.strip() for c in combos.split(' / ') for t in c.split('+')]
        record(f'flip_{key}', rows, landed and any(t == name or t.endswith(' ' + name) for t in tricks), f'{combos or "(none)"}; landed={landed}')
    if wanted('grab'):
        # Hold the right trigger for the first half second of the air (a grab held into the landing bails).
        rows = record_while(f'''
live.park.place({QUARTER[0]},{QUARTER[1]},0); live.park.look(-12,0); live.park.launch(950)
live.AIR=[0.0]
def grab(dt):
    s=live.skate_state(); air='mode=2 ' in s
    live.AIR[0]=live.AIR[0]+dt if air else 0.0
    live.skate_input(grab_right=air and .08<live.AIR[0]<.6)
live.behave('grab', grab)
''', 5)
        qa.py("live.stop('grab'); live.skate_input()")
        combos = qa.combos(rows)
        record('grab_indy', rows, 'Indy' in combos and rows[-1]['mode'] == '1' and not qa.count(rows, 'bails'), combos or '(none)')
    if wanted('spin'):
        for direction in (-1, 1):
            events = [(.4, {'right': (0, -1), 'left': (direction, 0)}), (.62, {'right': (0, 1), 'left': (direction, 0)}),
                      (.66, {'left': (direction, 0)}), (1.6, {})]
            rows = qa.run_scenario(f'{FLAT[0]},{FLAT[1]},0,500,{events!r},duration=2.6', 2.6)
            angle = 0
            for prev, row in zip(rows, rows[1:]):
                if row['mode'] == '2':
                    angle += (float(row['yaw']) - float(prev['yaw']) + 180) % 360 - 180
            record(f'flat_spin_{direction}', rows, abs(angle) > 200 and rows[-1]['mode'] == '1' and not qa.count(rows, 'bails'),
                   f'air rotation {angle:.0f} degrees; {qa.combos(rows)}')
        # A 360 needs a bigger air: off the quarter, the stick held for a 360 (see vert_checks); the release turns the
        # rest. (A yaw read while the deck stands on the wall is not the spin, so the hold is timed.)
        rows = record_while(f"live.park.place({QUARTER[0]},{QUARTER[1]},0); live.park.look(-12,0); live.park.launch(950)\n"
                            + SPIN_HOLD.replace('HOLD', '.48'), 5)
        qa.py("live.stop('spin'); live.skate_input()")
        record('quarter_360', rows, '360' in qa.combos(rows) or '540' in qa.combos(rows), qa.combos(rows) or '(none)')
    if wanted('grind'):
        grind_rows(record)
    if wanted('manual'):
        rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,480,[(.3,{{'right':(0,-.5)}}),(1.8,{{}})],duration=2.3", 2.3)
        record('manual', rows, qa.ever(rows, 'manual', '1') and rows[-1]['manual'] == '0' and 'Manual' in qa.combos(rows)
               and not qa.count(rows, 'bails'), qa.combos(rows))
        rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,480,[(.3,{{'right':(0,.5)}}),(1.8,{{}})],duration=2.3", 2.3)
        record('nose_manual', rows, 'Nose Manual' in qa.combos(rows) and not qa.count(rows, 'bails'), qa.combos(rows))
    if wanted('vert'):
        vert_checks(record)
        rows = qa.run_scenario(f"{BOWL[0]},{BOWL[1]},0,850,[],duration=5", 5)
        record('bowl_carve', rows, rows[-1]['mode'] == '1' and not qa.count(rows, 'bails') and max(map(speed, rows)) > 300,
               'states ' + ','.join(sorted(qa.modes(rows))) + f'; speed {speed(rows[-1]):.0f}')
    if wanted('wheels'):
        wheels_contact(record)
    if wanted('bail'):
        qa.py(f"live.park.place({FLAT[0] + 18},{FLAT[1]},0); live.park.launch(600); live.skate_release()")
        frame_sampler()
        rows = record_while("live.skate_input(); live.L.skate_release()\n"
                            "live.L.input_key('Gamepad_LeftThumbstick','press',1); live.L.input_key('Gamepad_RightThumbstick','press',1)\n"
                            "live.L.input_key('Gamepad_LeftTriggerAxis','axis',1); live.L.input_key('Gamepad_RightTriggerAxis','axis',1)", .5)
        qa.py("live.REC2=list(live.REC); live.behave('rec', lambda dt: live.REC2.append(live.skate_state()))\n"
              "live.L.input_key('Gamepad_LeftThumbstick','release',0); live.L.input_key('Gamepad_RightThumbstick','release',0)\n"
              "live.L.input_key('Gamepad_LeftTriggerAxis','axis',0); live.L.input_key('Gamepad_RightTriggerAxis','axis',0)")
        time.sleep(8)
        rows = [qa.parse(r) for r in json.loads(qa.py("live.stop('rec'); print(json.dumps(live.REC2))").strip().splitlines()[-1])]
        down = sum(1 for r in rows if r['mode'] == '4') / 60
        frames = frame_report()
        # The fall (ragdoll, loose board, the surfaces around made physical) must not hitch.
        record('bail_recovery', rows, '4' in qa.modes(rows) and '0' not in qa.modes(rows) and rows[-1]['mode'] == '1'
               and 1.5 < down < 6 and frames.get('worst_ms', 999) < 50,
               f'states {",".join(sorted(qa.modes(rows)))}; down about {down:.1f} s; worst frame {frames.get("worst_ms", 0):.1f} ms')
        rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,500,[(.1,{{'push':True}}),(.3,{{}})],duration=1", 1)
        record('ride_after_bail', rows, rows[-1]['mode'] == '1' and speed(rows[-1]) > 300, f'speed {speed(rows[-1]):.0f}')
    if wanted('hands_clear') or wanted('push_foot'):
        hand_rows(record)
    if wanted('pacing'):
        # Ride through the park with tricks, then mount and switch character, sampling every frame.
        frame_sampler()
        qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,0,[(0,{{'push':True}}),(2,{{}}),(2.3,('flick','kickflip')),(3.6,('flick','360_flip'))],duration=5", 5)
        qa.run_scenario(f"{QUARTER[0]},{QUARTER[1]},0,950,[],duration=4", 4)
        riding = frame_report()
        cost = qa.py('print(live.skate_state())').split('cost=')[-1].split()[0]
        frame_sampler()
        qa.py("live.skate_release(); live.skate()")
        time.sleep(1)
        qa.py("live.skate_park(); live.skate_input()")
        time.sleep(1.5)
        mounting = frame_report()
        frame_sampler()
        switched = qa.py("print(live.L.switch_character('Link'))").strip()
        time.sleep(2.5)
        qa.py("live.skate_park(); live.skate_input()")
        time.sleep(1.5)
        qa.py("live.L.switch_character('Cairo')")
        time.sleep(2.5)
        switching = frame_report()
        mount_ride()
        record('pacing_riding', [], riding['fps'] >= 58 and riding['p99_ms'] < 33.4 and not riding['over_50ms'], json.dumps(riding) + f' sim cost {cost} ms')
        record('pacing_mount', [], mounting['worst_ms'] < 100, json.dumps(mounting))
        record('pacing_switch', [], switching['worst_ms'] < 250, f'{switched}: ' + json.dumps(switching))
    if wanted('pose'):
        pose_checks(record, seen)
    if wanted('cost'):
        cost_ab(record)
    if wanted('megadrop'):
        megadrop(record)
    if wanted('parapet'):
        parapet_corner(record)
    if any(wanted(f'preland_{key}') for key in PRELAND):
        preland_checks(record)
    if any(wanted(name) for name in FAKIE_ROWS):
        fakie_checks(record, wanted)
    if any(wanted(name) for name in PHYSICAL):
        physical_checks(record, wanted)
    qa.py('live.skate_input(); live.skate_park(); live.skate_release()')
    out = qa.yori.OUT / 'skateqa' / 'ride.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2) + '\n')
    print(f'{sum(r["ok"] for r in results.values())}/{len(results)} passed -> {out}')
    return 0 if all(r['ok'] for r in results.values()) else 1


# The pool's north wall in Mega Park (island metres, the film's quarter airs), launched north from the pool floor at
# 11.5 m/s; its face's level normal points south (Unreal +y).
POOL = (-108., 1258.5, 82.)
POOL_OUT = (0, 1)
# Held from the take-off: the left stick, full right, for HOLD seconds of the air.
SPIN_HOLD = """
live.AIRT=[0.0]
def _spin(dt):
    s=live.skate_state(); air='mode=2 ' in s
    live.AIRT[0]=live.AIRT[0]+dt if air else 0.0
    live.skate_input(left=(1,0) if air and live.AIRT[0]<HOLD else (0,0))
live.behave('spin', _spin)
"""


def lip_air(rows, out):
    """The first air in `rows` and how it came down, or None. `out` is the take-off face's level normal (Unreal x, y),
    back into the ramp: 'into' is how far from the lip the board came down along it (cm), 'drop' how far below it."""
    a = next((i for i in range(1, len(rows)) if rows[i]['mode'] == '2' and rows[i - 1]['mode'] == '1'), None)
    b = next((i for i in range(a, len(rows)) if rows[i]['mode'] != '2'), None) if a is not None else None
    if b is None or b < a + 3:
        return None
    dt = lambda r: float(r.get('dt', 16.7)) / 1000
    lip, down = position(rows[a - 1]), position(rows[b])
    p0, p1 = position(rows[a]), position(rows[a + 2])
    span = dt(rows[a + 1]) + dt(rows[a + 2])
    v = [(p1[k] - p0[k]) / span for k in range(3)]
    after = rows[min(len(rows) - 1, b + 6)]
    return {'into': (down[0] - lip[0]) * out[0] + (down[1] - lip[1]) * out[1], 'drop': lip[2] - down[2],
            'apex': max(position(r)[2] for r in rows[a:b]) - lip[2], 'air': sum(dt(r) for r in rows[a:b]),
            'up': v[2], 'out': v[0] * out[0] + v[1] * out[1], 'along': abs(v[1] * out[0] - v[0] * out[1]),
            'mode': rows[b]['mode'], 'fakie': after.get('fakie') == '1', 'deckup': rows[a - 1].get('deckup', '?')}


def judge_lip(record, name, rows, out, fakie, want=''):
    """A lip air back into the face it left: down on the face within a metre of the lip (and at least 20 cm below it),
    fakie or forward as asked, no bail, riding away; `want` must be in the combo."""
    air = lip_air(rows, out)
    if air is None:
        record(name, rows, False, f"no air off the lip; states {','.join(sorted(qa.modes(rows)))}")
        return None
    bailed = any(r['mode'] == '4' for r in rows)
    away = rows[-1]['mode'] == '1' and speed(rows[-1]) > 150
    combos = qa.combos(rows)
    ok = (air['mode'] == '1' and not bailed and air['fakie'] == fakie and -30 < air['into'] < 100 and air['drop'] > 20
          and away and want in combos)
    record(name, rows, ok, f"{'fakie' if air['fakie'] else 'forward'} landing (wanted {'fakie' if fakie else 'forward'}) "
           f"{air['into']:.0f} cm out from the lip, {air['drop']:.0f} cm below it; lip-off (deck up z {air['deckup']}) {air['up']:.0f} up, {air['out']:.0f} "
           f"into the ramp, {air['along']:.0f} along it (cm/s); apex {air['apex']:.0f} cm over the lip, {air['air']:.2f} s up; "
           f"{'bailed' if bailed else 'no bail'}; then {speed(rows[-1]):.0f} cm/s, mode {rows[-1]['mode']}; {combos or '(no tricks)'}")
    return air


def vert_checks(record):
    """Lip airs (RIDE.md, Board, "Lip airs"): on the pier's quarter a straight air lands fakie back on the face, a 180
    forward and a 360 fakie (the stick let go short of each, the rest turned by touch-down); on Mega Park's pool wall
    (the film's) a straight air, and the same climbing it 20 degrees across either way; each comes down within a metre
    of the lip, below it, without a bail, and rides away. Then a back-and-forth in the pier's bowl, coasting: three
    airs keep or gain speed at the bottom, short of native's cap (native: 10 -> 11.9 -> 12.3 m/s), shown beside the
    same without AutoPump."""
    quarter = f"live.park.place({QUARTER[0]},{QUARTER[1]},0); live.park.look(-12,0); live.park.launch(950)\n"
    judge_lip(record, 'vert_quarter_straight', record_while(quarter, 5), QUARTER_OUT, True)
    # Full stick turns 752 degrees/s off a lip (SpinRate 470 x AirSpinScale 1.6) after SpinResponse's lag, which the
    # turn after the release makes up, so a hold of h turns about 752 h in all: .24 s for a 180, .48 s for a 360.
    for name, hold, fakie, want in (('vert_quarter_180', .24, False, '180'), ('vert_quarter_360', .48, True, '360')):
        rows = record_while(quarter + SPIN_HOLD.replace('HOLD', str(hold)), 5)
        qa.py("live.stop('spin'); live.skate_input()")
        judge_lip(record, name, rows, QUARTER_OUT, fakie, want)
    x, y, z = POOL
    ground = qa.py(f"g=live.L.ground_at(unreal.Vector({x * 100},{-y * 100},{z * 100}))\nprint(g.x, g.y, g.z)").split()
    for name, across in (('vert_pool_straight', 0), ('vert_pool_across_east', 20), ('vert_pool_across_west', -20)):
        yaw = -90 + across     # Unreal yaw: -90 is north
        mega_place(f"live.skate_place(unreal.Vector({ground[0]},{ground[1]},{ground[2]}), {yaw})")
        rows = record_while(f"live.L.skate_launch(unreal.Vector({1150 * math.cos(math.radians(yaw)):.1f},"
                            f"{1150 * math.sin(math.radians(yaw)):.1f},0))", 5)
        judge_lip(record, name, rows, POOL_OUT, True)
    tune = "unreal.SystemLibrary.execute_console_command(live.L.game_world(), 'skate.RideTune {}')"
    bottoms = {}
    for label, words in (('no AutoPump', 'AutoPump=0'), ('', '""')):   # "" empties the CVar (no value only prints it)
        qa.py(tune.format(words))
        rows = qa.run_scenario(f"{BOWL[0]},{BOWL[1]},0,1000,[],duration=12", 12)
        airs, start, i = [], 0, 1
        while i < len(rows):
            if rows[i]['mode'] == '2' and rows[i - 1]['mode'] != '2':
                j = next((k for k in range(i, len(rows)) if rows[k]['mode'] != '2'), len(rows))
                if j - i > 15:
                    airs.append((i, j))
                i = j
            i += 1
        bottoms[label] = [max((speed(r) for r in rows[s:a] if r['mode'] == '1'), default=0) for s, a in
                          zip([0] + [b for _, b in airs], [a for a, _ in airs])]
        bailed = any(r['mode'] == '4' for r in rows)
        # Each landing: the speed into it and out of it, on a face whose up is this steep (deck up z).
        landings = '; landings ' + ', '.join(f"{speed(rows[b - 1]):.0f}->{speed(rows[b]):.0f} at up z {rows[b].get('deckup', '?')}"
                                             for _, b in airs if b < len(rows))
        if label:
            print(f"INFO vert_back_and_forth with {label}: bottom speeds {' -> '.join(f'{v:.0f}' for v in bottoms[label])} cm/s, "
                  f"{len(airs)} airs, {'bailed' if bailed else 'no bail'}{landings}", flush=True)
    qa.py(tune.format('""'))
    got = bottoms['']
    # Native's band: no air loses speed at the bottom (2% slack) and none passes its cap (12.3 m/s, plus 0.7).
    record('vert_back_and_forth', rows, len(airs) >= 3 and not bailed and all(v >= .98 * got[0] for v in got[1:4]) and max(got) <= 1300,
           f"bottom speeds {' -> '.join(f'{v:.0f}' for v in got)} cm/s before each air (native 1000 -> 1190 -> 1230), "
           f"{len(airs)} airs, {'bailed' if bailed else 'no bail'}{landings}")


# Each frame, every wheel's clearance along the ground's normal under it: the wheel's centre (its bone) to the ground,
# less the wheel's reach toward it (the radius, by the axle's tilt to the normal), in cm.
WHEELS = """
import math
_ch = unreal.GameplayStatics.get_player_character(live.L.game_world(), 0)
# The board as shown: the skate component's wheel meshes (SkateWheel<end><side>, placed at the wheel bones' centres:
# front right, front left, back right, back left), not the hidden pose mesh, which stays in the clips' root space.
_parts = {c.get_name(): c for c in _ch.get_components_by_class(unreal.StaticMeshComponent)}
_w = [_parts[n] for n in ('SkateWheel00', 'SkateWheel01', 'SkateWheel10', 'SkateWheel11')]
_objects = [unreal.ObjectTypeQuery.OBJECT_TYPE_QUERY1, unreal.ObjectTypeQuery.OBJECT_TYPE_QUERY2]
_skip = [_ch] + list(_ch.get_attached_actors() or [])
live.WHITS = {}
def _hit(a, b):
    # The first hit that starts clear of what it hits: a trace that starts inside something (the rider's feet, a
    # volume) reports its own start, which is not the ground. What it skipped and what it took is counted in WHITS.
    a, b = unreal.Vector(*a), unreal.Vector(*b)
    hits = unreal.SystemLibrary.line_trace_multi_for_objects(live.L.game_world(), a, b, _objects, True, _skip, unreal.DrawDebugTrace.NONE, True) or []
    for h in hits:
        t = h.to_tuple()
        name = (t[9].get_name() if t[9] else '?') + '/' + (t[10].get_name() if t[10] else '?')
        if t[1] or t[3] <= 0:
            live.WHITS['skipped ' + name] = live.WHITS.get('skipped ' + name, 0) + 1
            continue
        live.WHITS[name] = live.WHITS.get(name, 0) + 1
        return ((t[5].x, t[5].y, t[5].z), (t[7].x, t[7].y, t[7].z))
    return None
def _wheels(dt):
    c = []
    for w in _w:
        l = w.get_world_location(); c.append((l.x, l.y, l.z))
    out = []
    for i, p in enumerate(c):
        q = c[i ^ 1]; ax = [q[k] - p[k] for k in range(3)]; s = math.sqrt(sum(v * v for v in ax)) or 1.
        # From 5 cm above the wheel's centre (under the deck, above the wheel's top) down the vertical for the ground's
        # normal, then down the normal itself, so a wheel up to 8 cm into the ground still reads.
        down = _hit((p[0], p[1], p[2] + 5), (p[0], p[1], p[2] - 80))
        hit = down and _hit(tuple(p[k] + down[1][k] * 5 for k in range(3)), tuple(p[k] - down[1][k] * 80 for k in range(3)))
        if not hit: out.append(None); continue
        n = down[1]; na = sum(n[k] * ax[k] for k in range(3)) / s
        out.append(round(sum((p[k] - hit[0][k]) * n[k] for k in range(3)) - WHEEL_R * math.sqrt(max(0., 1 - na * na)), 2))
    live.WREC.append((live.skate_state(), out))
live._wheels = _wheels
"""
# A low close-up from the inside of a carve (the board's right in a right turn), at wheel height.
CLOSEUP = """
import math
live.SHOT=[0]
def _closeup(dt):
    live.SHOT[0]+=1; n=live.SHOT[0]
    if n < 48: return
    if n > 70: unreal.MegaParkValidation.restore_player_camera(); live.stop('closeup'); return
    s=live.skate_state(); yaw=math.radians(float(s.split('yaw=')[1].split()[0]))
    pawn=unreal.GameplayStatics.get_player_pawn(live.L.game_world(), 0)
    at=next(c for c in pawn.get_components_by_class(unreal.StaticMeshComponent) if c.get_name() == 'SkateDeck').get_world_location()
    ahead=unreal.Vector(math.cos(yaw), math.sin(yaw), 0.0); right=unreal.Vector(-math.sin(yaw), math.cos(yaw), 0.0)
    unreal.MegaParkValidation.review_camera(at+right*150.0+ahead*30.0+unreal.Vector(0,0,-2), at+unreal.Vector(0,0,-4), 38.0)
    if n == 62: live.L.screenshot(PATH)
live.behave('closeup', _closeup)
"""
WHEEL_RUNS = [(f'carve {v / 100:.0f} m/s {"right" if d > 0 else "left"}', f"{OPEN[0]},{OPEN[1]},0,{v},[(.3,{{'left':({d},0)}}),(1.2,{{}})],duration=1.5", 1.5)
              for v in (300, 600, 900) for d in (1, -1)]


def wheel_run(args, seconds):
    qa.py(f"live.scenario({args})\nlive.WREC=[]\nlive.behave('wheels', live._wheels)")
    time.sleep(seconds + .6)
    frames = json.loads(qa.py("live.stop('rec'); live.stop('wheels'); import json; print(json.dumps(live.WREC))").strip().splitlines()[-1])
    return [(qa.parse(state), clear) for state, clear in frames]


def wheels_contact(record):
    """Wheels on the ground (RIDE.md, Rider, "Placement" and "Board"): carves at 3, 6 and 9 m/s both ways in both
    stances, a pump in the bowl, a powerslide and a manual. On the ground (mode 1) no wheel is more than 1 cm into the
    ground; rolling (an R_, M_ or L_ clip) none is more than 1.5 cm above it (in a manual, the axle it rolls on).
    Writes a low close-up of a hard carve to build/yorimichi/skateqa/ride-carve-closeup.png."""
    qa.py(WHEELS.replace('WHEEL_R', '3.1'))
    runs = []
    try:
        for goofy in (False, True):
            qa.py(f'live.L.skate_goofy({goofy})')
            runs += [(('goofy ' if goofy else 'regular ') + label, wheel_run(args, secs)) for label, args, secs in WHEEL_RUNS]
    finally:
        qa.py('live.L.skate_goofy(False)')
    runs.append(('bowl pump', wheel_run(f"{BOWL[0]},{BOWL[1]},0,850,[(0,{{'push':True}}),(4,{{}})],duration=4.5", 4.5)))
    runs.append(('powerslide', wheel_run(f"{FLAT[0]},{FLAT[1]},0,700,[(.3,{{'slide':True,'left':(.6,0)}}),(1.3,{{}})],duration=2", 2)))
    runs.append(('manual', wheel_run(f"{FLAT[0]},{FLAT[1]},0,480,[(.3,{{'right':(0,-.5)}}),(1.8,{{}})],duration=2.3", 2.3)))
    sink, lift, bad_sink, bad_lift, judged, notes = (99., ''), (-99., ''), 0, 0, 0, []
    for label, frames in runs:
        run_sink, run_lift = 99., -99.
        for row, clear in frames[4:]:
            if row.get('mode') != '1' or None in clear:
                continue
            judged += 1
            clip = row.get('clip', '')
            low = min(clear)
            run_sink = min(run_sink, low)
            if low < sink[0]: sink = (low, f'{label} {clip}')
            bad_sink += low < -1.
            if clip[:2] in ('R_', 'M_', 'L_'):
                axle = clear if row.get('manual') != '1' else min((clear[:2], clear[2:]), key=sum)
                high = max(axle)
                run_lift = max(run_lift, high)
                if high > lift[0]: lift = (high, f'{label} {clip}')
                bad_lift += high > 1.5
        notes.append(f'{label} {run_sink:.1f}/{run_lift:.1f}')
    hits = qa.py("import json; print(json.dumps(sorted(live.WHITS.items(), key=lambda kv: -kv[1])[:6]))").strip().splitlines()[-1]
    shot = qa.yori.OUT / 'skateqa' / 'ride-carve-closeup.png'
    shot.parent.mkdir(parents=True, exist_ok=True)
    qa.py(CLOSEUP.replace('PATH', repr(str(shot))) + f"live.scenario({OPEN[0]},{OPEN[1]},0,900,[(.3,{{'left':(1,0)}}),(1.2,{{}})],duration=1.5)")
    time.sleep(2.1)
    qa.py("live.stop('rec'); live.stop('closeup'); unreal.MegaParkValidation.restore_player_camera()")
    record('wheels_contact', [], judged > 300 and not bad_sink and not bad_lift,
           f'{judged} frames on the ground: deepest wheel {sink[0]:.2f} cm ({sink[1]}), {bad_sink} frames below -1 cm; '
           f'highest rolling wheel {lift[0]:.2f} cm ({lift[1]}), {bad_lift} frames above 1.5 cm; per run deepest/highest: '
           + ', '.join(notes) + f'; traces hit {hits}; close-up {shot}')


# Clips whose feet stand on the deck (RIDE.md, Rider): rolling, the load, powerslides, manuals, grinds, landings and
# the air idle. Pushes, brakes, standing, grabs, flips and bails move a foot off it.
PLANTED = ('R_IDLE', 'R_ANTIC', 'R_SLIDE', 'M_', 'G_', 'L_', 'IA_IDLE')
POP_SPEED = 1500.   # cm/s: a body bone moving this fast in one frame and not in the frames around it has popped


POSE_RIDES = (('push', "[(0,{'push':True}),(2,{})]", 0, 2.5), ('kickflip', "[(.4,('flick','kickflip'))]", 450, 2.3),
              ('manual', "[(.3,{'right':(0,-.5)}),(1.8,{})]", 480, 2.3))
REFERENCE = qa.GAME / 'assets/skate/ride/reference.json'
STAND_BONES = ('HIPS', 'SPINE3', 'HEAD', 'LEFTHAND', 'RIGHTHAND', 'LEFTFOOT', 'RIGHTFOOT', 'LEFTTOEBASE', 'RIGHTTOEBASE')
DECK_FRAME = """
import json
_ch = unreal.GameplayStatics.get_player_character(live.L.game_world(), 0)
_m = next(c for c in _ch.get_components_by_class(unreal.SkeletalMeshComponent) if c.get_name().startswith('RidePose'))
_cs = unreal.RelativeTransformSpace.RTS_COMPONENT
_deck = _m.get_socket_transform('SKATEBOARD_ROOT', _cs)
_out = {}
for _n in NAMES:
    _l = _deck.inverse_transform_location(_m.get_socket_transform(_n, _cs).translation)
    _out[_n] = (_l.x, _l.y, _l.z)
print(json.dumps(_out))
"""


def pose_rides(seen):
    for name, events, speed_in, seconds in POSE_RIDES:
        seen[name] = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,{speed_in},{events},duration={seconds}", seconds)
    seen['grind'] = qa.run_scenario(f"{RAIL[0]},{RAIL[1]},0,520,[(.98,('flick','ollie'))],duration=3.5", 3.5)


def pose_health(named):
    """Feet off the deck on planted clips, and pops between frames, over recorded runs ({name: rows}). Also returns
    each pop with the frames around it (the run, the frame, its step and the rows from 6 before to 3 after)."""
    runs = list(named.values())
    # Feet: frames that have been on a planted clip for at least a sixth of a second (the cross-fade in is done).
    planted, off, worst = 0, 0, {}
    for run in runs:
        held = 0
        for prev, r in zip([None] + run, run):
            held = held + 1 if prev and prev.get('clip') == r.get('clip') else 0
            if r.get('mode') == '4' or held < 10 or not r.get('clip', '').startswith(PLANTED):
                continue
            planted += 1
            if int(r.get('feetoff', 0)):
                off += 1
                worst.setdefault(r['clip'], r.get('feet'))
    feet = (planted > 60 and off / planted < .03,
            f'{off} of {planted} planted frames with a foot off the deck'
            + (' (' + ', '.join(f'{c} toes at {f} cm' for c, f in list(worst.items())[:4]) + ')' if worst else ''))
    # Continuity: no body bone jumps in one frame (a pop between clips) outside a bail; the first frames of a run
    # (the rider placed) are skipped.
    pops, fastest, context = [], 0., []
    for name, run in named.items():
        steps = [float(r.get('step', 0)) for r in run]
        for i in range(10, len(run) - 3):
            if run[i].get('mode') == '4' or run[i - 1].get('mode') == '4':
                continue
            fastest = max(fastest, steps[i])
            around = sorted(steps[i - 3:i] + steps[i + 1:i + 4])[3]
            if steps[i] > POP_SPEED and steps[i] > 3 * around:
                bone = f" {run[i]['stepbone']}" if 'stepbone' in run[i] else ''
                pops.append(f"{run[i - 1].get('clip')}->{run[i].get('clip')} {steps[i]:.0f} cm/s{bone}")
                context.append({'run': name, 'frame': i, 'step': steps[i], 'around': around, 'rows': run[i - 6:i + 4]})
    continuity = (not pops, f'{len(pops)} pops' + (': ' + '; '.join(pops[:4]) if pops else '')
                  + f'; fastest body bone {fastest:.0f} cm/s')
    return feet, continuity, context


def stand_errors(goofy):
    """The standing rider's bones in the deck's frame against the reference's stand (a regular rider's; a goofy rider
    mirrors it, left and right swapped), in cm."""
    reference = json.loads(REFERENCE.read_text())['mechanics']['stand/idle']['numbers']['bones_in_deck_frame']
    qa.py(f'live.L.skate_goofy({goofy})')
    rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,0,[],duration=2.5", 2.5)
    got = json.loads(qa.py(f'NAMES={list(STAND_BONES)!r}' + DECK_FRAME).strip().splitlines()[-1])
    swap = lambda n: n.replace('LEFT', '#').replace('RIGHT', 'LEFT').replace('#', 'RIGHT') if goofy else n
    errors = {}
    for name in STAND_BONES:
        left, up, forward = reference[name]     # native: x left, y up, z forward, metres
        errors[swap(name)] = math.dist((forward * 100, (left if goofy else -left) * 100, up * 100), got[swap(name)])
    return rows[-1].get('clip', ''), errors


def pose_checks(record, seen):
    """The rider's pose over every frame the other checks recorded (or a short ride of its own), the stand in both
    stances against the reference, and the same rides goofy (the clips unmirrored)."""
    if not seen:
        pose_rides(seen)
    runs = {name: rows for name, rows in seen.items() if rows and 'clip' in rows[0]}
    if not runs:
        record('pose', [], False, 'no clip= on the state line: the rider rig is not in this build')
        return
    rows = [r for run in runs.values() for r in run]
    bad = sum(int(r.get('nan', 0)) > 0 for r in rows)
    record('pose_nan', rows, not bad, f'{bad} of {len(rows)} frames with a NaN bone')
    feet, continuity, pops = pose_health(runs)
    record('pose_feet', rows, *feet)
    record('pose_continuity', rows, *continuity)
    anim = [float(r['anim']) for r in rows if 'anim' in r]
    if anim:
        anim.sort()
        print(f'animator {anim[len(anim) // 2]:.3f} ms p50, {anim[min(len(anim) - 1, round(.99 * (len(anim) - 1)))]:.3f} ms p99 per frame', flush=True)

    notes, ok = [], True
    try:
        for goofy in (False, True):
            clip, errors = stand_errors(goofy)
            mean, worst = sum(errors.values()) / len(errors), max(errors, key=errors.get)
            ok = ok and clip.startswith('R_IDLE_HCOM_000') and mean < 1.5 and errors[worst] < 3
            notes.append(f'{"goofy" if goofy else "regular"} {clip}: mean {mean:.2f} cm, worst {worst} {errors[worst]:.2f} cm')
        goofy_seen = {}
        pose_rides(goofy_seen)
    finally:
        qa.py('live.L.skate_goofy(False)')
    record('pose_stand', [], ok, '; '.join(notes))
    goofy_runs = {name: rows for name, rows in goofy_seen.items() if rows and 'clip' in rows[0]}
    feet, continuity, goofy_pops = pose_health(goofy_runs)
    record('pose_goofy', [r for run in goofy_runs.values() for r in run], feet[0] and continuity[0],
           f'{feet[1]}; {continuity[1]}')
    # Every recorded frame of both stances, and each pop with the frames around it, for a look afterwards.
    out = qa.yori.OUT / 'skateqa' / 'ride-pose.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({'regular': runs, 'goofy': goofy_runs, 'pops': pops,
                               'goofy_pops': goofy_pops}) + '\n')


# The reference (RIDE.md, Physical rider): the oracle's published body against its animation pose.
BAIL_REFERENCE = {.125: (0, 8), .25: (8, 26), .5: (14, 37), 1.: (64, 127)}
# The reference's falls (oracle traces): the pelvis's travel 1 s after the bail and where it comes to rest, over the
# entry speed times 1 s. A deliberate bail on flat at 4.6 m/s: 0.97 and 1.04 (across the ground); launched faster
# (5.6 to 12.2 m/s) 0.96 to 1.00 and 1.16 to 1.40, 0.97 and 1.26 at 10.6 m/s: the travel grows with the speed, and the
# body is at rest 1.5 to 2.4 s after the bail at any speed. One in the air at 4.8 m/s across, rising at 8.7 m/s: 1.04
# and 1.36 of the speed across, 0.50 and 0.65 of the whole speed. The bands are a third either side: on flat the
# 4.6 m/s bail's, fast on flat the 10.6 m/s one's; on a quarter (no twin in the reference) from the widest of the
# flat and air ones, the whole distance over the whole speed.
BAIL_TRAVEL = {'flat': ((.65, 1.3), (.7, 1.4)), 'fast': ((.65, 1.3), (.85, 1.7)), 'quarter': ((.33, 1.4), (.43, 1.8))}
BAIL_LIE = 40.   # cm: within 1 s of a fall the pelvis is down this close to the ground under it (lie=)
BAIL_POP = 10.   # cm: the hips never move further in a frame than the pelvis body's own speed carries them, plus this
GETUP_BOARD_STEP = 8.   # cm: the board's largest move in one ride tick while it shows in a get-up (v2's glide: ~10)
# cm: the skin's deepest sampled vertex under the ground (skin=, skate.RideSkinCheck), riding and through a fall to
# the get-up. Above it the mesh shows cut by the floor.
SKIN_DEPTH = 2.   # cm: no skin deeper under the ground than this, in any group of bodies
SKIN_GROUPS = ('hands', 'forearms', 'upperarms', 'feet', 'head', 'torso', 'legs')
MEGA_ROAD = (-127.9, 1471.1, 134.)   # Mega Park's road (island metres), running east into its bend
MEGADROP = (-44.5, 1305.1, 112., 135.)   # the top of Mega Park's roll-in (island metres) and the Unreal yaw down it
MEGADROP_FLOOR = 7600.   # cm: the board (z=) is on the floor at the bottom of the roll-in below this height
# Mega Park's parapet: a point on its south line 5 m from the corner (island metres) and the Unreal direction to it.
PARAPET = ((-71.13, 1376.69, 118.91), (.4655, .885))
PHYSICAL = ('physical_riding', 'physical_landing', 'physical_bail', 'physical_bail_fast', 'physical_bail_quarter',
            'physical_cost')


# Pre-landing (RIDE.md, Air): the hips over the board (native rig, HIPS over SKATEBOARD_ROOT, cm) before the
# touch-down against the reference's (feet_to_board, every 4 ticks): within PRELAND_CM at each sample from PRELAND_FROM
# ticks before it to 2 ticks before it (the touch-down's own tick shows the landing clip).
PRELAND = {'ollie': 'ollie/6', 'kickflip': 'flip/kickflip', '360_shove': 'flip/360-pop-shuvit'}
PRELAND_FROM, PRELAND_CM = 14, 6.


def at_time(rows, t, key):
    """`key` at time t (s, the rows' own clock from their dt) by linear interpolation, or None outside the rows."""
    times, clock = [], 0.
    for r in rows:
        times.append(clock); clock += float(r.get('dt', 16.7)) / 1000
    for i in range(1, len(rows)):
        if times[i - 1] <= t <= times[i]:
            a, b = float(rows[i - 1][key]), float(rows[i][key])
            f = (t - times[i - 1]) / max(1e-6, times[i] - times[i - 1])
            return a + (b - a) * f
    return None


def preland_checks(record):
    reference = json.loads(REFERENCE.read_text())['mechanics']
    for key, name in PRELAND.items():
        numbers = reference[name]['numbers']
        land = numbers['landing_tick']
        want = [(tick - land, hips * 100) for tick, _, _, hips, _ in numbers['feet_to_board'] if -PRELAND_FROM <= tick - land <= -2]
        rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,450,[(.4,('flick','{key}'))],duration=2.3", 2.3)
        if 'hipboard' not in rows[0]:
            record(f'preland_{key}', rows, False, 'no hipboard on the state line (old binary)')
            continue
        a = next((i for i in range(1, len(rows)) if rows[i]['mode'] == '2' and rows[i - 1]['mode'] == '1'), None)
        b = next((i for i in range(a, len(rows)) if rows[i]['mode'] != '2'), None) if a is not None else None
        if b is None:
            record(f'preland_{key}', rows, False, 'no air and landing')
            continue
        landed = sum(float(r.get('dt', 16.7)) / 1000 for r in rows[:b])
        got = [(tick, cm, at_time(rows, landed + tick / 60, 'hipboard')) for tick, cm in want]
        errors = [abs(g - cm) for _, cm, g in got if g is not None]
        ok = len(errors) == len(want) and max(errors) <= PRELAND_CM and rows[-1]['mode'] == '1' and not qa.count(rows, 'bails')
        record(f'preland_{key}', rows, ok, 'hips over board (ticks before touch-down: Ride/native cm) '
               + ', '.join(f'{-tick}: {g:.0f}/{cm:.0f}' if g is not None else f'{-tick}: -/{cm:.0f}' for tick, cm, g in got)
               + f'; air {sum(float(r.get("dt", 16.7)) for r in rows[a:b]) / 1000:.2f} s')


# The fakie channel (RIDE.md, Fakie): rolling fakie the head and chest turn toward the travel. Native's angles from the
# travel (degrees, head and chest; the rig's facing from its reference pose, as RideSession measures them), from the
# native clips through native's channel blend (offline, the riding idle, the manual and a forward push as the base):
# riding forward head 3, chest 46; fakie with no channel 177, 134; fakie 72, 126; a fakie manual (torso 1) 22, 100 on
# M_IDLE (13, 77 on the nose manual); a forward push's chest 25.
FAKIE_ROLL = (72., 126.)
FAKIE_MANUAL = {'M_IDLE_N_0_CYC': (22., 100.), 'M_NOSEIDLE_N_0_CYC': (13., 77.)}
FAKIE_DEG = 6.
# The fakie rows (--only takes any of these or a prefix of them, 'fakie' for all).
FAKIE_ROWS = ('fakie_roll', 'fakie_switch', 'fakie_push', 'fakie_switch_trick', 'fakie_switch_push', 'fakie_switch_manual',
              'fakie_manual', 'fakie_powerslide', 'fakie_creep', 'fakie_blend')
# Riding switch the rider faces the travel as riding forward does (the other stance's pose): head 3, chest 46.
FORWARD = (3., 46.)
# Turning round (RIDE.md, Switch): rolling fakie the switch clip starts after FakieSwitchTime (.6 s) and the stance
# flips at its end (.733 s - .02 at 1x); a push from fakie plays it at 1.25x and flips .25 s before its end (.337 s).
SWITCH_AFTER = (.55, .85)
SWITCH_FLIP = (.6, .8)
SWITCH_PUSH_FLIP = (.28, .42)
# Through a turn round the board does not turn and its wheels roll on: the deck no more than its travel (cm a frame
# off it), the hips no more than the pose's own motion on top, the wheels by the travel along the board (RideTuning's
# WheelRadius, cm), the deck's yaw no more than a frame's turning (degrees).
BOARD_STEP, HIPS_STEP, WHEEL_RADIUS, YAW_STEP = 3., 5., 3.1, 5.


def clock(rows):
    """Each row's time (s) on the rows' own clock (their dt)."""
    times, t = [], 0.
    for r in rows:
        times.append(t); t += float(r.get('dt', 16.7)) / 1000
    return times


def settled(rows, key, after=.6, until=None):
    """`key` over the rows from `after` seconds on (to `until`): their median."""
    values = sorted(float(r[key]) for t, r in zip(clock(rows), rows) if t >= after and (until is None or t < until) and key in r)
    return values[len(values) // 2] if values else None


def wrapped(a, b):
    """The angle from a to b (degrees, 0-180)."""
    return abs((b - a + 180.) % 360. - 180.)


def fakie_run(goofy, speed, events, duration, x=FLAT[0], cam=None):
    """Rolling fakie east along the flat run: the board placed facing west, launched east."""
    qa.py(f'live.L.skate_goofy({goofy})')
    look = '' if cam is None else f',cam={cam}'
    return qa.run_scenario(f"{x},{FLAT[1]},180,{speed},{events},duration={duration},velocity_heading=0{look}", duration)


def switch_times(rows):
    """When the switch clip starts and when the stance flips (s on the rows' clock), None for either that does not."""
    times = clock(rows)
    start = next((t for t, r in zip(times, rows) if r.get('clip', '').startswith('R_SWITCH')), None)
    flip = next((t for t, a, b in zip(times[1:], rows, rows[1:]) if a.get('turns') != b.get('turns')), None)
    return start, flip


def drift(rows, key):
    """The largest frame-to-frame step of the position `key` away from what the velocity explains (cm): a frame that
    moves back or jumps ahead shows here though its length is the travel's."""
    worst = 0.
    for a, b in zip(rows, rows[1:]):
        if key in a and key in b and 'vel' in b:
            pa, pb, v = ([float(x) for x in r.split(',')] for r in (a[key], b[key], b['vel']))
            dt = float(b.get('dt', 16.7)) / 1000
            worst = max(worst, math.dist([q - p for p, q in zip(pa, pb)], [x * dt for x in v]))
    return worst


def rolled(rows):
    """The share of rolling frames whose wheels (wheel=, degrees) turned by the board's travel along its nose (yaw=, the
    deck's heading): the session turns them each 60 Hz tick, and a frame holds one tick or two, or now and then none
    (left out, up to a tenth of the frames). Turning backward, or not at all, they miss it by far more than the slack.
    The travel is the speed along the board (on a slope too), frames sliding across it left out."""
    hits = frames = idle = 0
    for a, b in zip(rows, rows[1:]):
        if 'wheel' not in a or 'wheel' not in b or b.get('mode') != '1' or speed(b) < 100:
            continue
        v = [float(x) for x in b['vel'].split(',')]
        yaw = math.radians(float(b['yaw']))
        along = v[0] * math.cos(yaw) + v[1] * math.sin(yaw)
        if abs(along) < .9 * math.hypot(v[0], v[1]):
            continue
        tick = math.copysign(math.hypot(*v), along) / 60 / (2 * math.pi * WHEEL_RADIUS) * 360
        step = float(b['wheel']) - float(a['wheel'])
        if wrapped(0., step) < 1:
            idle += 1
            continue
        frames += 1
        hits += min(wrapped(k * tick, step) for k in (1, 2)) < 20
    return hits / frames if frames and idle <= .1 * (frames + idle) else 0.


def switch_health(rows, start, flip):
    """Through the turn round: the board's largest yaw step a frame (it does not turn), the deck's and the hips' step
    off the travel (neither moves back or on), the wheels rolling the board's way, the camera's step and its angle
    from the travel before and after the turn (the turn does not move it), body-bone pops, feet off the deck on
    planted clips away from the switch clip, and bails. (ok, note)

    These runs start the camera where the place leaves it, facing the board's nose, and launch the board straight back:
    a camera that follows the travel's heading never turns from the opposite one, so it is measured against itself."""
    times = clock(rows)
    board = max((wrapped(float(a['yaw']), float(b['yaw'])) for a, b in zip(rows, rows[1:])), default=0.)
    moved, hips, wheels = drift(rows[5:], 'deck'), drift(rows[5:], 'hip'), rolled(rows[5:])
    later = [r for t, r in zip(times, rows) if t >= .4 and 'camyaw' in r]
    cam = max((wrapped(float(a['camyaw']), float(b['camyaw'])) for a, b in zip(later, later[1:])), default=0.)
    heading = lambda r: math.degrees(math.atan2(float(r['vel'].split(',')[1]), float(r['vel'].split(',')[0])))
    off_travel = [(t, wrapped(float(r['camyaw']), heading(r))) for t, r in zip(times, rows)
                  if t >= .15 and 'camyaw' in r and 'vel' in r and speed(r) > 50]
    before = [o for t, o in off_travel if start is None or t < start]
    after = [o for t, o in off_travel if flip is not None and t > flip + .3]
    median = lambda xs: sorted(xs)[len(xs) // 2] if xs else None
    swing = abs(median(after) - median(before)) if before and after else 0.
    _, (unpopped, pops), _ = pose_health({'switch': rows})
    near = lambda t: start is not None and start - .05 <= t <= (flip or start + 1) + .3
    planted = [r for t, r in zip(times, rows) if t > .2 and not near(t) and r.get('clip', '').startswith(PLANTED)]
    off = sum(1 for r in planted if int(r.get('feetoff', 0)))
    ok = (board < YAW_STEP and moved < BOARD_STEP and hips <= HIPS_STEP and wheels is not None and wheels > .95 and cam < 3
          and swing < 5 and unpopped and off <= .03 * len(planted) and not qa.count(rows, 'bails'))
    rolling = f'{wheels:.0%}' if wheels is not None else '-'
    return ok, (f'board yaw step up to {board:.1f} deg/frame and {moved:.1f} cm off its travel, hips {hips:.1f} cm, wheels '
                f'rolling its way on {rolling} of the frames, camera step {cam:.1f}, camera '
                f'{median(before) if before else "-"} deg off the travel before the turn and {median(after) if after else "-"} '
                f'after; {pops}; {off} of {len(planted)} planted frames with a foot off')


def fakie_checks(record, wanted):
    for goofy in (False, True):
        stance = 'goofy' if goofy else 'regular'
        if wanted('fakie_roll'):
            # Measured before the rider turns round by himself (the switch clip starts after .6 s; fakie_switch).
            rows = fakie_run(goofy, 500, '[]', 1.)
            head, chest, weight = (settled(rows, key, .4, .6) for key in ('headyaw', 'chestyaw', 'fakiech'))
            fakie = all(r.get('fakie') == '1' for r in rows[5:])
            ok = fakie and weight is not None and weight > .99 and abs(head - FAKIE_ROLL[0]) <= FAKIE_DEG and abs(chest - FAKIE_ROLL[1]) <= FAKIE_DEG
            record(f'fakie_roll_{stance}', rows, ok, f'fakie={fakie} channel {weight}; head {head} chest {chest} degrees from the travel '
                   f'(native {FAKIE_ROLL[0]:.0f}, {FAKIE_ROLL[1]:.0f}; .4-.6 s)')
        if wanted('fakie_switch'):
            # Rolling fakie on the flat the rider turns round by himself (native: the switch clip at 1x after .6 s,
            # flipping at its end), then rides switch: facing the travel as riding forward, the other stance's clips
            # (mirror flips), the fakie channel out, rolling forward in his frame (fakie= is the rider's); the board
            # neither turns nor steps, its wheels roll on, and the camera does not move with the turn.
            rows = fakie_run(goofy, 500, '[]', 2.5, cam=0)
            start, flip = switch_times(rows)
            after = (flip or 9.) + .5
            head, chest, weight = settled(rows, 'headyaw', after), settled(rows, 'chestyaw', after), settled(rows, 'fakiech', after)
            mirror = (settled(rows, 'mirror', .2, start or 9.), settled(rows, 'mirror', after))
            # The session counts its turns over the whole game: this run's are the difference.
            turns = (rows[0].get('turns'), rows[-1].get('turns'))
            healthy, health = switch_health(rows, start, flip)
            ok = (start is not None and SWITCH_AFTER[0] <= start <= SWITCH_AFTER[1] and flip is not None
                  and SWITCH_FLIP[0] <= flip - start <= SWITCH_FLIP[1] and int(turns[1] or 0) - int(turns[0] or 0) == 1
                  and rows[-1].get('switch') == '1' and rows[-1].get('fakie') == '0' and weight is not None and weight < .01
                  and head is not None and abs(head - FORWARD[0]) <= FAKIE_DEG and abs(chest - FORWARD[1]) <= FAKIE_DEG
                  and mirror == (float(not goofy), float(goofy)) and healthy)
            record(f'fakie_switch_{stance}', rows, ok, f'switch clip at {start} s, flip at {flip} s, turns {turns[0]}->{turns[1]}; '
                   f"then switch={rows[-1].get('switch')} fakie={rows[-1].get('fakie')} channel {weight}, head {head} chest {chest} "
                   f'(forward {FORWARD[0]:.0f}, {FORWARD[1]:.0f}), mirror {mirror[0]}->{mirror[1]}; {health}')
        if wanted('fakie_push'):
            # Native turns round before a fakie push (PushFromFakie): the switch clip at 1.25x, the stance flipping .25 s
            # before its end, then the push from switch: the pushing foot moves against the travel and the chest faces
            # it. The foot on the ground is the one under the deck (feet= its height).
            rows = fakie_run(goofy, 300, "[(.3,{'push':True}),(2,{})]", 2.5, cam=0)
            start, flip = switch_times(rows)
            times = clock(rows)
            pushing = [r for t, r in zip(times, rows) if flip is not None and t >= flip and r.get('push') == '1' and 'PUSH' in r.get('clip', '')]
            foot, along = [], []
            for r in pushing:
                if 'feetalong' not in r:
                    continue
                heights = [float(v) for v in r['feet'].split(',')]
                low = min(range(2), key=lambda i: heights[i])
                if heights[low] < -3:
                    foot.append(low); along.append(float(r['feetalong'].split(',')[low]))
            steps = [b - a for a, b in zip(along, along[1:])]
            back = sum(1 for s in steps if s < 0) / max(1, len(steps))
            chest = settled(pushing, 'chestyaw', 0.)
            before = at_time(rows, .3, 'speed')
            gained = max((speed(r) for r in pushing), default=0.) - (before or 0.)
            healthy, health = switch_health(rows, start, flip)
            ok = (start is not None and .27 <= start <= .38 and flip is not None and SWITCH_PUSH_FLIP[0] <= flip - start <= SWITCH_PUSH_FLIP[1]
                  and len(steps) > 5 and back > .7 and chest is not None and chest < 90 and rows[-1].get('switch') == '1'
                  and gained > 30 and healthy)
            record(f'fakie_push_{stance}', rows, ok, f'switch clip at {start} s (push .3 s), flip at {flip} s; ground foot moving '
                   f'against the travel on {back:.0%} of {len(steps)} frames; chest {chest} degrees from the travel (native: '
                   f'switch push, about 25); {gained:.0f} cm/s gained; switch={rows[-1].get("switch")}; {health}')
        if wanted('fakie_switch_trick'):
            # From switch, the tricks are the stance in effect's: the flick follows it (a regular rider riding switch
            # flicks a kickflip as a goofy rider does), the trick is named Switch, the clips are the other stance's
            # (mirror) through the air and the landing, and he rides away still switch.
            qa.py("live.FLICKS['kickflip_mirror'] = [(-x, y) for x, y in live.FLICKS['kickflip']]")
            gesture = 'kickflip' if goofy else 'kickflip_mirror'
            rows = fakie_run(goofy, 500, f"[(1.7,('flick','{gesture}'))]", 3.3, cam=0)
            start, flip = switch_times(rows)
            combos = qa.combos(rows)
            air = [r for r in rows if r.get('mode') == '2']
            mirrored = {r.get('mirror') for r in air} | {r.get('mirror') for r in rows[-20:]}
            landed = bool(air) and rows[-1].get('mode') == '1' and not qa.count(rows, 'bails')
            ok = flip is not None and 'Switch Kickflip' in combos and landed and mirrored == {str(int(goofy))} and rows[-1].get('switch') == '1'
            record(f'fakie_switch_trick_{stance}', rows, ok, f'flip at {flip} s; {combos or "(none)"}; {len(air)} air frames, landed={landed}; '
                   f'mirror in the air and after {sorted(mirrored)} (want {int(goofy)}); switch={rows[-1].get("switch")}')
        if wanted('fakie_switch_push'):
            # Riding switch a push is the stance in effect's, forward in his frame: the push clip mirrored like the
            # roll, the pushing foot moving against the travel, the speed gained, and no turn back.
            rows = fakie_run(goofy, 300, "[(1.9,{'push':True}),(2.9,{})]", 3.3, cam=0)
            start, flip = switch_times(rows)
            times = clock(rows)
            pushing = [r for t, r in zip(times, rows) if t >= 1.9 and r.get('push') == '1' and 'PUSH' in r.get('clip', '')]
            along = []
            for r in pushing:
                heights = [float(v) for v in r['feet'].split(',')] if 'feet' in r else []
                if 'feetalong' in r and heights and min(heights) < -3:
                    along.append(float(r['feetalong'].split(',')[min(range(2), key=lambda i: heights[i])]))
            steps = [b - a for a, b in zip(along, along[1:])]
            back = sum(1 for d in steps if d < 0) / max(1, len(steps))
            turns = int(rows[-1].get('turns', 0)) - int(rows[0].get('turns', 0)) if rows else 0
            gained = max((speed(r) for r in pushing), default=0.) - (at_time(rows, 1.9, 'speed') or 0.)
            mirrored = {r.get('mirror') for r in pushing}
            healthy, health = switch_health(rows, start, flip)
            ok = (flip is not None and flip < 1.9 and turns == 1 and len(steps) > 5 and back > .7 and gained > 30
                  and mirrored == {str(int(goofy))} and rows[-1].get('switch') == '1' and healthy)
            record(f'fakie_switch_push_{stance}', rows, ok, f'flip at {flip} s, push at 1.9 s: {len(pushing)} pushing frames, mirror '
                   f'{sorted(mirrored)} (want {int(goofy)}), ground foot moving against the travel on {back:.0%} of {len(steps)} '
                   f'frames, {gained:.0f} cm/s gained, {turns} turn(s); switch={rows[-1].get("switch")}; {health}')
        if wanted('fakie_switch_manual'):
            # Riding switch the manual is the stance in effect's, forward in his frame (no fakie channel), and the
            # board stays as it is through it.
            rows = fakie_run(goofy, 480, "[(1.9,{'right':(0,-.5)}),(3.2,{})]", 3.5, cam=0)
            start, flip = switch_times(rows)
            held = [r for t, r in zip(clock(rows), rows) if t >= 1.9 and r.get('manual') == '1']
            channel = max((float(r['fakiech']) for r in held), default=1.)
            mirrored = {r.get('mirror') for r in held}
            healthy, health = switch_health(rows, start, flip)
            ok = (flip is not None and flip < 1.9 and len(held) >= 30 and channel < .01 and mirrored == {str(int(goofy))}
                  and all(r.get('switch') == '1' for r in held) and healthy)
            record(f'fakie_switch_manual_{stance}', rows, ok, f'flip at {flip} s, manual at 1.9 s: {len(held)} manual frames riding '
                   f'switch, fakie channel up to {channel:.2f}, mirror {sorted(mirrored)} (want {int(goofy)}); {health}')
        if wanted('fakie_manual'):
            rows = fakie_run(goofy, 480, "[(.3,{'right':(0,-.5)}),(2,{})]", 2.3)
            held = [r for r in rows if r.get('manual') == '1']
            torso = max((float(r['torso']) for r in held), default=0)
            head, chest = (settled(held, 'headyaw', 1.), settled(held, 'chestyaw', 1.)) if held else (None, None)
            # Whichever manual clip plays (the tail's or the nose's), native's angles on it.
            match = [clip for clip, (h, c) in FAKIE_MANUAL.items()
                     if head is not None and abs(head - h) <= FAKIE_DEG and abs(chest - c) <= FAKIE_DEG]
            ok = bool(held) and torso > .95 and bool(match)
            record(f'fakie_manual_{stance}', rows, ok, f'{len(held)} manual frames; torso up to {torso:.2f}; head {head} chest {chest} '
                   f'(native {FAKIE_MANUAL}; matches {match or "none"})')
        if wanted('fakie_powerslide'):
            rows = fakie_run(goofy, 700, "[(.3,{'slide':True,'left':(.6,0)}),(1.5,{})]", 2)
            slid = [r for r in rows if r.get('slide') == '1']
            torso = min((float(r['torso']) for r in slid), default=1)
            ok = bool(slid) and all(r.get('fakie') == '1' for r in slid) and torso < .05 and min(float(r['fakiech']) for r in slid) > .99
            record(f'fakie_powerslide_{stance}', rows, ok, f'{len(slid)} sliding frames, torso down to {torso:.2f} (native: the head-only clip)')
    qa.py('live.L.skate_goofy(False)')
    if wanted('fakie_creep'):
        # Creeping fakie the rider does not turn round: a push under PushFromRest (30 cm/s) goes nose-first, and rolling
        # fakie under SwitchMinSpeed (100 cm/s) he stays as he is.
        for name, speed_in, events in (('fakie_creep_push', 20, "[(.3,{'push':True}),(1.5,{})]"), ('fakie_creep_idle', 60, '[]')):
            rows = fakie_run(False, speed_in, events, 2.2)
            counts = [int(r.get('turns', 0)) for r in rows]
            turned = max(counts) - min(counts) if counts else 0
            clips = sum(1 for r in rows if r.get('clip', '').startswith('R_SWITCH'))
            ok = bool(rows) and turned == 0 and clips == 0 and not qa.count(rows, 'bails')
            record(name, rows, ok, f'turned round {turned} times, {clips} frames on a switch clip; then {speed(rows[-1]):.0f} cm/s, '
                   f"fakie={rows[-1].get('fakie')}" if rows else 'no rows')
    if wanted('fakie_blend'):
        # Back and forth in the bowl, coasting: a wall turns the board's travel round and the rider rolls fakie, then
        # turns round on the bowl's floor (or the next wall turns it back): the channel blends in and back out over .3 s
        # and the head turns without a jump. fakie= is the rider's (in and out of it: two changes at least); the
        # board's own is that riding switch the other way.
        rows = qa.run_scenario(f"{BOWL[0]},{BOWL[1]},0,600,[],duration=7", 7)
        board = lambda r: '1' if (r.get('fakie') == '1') != (r.get('switch') == '1') else '0'
        flips = sum(1 for a, b in zip(rows, rows[1:]) if board(a) != board(b))
        rate = max((abs(float(b['fakiech']) - float(a['fakiech'])) / max(1e-3, float(b.get('dt', 16.7)) / 1000)
                    for a, b in zip(rows, rows[1:])), default=0)
        # The head's angle from the board's nose (headyaw is from the travel, which turns round with the board's).
        nose = lambda r: float(r['headyaw']) if board(r) != '1' else 180 - float(r['headyaw'])
        # Near a stop (a wall's top) the travel and the board's fakie flag can turn round a frame apart: rows moving only.
        jump = max((abs(nose(b) - nose(a)) for a, b in zip(rows, rows[1:]) if min(speed(a), speed(b)) > 50), default=0)
        changes = ' '.join(f"{board(b)}@{t:.1f}" for t, a, b in zip(clock(rows)[1:], rows, rows[1:]) if board(a) != board(b))
        full = max(float(r['fakiech']) for r in rows)
        turns = int(rows[-1].get('turns', 0)) - int(rows[0].get('turns', 0)) if rows else 0
        rider = sum(1 for a, b in zip(rows, rows[1:]) if a.get('fakie') != b.get('fakie'))
        peak = max(range(len(rows)), key=lambda i: float(rows[i]['fakiech'])) if rows else 0
        out = min((float(r['fakiech']) for r in rows[peak:]), default=1.)
        bails = qa.count(rows, 'bails')
        ok = rider >= 2 and out < .01 and rate <= 1 / .3 * 1.1 and full > .99 and jump < 20 and not bails
        record('fakie_blend', rows, ok, f'{rider} rider fakie changes ({flips} of the board, {turns} turns round, {bails} bails); channel up to '
               f'{full:.2f} and back to {out:.2f}, fastest {rate:.1f}/s '
               f'(native 3.3/s); largest head step {jump:.1f} degrees a frame from the nose; board fakie {changes or "never changed"}, '
               f'{speed(rows[-1]):.0f} cm/s at the end' if rows else 'no rows')


def physical(on):
    qa.py(f"unreal.SystemLibrary.execute_console_command(live.L.game_world(), 'skate.RidePhysical {int(on)}')")


def floats(rows, key, keep=lambda r: True):
    return [float(r[key]) for r in rows if key in r and keep(r)]


def p95(values):
    values = sorted(values)
    return values[min(len(values) - 1, round((len(values) - 1) * .95))] if values else float('inf')


def hips(row):
    return tuple(float(x) for x in row['hips'].split(','))


def skin_check(on):
    qa.py(f"unreal.SystemLibrary.execute_console_command(live.L.game_world(), 'skate.RideSkinCheck {int(on)}')")


def skin(rows):
    """The deepest the skin goes under the ground over rows (cm, skin=), the body carrying it, and how many frames
    were measured and went deeper than SKIN_DEPTH."""
    seen = [(float(r['skin']), r.get('skin_bone', '-')) for r in rows if 'skin' in r]
    worst = max(seen, default=(float('nan'), '-'))
    return worst[0], worst[1], len(seen), sum(d > SKIN_DEPTH for d, _ in seen)


def skin_groups(rows):
    """The deepest each group of bodies (SKIN_GROUPS) goes under the ground over rows (cm, skin_groups=)."""
    worst = {}
    for r in rows:
        for part in r.get('skin_groups', '').split(','):
            group, _, depth = part.partition(':')
            if depth:
                worst[group] = max(worst.get(group, -99.), float(depth))
    return worst


def skin_text(worst):
    return ' '.join(f'{g} {worst[g]:.1f}' for g in SKIN_GROUPS if g in worst) or 'not measured'


def physical_checks(record, wanted):
    """The active ragdoll (skate.RidePhysical 1): tracking while riding and landing, falls on flat (at 6 and 11 m/s)
    and off a quarter, and its cost; the skin never under the ground (skate.RideSkinCheck, off for the cost). The
    cvars are put back as they were."""
    before = qa.py("print(unreal.SystemLibrary.get_console_variable_int_value('skate.RidePhysical'))").strip().splitlines()[-1]
    physical(True)
    skin_check(True)
    time.sleep(.8)
    try:
        if wanted('physical_riding'):
            physical_riding(record)
        if wanted('physical_landing'):
            physical_landing(record)
        if wanted('physical_bail'):
            physical_bail(record)
        if wanted('physical_bail_fast'):
            physical_bail_fast(record)
        if wanted('physical_bail_quarter'):
            physical_bail_quarter(record)
        if wanted('physical_cost'):
            skin_check(False)
            physical_cost(record)
    finally:
        skin_check(False)
        physical(before == '1')


def driven(row):
    return row.get('sim') == '1' and float(row.get('w', 0)) >= .99


def physical_riding(record):
    rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,300,[(0,{{'push':True,'left':(.5,0)}}),(1.5,{{'push':True,'left':(-.6,0)}}),"
                           f"(3,{{}})],duration=3.2", 3.2)
    held = [r for r in rows if driven(r)]
    pelvis, feet = p95(floats(held, 'pelvis_err')), p95(floats(held, 'foot_err'))
    depth, bone, measured, deep = skin(rows)
    ok = len(held) > .8 * len(rows) and pelvis < 3 and feet < 8 and measured and depth <= SKIN_DEPTH
    record('physical_riding', rows, ok,
           f'{len(held)}/{len(rows)} frames driven; pelvis {pelvis:.1f} cm, feet {feet:.1f} cm p95 '
           f'(reference: upper body 0.5 cm, feet 6-8 cm); skin {depth:.1f} cm under the ground at worst ({bone}, '
           f'{measured} frames measured; by group {skin_text(skin_groups(rows))}); pa={rows[-1].get("pa", "?")}, '
           f'{rows[-1].get("bodies", "?")} bodies')


def physical_landing(record):
    rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,500,[(.4,('flick','ollie'))],duration=2.4", 2.4)
    land = next((i for i in range(1, len(rows)) if rows[i - 1]['mode'] == '2' and rows[i]['mode'] == '1'), None)
    after = rows[land:land + 45] if land else []
    worst = max(floats(after, 'worst_err'), default=float('inf'))
    back = next((i for i, r in enumerate(after) if float(r.get('pelvis_err', 99)) < 3 and i > 3), None)
    record('physical_landing', rows, land is not None and worst < 20 and back is not None and back <= 30
           and all(driven(r) for r in after),
           f'landing worst {worst:.1f} cm, pelvis back under 3 cm after {back if back is not None else "-"} frames '
           f'(reference: 1-4 cm over riding, knocks 6 cm)')


def physical_bail(record, name='physical_bail', start=FLAT[0] + 18, speed=600, kind='flat'):
    """1 s of riding on the pier's flat (at 6 m/s), then the bail input held for 0.5 s."""
    keys = lambda on: (f"live.L.input_key('Gamepad_LeftThumbstick','{'press' if on else 'release'}',{int(on)}); "
                       f"live.L.input_key('Gamepad_RightThumbstick','{'press' if on else 'release'}',{int(on)}); "
                       f"live.L.input_key('Gamepad_LeftTriggerAxis','axis',{int(on)}); "
                       f"live.L.input_key('Gamepad_RightTriggerAxis','axis',{int(on)})")
    qa.py(f"live.park.place({start},{FLAT[1]},0); live.park.launch({speed}); live.skate_release()")
    qa.py("live.REC=[]; live.behave('rec', lambda dt: live.REC.append(live.skate_state()))\n"
          "live.skate_input(); live.L.skate_release()\n"
          "live.BAIL_AT=[0.0]\n"
          "def _bail(dt):\n"
          "    live.BAIL_AT[0]+=dt\n"
          f"    if live.BAIL_AT[0]>=1.0 and live.BAIL_AT[0]-dt<1.0: {keys(True)}\n"
          f"    if live.BAIL_AT[0]>=1.5: {keys(False)}; live.stop('bail_keys')\n"
          "live.behave('bail_keys', _bail)")
    time.sleep(10)
    judge_bail(record, name, recorded(), kind)


def physical_bail_fast(record):
    """The same at 11 m/s from the start of the flat run: the slide goes on for the entry speed times a second or so,
    as the reference's does at any speed, not for its square."""
    physical_bail(record, 'physical_bail_fast', FLAT[0], 1100, 'fast')


def physical_bail_quarter(record):
    """The film's bail on the pier's quarter: an Indy held from the take-off into the landing."""
    rows = qa.run_scenario(f"{QUARTER[0]},{QUARTER[1]},0,950,[(0,{{'grab_right':True}})],duration=9", 9)
    judge_bail(record, 'physical_bail_quarter', rows, 'quarter')


def getup_board(rows):
    """The board through a get-up (rows from the last fallen frame to half a second after he is up) never travels by
    itself while it shows: its largest move in one ride tick between two frames it shows in, how far it lay from where
    it ends, whether it went out of sight (dissolved out and in), and whether it shows at the end."""
    deck = lambda r: tuple(float(x) for x in r['deck'].split(','))
    rows = [r for r in rows if 'deck' in r]
    steps = [math.dist(deck(a), deck(b)) / max(1, int(b.get('tick', 0)) - int(a.get('tick', 0)))
             for a, b in zip(rows, rows[1:]) if a.get('vis') == '1' and b.get('vis') == '1']
    lay = math.dist(deck(rows[0]), deck(rows[-1])) if rows else float('nan')
    return max(steps, default=0.), lay, any(r.get('vis') == '0' for r in rows), bool(rows) and rows[-1].get('vis') == '1'


def judge_bail(record, name, rows, kind):
    """The first fall in rows: limp from its first frame to the get-up (the Bail profile, simulating; never handed to
    the animated slide), continuous, the pelvis down near the ground within 1 s, travel in the reference's band for
    the entry speed, and the rider up where the body lay. On flat at 6 m/s also the body against the bail clip."""
    start = next((i for i, r in enumerate(rows) if r['mode'] == '4'), None)
    if not start:
        record(name, rows, False, 'no bail' if start is None else 'bailing from the first frame')
        return
    end = next((i for i in range(start, len(rows)) if rows[i]['mode'] != '4'), len(rows))
    bail = rows[start:end]
    vel = [float(x) for x in rows[start - 1]['vel'].split(',')]
    flat = kind != 'quarter'
    entry = (math.hypot(vel[0], vel[1]) if flat else math.hypot(*vel)) / 100   # m/s
    clock = [0.]
    for r in bail[1:]:
        clock.append(clock[-1] + float(r.get('dt', 16.7)) / 1000)
    at = lambda t: next((i for i, c in enumerate(clock) if c >= t - 1e-3), None)
    lying = next((i for i, r in enumerate(bail) if r.get('phys') == 'GetUp'), len(bail))
    limp = lying > 0 and all(r.get('phys') == 'Bail' and r.get('sim') == '1' for r in bail[:lying])
    origin = hips(bail[0])
    gone = lambda r: (math.dist(hips(r)[:2], origin[:2]) if flat else math.dist(hips(r), origin)) / 100
    travel = {t: gone(bail[at(t)]) for t in (1., 2.) if at(t) is not None and at(t) < lying}
    rest = gone(bail[lying - 1]) if limp else 0.
    (low1, high1), (low_rest, high_rest) = BAIL_TRAVEL[kind]
    far = entry > 1 and low1 <= travel.get(1., 0) / entry <= high1 and low_rest <= rest / entry <= high_rest
    first = bail[:(at(1.) or len(bail)) + 1]
    lie = min((float(r['lie']) for r in first if float(r.get('lie', -1)) >= 0), default=float('inf'))
    steps = [math.dist(hips(a), hips(b)) for a, b in zip(bail, bail[1:]) if 'hips' in a and 'hips' in b]
    # A pop is the hips' move in a frame beyond what the pelvis body's speed covers in it (a fast slide's 18 cm a
    # frame, or more in a long frame, is no pop).
    pops = [math.dist(hips(a), hips(b)) - math.hypot(*(float(v) for v in b.get('hips_vel', '0,0,0').split(',')))
            * (float(b.get('dt', 0)) / 1000 or 1 / 60) for a, b in zip(bail, bail[1:]) if 'hips' in a and 'hips' in b]
    up = position(rows[end]) if end < len(rows) else None
    where = math.dist(hips(bail[lying - 1])[:2], up[:2]) if up and lying else float('inf')
    kind_seen = next((r['bail_kind'] for r in bail if r.get('bail_kind', 'none') != 'none'), '?')
    ok = limp and kind_seen == 'fall' and far and lie < BAIL_LIE and max(pops, default=99) < BAIL_POP and where < 100
    ok = ok and (kind != 'fast' or entry > 9.5)   # the fast fall comes at speed
    limpness = 'limp to the get-up' if limp else 'NOT limp throughout (handed to the animation)'
    note = (f'entry {entry:.1f} m/s, {limpness}, kind {kind_seen}; travel '
            + ', '.join(f'{t:g} s {d:.2f} m ({d / max(entry, .01):.2f}x)' for t, d in travel.items())
            + f', rest {rest:.2f} m ({rest / max(entry, .01):.2f}x) after {clock[lying - 1] if lying else 0:.1f} s '
            f'(band {low1}-{high1}x at 1 s, {low_rest}-{high_rest}x at rest); pelvis down to {lie:.0f} cm within 1 s; '
            f'largest hips step {max(steps, default=0):.1f} cm/frame ({max(pops, default=0):.1f} beyond its speed); '
            f'up {where:.0f} cm from where the hips lay')
    # The skin never under the ground, in any group of bodies, from the bail to the get-up and through it: the fall
    # and the slide, at rest (the last half second before the get-up), and the get-up until half a second after it.
    depth, bone, measured, deep = skin(bail[:lying])
    settle = next((i for i, c in enumerate(clock) if lying and c >= clock[lying - 1] - .5), lying)
    rising = start + lying
    risen = next((i for i in range(rising, len(rows)) if rows[i].get('phys') != 'GetUp'), len(rows))
    stages = {'slide': skin_groups(bail[:settle]), 'rest': skin_groups(bail[settle:lying]),
              'get-up': skin_groups(rows[rising:risen + 30])}
    deepest = max((d for worst in stages.values() for d in worst.values()), default=float('nan'))
    ok = ok and measured > 0 and deepest <= SKIN_DEPTH
    note += (f'; skin {depth:.1f} cm under the ground at worst in the bail ({bone}; {deep} of {measured} frames over '
             f'{SKIN_DEPTH:g} cm); by group (cm) ' + '; '.join(f'{k}: {skin_text(v)}' for k, v in stages.items()))
    step, lay, hidden, back = getup_board(rows[start + lying - 1:end + 30]) if lying < len(bail) else (99., 0., False, False)
    ok = ok and step < GETUP_BOARD_STEP and back
    note += (f'; get-up board lay {lay:.0f} cm from its end, {"dissolved out and in" if hidden else "stepped onto"}, '
             f'largest move while shown {step:.1f} cm/tick{"" if back else ", NOT shown after"}')
    if kind == 'flat':
        err = {t: float(bail[at(t)].get('pelvis_err', 'nan')) for t in BAIL_REFERENCE if at(t) is not None}
        ok = ok and err.get(.125, 99) < 16 and 20 < err.get(1., 0) < 200
        note += '; divergence ' + ', '.join(f'{t:g} s {v:.0f} cm (ref {BAIL_REFERENCE[t][0]}-{BAIL_REFERENCE[t][1]})'
                                            for t, v in err.items())
    record(name, rows, ok, note)


def physical_cost(record):
    """The same 4 s of riding on Mega Park's road with the physical rider off, then on."""
    ground = qa.py(f"g=live.L.ground_at(unreal.Vector({MEGA_ROAD[0] * 100},{-MEGA_ROAD[1] * 100},{MEGA_ROAD[2] * 100}))\n"
                   "print(g.x, g.y, g.z)").split()
    place = f"live.skate_place(unreal.Vector({ground[0]},{ground[1]},{ground[2]}), 0); live.L.skate_launch(unreal.Vector(700,0,0))"
    qa.py(place)
    time.sleep(3)   # the park streams in once, unmeasured
    report = {}
    for on in (False, True):
        physical(on)
        qa.py(place)
        time.sleep(1.5)
        frame_sampler()
        qa.py("live.skate_script([(2,{'push':True,'left':(.4,0)}),(2,{'push':True,'left':(-.4,0)}),(.2,{})])")
        time.sleep(4.2)
        report[on] = frame_report()
    off, on = report[False], report[True]
    record('physical_cost', [], on['frames'] and off['frames'] and on['p50_ms'] - off['p50_ms'] < .5
           and on['p99_ms'] - off['p99_ms'] < 1.5 and not on['over_50ms'],
           f"Mega Park p50 {off['p50_ms']:.2f} -> {on['p50_ms']:.2f} ms, p99 {off['p99_ms']:.2f} -> {on['p99_ms']:.2f} ms, "
           f"fps {off['fps']:.1f} -> {on['fps']:.1f}")


def cost_ab(record):
    """Ride's frame cost with the physical rider off and on: the pier's run with two flip tricks, and 6 s of pushing
    and carving on Mega Park's road. Per run: the frame intervals, the animator's time per frame (anim=) and the
    session's step per 60 Hz tick (cost=, mean and worst over each second), with the machine's load average."""
    def summary(rows, frames):
        anim = sorted(floats(rows, 'anim'))
        pick = lambda p: anim[min(len(anim) - 1, round((len(anim) - 1) * p))] if anim else 0.
        windows = {r['cost'] for r in rows if '/' in r.get('cost', '')}
        sim = [tuple(map(float, w.split('/'))) for w in windows]
        return dict(frames=frames.get('frames', 0), fps=round(frames.get('fps', 0), 1), p50_ms=round(frames.get('p50_ms', 0), 2),
                    p99_ms=round(frames.get('p99_ms', 0), 2), worst_ms=round(frames.get('worst_ms', 0), 1),
                    over_33ms=frames.get('over_33ms', 0), anim_p50_ms=round(pick(.5), 3), anim_p99_ms=round(pick(.99), 3),
                    sim_mean_ms=round(sum(m for m, _ in sim) / len(sim), 3) if sim else 0.,
                    sim_worst_ms=round(max(w for _, w in sim), 3) if sim else 0.)
    load = [round(os.getloadavg()[0], 1)]
    before = qa.py("print(unreal.SystemLibrary.get_console_variable_int_value('skate.RidePhysical'))").strip().splitlines()[-1]
    ground = qa.py(f"g=live.L.ground_at(unreal.Vector({MEGA_ROAD[0] * 100},{-MEGA_ROAD[1] * 100},{MEGA_ROAD[2] * 100}))\n"
                   "print(g.x, g.y, g.z)").split()
    place = f"live.skate_place(unreal.Vector({ground[0]},{ground[1]},{ground[2]}), 0); live.L.skate_launch(unreal.Vector(700,0,0))"
    report = {}
    try:
        for on in (False, True):
            physical(on)
            time.sleep(.5)
            frame_sampler()
            rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,0,[(0,{{'push':True}}),(2,{{}}),(2.3,('flick','kickflip')),"
                                   f"(3.6,('flick','360_flip'))],duration=5", 5)
            report[f'pier_physical_{int(on)}'] = summary(rows, frame_report())
            qa.py(place)
            time.sleep(3 if not on else 1.5)   # the first time, Mega Park streams in unmeasured
            qa.py(place)
            time.sleep(1)
            frame_sampler()
            rows = record_while("live.skate_script([(2,{'push':True,'left':(.4,0)}),(2,{'push':True,'left':(-.4,0)}),"
                                "(2,{'push':True}),(.2,{})])", 6.4)
            report[f'mega_physical_{int(on)}'] = summary(rows, frame_report())
            load.append(round(os.getloadavg()[0], 1))
    finally:
        physical(before == '1')
    print('cost ' + json.dumps(report), flush=True)
    ok = all(r['frames'] > 100 and r['worst_ms'] < 50 for r in report.values()) and len(report) == 4
    record('cost_ab', [], ok, '; '.join(f"{k}: p50 {r['p50_ms']} p99 {r['p99_ms']} worst {r['worst_ms']} ms, "
                                        f"anim {r['anim_p50_ms']}/{r['anim_p99_ms']} ms, sim {r['sim_mean_ms']}/{r['sim_worst_ms']} ms"
                                        for k, r in report.items()) + f'; load average {load}')


def mega_place(place):
    """Run `place` (a placement in Mega Park), letting the park stream in around it first."""
    qa.py(place)
    time.sleep(2.5)
    qa.py(place)
    time.sleep(.6)


def megadrop(record):
    """Roll in from the upper deck at 3 m/s: over the crest without leaving the ground, down the face and through the
    concave transition at the bottom (over 20 m/s) without a bail."""
    x, y, z, yaw = MEGADROP
    ground = qa.py(f"g=live.L.ground_at(unreal.Vector({x * 100},{-y * 100},{z * 100}))\nprint(g.x, g.y, g.z)").split()
    mega_place(f"live.skate_place(unreal.Vector({ground[0]},{ground[1]},{ground[2]}), {yaw})")
    rows = record_while(f"live.L.skate_launch(unreal.Vector({300 * math.cos(math.radians(yaw)):.1f},"
                        f"{300 * math.sin(math.radians(yaw)):.1f},0))", 7)
    floor = next((i for i, r in enumerate(rows) if float(r['z']) < MEGADROP_FLOOR), None)
    judged = rows[:floor + 30] if floor is not None else rows
    air = [i for i, r in enumerate(rows[:floor] if floor is not None else rows) if i > 6 and r['mode'] == '2']
    bailed = any(r['mode'] == '4' for r in judged)
    record('megadrop', rows, floor is not None and not air and not bailed,
           f"floor reached {'at %.0f cm/s after %.1f s' % (speed(rows[floor]), floor / 60) if floor is not None else 'never'}; "
           f"{len(air)} air frames before it{' from frame %d' % air[0] if air else ''}; "
           f"{'bailed' if bailed else 'no bail'} through half a second on the floor; top speed {max(map(speed, judged)):.0f} cm/s")


def parapet_corner(record):
    """Drop onto the parapet's south line 5 m before its corner, moving at 6 m/s toward it: the board locks on without
    jumping onto the line, grinds to the corner, and flies off the end (the corner is too sharp to follow) without
    stalling or bailing."""
    (x, y, z), (dx, dy) = PARAPET
    yaw = math.degrees(math.atan2(dy, dx))
    # 80 cm over the line, so the board starts in the air and comes down onto it.
    place = f"live.skate_place(unreal.Vector({x * 100},{-y * 100},{z * 100 + 80}), {yaw:.2f})"
    mega_place(place)
    qa.py(place)
    rows = record_while(f"live.L.skate_launch(unreal.Vector({600 * dx:.1f},{600 * dy:.1f},0))", 3)
    lock = next((i for i, r in enumerate(rows) if r['mode'] == '3'), None)
    end = next((i for i in range(lock, len(rows)) if rows[i]['mode'] != '3'), None) if lock is not None else None
    after = rows[lock:end + 36] if end is not None else []
    slowest = min(map(speed, after), default=0)
    bailed = any(r['mode'] == '4' for r in after)
    # The board's step at the lock beyond its own speed: the native board touches the line before it locks.
    jump = max((math.dist(position(a), position(b)) - speed(b) * float(b.get('dt', 16.7)) / 1000
                for a, b in zip(rows[max(0, lock - 1):lock + 8], rows[max(0, lock - 1) + 1:lock + 9])), default=99) if lock is not None else 99
    record('parapet_corner', rows, lock is not None and end is not None and not bailed and slowest >= 100 and jump < 15,
           (f"locked at {speed(rows[lock]):.0f} cm/s, grinded {(end - lock) / 60:.2f} s, left at {speed(rows[end]):.0f} cm/s "
            f"(mode {rows[end]['mode']}); slowest {slowest:.0f} cm/s up to 0.6 s after; "
            f"{'bailed' if bailed else 'no bail'}; largest step at the lock {jump:.1f} cm beyond the speed; {qa.combos(rows)}")
           if end is not None else f"states {','.join(sorted(qa.modes(rows)))}; never {'locked' if lock is None else 'left the line'}")


def grind_rows(record):
    """flatbar_red is 18 m long and a grind loses 0.97 m/s² on a rail (the reference, assets/skate/ride/README.md):
    at 7 m/s the board grinds it to its end, flies off and rolls away; at 5.2 m/s it stalls about 14 m along, steps
    off the line with a small hop and stands on the deck beside it (at the deck's height, at least 20 cm off the line,
    on the ground from its landing on), neither bailing."""
    for name, spot, entry, seconds in (('grind', RAIL_FAST, 700, 6.5), ('grind_stall', RAIL, 520, 8.5)):
        rows = qa.run_scenario(f"{spot[0]},{spot[1]},0,{entry},[(.98,('flick','ollie'))],duration={seconds}", seconds)
        lock = next((i for i, r in enumerate(rows) if r['mode'] == '3'), None)
        end = next((i for i in range(lock, len(rows)) if rows[i]['mode'] != '3'), None) if lock is not None else None
        bailed = qa.count(rows, 'bails') or any(r['mode'] == '4' for r in rows)
        if end is None:
            record(name, rows, False, f"states {','.join(sorted(qa.modes(rows)))}; never {'locked' if lock is None else 'left the line'}; "
                   + qa.combos(rows))
            continue
        held = sum(float(r.get('dt', 16.7)) for r in rows[lock:end]) / 1000
        loss = (speed(rows[lock]) - speed(rows[end - 1])) / max(held, .1)
        along = (position(rows[end - 1])[0] - position(rows[lock])[0]) / 100
        stalled = speed(rows[end - 1]) < 60
        ok = rows[-1]['mode'] == '1' and not bailed and 70 < loss < 125 and stalled == (name == 'grind_stall')
        off = ''
        if name == 'grind_stall':
            # Off the line onto the deck: the board's height back to the deck's before the grind, beside the line (the
            # last position's distance from the line through the grind's ends), and on the ground from the landing on.
            deck, last_z = float(rows[min(5, lock)]['z']), float(rows[-1]['z'])
            landed = next((i for i in range(end, len(rows)) if rows[i]['mode'] == '1'), len(rows))
            flicker = sum(1 for r in rows[landed:] if r['mode'] != '1')
            a, b, c = position(rows[lock]), position(rows[end - 1]), position(rows[-1])
            run = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.
            aside = abs((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])) / run
            ok = ok and abs(last_z - deck) < 3 and aside >= 20 and flicker == 0
            off = (f"; stood at z {last_z:.0f} (the deck {deck:.0f}), {aside:.0f} cm beside the line, {flicker} frames off the "
                   f"ground after landing")
        record(name, rows, ok,
               f"locked at {speed(rows[lock]):.0f} cm/s, grinded {held:.2f} s and {along:.1f} m, left at {speed(rows[end - 1]):.0f} cm/s "
               f"({'a stall' if stalled else 'off the end'}), losing {loss:.0f} cm/s² (reference 97); last mode {rows[-1]['mode']}, "
               f"{'bailed' if bailed else 'no bail'}{off}; {qa.combos(rows)}")


def release_controls():
    qa.py("live.stop('skate_script'); live.stop('rec'); live.stop('grab'); live.stop('spin'); live.stop('frames'); live.skate_release()\n"
          "for k in ['Gamepad_LeftThumbstick','Gamepad_RightThumbstick']: live.L.input_key(k,'release',0)\n"
          "for k in ['Gamepad_LeftTriggerAxis','Gamepad_RightTriggerAxis']: live.L.input_key(k,'axis',0)")


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    finally:
        release_controls()
