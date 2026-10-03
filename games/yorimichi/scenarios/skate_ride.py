#!/usr/bin/env python3
"""In-game checks for the Ride skating backend (Skate plugin, Private/Ride, RIDE.md) on the skate pier park.

Run against a running game (atelier play yorimichi):  atelier qa yorimichi skate_ride [--only name,name]
Mounts with skate.Backend Ride, then checks pushing, steering, braking, the ollie's height, every Flick-It trick, a grab,
a 360, a grind, a manual, a bail and its recovery, a vert air that comes back in, frame pacing (including mounting
and switching character), Mega Park's roll-in from the upper deck (over the crest without leaving it, through the
concave at the bottom without a bail) and a grind into the parapet's corner (it flies off the end, never stalling), and
the physical rider (skate.RidePhysical, on by default): how closely it holds the animation riding and landing, bails on
flat and on a quarter that go limp at once, lie down within a second and travel as far as the reference's, and its
frame cost in Mega Park. Over every frame recorded,
the rider's pose (the clips through Unreal's animation graph) must keep both feet on the deck where the clip stands on
it, carry no NaN and never pop between clips, in both stances, and the standing rider matches the reference's stand.
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
FLAT = (-28, 38)       # the pier's long flat run, heading east
# The steering turns start a metre apart: a left turn from FLAT meets the planter beside the bench at (-26, 41).
STEER = {1: FLAT, -1: (FLAT[0], FLAT[1] - 1)}
RAIL = (-23, 20)       # an ollie at .98 s onto the rail
QUARTER = (33, 25)     # a quarter pipe, launched at 950 cm/s


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

    if wanted('push'):
        rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,0,[(0,{{'push':True}}),(3.5,{{}})],duration=4", 4)
        first = next((float(r['speed']) for r in rows if float(r['speed']) > 150), 0)
        top = max(map(speed, rows))
        record('push_cruise', rows, top > 750 and rows[-1]['mode'] == '1' and not qa.count(rows, 'bails'),
               f'top speed {top:.0f} cm/s after 3.5 s of pushing')
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
        # A 360 needs a bigger air: off the quarter, spinning until about 320 degrees (the release carries the rest).
        rows = record_while(f'''
live.park.place({QUARTER[0]},{QUARTER[1]},0); live.park.look(-12,0); live.park.launch(950)
live.SPIN=[0.0, None]
def spin(dt):
    s=live.skate_state(); yaw=float(s.split('yaw=')[1].split()[0])
    if 'mode=2 ' in s and live.SPIN[1] is not None: live.SPIN[0]+=(yaw-live.SPIN[1]+180)%360-180
    live.SPIN[1]=yaw
    live.skate_input(left=(1,0) if 'mode=2 ' in s and abs(live.SPIN[0])<320 else (0,0))
live.behave('spin', spin)
''', 5)
        qa.py("live.stop('spin'); live.skate_input()")
        record('quarter_360', rows, '360' in qa.combos(rows) or '540' in qa.combos(rows), qa.combos(rows) or '(none)')
    if wanted('grind'):
        rows = qa.run_scenario(f"{RAIL[0]},{RAIL[1]},0,520,[(.98,('flick','ollie'))],duration=3.5", 3.5)
        record('grind', rows, '3' in qa.modes(rows) and rows[-1]['mode'] == '1' and not qa.count(rows, 'bails'),
               'states ' + ','.join(sorted(qa.modes(rows))) + '; ' + qa.combos(rows))
    if wanted('manual'):
        rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,480,[(.3,{{'right':(0,-.5)}}),(1.8,{{}})],duration=2.3", 2.3)
        record('manual', rows, qa.ever(rows, 'manual', '1') and rows[-1]['manual'] == '0' and 'Manual' in qa.combos(rows)
               and not qa.count(rows, 'bails'), qa.combos(rows))
        rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,480,[(.3,{{'right':(0,.5)}}),(1.8,{{}})],duration=2.3", 2.3)
        record('nose_manual', rows, 'Nose Manual' in qa.combos(rows) and not qa.count(rows, 'bails'), qa.combos(rows))
    if wanted('vert'):
        rows = qa.run_scenario(f"{QUARTER[0]},{QUARTER[1]},0,950,[],duration=5", 5)
        record('vert_air_back_in', rows, '2' in qa.modes(rows) and rows[-1]['mode'] == '1' and not qa.count(rows, 'bails'),
               'states ' + ','.join(sorted(qa.modes(rows))))
        rows = qa.run_scenario("29,-10,0,850,[],duration=5", 5)
        record('bowl_carve', rows, rows[-1]['mode'] == '1' and not qa.count(rows, 'bails') and max(map(speed, rows)) > 300,
               'states ' + ','.join(sorted(qa.modes(rows))) + f'; speed {speed(rows[-1]):.0f}')
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
    if any(wanted(name) for name in PHYSICAL):
        physical_checks(record, wanted)
    qa.py('live.skate_input(); live.skate_park(); live.skate_release()')
    out = qa.yori.OUT / 'skateqa' / 'ride.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2) + '\n')
    print(f'{sum(r["ok"] for r in results.values())}/{len(results)} passed -> {out}')
    return 0 if all(r['ok'] for r in results.values()) else 1


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
# entry speed times 1 s. A deliberate bail on flat at 4.6 m/s: 0.97 and 1.04 (across the ground). One in the air at
# 4.8 m/s across, rising at 8.7 m/s: 1.04 and 1.36 of the speed across, 0.50 and 0.65 of the whole speed. The bands
# are a third either side: on flat the flat bail's; on a quarter (no twin in the reference) from the widest of the two,
# the whole distance over the whole speed.
BAIL_TRAVEL = {'flat': ((.65, 1.3), (.7, 1.4)), 'quarter': ((.33, 1.4), (.43, 1.8))}
BAIL_LIE = 40.   # cm: within 1 s of a fall the pelvis is down this close to the ground under it (lie=)
MEGA_ROAD = (-127.9, 1471.1, 134.)   # Mega Park's road (island metres), running east into its bend
MEGADROP = (-44.5, 1305.1, 112., 135.)   # the top of Mega Park's roll-in (island metres) and the Unreal yaw down it
MEGADROP_FLOOR = 7600.   # cm: the board (z=) is on the floor at the bottom of the roll-in below this height
# Mega Park's parapet: a point on its south line 5 m from the corner (island metres) and the Unreal direction to it.
PARAPET = ((-71.13, 1376.69, 118.91), (.4655, .885))
PHYSICAL = ('physical_riding', 'physical_landing', 'physical_bail', 'physical_bail_quarter', 'physical_cost')


def physical(on):
    qa.py(f"unreal.SystemLibrary.execute_console_command(live.L.game_world(), 'skate.RidePhysical {int(on)}')")


def floats(rows, key, keep=lambda r: True):
    return [float(r[key]) for r in rows if key in r and keep(r)]


def p95(values):
    values = sorted(values)
    return values[min(len(values) - 1, round((len(values) - 1) * .95))] if values else float('inf')


def hips(row):
    return tuple(float(x) for x in row['hips'].split(','))


def physical_checks(record, wanted):
    """The active ragdoll (skate.RidePhysical 1): tracking while riding and landing, falls on flat and off a quarter,
    and its cost. The cvar is put back as it was."""
    before = qa.py("print(unreal.SystemLibrary.get_console_variable_int_value('skate.RidePhysical'))").strip().splitlines()[-1]
    physical(True)
    time.sleep(.8)
    try:
        if wanted('physical_riding'):
            physical_riding(record)
        if wanted('physical_landing'):
            physical_landing(record)
        if wanted('physical_bail'):
            physical_bail(record)
        if wanted('physical_bail_quarter'):
            physical_bail_quarter(record)
        if wanted('physical_cost'):
            physical_cost(record)
    finally:
        physical(before == '1')


def driven(row):
    return row.get('sim') == '1' and float(row.get('w', 0)) >= .99


def physical_riding(record):
    rows = qa.run_scenario(f"{FLAT[0]},{FLAT[1]},0,300,[(0,{{'push':True,'left':(.5,0)}}),(1.5,{{'push':True,'left':(-.6,0)}}),"
                           f"(3,{{}})],duration=3.2", 3.2)
    held = [r for r in rows if driven(r)]
    pelvis, feet = p95(floats(held, 'pelvis_err')), p95(floats(held, 'foot_err'))
    record('physical_riding', rows, len(held) > .8 * len(rows) and pelvis < 3 and feet < 8,
           f'{len(held)}/{len(rows)} frames driven; pelvis {pelvis:.1f} cm, feet {feet:.1f} cm p95 '
           f'(reference: upper body 0.5 cm, feet 6-8 cm); pa={rows[-1].get("pa", "?")}, {rows[-1].get("bodies", "?")} bodies')


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


def physical_bail(record):
    """1 s of riding at 6 m/s on the pier's flat, then the bail input held for 0.5 s."""
    keys = lambda on: (f"live.L.input_key('Gamepad_LeftThumbstick','{'press' if on else 'release'}',{int(on)}); "
                       f"live.L.input_key('Gamepad_RightThumbstick','{'press' if on else 'release'}',{int(on)}); "
                       f"live.L.input_key('Gamepad_LeftTriggerAxis','axis',{int(on)}); "
                       f"live.L.input_key('Gamepad_RightTriggerAxis','axis',{int(on)})")
    qa.py(f"live.park.place({FLAT[0] + 18},{FLAT[1]},0); live.park.launch(600); live.skate_release()")
    qa.py("live.REC=[]; live.behave('rec', lambda dt: live.REC.append(live.skate_state()))\n"
          "live.skate_input(); live.L.skate_release()\n"
          "live.BAIL_AT=[0.0]\n"
          "def _bail(dt):\n"
          "    live.BAIL_AT[0]+=dt\n"
          f"    if live.BAIL_AT[0]>=1.0 and live.BAIL_AT[0]-dt<1.0: {keys(True)}\n"
          f"    if live.BAIL_AT[0]>=1.5: {keys(False)}; live.stop('bail_keys')\n"
          "live.behave('bail_keys', _bail)")
    time.sleep(10)
    judge_bail(record, 'physical_bail', recorded(), 'flat')


def physical_bail_quarter(record):
    """The film's bail on the pier's quarter: an Indy held from the take-off into the landing."""
    rows = qa.run_scenario(f"{QUARTER[0]},{QUARTER[1]},0,950,[(0,{{'grab_right':True}})],duration=9", 9)
    judge_bail(record, 'physical_bail_quarter', rows, 'quarter')


def judge_bail(record, name, rows, kind):
    """The first fall in rows: limp from its first frame to the get-up (the Bail profile, simulating; never handed to
    the animated slide), continuous, the pelvis down near the ground within 1 s, travel in the reference's band for
    the entry speed, and the rider up where the body lay. On flat also the body against the bail clip."""
    start = next((i for i, r in enumerate(rows) if r['mode'] == '4'), None)
    if not start:
        record(name, rows, False, 'no bail' if start is None else 'bailing from the first frame')
        return
    end = next((i for i in range(start, len(rows)) if rows[i]['mode'] != '4'), len(rows))
    bail = rows[start:end]
    vel = [float(x) for x in rows[start - 1]['vel'].split(',')]
    flat = kind == 'flat'
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
    up = position(rows[end]) if end < len(rows) else None
    where = math.dist(hips(bail[lying - 1])[:2], up[:2]) if up and lying else float('inf')
    kind_seen = next((r['bail_kind'] for r in bail if r.get('bail_kind', 'none') != 'none'), '?')
    ok = limp and kind_seen == 'fall' and far and lie < BAIL_LIE and max(steps, default=99) < 25 and where < 100
    limpness = 'limp to the get-up' if limp else 'NOT limp throughout (handed to the animation)'
    note = (f'entry {entry:.1f} m/s, {limpness}, kind {kind_seen}; travel '
            + ', '.join(f'{t:g} s {d:.2f} m ({d / max(entry, .01):.2f}x)' for t, d in travel.items())
            + f', rest {rest:.2f} m ({rest / max(entry, .01):.2f}x) after {clock[lying - 1] if lying else 0:.1f} s '
            f'(band {low1}-{high1}x at 1 s, {low_rest}-{high_rest}x at rest); pelvis down to {lie:.0f} cm within 1 s; '
            f'largest hips step {max(steps, default=0):.1f} cm/frame; up {where:.0f} cm from where the hips lay')
    if flat:
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


def release_controls():
    qa.py("live.stop('skate_script'); live.stop('rec'); live.stop('grab'); live.stop('spin'); live.stop('frames'); live.skate_release()\n"
          "for k in ['Gamepad_LeftThumbstick','Gamepad_RightThumbstick']: live.L.input_key(k,'release',0)\n"
          "for k in ['Gamepad_LeftTriggerAxis','Gamepad_RightTriggerAxis']: live.L.input_key(k,'axis',0)")


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    finally:
        release_controls()
