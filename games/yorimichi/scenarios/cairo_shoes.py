"""Cairo's shoes on the merged move set (CairoAdventure: the reference rig's clips retargeted onto Cairo): idle and walk on flat concrete and on
grass, each foot's height over the ground measured every frame, and sole close-ups at floor level.

    atelier play yorimichi -- -rider=CairoAdventure -nofox -nosound -RenderOffscreen -ForceRes
    atelier live py "TAKE='take1'" && atelier live py - < games/yorimichi/scenarios/cairo_shoes.py
    ... wait for build/yorimichi/cairo/shoes/<take>/done.json

Two places: the Sunset Pier deck between long_ledge and flatbar_red (skatepark x -24 to -16, y 35: bare concrete), and
grass by the forest lake's cabin, from (-51, 235) north to (-51, 241) (an 8 m corridor measured level to 0.6 cm in the
game; GRASS=((x, y), (x, y)) in island metres sets another). Should that grass ever stop being level, the levellest 6 m
line by GroundAt within 20 m of it, above the lake's surface, is used. A place whose ground spans more than 10 cm along
the walk, or with no ground under any point of it, is reported as not level and its foot checks are skipped. At each, Cairo stands 3 s, walks 6 m across
the camera's view and stands again; the walk is checked to be the merged move set's (ground mode,
walking speed). Stills: a wide side-on view standing; close-ups of each shoe from its own
side, the camera 3 cm over the floor and 70 cm away, standing before and after the walk; and every 0.3 s of the walk,
a camera 1.2 m to his left at the same height tracking his feet. The close-ups are the evidence that the shoe mesh meets
the floor: the joint heights below are only a proxy for the sole.

The proxy is the toe joint's height over the ground (GroundAt straight under it, which ignores the player): Cairo's own
rest pose puts it at about 2.8-3.1 cm (cairo/export.json), inside the shoe, which is authored with its sole on the
floor. Before the level-foot retarget (adventure/retarget.py) the reference rig's 27-degree toe-down rest tipped it to 1.46 cm, the shoe into the
ground. Checks per place: standing, both toes within 1.5-5 cm; walking, each foot's planted height (its lowest 15% of
frames) within 1.5-5 cm, and no frame under 0.5 cm. done.json lists every check with what it measured, log.json the per-frame heights, and the stills
are saved beside them. Optional globals: SHOTS (False for no stills), ONLY (place names: concrete, grass), RIDER
(CairoAdventure by default). An existing take is refused, never overwritten; an error mid-run still writes done.json (failed,
with the error) and gives the camera and controls back.
"""
import json, math, os
import unreal

L = live.L
TAKE = globals().get('TAKE', 'take1')
SHOTS = globals().get('SHOTS', True)
RIDER = globals().get('RIDER') or 'CairoAdventure'
OUT = os.path.join(os.environ.get('ATELIER_BUILD_ROOT') or os.path.join(live.ROOT, 'build'), 'yorimichi/cairo/shoes', TAKE)
if os.path.isdir(OUT) and os.listdir(OUT):
    raise RuntimeError(f'take {TAKE} already exists at {OUT}: choose a new TAKE')
os.makedirs(OUT, exist_ok=True)
pc = unreal.GameplayStatics.get_player_controller(L.game_world(), 0)
MV = unreal.MegaParkValidation   # ReviewCamera: a free camera as the view target; RestorePlayerCamera
PIER = (-110., -234., 1.8)    # skatepark/park.json origin (island metres): skatepark x, y are offsets from it
# Name, start, toward, and a height near the ground there (m): the player is placed on the ground under it, traced from
# 20 m above.
PLACES = [('concrete', (PIER[0] - 24., PIER[1] + 35.), (PIER[0] - 16., PIER[1] + 35.), PIER[2] + 1.),
          ('grass', *(globals().get('GRASS') or ((-51., 235.), (-51., 241.))), 76.)]
LAKE_Z = 75.                                 # the forest lake's surface (m, world.json)
LEVEL = 10.                                  # cm: the most the ground may rise or fall along a walk
ONLY = globals().get('ONLY') or [p[0] for p in PLACES]
if isinstance(ONLY, str) or not set(ONLY) <= {p[0] for p in PLACES}:
    raise ValueError(f'ONLY must list places from {[p[0] for p in PLACES]}, got {ONLY!r}')
PLACES = [p for p in PLACES if p[0] in ONLY]
BONES = {'foot_L': 'ankle L', 'foot_R': 'ankle R', 'toe_L': 'toe L', 'toe_R': 'toe R'}
LOW, HIGH, FLOOR = 1.5, 5., .5    # cm: a planted toe joint below LOW is a shoe in the ground, above HIGH a floating one


def ue(x, y, z=0.):
    """Island metres (x east, y north) to Unreal cm."""
    return unreal.Vector(x * 100., -y * 100., z * 100.)


def yaw_to(a, b):
    return math.degrees(math.atan2(-(b[1] - a[1]), b[0] - a[0]))


def state():
    return json.loads(L.move_state())


def mesh():
    """The player's skeletal mesh that carries Cairo's foot bones."""
    for c in L.player().get_components_by_class(unreal.SkeletalMeshComponent):
        if all(c.get_bone_index(b) >= 0 for b in BONES):
            return c
    return None


def heights():
    """Each foot bone's height over the ground straight under it (cm)."""
    m = st['mesh']
    out = {}
    for b in BONES:
        p = m.get_socket_location(b)
        out[b] = round(p.z - L.ground_at(unreal.Vector(p.x, p.y, p.z)).z, 2)
    # GroundAt traces from 20 m up: anything over the feet (a branch) reads as the foot deep underground.
    out['blocked'] = any(out[b] < -30. for b in BONES)
    return out


st = {'checks': [], 'log': [], 'place': None, 'shots': [], 'camera': None, 'track': None}


def check(name, ok, **seen):
    st['checks'].append(dict(place=st['place'], name=name, ok=bool(ok), **seen))
    unreal.log(f"CAIRO SHOES {'PASS' if ok else 'FAIL'} {st['place']}: {name} {json.dumps(seen)}")


def shot(name):
    if SHOTS:
        path = os.path.join(OUT, f'{len(st["shots"]):02d}_{st["place"]}_{name}.png')
        L.screenshot(path); st['shots'].append(os.path.basename(path))


def wait(seconds):
    t = 0.
    while t < seconds:
        t += (yield)


def watch(seconds, phase):
    seen, t = [], 0.
    while t < seconds:
        s = state()
        h = heights(); h['t'] = round(t, 3); h['phase'] = phase
        h.update(action=s.get('action'), mode=s.get('mode'), speed=round(s.get('speed', 0.), 1))
        seen.append(h); st['log'].append(dict(place=st['place'], **h))
        t += (yield)
    return seen


def planted(seen, bone):
    """A foot's planted height while walking: the mean of its lowest 15% of frames."""
    low = sorted(h[bone] for h in seen)[:max(1, len(seen) * 15 // 100)]
    return round(sum(low) / len(low), 2)


def side(heading, sign):
    """The unit vector to his right (sign 1) or left (-1) of `heading` (UE yaw, degrees)."""
    r = math.radians(heading + 90. * sign)
    return math.cos(r), math.sin(r)


def low_camera(at, heading, sign, dist, fov):
    """A camera `dist` cm to one side of `at` (x, y), 3 cm over the floor there, aimed level at the soles."""
    dx, dy = side(heading, sign)
    floor = L.ground_at(unreal.Vector(at[0], at[1], L.player_transform().translation.z)).z
    MV.review_camera(unreal.Vector(at[0] + dx * dist, at[1] + dy * dist, floor + 3.), unreal.Vector(at[0], at[1], floor + 3.), fov)


def soles(heading, when):
    """A close-up of each shoe from its own side."""
    for b, sign in (('L', -1), ('R', 1)):
        f, t = st['mesh'].get_socket_location(f'foot_{b}'), st['mesh'].get_socket_location(f'toe_{b}')
        low_camera(((f.x + t.x) / 2, (f.y + t.y) / 2), heading, sign, 70., 30.)
        yield from wait(.1)
        shot(f'sole_{b}_{when}')
        yield from wait(.1)
    MV.restore_player_camera()


def along(start, toward, height, n=7):
    """Ground heights (cm) at n points from start to toward; None where nothing lies under a point (GroundAt then
    answers the height it was asked from, which would read as level ground)."""
    out = []
    for k in range(n):
        at = ue(start[0] + (toward[0] - start[0]) * k / (n - 1), start[1] + (toward[1] - start[1]) * k / (n - 1), height)
        z = L.ground_at(at).z
        out.append(None if abs(z - at.z) < 1e-3 else z)
    return out


def spread(ground):
    """How far the ground rises or falls along a walk (cm); infinite when any point has no ground."""
    return math.inf if None in ground else max(ground) - min(ground)


def level_line(near, height, reach=20., step=5., length=6.):
    """The levellest walk of `length` m within `reach` m of `near`, its ground above the lake's surface and spanning
    under LEVEL: (start, toward), or None. The stills show what it stands on."""
    best = None
    for dx in range(-int(reach), int(reach) + 1, int(step)):
        for dy in range(-int(reach), int(reach) + 1, int(step)):
            start = (near[0] + dx, near[1] + dy)
            for a in range(0, 360, 45):
                toward = (start[0] + length * math.cos(math.radians(a)), start[1] + length * math.sin(math.radians(a)))
                g = along(start, toward, height)
                if spread(g) >= LEVEL or min(g) < (LAKE_Z + .2) * 100.:
                    continue
                if best is None or spread(g) < best[0]:
                    best = (spread(g), start, toward)
    return best and best[1:]


def visit(name, start, toward, height):
    st['place'] = name
    ground = along(start, toward, height)
    if name == 'grass' and spread(ground) > LEVEL:
        found = level_line(start, height)
        check('a level place was found', found is not None, near=list(start), span_there_cm=round(spread(ground), 1),
              no_ground_points=ground.count(None))
        if found is None:
            return
        start, toward = found
        ground = along(start, toward, height)
    span = spread(ground)                 # gated unrounded: 10.04 cm is not level; no ground is not level either
    check('the walk is level', span <= LEVEL, ground_span_cm=round(span, 2) if span < math.inf else None,
          no_ground_points=ground.count(None), start=[round(v, 2) for v in start], toward=[round(v, 2) for v in toward])
    if span > LEVEL:
        return
    heading = yaw_to(start, toward)
    st['camera'] = unreal.Rotator(0, -4, heading - 90.)    # pitch -4, yaw 90 degrees left of his heading: side-on
    live.drive(0)
    L.teleport_player(ue(*start, height), heading)
    yield from wait(2.5)
    still = yield from watch(3., 'idle')
    shot('idle')
    yield from soles(heading, 'standing')
    toes = {b: round(sum(h[b] for h in still) / len(still), 2) for b in BONES}
    check('standing: toe joints at rest height (proxy)', all(LOW <= toes[b] <= HIGH for b in ('toe_L', 'toe_R')), heights=toes)
    live.drive(0., 1., 'walk')     # the stick's frame is side-on, so camera-right is his heading
    st['track'] = heading
    walk = []
    for k in range(13):
        walk += yield from watch(.3, 'walk')
        if k >= 2:
            shot(f'walk_{k:02d}')
    st['track'] = None
    MV.restore_player_camera()
    live.drive(0)
    walk = walk[20:]               # past the start of the walk
    check('the ground under the feet was traced', not any(h['blocked'] for h in still + walk),
          blocked=sum(h['blocked'] for h in still + walk))
    walk = [h for h in walk if not h['blocked']] or walk
    plant = {b: planted(walk, b) for b in ('toe_L', 'toe_R', 'foot_L', 'foot_R')}
    lowest = {b: min(h[b] for h in walk) for b in ('toe_L', 'toe_R')}
    speeds = sorted(h['speed'] for h in walk)
    modes = sorted({h['mode'] for h in walk})
    check('walking on the merged move set', modes == ['ground'] and speeds[len(speeds) // 2] > 50.,
          modes=modes, median_speed=round(speeds[len(speeds) // 2]),
          actions=sorted({h['action'] for h in walk}))
    check('walking: planted toe joints at rest height (proxy)', all(LOW <= plant[b] <= HIGH for b in ('toe_L', 'toe_R')),
          planted=plant)
    check('walking: no toe joint near the floor (proxy)', all(v >= FLOOR for v in lowest.values()), lowest=lowest)
    yield from wait(1.)
    still = yield from watch(1.5, 'stop')
    shot('stopped')
    yield from soles(heading, 'stopped')
    toes = {b: round(sum(h[b] for h in still) / len(still), 2) for b in ('toe_L', 'toe_R')}
    check('stopped: toe joints at rest height (proxy)', all(LOW <= v <= HIGH for v in toes.values()), heights=toes)


def steps():
    playing = L.switch_character(RIDER)
    yield from wait(2.)
    st['mesh'] = mesh()
    check('the player is Cairo with the move set and his foot bones', playing == RIDER and state() != {} and st['mesh'] is not None,
          playing=playing)
    if st['mesh'] is None:
        return
    for place in PLACES:
        yield from visit(*place)


def run(dt):
    # The world steps a fixed 1/60 s a frame however fast frames come: count its time, not the frame's (Slate's).
    dt = unreal.GameplayStatics.get_world_delta_seconds(L.game_world())
    try:
        if st.get('gen') is None:
            st['gen'] = steps(); next(st['gen'])
            return
        if st['camera'] is not None:
            pc.set_control_rotation(st['camera'])
        if st['track'] is not None:
            p = L.player_transform().translation
            low_camera((p.x, p.y), st['track'], -1, 120., 40.)
        st['gen'].send(dt)
    except StopIteration:
        finish()
    except Exception as error:     # end the run with a report rather than leave the game driven and the camera held
        finish(f'{type(error).__name__}: {error}')


def finish(error=None):
    live.stop('cairo_shoes')
    st['camera'] = st['track'] = None
    live.drive(0); L.fixed_step(0); MV.restore_player_camera()
    failed = [c for c in st['checks'] if not c['ok']]
    json.dump(st['log'], open(os.path.join(OUT, 'log.json'), 'w'))
    json.dump({'passed': not failed and error is None and bool(st['checks']), 'error': error, 'checks': st['checks'],
               'failed': [f"{c['place']}: {c['name']}" for c in failed], 'shots': st['shots']},
              open(os.path.join(OUT, 'done.json'), 'w'), indent=1)
    if error:
        unreal.log_error(f'CAIRO SHOES ERROR {error}')
    unreal.log(f'CAIRO SHOES COMPLETE {len(st["checks"]) - len(failed)}/{len(st["checks"])}')


L.fixed_step(60)
live.behave('cairo_shoes', run)
print('CAIRO SHOES started', OUT, [p[0] for p in PLACES])
