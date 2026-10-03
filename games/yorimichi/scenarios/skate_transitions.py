#!/usr/bin/env python3
"""In-game checks for getting on and off the board with the Ride backend (Skate plugin, RIDE.md "Transitions").

Run against a running game (atelier play yorimichi):  atelier qa yorimichi skate_transitions [--only name,name] [--film]
On the skate pier's long flat, with skate.Backend Ride and the player's own buttons (the top face button gets on and
off, D-pad Right brings the board to the hand or puts it away): mounts from standing, walking, running and sprinting
(each its own BR_*_INTO_MOUNT clip), a mount from the board carry, dismounts to a stand, a run and a fast run (the
BR_DISMOUNT_* clips, into the carry), the carry put away after its hold time, the board button with no board and
with a board lying, a bail left on foot (the rider gets up where the body lies), a bail back onto the board, a board
left lying that dissolves, jumps with the board in hand (JBR_* then BR_LAND_*), the board thrown under the feet mid-jump
(a caveman, with and without the board in hand), a step off the board in the air from a grab (BR_DISMOUNT_*_INTO_BR_AIR,
then a landing), a kick-out in the air without a grab (BR_KICKOUT_*, the board flying on by itself), a slow bail run
out on foot (RUNOUT_*, the board rolling on), a fallen rider getting up on foot where the body lies (W_RECOVERY_*), a
step onto a board lying on its wheels, and Link and a Bokoblin as the rider. The capsule checks: a crouched Cairo
stands up for the board, and a BotW rider's fitted capsule keeps its size through three board toggles and a jump.

Every frame is checked for continuity: the character moves no farther than its speed allows, the hips do not jump,
the velocity changes no faster than a push or a brake could (at a landing, the horizontal velocity), the camera eases
rather than cuts (no frame moves it much farther than the character or turns it more than a few degrees), and the board
shows whenever it is somewhere; the checks count the world's time, the pacing check the frames'. Writes
build/yorimichi/skateqa/transitions.json, and each check's frames to transitions-rows/<check>.json. With --film the checks are filmed in close-up instead, at a fixed 60 Hz step
(build/yorimichi/skateqa/transitions-film/<nn>/f<frame>.jpg, the folders of each check in transitions-film.json); the
camera and pacing checks are left out then.
"""
import argparse
import json
import math
import time
import skate as qa

FLAT = (-28, 38)        # the pier's long flat run, heading east
TOP = 'Gamepad_FaceButton_Top'
HAND = 'Gamepad_DPad_Right'   # the board button (G on the keyboard)
SLACK_MOVE = 6.0        # cm a frame the character may move beyond its speed's travel
SLACK_HIP = 12.0        # cm a frame the hips may move beyond that travel (the pose's own motion)
SLACK_HIP_BAIL = 40.0   # ... while the body tumbles
ACCEL = 4000.0          # cm/s^2: the most a push, a brake or a landing changes the speed
SLACK_SPEED = 60.0      # cm/s a frame on top
BAIL_AWAY = 150.0       # cm at least from the bail start to where the rider gets up ...
BAIL_NEAR = 50.0        # ... and at most from where the body lay
SLACK_CAM = 30.0        # cm a frame the camera may move beyond the character's travel (a cut moves it a metre or more)
SLACK_CAM_DEG = 8.0     # degrees a frame the camera may turn
BAIL_KEYS = ('Gamepad_LeftThumbstick', 'Gamepad_RightThumbstick')
BAIL_AXES = ('Gamepad_LeftTriggerAxis', 'Gamepad_RightTriggerAxis')


def vec(text):
    return tuple(float(x) for x in text.strip().strip('()').split(','))


def length(v):
    return math.sqrt(sum(x * x for x in v))


# The behaviours' dt is Slate's frame time; the world steps its own (a fixed 1/60 s while filming): the checks count
# the world's time (WDT), and the pacing the frame's.
WDT = 'unreal.GameplayStatics.get_world_delta_seconds(live.L.game_world())'
RECORD = '''
import json, math
live.TR=[]
live.CM=unreal.GameplayStatics.get_player_camera_manager(live.L.game_world(), 0)
live.FILM_AT=None
def _film(dt):
    # A close-up from the character's right, following it smoothly, its hips in the middle of the frame: the follow
    # aims a fifth of a second ahead (its own lag), so a running or rolling character stays centred.
    pawn=unreal.GameplayStatics.get_player_pawn(live.L.game_world(), 0)
    at=pawn.get_actor_location()
    if live.FILM_AT is None: live.FILM_AT=[at, math.radians(pawn.get_actor_rotation().yaw), 0]
    f=live.FILM_AT
    f[0]=f[0]+(at+pawn.get_velocity()*0.2-f[0])*min(1.0, dt*5.0)
    side=unreal.Vector(-math.sin(f[1]), math.cos(f[1]), 0.0); ahead=unreal.Vector(math.cos(f[1]), math.sin(f[1]), 0.0)
    unreal.MegaParkValidation.review_camera(f[0]+side*300.0+ahead*80.0+unreal.Vector(0,0,40), f[0]+unreal.Vector(0,0,-5), 40.0)
    live.L.screenshot(live.FILM_DIR+'/f%05d.jpg' % f[2]); f[2]+=1
def _row(frame):
    dt=''' + WDT + '''
    if live.FILM_DIR: _film(dt); cam=None
    else:
        l=live.CM.get_camera_location(); r=live.CM.get_camera_rotation(); cam=(l.x,l.y,l.z,r.pitch,r.yaw)
    live.TR.append((dt, live.L.skate_state(), cam, frame))
live.behave('tr', _row)
'''
FILM = {'dir': None, 'n': 0, 'since': []}    # --film: where the close-ups go, and the folders since the last report
FILM_SLOW = 3.0                               # filming, a game second takes about this long


def record(code, seconds):
    """Run `code` in the game and record every frame's skate state (with the frame time and the camera: location and
    pitch, yaw) for `seconds`; with --film, film it in close-up instead of reading the camera."""
    folder = ''
    if FILM['dir']:
        FILM['n'] += 1
        folder = str(FILM['dir'] / f'{FILM["n"]:02d}')
        (FILM['dir'] / f'{FILM["n"]:02d}').mkdir(parents=True, exist_ok=True)
        FILM['since'].append(f'{FILM["n"]:02d}')
    qa.py(f'live.FILM_DIR={folder!r}\n' + RECORD + code)
    slow = FILM_SLOW if folder else 1.0
    time.sleep(seconds * slow)
    # Until the game has played `seconds` of its own time: a loaded machine (or filming) runs it slower than the wall.
    deadline = time.monotonic() + seconds * slow * 4 + 10
    while time.monotonic() < deadline:
        played = float(qa.py('print(sum(r[0] for r in live.TR))').strip().splitlines()[-1])
        if played >= seconds:
            break
        time.sleep(min(2.0, max(0.1, (seconds - played) * slow)))
    rows = json.loads(qa.py("import json; live.stop('tr'); print(json.dumps(live.TR))").strip().splitlines()[-1])
    if folder:
        qa.py('unreal.MegaParkValidation.restore_player_camera()')
    out = []
    for dt, state, cam, frame in rows:
        row = qa.parse(state)
        row['dt'] = dt          # the world's step
        row['frame'] = frame    # the frame's time (Slate)
        row['cam'] = cam
        out.append(row)
    return [r for r in out if 'hip' in r and 'pos' in r]


STEP_ON_NEAR = 90.0     # cm from the lying board the character walks up to before stepping on
WALK_TO = '''
import math
live.WALK=[{x},{y},{stop},0]
def _walk(dt):
    # Walk to (x, y), steering the stick against the camera's heading, and stop `stop` cm short.
    w=live.WALK
    at=unreal.GameplayStatics.get_player_pawn(live.L.game_world(), 0).get_actor_location()
    dx, dy = w[0]-at.x, w[1]-at.y
    n=math.hypot(dx, dy)
    if n < w[2]:
        live.drive(0); w[3]=1; live.stop('walk'); return
    yaw=math.radians(unreal.GameplayStatics.get_player_camera_manager(live.L.game_world(), 0).get_camera_rotation().yaw)
    fx, fy = math.cos(yaw), math.sin(yaw)
    live.drive((dx*fx+dy*fy)/n, (dy*fx-dx*fy)/n, 'walk')
live.behave('walk', _walk)
'''


def tap(key, delay):
    """Code that presses `key` after `delay` seconds and lets go two frames later, as a player's tap."""
    return f'''
live.TAP=[0.0,0]
def _tap(frame):
    live.TAP[0]+={WDT}
    if live.TAP[1]==0 and live.TAP[0]>={delay}: live.L.input_key('{key}','press',1); live.TAP[1]=1
    elif 1<=live.TAP[1]<3: live.TAP[1]+=1
    elif live.TAP[1]==3: live.L.input_key('{key}','release',0); live.TAP[1]=4; live.stop('tap')
live.behave('tap', _tap)
'''


def later(delay, code):
    """Code that runs `code` (one line) once, `delay` seconds of the world's time from now: one recording, no gap."""
    return f'''
live.LATER=[0.0]
def _later(frame):
    live.LATER[0]+={WDT}
    if live.LATER[0]>={delay}:
        live.stop('later')
        {code}
live.behave('later', _later)
'''


def facing(cam):
    pitch, yaw = math.radians(cam[3]), math.radians(cam[4])
    return (math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch))


def airborne(row):
    return row.get('mm', '').startswith('3/') or row.get('mode') == '2'


def continuity(rows, tumbling=lambda row: False):
    """The worst frame-to-frame jumps beyond what the speed explains: the character, its hips, its velocity and the
    camera, each with the frame it happened at (index, foot, clip and clip time) under 'at'."""
    worst = {'move_cm': 0.0, 'hip_cm': 0.0, 'speed_cm_s': 0.0, 'cam_cm': 0.0, 'cam_deg': 0.0}
    at = {}

    def note(key, value, i, row):
        if value > worst[key]:
            worst[key] = value
            at[key] = f"{i}:{row.get('foot', '-')}/{row.get('clip', '-')}@{row.get('t', '-')}"

    for i, (a, b) in enumerate(zip(rows, rows[1:]), 1):
        dt = b['dt']
        va, vb = vec(a['vel']), vec(b['vel'])
        speed = max(length(va), length(vb))
        travel = speed * dt
        # The hips are the mesh's pose, which can show a world step a frame late: a long step may move them a row
        # later.
        hip_travel = speed * max(a['dt'], dt)
        bail = tumbling(a) or tumbling(b)
        if not bail:
            note('move_cm', math.dist(vec(a['pos']), vec(b['pos'])) - travel, i, b)
            # A landing stops the fall in a frame, and a jump starts one, on foot (falling) or on the board (the air
            # mode): only the horizontal velocity carries on.
            if airborne(a) != airborne(b):
                va, vb = (va[0], va[1], 0.0), (vb[0], vb[1], 0.0)
            note('speed_cm_s', math.dist(va, vb) - ACCEL * dt, i, b)
        hip = math.dist(vec(a['hip']), vec(b['hip'])) - hip_travel
        note('hip_cm', hip - (SLACK_HIP_BAIL - SLACK_HIP if bail else 0), i, b)
        if a.get('cam') and b.get('cam'):
            # The ride's own camera follows a tumbling body as it likes: only the switches are this check's.
            if not bail:
                note('cam_cm', math.dist(a['cam'][:3], b['cam'][:3]) - travel, i, b)
                dot = sum(x * y for x, y in zip(facing(a['cam']), facing(b['cam'])))
                note('cam_deg', math.degrees(math.acos(max(-1.0, min(1.0, dot)))), i, b)
    worst['at'] = at
    return worst


def smooth(worst):
    return (worst['move_cm'] <= SLACK_MOVE and worst['hip_cm'] <= SLACK_HIP and worst['speed_cm_s'] <= SLACK_SPEED and
            worst['cam_cm'] <= SLACK_CAM and worst['cam_deg'] <= SLACK_CAM_DEG)


def board_shown(rows):
    """The board shows whenever it is somewhere, and fades rather than pops (no frame jumps more than half way)."""
    hidden = sum(1 for r in rows if r['board'] in ('ride', 'hand', 'world') and float(r['shown']) > 0 and r['vis'] != '1')
    pops = sum(1 for a, b in zip(rows, rows[1:]) if abs(float(b['shown']) - float(a['shown'])) > .5)
    return hidden == 0 and pops == 0, f'hidden {hidden}, pops {pops}'


def describe(worst):
    slack = {'move_cm': SLACK_MOVE, 'hip_cm': SLACK_HIP, 'speed_cm_s': SLACK_SPEED, 'cam_cm': SLACK_CAM, 'cam_deg': SLACK_CAM_DEG}
    return 'jumps ' + ', '.join(f'{k} {v:.1f}' + (f' (at {worst["at"].get(k, "?")})' if v > slack[k] else '')
                                for k, v in worst.items() if k != 'at')


def state():
    return qa.parse(qa.py('print(live.skate_state())'))


def press_key(key):
    qa.py(f"live.L.input_key('{key}','press',1); live.L.input_key('{key}','release',0)")


CAPSULE = '''
p=unreal.GameplayStatics.get_player_pawn(live.L.game_world(), 0); c=p.get_component_by_class(unreal.CapsuleComponent)
print('%.2f %.2f %d' % (c.get_unscaled_capsule_half_height(), c.get_unscaled_capsule_radius(), p.get_movement_component().is_crouching()))
'''


def capsule():
    """The player's capsule: half height, radius (cm) and whether it is crouched."""
    half, radius, crouched = qa.py(CAPSULE).strip().splitlines()[-1].split()
    return float(half), float(radius), crouched == '1'


def on_foot(heading=0, board=False):
    """Stand on the flat, off the board (with the board in hand or not), the camera looking along the run."""
    if state()['mode'] != '0':
        qa.py('live.skate_release(); live.skate()')
        time.sleep(1.5)
    qa.py(f'live.drive(0); live.teleport(live.L.ground_at(live.park.ue({FLAT[0]},{FLAT[1]},3.0)), {-heading}); live.park.look(-12,{heading})')
    time.sleep(.8)
    if (state().get('board') == 'hand') != board:
        press_key(HAND)
    time.sleep(1.2)


def riding(speed, heading=0):
    qa.py(f'live.skate_release(); live.park.place({FLAT[0]},{FLAT[1]},{heading}); live.park.look(-12,{heading}); live.park.launch({speed},{heading})')
    time.sleep(.6)


def first(rows, mode):
    return next((i for i, r in enumerate(rows) if r['mode'] == mode), None)


def flat_speed(row):
    v = vec(row['vel'])
    return math.hypot(v[0], v[1])


def clip_of(rows, foot):
    """The clip played while `foot` (mount, dismount) and the index of its first frame."""
    at = next((i for i, r in enumerate(rows) if r.get('foot') == foot), None)
    return (rows[at].get('clip', '-'), at) if at is not None else ('-', None)


def fading(rows):
    return sum(1 for r in rows if 0 < float(r['shown']) < 1)


def clips(rows):
    """The clips played, in order, each with the foot it played as (air, land, airmount...)."""
    seen = []
    for r in rows:
        clip = (r.get('foot', '-'), r.get('clip', '-'))
        if clip[1] != '-' and (not seen or seen[-1] != clip):
            seen.append(clip)
    return seen


def line(seen):
    return ' > '.join(f'{foot}:{clip}' for foot, clip in seen) or '(no clips)'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8830)
    parser.add_argument('--only', default='', help='comma-separated check names (prefixes) to run')
    parser.add_argument('--film', action='store_true', help='film the checks in close-up (fixed 60 Hz step)')
    args = parser.parse_args()
    qa.bridge.URL = f'http://127.0.0.1:{args.port}'
    only = [o for o in args.only.split(',') if o]
    wanted = lambda name: not only or any(name.startswith(o) for o in only)
    qa.py((qa.GAME / 'scenarios/skate_live_skate.py').read_text())
    qa.py("unreal.SystemLibrary.execute_console_command(live.L.game_world(), 'skate.Backend Ride')")
    qa.py('live.L.skate_goofy(False)')
    results, frames = {}, []
    # Every check's frames, for a closer look at a failure.
    rows_dir = qa.yori.OUT / 'skateqa' / ('transitions-film-rows' if args.film else 'transitions-rows')
    rows_dir.mkdir(parents=True, exist_ok=True)
    if args.film:
        FILM['dir'] = qa.yori.OUT / 'skateqa' / 'transitions-film'
        FILM['dir'].mkdir(parents=True, exist_ok=True)
        qa.py('live.L.film_hud(True); live.L.fixed_step(60)')

    def report(name, rows, passed, note):
        frames.extend(r['frame'] for r in rows)
        results[name] = {'ok': bool(passed), 'note': note, 'frames': len(rows)}
        (rows_dir / f'{name}.json').write_text(json.dumps(rows))
        if FILM['dir']:
            results[name]['film'] = FILM['since'][:]
            FILM['since'].clear()
        print(('PASS' if passed else 'FAIL') + ' ' + name + ': ' + note, flush=True)

    qa.settle(minimum=50, seconds=2, limit=60)

    def toggles(name):
        """The board on and off three times from a stand, then a jump: the capsule keeps its size (a fitted one, a BotW
        rider's, too: standing up for an action must not give back the class default)."""
        on_foot()
        before = capsule()
        sizes, rode = [], 0
        for _ in range(3):
            press_key(TOP)
            time.sleep(2.2)
            rode += state()['mode'] != '0'
            press_key(TOP)
            time.sleep(2.6)
            sizes.append(capsule())
        qa.py("live.press('jump')")
        time.sleep(.3)
        qa.py("live.press('jump_release')")
        time.sleep(1.4)
        sizes.append(capsule())
        same = all(abs(h - before[0]) < .05 and abs(r - before[1]) < .05 for h, r, _ in sizes)
        report(name, [], same and rode == 3,
               f'half height/radius {before[0]:.1f}/{before[1]:.1f} before; after each toggle and the jump '
               + ', '.join(f'{h:.1f}/{r:.1f}' for h, r, _ in sizes) + f'; on the board {rode} of 3 times')

    def crouch_stand(name):
        """Crouched, the board button stands the character up first (and gets on): it uncrouches as before."""
        on_foot()
        before = capsule()
        qa.py("live.press('crouch')")
        time.sleep(.8)
        crouched = capsule()
        press_key(TOP)
        time.sleep(.3)
        stood = capsule()
        time.sleep(1.9)
        rode = state()['mode'] != '0'
        press_key(TOP)
        time.sleep(2.6)
        after = capsule()
        ok = (crouched[2] and crouched[0] < before[0] - 5 and not stood[2] and rode
              and abs(after[0] - before[0]) < .05 and not after[2])
        report(name, [], ok, f'half height {before[0]:.1f} standing, {crouched[0]:.1f} crouched (crouched {crouched[2]}), '
               f'{stood[0]:.1f} after the board button (crouched {stood[2]}), {"on the board" if rode else "never got on"}, '
               f'{after[0]:.1f} off it again')

    if wanted('capsule'):
        crouch_stand('capsule_cairo_crouch')

    def mount(name, gait, carrying=False):
        on_foot(board=carrying)
        if gait:
            qa.py(f"live.drive(1,0,'{gait}')")
            time.sleep(1.8)
        rows = record(tap(TOP, .25), 2.6)
        qa.py('live.drive(0)')
        clip, start = clip_of(rows, 'mount')
        at = first(rows, '1')
        if at is None or start is None:
            report(name, rows, False, f'never got on (clip {clip})')
            return
        entry, before, after = flat_speed(rows[max(0, start - 1)]), flat_speed(rows[at - 1]), flat_speed(rows[at])
        # The clip's gait goes by the speed (the carry cycles' own speeds: walk ~170, run ~540, sprint ~910 cm/s).
        want = ('BR_STAND_0_INTO_MOUNT' if entry < 80 else 'BR_WALK_FWD_' if entry < 350 else 'BR_RUN_FWD_' if entry < 720
                else 'BR_SPRINT_FWD_')
        worst = continuity(rows)
        shown, note = board_shown(rows)
        # The speed carries on into the clip and out of it onto the board; a held board never fades.
        carried = flat_speed(rows[start]) >= .85 * entry - 20 and after >= .85 * before - 20
        held = not carrying or all(float(r['shown']) == 1.0 for r in rows[start:at])
        in_hand = all(r['board'] == 'hand' for r in rows[start:at])
        report(name, rows, smooth(worst) and shown and carried and held and in_hand and clip.startswith(want) and
               rows[-1]['board'] == 'ride' and float(rows[-1]['shown']) == 1.0,
               f'{clip} ({(at - start)} frames) at {entry:.0f} cm/s, onto the board {before:.0f} -> {after:.0f} cm/s; '
               f'{describe(worst)}; board {note}{", held throughout" if carrying and held else ""}')

    def dismount(name, speed, want, run=True):
        riding(speed)
        rows = record(tap(TOP, .2) + ("live.drive(1,0,'run')\n" if run else ''), 2.6)
        qa.py('live.drive(0)')
        at = first(rows, '0')
        clip, start = clip_of(rows, 'dismount')
        if at is None or start is None:
            report(name, rows, False, f'never got off (clip {clip})')
            return
        before, after = flat_speed(rows[at - 1]), flat_speed(rows[at])
        worst = continuity(rows)
        shown, note = board_shown(rows)
        walking = rows[-1]['mm'].startswith('1/')
        carry = next((i for i, r in enumerate(rows) if r.get('foot') == 'carry'), None)
        held = carry is not None and all(r['board'] == 'hand' and r['vis'] == '1' for r in rows[start:])
        report(name, rows, smooth(worst) and shown and after >= .9 * before - 20 and walking and held and clip == want,
               f'{clip} ({(carry or len(rows)) - start} frames), {before:.0f} -> {after:.0f} cm/s, {flat_speed(rows[-1]):.0f} after 2.6 s, '
               f'momentum {rows[at]["momentum"]}, then {"carrying" if carry is not None else "no carry"}; {describe(worst)}; board {note}')

    def bail(name, leave_on_foot, speed=600):
        # A deliberate bail at speed: the body falls (a ragdoll), and gets up where it lies, on foot (the skate button
        # during the bail: W_RECOVERY_* out of the fallen pose) or back onto the board.
        riding(speed)
        start = vec(qa.parse(qa.py('print(live.skate_state())'))['pos'])
        press = '\n'.join([f"live.L.input_key('{k}','press',1)" for k in BAIL_KEYS] + [f"live.L.input_key('{k}','axis',1)" for k in BAIL_AXES])
        release = '\n'.join([f"live.L.input_key('{k}','release',0)" for k in BAIL_KEYS] + [f"live.L.input_key('{k}','axis',0)" for k in BAIL_AXES])
        code = f'''
live.skate_input(); live.L.skate_release()
{press}
live.BAIL=[0.0]
def _bail(frame):
    live.BAIL[0]+={WDT}
    if live.BAIL[0]>.5:
{chr(10).join('        ' + line for line in release.splitlines())}
        live.stop('bail')
live.behave('bail', _bail)
''' + (tap(TOP, 1.0) if leave_on_foot else '')
        rows = record(code, 9)
        if '4' not in qa.modes(rows):
            report(name, rows, False, 'no bail')
            return
        last_bail = max(i for i, r in enumerate(rows) if r['mode'] == '4')
        end = vec(rows[-1]['pos'])
        body = vec(rows[last_bail]['hip'])
        worst = continuity(rows, tumbling=lambda r: r['mode'] == '4')
        shown, note = board_shown(rows)
        away = math.dist(end[:2], start[:2])
        near = math.dist(end[:2], body[:2])
        seen = clips(rows)
        recover = next((c for f, c in seen if f == 'recover'), '-')
        # Up where the body lay (never back at the bail start: the fall carries the body BAIL_AWAY or more).
        if leave_on_foot:
            passed = (rows[-1]['mode'] == '0' and away > BAIL_AWAY and near < BAIL_NEAR and rows[-1]['board'] == 'world' and rows[-1]['vis'] == '1'
                      and recover.startswith('W_RECOVERY_'))
        else:
            passed = rows[-1]['mode'] == '1' and away > BAIL_AWAY and near < BAIL_NEAR
        report(name, rows, passed and smooth(worst) and shown,
               f'ended mode {rows[-1]["mode"]} {away:.0f} cm from the bail start, {near:.0f} cm from where the body lay'
               f'{", up with " + recover if leave_on_foot else ""}; board {rows[-1]["board"]}; {describe(worst)}; board {note}')

    def runout(name, speed):
        # A slow, upright bail runs out on foot (RUNOUT_*): no ragdoll, the board rolls on and settles, the speed carries.
        riding(speed)
        before = flat_speed(state())
        press = '\n'.join([f"live.L.input_key('{k}','press',1)" for k in BAIL_KEYS] + [f"live.L.input_key('{k}','axis',1)" for k in BAIL_AXES])
        release = '\n'.join([f"live.L.input_key('{k}','release',0)" for k in BAIL_KEYS] + [f"live.L.input_key('{k}','axis',0)" for k in BAIL_AXES])
        code = f'''
live.skate_input(); live.L.skate_release()
{press}
live.BAIL=[0.0]
def _bail(frame):
    live.BAIL[0]+={WDT}
    if live.BAIL[0]>.3:
{chr(10).join('        ' + line for line in release.splitlines())}
        live.stop('bail')
live.behave('bail', _bail)
'''
        rows = record(code, 4.5)
        seen = clips(rows)
        clip = next((c for f, c in seen if f == 'runout'), '-')
        start = next((i for i, r in enumerate(rows) if r.get('foot') == 'runout'), None)
        if start is None:
            report(name, rows, False, f'no run-out ({line(seen)}; modes {"".join(sorted(qa.modes(rows)))})')
            return
        worst = continuity(rows[start - 1:])
        shown, note = board_shown(rows)
        fell = sum(1 for r in rows if r['mode'] == '4')
        after = flat_speed(rows[start])
        rolled = any(r.get('loose') == 'flying' for r in rows[start:]) or any(r.get('loose') == 'settling' for r in rows[start:])
        report(name, rows, clip.startswith('RUNOUT_') and fell <= 3 and rows[-1]['mode'] == '0' and rows[-1]['board'] == 'world' and
               rows[-1]['vis'] == '1' and after >= .8 * before - 30 and smooth(worst) and shown,
               f'{line(seen)}; {before:.0f} -> {after:.0f} cm/s, {fell} bail frames, board {rows[-1]["board"]} '
               f'({"rolled on" if rolled else "stopped with the clip"}, up {rows[-1].get("deckup", "?")}); {describe(worst)}; board {note}')

    def step_on(name):
        # A board lying on its wheels: next to it, the skate button steps onto it where it lies (no fresh board).
        # The board rolls on after the run-out: it is stepped onto once it lies still.
        s = state()
        for _ in range(24):
            if s.get('loose') not in ('flying', 'settling'):
                break
            time.sleep(.25)
            s = state()
        # A board with a body of its own may still be rolling: until it moves less than 2 cm in a quarter second.
        for _ in range(40):
            if s.get('board') != 'world' or 'deck' not in s:
                break
            time.sleep(.25)
            was, s = vec(s['deck']), state()
            if 'deck' in s and math.dist(vec(s['deck'])[:2], was[:2]) < 2:
                break
        if s.get('board') != 'world':
            report(name, [], False, f'no board lying (board {s.get("board")})')
            return
        if float(s.get('deckup', '1')) < .85:
            report(name, [], False, f'the board lies upside down (up {s.get("deckup")}): a fresh board would be used')
            return
        deck = vec(s['deck'])
        # Walk up to it (a teleport is a cut, and a cut puts a lying board away).
        qa.py(WALK_TO.format(x=deck[0], y=deck[1], stop=STEP_ON_NEAR))
        for _ in range(40):
            time.sleep(.25)
            if qa.py('print(live.WALK[3])').strip().endswith('1'):
                break
        qa.py("live.stop('walk'); live.drive(0)")
        time.sleep(.6)
        s = state()
        near = math.dist(vec(s['pos'])[:2], deck[:2])
        rows = record(tap(TOP, .25), 2.4)
        clip, start = clip_of(rows, 'mount')
        at = first(rows, '1')
        if start is None or at is None:
            report(name, rows, False, f'never got on ({line(clips(rows))}; the board {near:.0f} cm away, {flat_speed(s):.0f} cm/s)')
            return
        worst = continuity(rows)
        shown, note = board_shown(rows)
        moved = math.dist(vec(rows[at]['deck'])[:2], deck[:2])
        fresh = any(float(r['shown']) < 1 for r in rows[start:at])
        report(name, rows, clip == 'BR_STAND_0_INTO_MOUNT' and moved < 40 and not fresh and rows[-1]['board'] == 'ride' and smooth(worst) and shown,
               f'{clip} from frame {start} ({near:.0f} cm from the board at {flat_speed(s):.0f} cm/s), the board {moved:.0f} cm from where it lay '
               f'at the ride start{", a fresh board" if fresh else ""}; '
               f'{describe(worst)}; board {note}')

    if wanted('mount'):
        for gait in ('', 'walk', 'run', 'sprint'):
            mount('mount_' + (gait or 'stand'), gait)
        mount('mount_carry_run', 'run', carrying=True)
    if wanted('dismount'):
        dismount('dismount_stand', 90, 'BR_DISMOUNT_HI_INTO_STAND_0', run=False)
        dismount('dismount_low', 350, 'BR_DISMOUNT_HI_INTO_RUN_FWD')
        dismount('dismount_high', 900, 'BR_DISMOUNT_FAST_HI_INTO_RUN_FWD')
    if wanted('carry'):
        # Held past its hold time, the board dissolves in the hand and the character's own pose blends back.
        qa.py("unreal.SystemLibrary.execute_console_command(live.L.game_world(), 'skate.RideTune BoardHoldTime=1.5')")
        riding(350)
        rows = record(tap(TOP, .2) + "live.drive(1,0,'run')\n" + later(1.6, 'live.drive(0)'), 3.6)
        qa.py("unreal.SystemLibrary.execute_console_command(live.L.game_world(), 'skate.RideTune \"\"')")
        worst = continuity(rows)
        shown, note = board_shown(rows)
        carried = sum(1 for r in rows if r.get('foot') == 'carry')
        report('carry_put_away', rows, carried > 10 and rows[-1]['board'] == 'away' and rows[-1]['vis'] == '0' and
               rows[-1].get('foot') == 'off' and fading(rows) >= 4 and smooth(worst) and shown,
               f'{carried} carry frames, board {rows[-1]["board"]}, {fading(rows)} fading frames; {describe(worst)}; board {note}')
    if wanted('board_button'):
        # No board: one dissolves into the hand; pressed again, it is put away.
        on_foot()
        rows = record(tap(HAND, .2), 1.4)
        worst = continuity(rows)
        shown, note = board_shown(rows)
        got = rows[-1]['board'] == 'hand' and rows[-1].get('foot') == 'carry' and rows[-1]['vis'] == '1'
        report('board_button_take', rows, got and fading(rows) >= 4 and smooth(worst) and shown,
               f'board {rows[-1]["board"]}, foot {rows[-1].get("foot")}, {fading(rows)} fading frames; {describe(worst)}; board {note}')
        rows = record(tap(HAND, .2), 1.2)
        worst = continuity(rows)
        shown, note = board_shown(rows)
        report('board_button_put_away', rows, rows[-1]['board'] == 'away' and rows[-1].get('foot') == 'off' and fading(rows) >= 4 and smooth(worst) and shown,
               f'board {rows[-1]["board"]}, foot {rows[-1].get("foot")}, {fading(rows)} fading frames; {describe(worst)}; board {note}')
    if wanted('bail_on_foot'):
        bail('bail_on_foot', True)
    if wanted('lying_board'):
        # Out of reach for a short lying time, the board left by the bail dissolves.
        if results.get('bail_on_foot', {}).get('ok'):
            qa.py("unreal.SystemLibrary.execute_console_command(live.L.game_world(), 'skate.RideTune BoardLyingTime=1.5')")
            rows = record("live.drive(1,0,'run')\n" + later(1.0, 'live.drive(0)'), 3.5)
            qa.py("unreal.SystemLibrary.execute_console_command(live.L.game_world(), 'skate.RideTune \"\"')")
            faded = fading(rows)
            shown, note = board_shown(rows)
            report('lying_board', rows, rows[-1]['board'] == 'away' and rows[-1]['vis'] == '0' and faded >= 4 and shown,
                   f'board {rows[-1]["board"]}, {faded} fading frames; board {note}')
        else:
            report('lying_board', [], False, 'needs bail_on_foot')
    if wanted('bail_back'):
        bail('bail_back_on_board', False)
    if wanted('runout'):
        runout('runout_slow', 250)
        if wanted('step_on'):
            step_on('step_on_lying')
    elif wanted('step_on'):
        runout('runout_for_step_on', 250)
        step_on('step_on_lying')
    if wanted('recall_lying'):
        # A board lying in the world: the board button dissolves it and a fresh one comes to the hand.
        bail('bail_on_foot_again', True)
        if state().get('board') == 'world':
            rows = record(tap(HAND, .2), 1.6)
            shown, note = board_shown(rows)
            worst = continuity(rows)
            went = any(r['board'] == 'away' or float(r['shown']) < .5 for r in rows)
            report('recall_lying', rows, went and rows[-1]['board'] == 'hand' and rows[-1].get('foot') == 'carry' and shown and smooth(worst),
                   f'board {rows[-1]["board"]}, foot {rows[-1].get("foot")}, {fading(rows)} fading frames; {describe(worst)}; board {note}')
        else:
            report('recall_lying', [], False, 'no board lying after the bail')
    def jump(name, gait, want_air, want_land, seconds=2.6):
        # A jump with the board in hand: the jump clip from the stride, then a landing clip, the board held throughout.
        on_foot(board=True)
        if gait:
            qa.py(f"live.drive(1,0,'{gait}')")
            time.sleep(1.5)
        before = flat_speed(state())
        rows = record("live.press('jump')\n", seconds)
        qa.py("live.press('jump_release'); live.drive(0)")
        seen = clips(rows)
        air = next((c for f, c in seen if f == 'air'), '-')
        land = next((c for f, c in seen if f == 'land'), '-')
        landed = next((i for i, r in enumerate(rows) if r.get('foot') == 'land'), None)
        worst = continuity(rows)
        shown, note = board_shown(rows)
        held = all(r['board'] == 'hand' and r['vis'] == '1' for r in rows)
        after = flat_speed(rows[landed]) if landed is not None else 0.0
        kept = not gait or after >= .8 * before - 20
        report(name, rows, air.startswith(want_air) and land.startswith(want_land) and held and kept and smooth(worst) and shown,
               f'{line(seen)}; {before:.0f} cm/s, {after:.0f} at the landing, {flat_speed(rows[-1]):.0f} after {seconds} s; '
               f'{describe(worst)}; board {note}{", in hand throughout" if held else ""}')

    def caveman(name, carrying):
        # Running, a jump, then the skate button in the air: the board goes under the feet and the ride goes on.
        on_foot(board=carrying)
        qa.py("live.drive(1,0,'run')")
        time.sleep(1.5)
        before = flat_speed(state())
        rows = record("live.press('jump')\n" + tap(TOP, .22), 2.6)
        qa.py("live.press('jump_release'); live.drive(0)")
        seen = clips(rows)
        mount = next((c for f, c in seen if f == 'airmount'), '-')
        at = first(rows, '1')
        at = at if at is not None else first(rows, '2')
        worst = continuity(rows)
        shown, note = board_shown(rows)
        on = at is not None and rows[-1]['board'] == 'ride' and rows[-1]['mode'] in ('1', '2')
        after = flat_speed(rows[at]) if at is not None else 0.0
        jumped = not carrying or any(f == 'air' and c.startswith('JBR_RUN_FWD_') for f, c in seen)
        report(name, rows, 'AIR_INTO_MOUNT_BSGRAB' in mount and on and jumped and after >= .8 * before - 20 and smooth(worst) and shown,
               f'{line(seen)}; {before:.0f} cm/s running, {after:.0f} onto the board, mode {rows[-1]["mode"]} at the end; '
               f'{describe(worst)}; board {note}')

    def air_dismount(name, grab, want, height=4.5):
        # In the air with a grab held, the skate button: off the board from the grab, the board into the hand, a landing.
        # Without a grab the feet kick the board away (BR_KICKOUT_*): it flies on by itself and the rider lands without it.
        riding(0)
        code = (f"g=live.L.ground_at(live.park.ue({FLAT[0]},{FLAT[1]},3.0)); live.skate_place(g+unreal.Vector(0,0,{height * 100}),0)\n"
                f"live.park.launch(500,0); live.park.look(-12,0); live.skate_input(grab_right={grab})\n" + tap(TOP, .3))
        rows = record(code, 3.0)
        qa.py('live.skate_release()')
        seen = clips(rows)
        off = next((c for f, c in seen if f == 'air'), '-')
        land = next((c for f, c in seen if f == 'land'), '-')
        start = next((i for i, r in enumerate(rows) if r.get('foot') == 'air'), None)
        if start is None:
            report(name, rows, False, f'never got off ({line(seen)}; modes {"".join(sorted(qa.modes(rows)))})')
            return
        worst = continuity(rows[start - 1:])
        shown, note = board_shown(rows)
        before, after = flat_speed(rows[start - 1]), flat_speed(rows[start])
        if grab:
            held = all(r['board'] == 'hand' and r['vis'] == '1' for r in rows[start:])
            ok = land.startswith('BR_LAND_') and held
            how = ', in hand throughout' if held else ''
        else:
            flew = any(r.get('loose') == 'flying' for r in rows[start:])
            ok = flew and rows[-1]['board'] == 'world' and rows[-1]['vis'] == '1' and rows[-1]['mode'] == '0'
            how = f', the board {"flew" if flew else "never flew"}, {rows[-1]["board"]} at the end ({rows[-1].get("loose")})'
        report(name, rows, off == want and ok and after >= .9 * before - 20 and smooth(worst) and shown,
               f'{line(seen)}; {before:.0f} -> {after:.0f} cm/s off the board, {flat_speed(rows[-1]):.0f} after 3 s; '
               f'{describe(worst)}; board {note}{how}')

    if wanted('jump'):
        jump('jump_run', 'run', 'JBR_RUN_FWD_', 'BR_LAND_SML_FWD_')
        jump('jump_stand', '', 'JBR_STAND_0_TO_SML_FWD_0', 'BR_LAND_SML_FWD_0_INTO_STAND', seconds=3.4)
    if wanted('caveman'):
        caveman('caveman_run', False)
        caveman('caveman_carry', True)
    if wanted('air_dismount'):
        air_dismount('air_dismount_grab', True, 'BR_DISMOUNT_FS_INTO_BR_AIR')
        air_dismount('air_kickout', False, 'BR_KICKOUT_HI_INTO_NB_AIR')
    for rider in ('Link', 'Bokoblin'):
        # The other riders' bodies (Link taller and slighter, a Bokoblin short and heavy) through the same transitions.
        key = rider.lower()
        if not wanted(key) and not wanted('capsule'):
            continue
        switched = qa.py(f"print(live.L.switch_character('{rider}'))").strip()
        time.sleep(2.5)
        if switched != rider:
            report(f'{key}_switch', [], False, f'switch to {rider} refused ({switched or "nothing"})')
            continue
        # First, while nothing has stood this body up yet.
        toggles(f'capsule_{key}')
        if wanted(key):
            mount(f'{key}_mount_run', 'run')
            dismount(f'{key}_dismount_high', 900, 'BR_DISMOUNT_FAST_HI_INTO_RUN_FWD')
            runout(f'{key}_runout', 250)
            results[f'{key}_mount_run']['note'] += f' ({switched})'
        qa.py("live.L.switch_character('Cairo')")
        time.sleep(2.5)

    if frames and not FILM['dir']:
        ms = sorted(dt * 1000 for dt in frames)
        p99 = ms[min(len(ms) - 1, round((len(ms) - 1) * .99))]
        report('pacing', [], p99 < 17, f'{len(ms)} frames, p50 {ms[len(ms) // 2]:.1f} ms, p99 {p99:.1f} ms, worst {ms[-1]:.1f} ms')
    qa.py('live.drive(0); live.skate_release()')
    out = qa.yori.OUT / 'skateqa' / ('transitions-film.json' if FILM['dir'] else 'transitions.json')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2) + '\n')
    print(f'{sum(r["ok"] for r in results.values())}/{len(results)} passed -> {out}')
    return 0 if all(r['ok'] for r in results.values()) else 1


def release_controls():
    qa.py("live.stop('tr'); live.stop('tap'); live.stop('bail'); live.stop('later'); live.stop('walk'); live.drive(0); live.skate_release(); live.press('jump_release')\n"
          "for k in ['Gamepad_LeftThumbstick','Gamepad_RightThumbstick','Gamepad_FaceButton_Top','Gamepad_DPad_Right']: live.L.input_key(k,'release',0)\n"
          "for k in ['Gamepad_LeftTriggerAxis','Gamepad_RightTriggerAxis']: live.L.input_key(k,'axis',0)\n"
          "unreal.SystemLibrary.execute_console_command(live.L.game_world(), 'skate.RideTune \"\"')\n"
          "live.FILM_DIR=''; unreal.MegaParkValidation.restore_player_camera(); live.L.film_hud(False); live.L.fixed_step(0)")


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    finally:
        release_controls()
