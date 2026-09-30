"""The in-game half of treehouse_walk.py: steer Cairo along build/yorimichi/treehouse/walk/route.json and film it.

    atelier live py "TAKE='take1'; FILM=True" && atelier live py - < games/yorimichi/scenarios/treehouse_walk_live.py

Runs in the game's Python (the live bridge) at a fixed 60 fps step. Cairo is driven with stick input (live.drive)
towards a point a metre ahead on the route, the way a player steers. The camera is the game's own spring arm in three
modes, as the route asks:
- follow: the chase camera turns smoothly towards the path 3 m ahead; each few frames it tries a few headings and
  heights around that and keeps the one with the most room behind Cairo and a clear view of him (a wall or a post
  would otherwise pull it in to his hair or hide him, and a door curtain or a bridge-end lantern, which have no
  collision, would hide him);
  on the crow's nest it stays under the canvas roof;
- orbit: on the spiral stairs it circles outside the trunk with its wall test off, with the same view check;
- room: inside the small huts it holds still in a top corner of the room and turns to keep Cairo in frame (the arm's
  length and socket offset put it exactly there), cutting in and out at the door like a game's room camera;
- ring: the same free camera circling a place's centre at a set radius and height, a set angle from Cairo (in the
  heart room, and over the stairwell at the top of the spiral).
At a stop Cairo stands, turns to what he looks at, and the camera eases through its look targets (the chase camera
stays about level: looking up would drop it to the floor behind his head). With FILM every
frame is saved as a JPG with the camera (camera.csv) and the sounds the game starts (audio.json); a rehearsal keeps a
frame every half second and camlog.json (how far the camera sits from Cairo, and whether it sees him). stuck.json
lists any point where Cairo made no progress and was moved on.
"""
import json, math, os
import unreal

L = live.L
TAKE = globals().get('TAKE', 'take1'); FILM = bool(globals().get('FILM', True))
BUILD = os.environ.get('ATELIER_BUILD_ROOT') or os.path.join(live.ROOT, 'build')
WALK = os.path.join(BUILD, 'yorimichi/treehouse/walk'); OUT = os.path.join(WALK, TAKE)
os.makedirs(OUT, exist_ok=True)
ROUTE = json.load(open(os.path.join(WALK, 'route.json')))
PTS = ROUTE['points']; N = len(PTS); STOPS = {s['at']: s for s in ROUTE['stops']}
CURTAINS = [(c[0]*100, -c[1]*100, c[2]*100, c[3]*100) for c in ROUTE.get('curtains', [])]      # cloth and lanterns
FEET = .75             # capsule half height (m): the player's location is the capsule centre
SETTLE = 150           # frames at the start, not filmed, while the world streams in and the camera settles
ARM = 330.             # the chase camera's length (cm), as cam_dist in the launch settings

world = L.game_world()
pc = unreal.GameplayStatics.get_player_controller(world, 0)
cm = unreal.GameplayStatics.get_player_camera_manager(world, 0)
pawn = unreal.GameplayStatics.get_player_pawn(world, 0)
arm = pawn.get_component_by_class(unreal.SpringArmComponent)
V = unreal.Vector


def ue(p):
    return V(p[0]*100, -p[1]*100, p[2]*100)


def feet():
    loc = live.player()[0]; return (loc.x/100, -loc.y/100, loc.z/100-FEET)


def wrap(a):
    return (a+540) % 360-180


def heading(a, b):
    return math.degrees(math.atan2(b[1]-a[1], b[0]-a[0]))


def ease(u):
    u = min(1., max(0., u)); return u*u*(3-2*u)


def dot(a, b):
    return a.x*b.x+a.y*b.y+a.z*b.z


def place(p, yaw):
    """Cairo straight onto route point p facing yaw (live.teleport drops onto the highest floor, a hut's roof)."""
    pawn.set_actor_location_and_rotation(ue((p[0], p[1], p[2]+FEET+.03)), unreal.Rotator(roll=0., pitch=0., yaw=-yaw), False, True)


S = dict(f=0, film=0, i=0, mode='settle', t=0., yaw=0., pitch=-10., since=0, stops_done=set(), rows=[], stuck=[], marks=[],
         cam='', off=(0., 0.), score=-9., aim=None, camlog=[], ceil=None, ring=0.)


def arm_mode(mode):
    """follow: the chase arm with its wall test; orbit: no wall test; room and ring: a free camera (no wall test, no
    lag)."""
    if mode == S['cam']: return False
    free = mode in ('room', 'ring')
    arm.set_editor_property('do_collision_test', mode == 'follow')
    arm.set_editor_property('enable_camera_lag', not free)
    if not free:
        arm.set_editor_property('target_arm_length', ARM); arm.set_editor_property('socket_offset', V(0, 0, 0))
    S['cam'] = mode; S['off'] = (0., 0.); S['score'] = -9.
    return True


def set_camera(dt, want_yaw, want_pitch, rate, snap=False):
    d = wrap(want_yaw-S['yaw']); k = 1-math.exp(-2.8*dt)
    if snap: S['yaw'], S['pitch'] = want_yaw, want_pitch
    else:
        S['yaw'] += max(-rate*dt, min(rate*dt, d*k))
        S['pitch'] += (want_pitch-S['pitch'])*(1-math.exp(-2.2*dt))
    pc.set_control_rotation(unreal.Rotator(roll=0., pitch=S['pitch'], yaw=-S['yaw']))


def pivot():
    """Where the arm starts next tick (the pawn moves before the arm updates)."""
    return arm.get_world_location()+arm.get_editor_property('target_offset')+pawn.get_velocity()*(1/60.)


def blocked(a, b, channel, radius=0.):
    ign = [pawn]
    if radius > 0:
        h = unreal.SystemLibrary.sphere_trace_single(world, a, b, radius, channel, True, ign, unreal.DrawDebugTrace.NONE, True)
    else:
        h = unreal.SystemLibrary.line_trace_single(world, a, b, channel, True, ign, unreal.DrawDebugTrace.NONE, True)
    return None if h is None else h.to_tuple()[3]


def near_curtain(a, b, curtains, pad=0.):
    """Whether the segment a-b (tuples, cm) passes through a door curtain or a lantern (its radius, plus pad)."""
    ab = [b[k]-a[k] for k in range(3)]; l2 = sum(v*v for v in ab) or 1.
    for c in curtains:
        t = max(0., min(1., sum((c[k]-a[k])*ab[k] for k in range(3))/l2))
        if sum((c[k]-a[k]-ab[k]*t)**2 for k in range(3)) < (c[3]+pad)**2: return True
    return False


def view_score(yaw, pitch, collide):
    """Room behind Cairo (the arm's wall test would pull the camera in to it) and a clear line to his head and chest,
    not through a door curtain or a lantern and, where the route sets a ceiling, not above it."""
    piv = pivot(); D = unreal.Rotator(roll=0., pitch=pitch, yaw=-yaw).get_forward_vector()
    free = ARM
    if collide:
        h = blocked(piv, piv-D*ARM, unreal.TraceTypeQuery.ECC_CAMERA, 12.)
        if h is not None: free = h
    eye = piv-D*max(free-15, 10)
    loc = pawn.get_actor_location()
    e = (eye.x, eye.y, eye.z); cur = [c for c in CURTAINS if abs(c[0]-e[0])+abs(c[1]-e[1]) < 900]
    seen = sum(blocked(eye, loc+V(0, 0, z), unreal.TraceTypeQuery.ECC_VISIBILITY) is None
               and not near_curtain(e, (loc.x, loc.y, loc.z+z), cur) for z in (55., 5.))
    if cur and near_curtain(e, e, cur, 20.): seen = 0
    over = S['ceil'] is not None and eye.z > S['ceil']*100
    return min(1., free/220.)+.55*seen/2-(2. if over else 0.), free, seen


YAWS = (0., 15., -15., 30., -30., 45., -45., 60., -60.)


def smart(want_yaw, want_pitch, collide, spread):
    """The heading and height offset (from want) with the best view; kept unless another is clearly better (and
    chosen at once as the mode starts, so a cut lands on it)."""
    if S['f'] % 3 == 0 or S['score'] == -9.:
        cur = view_score(want_yaw+S['off'][0], want_pitch+S['off'][1], collide)[0]-.5*abs(S['off'][0])/60-.1*(S['off'][1] != 0)
        best, bs = S['off'], cur
        for dy in YAWS:
            if abs(dy) > spread: continue
            for dp in (0., -14.):
                s = view_score(want_yaw+dy, want_pitch+dp, collide)[0]-.5*abs(dy)/60-.1*(dp != 0)
                if s > bs+.12: best, bs = (dy, dp), s
        S['off'] = best; S['score'] = bs
    return want_yaw+S['off'][0], want_pitch+S['off'][1]


def room_camera(dt, E, aim, snap, rate=3.):
    """The spring arm as a fixed camera at E looking at aim: its rotation looks along the arm, so the arm length is
    E's depth behind the pivot and the socket offset the rest (both in the arm's own axes)."""
    aim = V(*aim)
    S['aim'] = aim if (snap or S['aim'] is None) else S['aim']+(aim-S['aim'])*(1-math.exp(-rate*dt))
    Eu = ue(E); d = S['aim']-Eu
    rot = unreal.Rotator(roll=0., pitch=math.degrees(math.atan2(d.z, math.hypot(d.x, d.y))), yaw=math.degrees(math.atan2(d.y, d.x)))
    pc.set_control_rotation(rot); S['yaw'], S['pitch'] = -rot.yaw, rot.pitch
    F, R, U = rot.get_forward_vector(), rot.get_right_vector(), rot.get_up_vector()
    piv = pivot(); ln = dot(piv-Eu, F); off = Eu-(piv-F*ln)
    arm.set_editor_property('target_arm_length', ln); arm.set_editor_property('socket_offset', V(0., dot(off, R), dot(off, U)))


def head_ue():
    loc = pawn.get_actor_location(); return (loc.x, loc.y, loc.z+45.)


def turn_to(dt, yaw):
    """Cairo turns on the spot towards yaw (Blender degrees) at a stop."""
    cur = -pawn.get_actor_rotation().yaw; d = wrap(yaw-cur)
    if abs(d) < 1: return
    step = max(-260*dt, min(260*dt, d*(1-math.exp(-9*dt))))
    pawn.set_actor_rotation(unreal.Rotator(roll=0., pitch=0., yaw=-(cur+step)), False)


def drive_towards(target, gait, mag):
    p = feet(); dx, dy = target[0]-p[0], target[1]-p[1]; n = math.hypot(dx, dy)
    if n < 1e-3: live.drive(0, 0); return
    r = math.radians(S['yaw']); fx, fy = math.cos(r), math.sin(r)
    # Blender axes: forward = (fx, fy), right of the camera = (fy, -fx)
    live.drive(forward=mag*(dx*fx+dy*fy)/n, right=mag*(dx*fy-dy*fx)/n, gait=gait)


def progress(stop):
    """Advance the route index to the nearest point ahead (horizontal distance, floors apart on the spiral skipped),
    never past the next stop (in a hut the way out runs back over the way in)."""
    p = feet(); best, bd = S['i'], 9e9
    for j in range(S['i'], min(N, S['i']+14, N if stop is None else stop+1)):
        q = PTS[j]
        if abs(q[2]-p[2]) > 1.1: continue
        d = math.hypot(q[0]-p[0], q[1]-p[1])
        if d < bd: best, bd = j, d
    if bd < 1.2: S['i'] = best
    return bd


def next_stop():
    ahead = [a for a in STOPS if a >= S['i'] and a not in S['stops_done']]
    return min(ahead) if ahead else None


def record():
    if not FILM:                 # a rehearsal keeps a frame every half second to review the camera
        if S['f'] % 30 == 0: L.screenshot(os.path.join(OUT, 'look_%05d.jpg' % S['f']))
        if S['f'] % 6 == 0:
            c = cm.get_camera_location(); loc = pawn.get_actor_location()
            seen = sum(blocked(c, loc+V(0, 0, z), unreal.TraceTypeQuery.ECC_VISIBILITY) is None for z in (55., 5.))
            S['camlog'].append([S['f'], S['i'], S['cam'], round((c-loc-V(0, 0, 35)).length()), seen])
        return
    L.audio_frame(S['film'])
    L.screenshot(os.path.join(OUT, 'frame_%05d.jpg' % S['film']))
    loc = cm.get_camera_location(); rot = cm.get_camera_rotation()
    S['rows'].append('%d,%.1f,%.1f,%.1f,%.2f,%.2f' % (S['film'], loc.x, loc.y, loc.z, rot.pitch, rot.yaw))
    S['film'] += 1


def look_at(s, t, eye):
    """The stop's look target at time t, eased between its keys."""
    looks = s['looks']; k = max(j for j in range(len(looks)) if looks[j][0] <= t)
    a, b = looks[k], looks[min(k+1, len(looks)-1)]
    u = ease((t-a[0])/max(.01, b[0]-a[0])) if b is not a else 1.
    return [a[1][c]+(b[1][c]-a[1][c])*u for c in range(3)]


def level_for(pitch):
    """The steepest downward pitch that keeps the full-length arm under the route's ceiling."""
    if S['ceil'] is None: return pitch
    drop = (S['ceil']*100-pivot().z)/ARM
    return pitch if drop >= 1 else max(pitch, -math.degrees(math.asin(max(-1., drop))))


def camera_for(i, dt, stop_target=None):
    cam = ROUTE['cam'][min(i, N-1)]; p = feet()
    S['ceil'] = cam[2] if cam[0] == 'follow' and len(cam) > 2 else None
    if cam[0] == 'ring':
        snap = arm_mode('ring'); cx, cy, rc, zc, lag, mix = cam[1:7]
        want = heading((cx, cy), p)+lag
        S['ring'] = want if snap else S['ring']+wrap(want-S['ring'])*(1-math.exp(-6.*dt))
        a = math.radians(S['ring']); E = (cx+rc*math.cos(a), cy+rc*math.sin(a), zc)
        loc = pawn.get_actor_location(); aim = (loc.x, loc.y, loc.z+25.)
        if stop_target is not None:
            t = ue(stop_target); aim = tuple(aim[c]+([t.x, t.y, t.z][c]-aim[c])*mix for c in range(3))
        room_camera(dt, E, aim, snap, 8.); return
    if cam[0] == 'room':
        snap = arm_mode('room'); E = cam[1:4]
        aim = head_ue()
        if stop_target is not None:
            t = ue(stop_target); aim = tuple(aim[c]+([t.x, t.y, t.z][c]-aim[c])*cam[4] for c in range(3))
        room_camera(dt, E, aim, snap); return
    if stop_target is not None:
        eye = (p[0], p[1], p[2]+1.6); q = stop_target
        top = STOPS[i].get('pitch', -5) if i in STOPS else -5
        yaw = heading(eye, q); pitch = max(-35, min(top, math.degrees(math.atan2(q[2]-eye[2], math.hypot(q[0]-eye[0], q[1]-eye[1])))))
        snap = arm_mode('follow')
        yaw, pitch = smart(yaw, level_for(pitch), True, 45)
        set_camera(dt, yaw, pitch, 70, snap); return
    if cam[0] == 'orbit':
        snap = arm_mode('orbit')
        yaw, pitch = smart(heading((cam[1], cam[2]), p)+cam[3], cam[4], False, 45)
        set_camera(dt, yaw, pitch, 200, snap); return
    snap = arm_mode('follow')
    ahead = PTS[min(i+12, N-1)]
    want = heading(p, ahead) if math.hypot(ahead[0]-p[0], ahead[1]-p[1]) > .6 else heading(PTS[max(0, i-1)], PTS[min(i+1, N-1)])
    yaw, pitch = smart(want, level_for(cam[1]), True, 60)
    set_camera(dt, yaw, pitch, 110, snap)


def step(dt):
    dt = 1/60.; S['f'] += 1
    if S['mode'] == 'settle':
        if S['f'] == 1:
            p = PTS[0]; q = PTS[min(8, N-1)]; S['yaw'] = heading(p, q)
            live.teleport(L.ground_at(ue((p[0], p[1], p[2]+1.5))), -S['yaw'])
            arm_mode('follow')
        set_camera(dt, S['yaw'], -8, 90); live.drive(0, 0)
        if S['f'] >= SETTLE: S['mode'] = 'go'; S['since'] = 0
        return
    if S['mode'] == 'stop':
        s = STOPS[S['stop']]; S['t'] += dt; live.drive(0, 0)
        p = feet(); target = look_at(s, S['t'], p)
        turn_to(dt, heading(p, target))
        camera_for(S['stop'], dt, target)
        record()
        if S['t'] >= s['seconds']:
            S['stops_done'].add(S['stop']); S['mode'] = 'go'; S['since'] = 0
        return
    i0 = S['i']
    stop = next_stop()                   # taken before progress, so a jump of the index cannot pass a stop by
    progress(stop); i = S['i']
    if i >= N-1:
        live.drive(0, 0); finish(); return
    p = feet()
    if stop is not None:
        ds = math.hypot(PTS[stop][0]-p[0], PTS[stop][1]-p[1])
        if i >= stop or (stop-i <= 4 and ds < .5) or (S['since'] > 40 and stop-i <= 10):
            S['mode'] = 'stop'; S['stop'] = stop; S['t'] = 0.; S['i'] = max(i, stop); live.drive(0, 0)
            S['marks'].append({'stop': stop, 'frame': S['film'], 'sim': S['f'], 'feet': [round(v, 2) for v in p]}); record(); return
    gait, mag = ROUTE['gait'][i], ROUTE['mag'][i]
    j = min(i+4, N-1) if stop is None else min(i+4, stop)
    target = PTS[j]
    if stop is not None and stop-i < 6:
        mag *= max(.6, min(1., math.hypot(target[0]-p[0], target[1]-p[1])/.9))
    camera_for(i, dt)
    drive_towards(target, gait, mag)
    record()
    S['since'] = 0 if S['i'] > i0 else S['since']+1
    if S['since'] > 90:                  # no progress for 1.5 s: note it and move Cairo on (never past a stop)
        k = min(N-1, S['i']+6, stop if stop is not None else N-1); q = PTS[k]
        S['stuck'].append({'frame': S['film'], 'sim': S['f'], 'index': S['i'], 'feet': [round(v, 2) for v in p]})
        place(q, heading(q, PTS[min(k+2, N-1)])); S['i'] = k; S['since'] = 0
    if S['f'] % 60 == 0:
        open(os.path.join(OUT, 'progress.txt'), 'w').write('%d/%d points, %d stuck' % (S['i'], N, len(S['stuck'])))


def run(dt):
    try: step(dt)
    except Exception as e:
        open(os.path.join(OUT, 'error.txt'), 'w').write(repr(e)); finish()
        raise


def finish():
    live.stop('treehouse_walk'); live.drive(0, 0); arm_mode('follow')
    L.film_hud(False); L.fixed_step(0)
    n = L.audio_log('stop', os.path.join(OUT, 'audio.json'))
    open(os.path.join(OUT, 'camera.csv'), 'w').write('frame,x,y,z,pitch,yaw\n'+'\n'.join(S['rows'])+'\n')
    json.dump(S['stuck'], open(os.path.join(OUT, 'stuck.json'), 'w'), indent=1)
    if not FILM: json.dump(S['camlog'], open(os.path.join(OUT, 'camlog.json'), 'w'))
    json.dump({'film_frames': S['film'], 'sim_frames': S['f'], 'fps': 60, 'sounds': n, 'stuck': len(S['stuck']), 'filmed': FILM,
               'stops': S['marks']},
              open(os.path.join(OUT, 'done.json'), 'w'), indent=1)


for f in os.listdir(OUT):
    if f.endswith('.jpg') or f in ('done.json', 'audio.json', 'stuck.json', 'camlog.json', 'error.txt'): os.remove(os.path.join(OUT, f))
L.film_hud(True); L.fixed_step(60); L.audio_log('start')
live.behave('treehouse_walk', run)
print('TREEHOUSE WALK started', TAKE, 'film' if FILM else 'rehearsal', N, 'points')
