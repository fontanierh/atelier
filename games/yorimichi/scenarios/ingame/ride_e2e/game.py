
import json, math, time, unreal
GS = unreal.GameplayStatics
def _w(): return live.L.game_world()
class _E: pass
E = _E(); live.E2E = E
E.T = 0.0; E.N = 0; E.ROWS = []; E.EV = []; E.ERR = []; E.STEP = 'setup'; E.WANT = {}; E.SENT = {}; E.TL = []
E.PILOT = None; E.WHEN = []; E.DONE = {}; E.F = {}; E.AT = (0.0, 0.0, 0.0); E.YAW = 0.0; E.LOOPS = None; E.SHOTDIR = ''
E.AIR = 0.0; E.PREV = '0'; E.LAND = -1.0; E.SKIPTO = 0; E.CM = None; E.GOOFY = False
KEEP = ('mm', 'mode', 'speed', 'fakie', 'manual', 'slide', 'push', 'ps', 'yaw', 'board', 'shown', 'vis', 'hip', 'deck', 'vel',
        'momentum', 'foot', 'clip', 't', 'hold', 'loose', 'simulation', 'combo', 'last', 'landed', 'bails', 'grinds', 'pos')
KEYS = {'A': 'Gamepad_FaceButton_Bottom', 'B': 'Gamepad_FaceButton_Right', 'X': 'Gamepad_FaceButton_Left',
        'Y': 'Gamepad_FaceButton_Top', 'L3': 'Gamepad_LeftThumbstick', 'R3': 'Gamepad_RightThumbstick',
        'DL': 'Gamepad_DPad_Left', 'DR': 'Gamepad_DPad_Right', 'DU': 'Gamepad_DPad_Up', 'DD': 'Gamepad_DPad_Down',
        'LX': 'Gamepad_LeftX', 'LY': 'Gamepad_LeftY', 'RX': 'Gamepad_RightX', 'RY': 'Gamepad_RightY',
        'LT': 'Gamepad_LeftTriggerAxis', 'RT': 'Gamepad_RightTriggerAxis', 'C': 'C'}
AXES = {'Gamepad_LeftX', 'Gamepad_LeftY', 'Gamepad_RightX', 'Gamepad_RightY', 'Gamepad_LeftTriggerAxis', 'Gamepad_RightTriggerAxis'}

def parse(s):
    head = s.split(' | ')[0]
    f = {}
    for kv in head.split(' '):
        if '=' in kv and not kv.startswith('flick'):
            k, v = kv.split('=', 1); f[k] = v
    parts = s.split(' | ')
    f['combo'] = parts[1][6:] if len(parts) > 1 else ''
    for kv in ' '.join(parts[2:]).split(' '):
        if '=' in kv:
            k, v = kv.split('=', 1); f.setdefault(k, v)
    return f

def vec(t):
    try: return tuple(float(x) for x in t.strip().strip('()').split(','))
    except Exception: return None
E.vec = vec
def ev(name, info=''): E.EV.append([E.N, round(E.T, 3), E.STEP, name, str(info)])
E.ev = ev
def pad(k, v): E.WANT[KEYS.get(k, k)] = float(v)
E.pad = pad
def at(dt, *items):
    E.TL.append([E.T + dt, list(items)]); E.TL.sort(key=lambda e: e[0])
E.at = at
def tap(k, dt=0.0, hold=0.09):
    at(dt, (k, 1), lambda: ev('tap', k)); at(dt + hold, (k, 0))
E.tap = tap
def later(dt, fn): at(dt, fn)
E.later = later
def flick(name, dt=0.0, load=0.18, step=0.035):
    # The right stick's raw Y reads up as negative (the skate input flips it back). live.FLICKS is drawn for a regular
    # stance; Ride mirrors the stick's X for a goofy one, so a goofy player flicks the mirror image for the same trick.
    m = -1.0 if E.GOOFY else 1.0
    pts = live.FLICKS[name]; t = dt
    at(t, ('RX', m * pts[0][0]), ('RY', -pts[0][1]), lambda: ev('flick', name)); t += load
    for p in pts[1:]:
        at(t, ('RX', m * p[0]), ('RY', -p[1])); t += step
    at(t, ('RX', 0.0), ('RY', 0.0))
E.flick = flick
def shot(name):
    if E.SHOTDIR:
        live.L.screenshot(E.SHOTDIR + '/' + name + '.png'); ev('shot', name)
E.shot = shot
def when(name, cond, act, once=True):
    E.WHEN = [w for w in E.WHEN if w[0] != name]; E.WHEN.append([name, cond, act, once])
E.when = when
def unwhen(*names): E.WHEN = [w for w in E.WHEN if w[0] not in names]
E.unwhen = unwhen
def coast(on):
    if E.PILOT: E.PILOT['coast'] = bool(on)
E.coast = coast
def steer(v):
    if E.PILOT: E.PILOT['steer'] = v
E.steer = steer
def stop_walk():
    if E.PILOT and E.PILOT['kind'] == 'walk': E.PILOT = None
    pad('LX', 0); pad('LY', 0); pad('L3', 0); live.drive(0)
E.stop_walk = stop_walk
def release():
    E.TL = []; E.WHEN = []; E.PILOT = None
    for k in list(E.WANT): E.WANT[k] = 0.0
    live.drive(0)
E.release = release
def sword():
    p = GS.get_player_pawn(_w(), 0)
    for c in p.get_components_by_class(unreal.StaticMeshComponent):
        if c.get_name() == 'Bokken': return bool(c.is_visible())
    return None
E.sword = sword

def send():
    for k, v in E.WANT.items():
        if k in AXES:
            # One sample a frame, as a pad sends: the player input adds up the samples of a frame.
            if abs(v) > 1e-4 or abs(E.SENT.get(k, 0.0)) > 1e-4:
                live.L.input_key(k, 'axis', v); E.SENT[k] = v
        else:
            on = v > .5
            if on and not E.SENT.get(k): live.L.input_key(k, 'press', 1.0); E.SENT[k] = 1
            elif not on and E.SENT.get(k): live.L.input_key(k, 'release', 0.0); E.SENT[k] = 0

# The steering curve (stick -> share of the full yaw rate), inverted.
INV = [(0.0, 0.0), (.034, .25), (.078, .375), (.172, .509), (.335, .69), (.564, .858), (.835, 1.0)]
def inv_steer(o):
    s = 1.0 if o >= 0 else -1.0; o = min(abs(o), .835)
    if o < .006: return 0.0
    for (o0, s0), (o1, s1) in zip(INV, INV[1:]):
        if o <= o1: return s * max(.26, s0 + (s1 - s0) * (o - o0) / (o1 - o0))
    return s

def follow(P, x, y, look):
    path = P['path']; n = len(path); i = P['i']; best = None
    for j in range(max(0, i - 2), min(n - 1, i + 16)):
        ax, ay = path[j]; bx, by = path[j + 1]; dx, dy = bx - ax, by - ay; l2 = dx * dx + dy * dy or 1.0
        u = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / l2))
        px, py = ax + u * dx, ay + u * dy; d = (x - px) ** 2 + (y - py) ** 2
        if best is None or d < best[0]: best = (d, j, px, py)
    d, j, px, py = best
    P['i'] = j; P['xt'] = math.sqrt(d)
    rem = look; k = j; cx, cy = px, py
    while True:
        bx, by = path[k + 1]; seg = math.hypot(bx - cx, by - cy)
        if seg >= rem or k + 2 >= n:
            f = min(1.0, rem / seg) if seg > 1e-6 else 0.0
            return cx + (bx - cx) * f, cy + (by - cy) * f, j
        rem -= seg; cx, cy = bx, by; k += 1

def cap_ahead(P, x, y, reach):
    caps = P.get('caps'); path = P['path']
    if not caps: return None
    j = P['i']; best = caps[j]; k = j + 1
    acc = math.hypot(path[min(k, len(path) - 1)][0] - x, path[min(k, len(path) - 1)][1] - y)
    while k < len(path) and acc <= reach:
        if caps[k] is not None: best = caps[k] if best is None else min(best, caps[k])
        if k + 1 < len(path): acc += math.hypot(path[k + 1][0] - path[k][0], path[k + 1][1] - path[k][1])
        k += 1
    return best

def arrived(P, x, y, j, radius):
    path = P['path']
    if j >= len(path) - 2 and math.hypot(path[-1][0] - x, path[-1][1] - y) < radius:
        E.DONE[P['name']] = round(E.T, 3); ev('arrived', P['name']); E.PILOT = None
        return True
    return False

def ride(f, dt):
    P = E.PILOT; mode = f.get('mode', '0'); x, y, z = E.AT
    if mode not in ('1', '2', '3'):
        pad('A', 0); pad('B', 0); pad('LX', 0); return
    v = vec(f.get('vel', '')) or (0.0, 0.0, 0.0); spd = math.hypot(v[0], v[1])
    if spd > 120: hd = math.atan2(v[1], v[0])
    else: hd = math.radians(float(f.get('yaw', 0) or 0) + (180.0 if f.get('fakie') == '1' else 0.0))
    tx, ty, j = follow(P, x, y, P.get('look') or max(320.0, spd * .65))
    if P.get('carve'):
        amp, per = P['carve']; P['ct'] = P.get('ct', 0.0) + dt
        path = P['path']; sx, sy = path[j + 1][0] - path[j][0], path[j + 1][1] - path[j][1]; sl = math.hypot(sx, sy) or 1.0
        off = amp * math.sin(2 * math.pi * P['ct'] / per); tx += -sy / sl * off; ty += sx / sl * off
    a = (math.atan2(ty - y, tx - x) - hd + math.pi) % (2 * math.pi) - math.pi
    ld = math.hypot(tx - x, ty - y) or 1.0
    rate = math.degrees(2.0 * max(spd, 150.0) * math.sin(a) / ld)
    stick = inv_steer(rate / (60.0 + .045 * spd) * .835) if mode == '1' and not P.get('nosteer') else 0.0
    if P.get('steer') is not None: stick = P['steer']
    pad('LX', stick)
    target = P.get('v', 500.0); over = P.get('over', 140.0); c = cap_ahead(P, x, y, 900.0)
    if c is not None and c < target: target, over = c, 40.0
    if P.get('brake'):
        pad('A', 0); pad('B', 1)
    elif mode == '1' and not P.get('coast'):
        if spd < target - 40: pad('A', 1)
        elif spd >= target: pad('A', 0)
        if spd > target + over: pad('B', 1)
        elif spd < target + 30: pad('B', 0)
    else:
        pad('A', 0); pad('B', 0)
    if arrived(P, x, y, j, P.get('end_r', 300.0)):
        pad('LX', 0); pad('A', 0); pad('B', 0)

def walk(f, dt):
    P = E.PILOT; x, y, z = E.AT
    tx, ty, j = follow(P, x, y, P.get('look', 220.0))
    if arrived(P, x, y, j, P.get('end_r', 90.0)):
        pad('LX', 0); pad('LY', 0); pad('L3', 0); live.drive(0); return
    yaw = math.radians(E.CM.get_camera_rotation().yaw)
    dx, dy = tx - x, ty - y; n = math.hypot(dx, dy) or 1.0
    fx, fy = math.cos(yaw), math.sin(yaw)
    fwd, right = (dx * fx + dy * fy) / n, (dy * fx - dx * fy) / n
    m = P.get('mag', 1.0); gait = P.get('gait', 'run')
    pad('LX', right * m); pad('LY', fwd * m); pad('L3', 1 if gait == 'sprint' else 0)
    live.drive(fwd * m, right * m, gait)

def set_pilot(kind, path, caps=None, **kw):
    P = dict(kind=kind, path=[tuple(p) for p in path], caps=caps, i=0, name=kw.pop('name', kind))
    P.update(kw)
    # Start on the nearest stretch going the way the rider faces (the lanes run side by side both ways).
    x, y, z = E.AT
    v = vec(E.F.get('vel', '')) or (0.0, 0.0, 0.0)
    h = math.atan2(v[1], v[0]) if math.hypot(v[0], v[1]) > 100 else math.radians(E.YAW)
    best = None
    for j in range(len(P['path']) - 1):
        (ax, ay), (bx, by) = P['path'][j], P['path'][j + 1]
        d = math.hypot(ax - x, ay - y); s = math.hypot(bx - ax, by - ay) or 1.0
        agree = ((bx - ax) * math.cos(h) + (by - ay) * math.sin(h)) / s > 0.0
        key = (0 if agree else 1, d) if d < 1500 else (2, d)
        if best is None or key < best[0]: best = (key, j)
    P['i'] = best[1] if best else 0
    E.DONE.pop(P['name'], None)
    if kind == 'ride': pad('LY', 0); pad('L3', 0); live.drive(0)
    E.PILOT = P; ev('pilot', kind + ' ' + P['name'] + ' @' + str(P['i']))
    return P
E.set_pilot = set_pilot

def tick(dt):
    try:
        w = _w(); wdt = GS.get_world_delta_seconds(w); E.T += wdt
        E.CM = GS.get_player_camera_manager(w, 0)
        s = live.L.skate_state()
        full = parse(s) if s and s != 'no skate' else {}
        f = {k: full[k] for k in KEEP if k in full}
        E.F = f
        p = GS.get_player_pawn(w, 0)
        if p:
            l = p.get_actor_location(); E.AT = (l.x, l.y, l.z); E.YAW = p.get_actor_rotation().yaw
        cl = E.CM.get_camera_location(); cr = E.CM.get_camera_rotation()
        mode = f.get('mode', '0')
        E.AIR = E.AIR + wdt if mode == '2' else 0.0
        if E.PREV == '2' and mode in ('1', '3'): E.LAND = E.T; ev('landed', f.get('combo', ''))
        E.PREV = mode
        row = {'n': E.N, 's': E.STEP, 'T': round(E.T, 4), 'wdt': round(wdt, 5), 'dt': round(dt, 5), 'w': round(time.time(), 3),
               'f': f, 'at': [round(c, 1) for c in E.AT],
               'cam': [round(cl.x, 1), round(cl.y, 1), round(cl.z, 1), round(cr.pitch, 2), round(cr.yaw, 2)]}
        if E.N < E.SKIPTO: row['x'] = 1
        if E.PILOT: row['pilot'] = [E.PILOT['name'], E.PILOT['i'], round(E.PILOT.get('xt', 0.0), 1)]
        loops = live.L.skate_loops()
        if loops != E.LOOPS: row['loops'] = loops; E.LOOPS = loops
        E.ROWS.append(row); E.N += 1
        live.L.audio_frame(E.N)
    except Exception as e:
        if len(E.ERR) < 200: E.ERR.append(['rec', E.N, repr(e)])
    for item in list(E.WHEN):
        try:
            if item[1](E.F):
                if item[3] and item in E.WHEN: E.WHEN.remove(item)
                ev('when', item[0]); item[2]()
        except Exception as e:
            if item in E.WHEN: E.WHEN.remove(item)
            if len(E.ERR) < 200: E.ERR.append(['when ' + item[0], E.N, repr(e)])
    try:
        if E.TL and E.TL[0][0] <= E.T:
            for it in E.TL.pop(0)[1]:
                if callable(it): it()
                else: pad(it[0], it[1])
    except Exception as e:
        if len(E.ERR) < 200: E.ERR.append(['timeline', E.N, repr(e)])
    try:
        if E.PILOT: (ride if E.PILOT['kind'] == 'ride' else walk)(E.F, GS.get_world_delta_seconds(_w()))
    except Exception as e:
        if len(E.ERR) < 200: E.ERR.append(['pilot', E.N, repr(e)])
    try: send()
    except Exception as e:
        if len(E.ERR) < 200: E.ERR.append(['send', E.N, repr(e)])
live.behave('e2e', tick)
