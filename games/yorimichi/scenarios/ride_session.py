# ride_session.py: runs inside the game (atelier live py - < this file). This line keeps the bridge from taking the code
# for a file name: Unreal's Python reads any text whose first .py is followed by a space as a script path.
"""Ride session: the player records a skating session that replays exactly, then it replays through either backend.

    atelier live py "TAKE='carpark-1'" && atelier live py - < games/yorimichi/scenarios/ride_session.py
    ... the player skates from GO, then:
    atelier live py "print(session_close())"
    atelier live py "TAKE='carpark-1'; MODE='replay'" && atelier live py - < games/yorimichi/scenarios/ride_session.py

Both modes start the same way, so a replay starts where the recording did. The rider gets off and rides Ride a moment at
the start, AT, so that the next mount opens a new session. Then he gets on the board with BACKEND, stopped at AT, and
stands with every control released. Under Native he stands SETTLE frames from the frame his skater rides; under Ride,
SETTLE frames. From the start the game runs at a fixed 60 Hz frame rate in real time: the engine waits out each frame
and counts it as 1/60 s, and Native steps in lockstep with its thread (skate.Lockstep), so the same controls ride the
same way.

record: from GO the player's pad drives, and each frame writes one row, flushed at once: quitting the game ends it.
replay: from GO, each frame injects the recorded controls for the next frame, as a pad sends them. A stick gets the raw
value that the engine's dead zone turns exactly into the recorded one; triggers go in as recorded; buttons are pressed
and released when the recording changes them. GHOST draws the recorded board and skeleton over the replay, and SHOTS
saves a JPG every second frame for a film.

A row has:
- k: frames from GO
- gt: game time
- dt: the game's frame time; rdt: the real one
- ax: the axes as the game read them
- b: the buttons held, in meta's order
- s: the skate state
- d: the SkateDeck's location (cm) and quaternion
- p: the rider's location, quaternion and velocity
- c: the camera's location, pitch, yaw and roll
- jm and j: the visible rider mesh, and each of its bones' world location, in meta's order for that mesh

Writes build/yorimichi/ride-record/<TAKE>/:
- record: meta.json and frames.jsonl.
- replay: <OUT>/ beside them, with frames.jsonl, report.json (the board's error, and the first frames where the board or
  the pad sent to Native differ) and shots/.
- done.json when it ends, and error.txt on a failure.

Globals:
- TAKE
- MODE: 'record' or 'replay'
- BACKEND: 'Native' by default; a replay takes the recording's
- AT: (x, y, z, yaw), the start in UE cm and degrees (the ground is found under x, y near z); the car park by default
- SETTLE: frames, 30 by default
- OUT: the replay folder, replay-<BACKEND> by default
- GHOST: True by default
- SHOTS: False by default
- FRAMES: replay at most this many frames
"""
import json, math, os, struct, time, traceback
import unreal

L = live.L
TAKE = globals().get('TAKE', 'session')
MODE = globals().get('MODE', 'record')
DIR = os.path.join(live.ROOT, 'build/yorimichi/ride-record', TAKE)
META = json.load(open(os.path.join(DIR, 'meta.json'))) if MODE == 'replay' else {}
BACKEND = globals().get('BACKEND') or META.get('backend') or 'Native'
AT = tuple(globals().get('AT') or META.get('at') or (-2775.7, -139302.1, 11803., 103.6))
SETTLE = int(globals().get('SETTLE') or META.get('settle') or 30)
GHOST = bool(globals().get('GHOST', True))
SHOTS = bool(globals().get('SHOTS', False))
FRAMES = globals().get('FRAMES')
OUT = os.path.join(DIR, globals().get('OUT') or 'replay-' + BACKEND) if MODE == 'replay' else DIR
AXES = ['Gamepad_LeftX', 'Gamepad_LeftY', 'Gamepad_RightX', 'Gamepad_RightY', 'Gamepad_LeftTriggerAxis', 'Gamepad_RightTriggerAxis']
BUTTONS = ['Gamepad_FaceButton_Bottom', 'Gamepad_FaceButton_Right', 'Gamepad_FaceButton_Left', 'Gamepad_FaceButton_Top',
           'Gamepad_LeftShoulder', 'Gamepad_RightShoulder', 'Gamepad_LeftThumbstick', 'Gamepad_RightThumbstick',
           'Gamepad_DPad_Up', 'Gamepad_DPad_Down', 'Gamepad_DPad_Left', 'Gamepad_DPad_Right',
           'Gamepad_Special_Left', 'Gamepad_Special_Right',
           'W', 'A', 'S', 'D', 'SpaceBar', 'Q', 'E', 'C', 'B', 'G', 'LeftShift', 'LeftMouseButton', 'Escape']
STICKS = set(AXES[:4])               # the engine's 0.25 dead zone (BaseInput.ini AxisConfig) applies to these only
SKIP = {'Escape', 'Gamepad_Special_Left', 'Gamepad_Special_Right', 'LeftMouseButton'}   # menus and the mouse
DEAD = .25


def _key(name):
    k = unreal.Key(); k.import_text(name); assert k.export_text() == name, name
    return k


_world = L.game_world()
_pc = unreal.GameplayStatics.get_player_controller(_world, 0)
_AK = [_key(n) for n in AXES]
_BK = [_key(n) for n in BUTTONS]
os.makedirs(os.path.join(OUT, 'shots') if SHOTS else OUT, exist_ok=True)
for _f in ('frames.jsonl', 'report.json', 'error.txt', 'done.json'):
    if os.path.exists(os.path.join(OUT, _f)): os.remove(os.path.join(OUT, _f))
ROWS = [json.loads(l) for l in open(os.path.join(DIR, 'frames.jsonl')) if l.endswith('\n')] if MODE == 'replay' else []
S = {'ph': 'off', 'n': 0, 'ok': 0, 'since': time.time(), 't': time.time(), 'k': 0, 'sent': {}, 'f': open(os.path.join(OUT, 'frames.jsonl'), 'w'),
     'err': [], 'deck_at': None, 'pad_at': None, 'bones': {}}


def field(s, key):
    for part in s.split(' '):
        if part.startswith(key + '='): return part[len(key) + 1:]
    return None


def mode():
    m = field(L.skate_state(), 'mode')
    return int(m) if m and m.lstrip('-').isdigit() else 0


def f32(x):
    return struct.unpack('<f', struct.pack('<f', x))[0]


def raw_stick(v):
    """The raw stick value the engine's dead zone turns exactly into v (UPlayerInput::MassageAxisInput, float maths)."""
    if v == 0.: return 0.
    a = abs(v); guess = f32(DEAD + (1. - DEAD) * a)
    bits = struct.unpack('<I', struct.pack('<f', guess))[0]
    for d in (0, 1, -1, 2, -2, 3, -3, 4, -4):
        w = struct.unpack('<f', struct.pack('<I', bits + d))[0]
        if f32(f32(max(0., f32(w - DEAD))) / f32(1. - DEAD)) == f32(a): return math.copysign(w, v)
    return math.copysign(guess, v)


def player():
    return L.player()


def deck():
    d = S.get('deck')
    if d is None:
        d = S['deck'] = next((m for m in player().get_components_by_class(unreal.StaticMeshComponent)
                              if m.get_name() == 'SkateDeck'), None)
    if d is None: return None
    t = d.get_world_transform(); c, q = t.translation, t.rotation
    return [round(c.x, 3), round(c.y, 3), round(c.z, 3), round(q.x, 6), round(q.y, 6), round(q.z, 6), round(q.w, 6),
            int(d.is_visible())]


def body():
    """The visible rider mesh's name and every bone's world location (the bone order is in meta)."""
    meshes = {m.get_name(): m for m in player().get_components_by_class(unreal.SkeletalMeshComponent)}
    m = next((x for n, x in meshes.items() if n.startswith('RidePose') and x.is_visible()), None) or meshes.get('CharacterMesh0')
    if m is None: return None, []
    name = m.get_name()
    if name not in S['bones']:
        names = [str(m.get_bone_name(i)) for i in range(m.get_num_bones())]
        S['bones'][name] = {'names': names, 'parents': [str(m.get_parent_bone(n)) for n in names]}
    out = []
    for n in S['bones'][name]['names']:
        p = m.get_socket_location(n); out += [round(p.x, 2), round(p.y, 2), round(p.z, 2)]
    return name, out


def controls():
    ax = [_pc.get_input_analog_key_state(k) for k in _AK]
    mask = 0
    for i, k in enumerate(_BK):
        if _pc.is_input_key_down(k): mask |= 1 << i
    return ax, mask


def row(dt):
    ax, mask = controls()
    t = L.player_transform(); p, q = t.translation, t.rotation; v = player().get_velocity()
    cam = unreal.GameplayStatics.get_player_camera_manager(_world, 0)
    cl, cr = cam.get_camera_location(), cam.get_camera_rotation()
    jm, j = body()
    return {'k': S['k'], 'gt': unreal.GameplayStatics.get_time_seconds(_world),
            'dt': unreal.GameplayStatics.get_world_delta_seconds(_world), 'rdt': dt, 'ax': ax, 'b': mask,
            's': L.skate_state(), 'd': deck(),
            'p': [round(p.x, 3), round(p.y, 3), round(p.z, 3), round(q.x, 6), round(q.y, 6), round(q.z, 6), round(q.w, 6),
                  round(v.x, 3), round(v.y, 3), round(v.z, 3)],
            'c': [round(cl.x, 2), round(cl.y, 2), round(cl.z, 2), round(cr.pitch, 4), round(cr.yaw, 4), round(cr.roll, 4)],
            'jm': jm, 'j': j}


def send(r):
    """Row r's controls, as the pad and keyboard would send them."""
    for name, v in zip(AXES, r['ax']):
        w = raw_stick(v) if name in STICKS else v
        if w != 0. or S['sent'].get(name, 0.) != 0.:
            L.input_key(name, 'axis', w); S['sent'][name] = w
    for i, name in enumerate(BUTTONS):
        if name in SKIP: continue
        on = bool(r['b'] >> i & 1)
        if on and not S['sent'].get(name): L.input_key(name, 'press', 1.); S['sent'][name] = 1
        elif not on and S['sent'].get(name): L.input_key(name, 'release', 0.); S['sent'][name] = 0


def release():
    for name, v in list(S['sent'].items()):
        if name in AXES:
            if v != 0.: L.input_key(name, 'axis', 0.)
        elif v: L.input_key(name, 'release', 0.)
    S['sent'] = {}


def ghost(r):
    """The recorded board (a box) and skeleton (lines), drawn for one frame."""
    d = r.get('d')
    if d:
        rot = unreal.Quat(d[3], d[4], d[5], d[6]).rotator()
        unreal.SystemLibrary.draw_debug_box(_world, unreal.Vector(d[0], d[1], d[2]), unreal.Vector(41., 10.5, 1.5),
                                            unreal.LinearColor(0., 1., .3, 1.), rot, .02, 1.5)
    bones = META.get('bones', {}).get(r.get('jm') or '')
    if bones and r.get('j'):
        j, index = r['j'], {n: i for i, n in enumerate(bones['names'])}
        for i, parent in enumerate(bones['parents']):
            pi = index.get(parent)
            if pi is None: continue
            unreal.SystemLibrary.draw_debug_line(_world, unreal.Vector(*j[3 * i:3 * i + 3]), unreal.Vector(*j[3 * pi:3 * pi + 3]),
                                                 unreal.LinearColor(0., 1., .3, 1.), .02, 1.)


def write(r):
    S['f'].write(json.dumps(r, separators=(',', ':')) + '\n')
    if MODE == 'record' or S['k'] % 60 == 0: S['f'].flush()   # a recording survives the game being quit


def write_meta(extra=None):
    meta = {'backend': BACKEND, 'at': list(AT), 'settle': SETTLE, 'axes': AXES, 'buttons': BUTTONS, 'fps': 60,
            'bones': S['bones'], 'started': S.get('started'), 'frames': S['k'] + 1, 'state0': S.get('state0')}
    meta.update(extra or {})
    json.dump(meta, open(os.path.join(OUT, 'meta.json' if MODE == 'record' else 'run.json'), 'w'), indent=1)


def finish(error=None):
    live.stop('ride_session')
    try: release()
    except Exception: pass
    L.fixed_frame_rate(0)
    S['f'].close()
    if MODE == 'record': write_meta()
    else:
        e = S['err']
        report = {'take': TAKE, 'backend': BACKEND, 'frames': len(e), 'recorded': len(ROWS),
                  'board_error_cm': {'max': round(max(e), 3) if e else None, 'mean': round(sum(e) / len(e), 4) if e else None},
                  'first_board_difference': S['deck_at'], 'first_pad_difference': S['pad_at'],
                  'seconds': round(time.time() - S['t'], 1)}
        json.dump(report, open(os.path.join(OUT, 'report.json'), 'w'), indent=1); write_meta()
    if error: open(os.path.join(OUT, 'error.txt'), 'w').write(error)
    json.dump({'frames': S['k'] + 1, 'error': bool(error)}, open(os.path.join(OUT, 'done.json'), 'w'))
    return S['k'] + 1


def session_close():
    """Stop the recording; the number of rows written."""
    return finish()


def step(dt):
    try:
        tick(dt)
    except Exception:
        finish(traceback.format_exc())


def phase(name):
    S['ph'] = name; S['n'] = 0; S['ok'] = 0; S['since'] = time.time()


def hold(condition, frames, seconds=30.):
    """Whether the condition has held `frames` frames running; the phase gives up after `seconds` of real time."""
    S['n'] += 1; S['ok'] = S['ok'] + 1 if condition else 0
    if time.time() - S['since'] > seconds: raise RuntimeError('timed out in ' + S['ph'])
    return S['ok'] >= frames


def at_ground():
    g = L.ground_at(unreal.Vector(AT[0], AT[1], AT[2] + 300.))
    return None if abs(g.z - (AT[2] + 300.)) < 1. else g


def tick(dt):
    ph = S['ph']
    if ph == 'off':
        # Off the board, wherever he is.
        if S['n'] == 0: release(); live.skate_release(); L.fixed_step(0); L.fixed_frame_rate(60)
        if mode() != 0 and S['n'] % 300 == 0: L.skate_toggle()
        if hold(mode() == 0, 30, 60.): phase('warm')
        return
    if ph == 'warm':
        # Ride Ride a moment at the start, so the next mount opens a new session (and the ground around has loaded).
        g = at_ground()
        if g is None:
            if S['n'] % 30 == 0: L.teleport_player(unreal.Vector(AT[0], AT[1], AT[2] + 100.), AT[3])
            hold(False, 1, 60.); return
        if not S.get('placed'):
            unreal.SystemLibrary.execute_console_command(None, 'skate.Backend Ride')
            if not live.skate_place(g, AT[3]): raise RuntimeError('could not get on Ride at the start')
            S['placed'] = True; return
        if hold(mode() != 0, 90): L.skate_toggle(); phase('down')
        return
    if ph == 'down':
        if hold(mode() == 0, 60): phase('place')
        return
    if ph == 'place':
        unreal.SystemLibrary.execute_console_command(None, 'skate.Backend ' + BACKEND)
        L.skate_input(unreal.Vector2D(0., 0.), unreal.Vector2D(0., 0.), False, False, False, 0., 0.)
        if not live.skate_place(at_ground(), AT[3]): raise RuntimeError('could not get on the board')
        if MODE == 'record': live.say('Hands off the pad: recording starts at GO', 30.)
        phase('settle'); return
    if ph == 'settle':
        state = L.skate_state()
        riding = field(state, 'retail') == 'PhysicsGround' if BACKEND == 'Native' else mode() == 1
        hold(riding, SETTLE, 60.)
        # The Native session, the Native backend's or the one under Ride's body, goes at its SETTLE + 3rd step (where
        # the Native backend's SETTLE frames end), so it has stepped as often at GO on either backend: under Ride's body
        # it rides two steps before the body has mounted, and two more steps at rest put the board centimetres off by
        # the pier's end.
        step = field(state, 'tick')
        ready = riding and S['ok'] >= SETTLE // 2 and step is not None and int(step) >= SETTLE + 3
        if MODE == 'record' and not ready and S['ok'] and (SETTLE - S['ok']) % 60 == 0:
            live.say('Hands off the pad. GO in %d' % ((SETTLE - S['ok']) // 60), 1.5)
        if not ready: return
        # GO: the controls are the pad's from the next frame on.
        live.skate_release(); S['k'] = 0; S['started'] = time.strftime('%Y-%m-%d %H:%M:%S'); S['state0'] = L.skate_state()
        r = row(dt); write(r)
        if MODE == 'record':
            live.say('GO: skate now', 6.); write_meta(); phase('record')
        else:
            compare(r); phase('replay'); feed()
        return
    S['k'] += 1
    r = row(dt); write(r)
    if MODE == 'replay':
        compare(r)
        if S['k'] >= len(ROWS) - 1 or (FRAMES and S['k'] >= FRAMES): return finish()
        feed()


def feed():
    nxt = ROWS[S['k'] + 1]
    send(nxt)
    if GHOST: ghost(nxt)
    if SHOTS and S['k'] % 2 == 1: L.screenshot(os.path.join(OUT, 'shots', 'f%05d.jpg' % (S['k'] // 2)))


def compare(r):
    ref = ROWS[S['k']]
    e = math.dist(r['d'][:3], ref['d'][:3]) if r.get('d') and ref.get('d') else 0.
    S['err'].append(e)
    if e > .01 and S['deck_at'] is None: S['deck_at'] = {'k': S['k'], 'cm': round(e, 3)}
    pad, rpad = field(r['s'], 'pad'), field(ref['s'], 'pad')
    if pad != rpad and S['pad_at'] is None: S['pad_at'] = {'k': S['k'], 'replay': pad, 'recorded': rpad}
    live.say('Replay of %s through %s   frame %d / %d   board error %.2f cm%s' % (
        TAKE, BACKEND, S['k'], len(ROWS) - 1, e, '' if pad == rpad else '   controls differ'), .5)


live.stop('ride_session'); live.stop('ride_rec'); live.stop('ride_replay')
live.behave('ride_session', step)
print(f'{MODE} {TAKE} through {BACKEND} at {AT} -> {OUT}')
