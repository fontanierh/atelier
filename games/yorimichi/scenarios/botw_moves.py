"""Move set checks: the player's merged move set (UBotwMoveSet; Link, or Cairo with it) driven through the live bridge as
a player would drive it.

    atelier play yorimichi -- -rider=Link -nofox -nosound -ForceDPCVars=r.Streaming.PoolSize=250 -RenderOffscreen -ForceRes
    atelier live py "TAKE='take1'" && atelier live py - < games/yorimichi/scenarios/botw_moves.py
    ... wait for build/yorimichi/botw/moves/<take>/done.json

Under the 10 GiB memory guard the game also renders at 720p and half scale (r.SetRes 1280x720w, r.ScreenPercentage 50)
with r.Streaming.DropMips 2, set through the live bridge before the scenario; it then peaks at about 9.3 GiB.

By the forest lake's cabin: a standing and a running jump, the sprint, the double jump (once per jump, the glider on the
next press; none in the legacy BOTW set, whose first press opens it), the side hop and backflip, the sword's draw, the four-cut combo, the charged spin, the guard and its parry
with the sword (no shield) and with the shield (the "Shield" setting switched on, then put back), a strike on a
Bokoblin, the sheathe and the guard button drawing the sword; the paraglider,
opened at the top of a throw over the lake, steered, braked, closed and opened again; the swim it lands in, the swim
dash and the swim back to the shore; the climb up a steep bank onto its top, and up the cabin's wall to its eave; the
plunge and the hard landing.
Each check reads UBotwMoveSet's state (YorimichiLive::MoveState) every frame at a fixed 60 fps step; done.json lists
every check with what it measured, log.json the per-frame state, and the key moments are saved as stills. Optional
globals: ONLY, the checks to run; SHOTS, False for no stills; RIDER, the character switched to when the player has no
move set (Link, or CairoBotw: Cairo with the move set, -rider=CairoBotw).
"""
import json, math, os
import unreal

L = live.L
TAKE = globals().get('TAKE', 'take1')
SHOTS = globals().get('SHOTS', True)
RIDER = globals().get('RIDER') or 'Link'
OUT = os.path.join(os.environ.get('ATELIER_BUILD_ROOT') or os.path.join(live.ROOT, 'build'), 'yorimichi/botw/moves', TAKE)
os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT):
    os.remove(os.path.join(OUT, f))
pc = unreal.GameplayStatics.get_player_controller(L.game_world(), 0)
LAKE = (-90., 235., 75.)      # world.json forest_lake: its centre (island metres) and water height
SHORE = (-54., 223.)          # the lake's safe shore, beside the cabin
CABIN = (-56., 215.)
RUN = ((-30., 215.), (-35., 206.34))   # 30 m of clear, nearly flat ground south-east of the cabin, and its heading
OFFSHORE = (-72., 229.)       # open water, 19 m out from the shore
BANK = ((-29.5, 215.), (-36., 215.))   # the foot of a steep bank (55-58 degrees, 4.5 m) with a flat top, and its heading


def ue(x, y, z=0.):
    """Island metres (x east, y north) to Unreal cm."""
    return unreal.Vector(x * 100., -y * 100., z * 100.)


def yaw_to(a, b):
    return math.degrees(math.atan2(-(b[1] - a[1]), b[0] - a[0]))


def state():
    return json.loads(L.move_state())


def z():
    return L.player_transform().translation.z


st = {'checks': [], 'log': [], 'check': None, 'shots': []}


def check(name, ok, **seen):
    st['checks'].append(dict(check=st['check'], name=name, ok=bool(ok), **seen))
    unreal.log(f"BOTW MOVES {'PASS' if ok else 'FAIL'} {st['check']}: {name} {json.dumps(seen)}")


def shot(name):
    if SHOTS:
        path = os.path.join(OUT, f'{len(st["shots"]):02d}_{name}.png')
        L.screenshot(path); st['shots'].append(os.path.basename(path))


def place(at, toward, height=None):
    """Stand the player at `at` facing `toward`, the camera behind; the ground under it unless `height` (m) is given."""
    yaw = yaw_to(at, toward)
    live.drive(0)
    L.teleport_player(ue(at[0], at[1], height if height is not None else LAKE[2]), yaw)
    pc.set_control_rotation(unreal.Rotator(0, -12, yaw))


def wait(seconds):
    t = 0.
    while t < seconds:
        t += (yield)


def until(test, timeout):
    """Frames until test(state) holds: (state, seconds), or (None, seconds) at the timeout."""
    t = 0.
    while t < timeout:
        s = state()
        if test(s):
            return s, t
        t += (yield)
    return None, t


def watch(seconds, each=None):
    """The states over `seconds` (each passed to `each` as it comes)."""
    seen, t = [], 0.
    while t < seconds:
        s = state(); s['t'] = t; s['z'] = z(); seen.append(s)
        if each:
            each(s)
        t += (yield)
    return seen


def actions(seen):
    out = []
    for s in seen:
        if not out or out[-1] != s['action']:
            out.append(s['action'])
    return out


def grounded(s):
    return s.get('mode') == 'ground' and not s.get('driving')


def settled(s):
    """Standing still on the ground, any landing over."""
    return grounded(s) and s.get('action') == 'None' and s.get('speed', 0.) < 5.


# ------------------------------------------------------------------------------------------------------------ checks

def on_foot():
    place(*RUN)
    s, _ = yield from until(settled, 6.)
    check('has a move set on the ground', s is not None, mode=s and s['mode'])
    yield from wait(1.)
    start = z(); stamina = state()['stamina']
    live.press('jump'); live.press('jump_release')
    seen = yield from watch(1.6)
    rise = max(s['z'] for s in seen) - start
    check('standing jump', any(s['mode'] == 'air' for s in seen) and 30. < rise < 150. and seen[-1]['mode'] == 'ground',
          rise=round(rise, 1), actions=actions(seen))
    live.drive(1., 0., 'run')
    yield from wait(1.2)
    live.press('jump'); live.press('jump_release')
    seen = yield from watch(1.6)
    check('running jump', any(a in ('RunJumpL', 'RunJumpR') for a in actions(seen)) and seen[-1]['mode'] == 'ground',
          actions=actions(seen))
    live.drive(1., 0., 'sprint')
    seen = yield from watch(2.)
    live.drive(0)
    top = max(s['speed'] for s in seen)
    check('sprint', top > 550. * st['size'] and seen[-1]['stamina'] < stamina, top=round(top), stamina=round(seen[-1]['stamina'], 3))
    yield from wait(1.)


def double_jump():
    place(*RUN)
    yield from until(settled, 6.)
    start, before = z(), state()['double_jumps']
    live.press('jump'); live.press('jump_release')
    seen = yield from watch(.35)
    live.press('jump'); live.press('jump_release')
    seen += yield from watch(.35)
    check('double jump: a second launch in the air, no glider', state()['double_jumps'] == before + 1 and
          max(s['vz'] for s in seen[20:]) > 500. and not any(s['glider'] for s in seen),
          vz=round(max(s['vz'] for s in seen[20:])), actions=actions(seen))
    check('double jump plays the somersault', any(a in ('DoubleJump', 'DoubleJumpTuck') for a in actions(seen)), actions=actions(seen))
    shot('double_jump')
    live.press('jump'); live.press('jump_release')
    s, _ = yield from until(lambda s: s['mode'] == 'glide', .8)
    check('the next press opens the paraglider', s is not None)
    if s:
        live.press('jump'); live.press('jump_release')
    seen = yield from watch(.1)
    s, _ = yield from until(grounded, 5.)
    rise = max(x['z'] for x in seen) - start
    check('back on the ground the double jump is ready again', s is not None and not state()['air_jump_used'],
          rise=round(rise, 1))
    yield from wait(1.)
    # The legacy BOTW set ("Move set" setting): no double jump, the first press in the air opens the paraglider.
    L.set_preference('moveset', 2.)
    yield from until(settled, 4.)
    before = state()['double_jumps']
    live.press('jump'); live.press('jump_release')
    yield from wait(.45)
    live.press('jump'); live.press('jump_release')
    s, _ = yield from until(lambda s: s['mode'] == 'glide', .8)
    check('legacy BOTW set: no double jump, the glider instead', s is not None and state()['double_jumps'] == before and state()['legacy'],
          double_jumps=state()['double_jumps'] - before)
    if s:
        live.press('jump'); live.press('jump_release')
    L.set_preference('moveset', st['moveset'])
    yield from until(grounded, 5.)
    yield from wait(1.)


def hops():
    place(*RUN)
    yield from until(settled, 6.)
    live.press('guard')
    yield from wait(.3)
    s = state()
    check('lock-on with the guard button', s['locked'], locked=s['locked'])
    live.drive(0., 1., 'run'); live.press('dodge')
    seen = yield from watch(1.2)
    check('side hop', 'HopR' in actions(seen) and seen[-1]['mode'] == 'ground', actions=actions(seen))
    live.drive(-1., 0., 'run'); live.press('dodge')
    seen = yield from watch(1.6)
    check('backflip', 'BackFlip' in actions(seen) and seen[-1]['mode'] == 'ground', actions=actions(seen))
    live.drive(0); live.press('guard_release')
    yield from wait(.6)


def sword():
    place(*RUN)
    yield from until(settled, 6.)
    live.press('weapon')
    seen = yield from watch(1.2)
    check('draw the sword', 'DrawSword' in actions(seen) and seen[-1]['armed'], actions=actions(seen))
    shot('armed')
    seen = []
    for _ in range(4):
        live.press('attack'); live.press('attack_release')
        seen += yield from watch(.4)
    seen += yield from watch(1.5)
    check('four-cut combo', all(c in actions(seen) for c in ('CutS1', 'CutS2', 'CutS3', 'CutSF')), actions=actions(seen))
    live.press('attack')
    seen = yield from watch(1.4)
    charged = actions(seen)
    if any(s['charging'] for s in seen[-5:]):
        shot('charge')
    live.press('attack_release')
    seen = yield from watch(1.8)
    check('charged spin', 'ChargeStart' in charged and 'ChargeSpin' in actions(seen), held=charged, released=actions(seen))
    L.set_preference('shield', 0.)
    live.press('guard')
    seen = yield from watch(.6)
    check('sword guard (no shield)', seen[-1]['sword_guard'] and seen[-1]['sword_guard_carry'] > .5 and not seen[-1]['shield'],
          sword_guard_carry=round(seen[-1]['sword_guard_carry'], 2))
    shot('sword_guard')
    live.press('jump'); live.press('jump_release')
    seen = yield from watch(.8)
    check('sword parry (jump while guarding, no shield)', 'SwordParry' in actions(seen), actions=actions(seen))
    live.press('guard_release')
    yield from wait(.5)
    L.set_preference('shield', 1.)
    live.press('guard')
    seen = yield from watch(.6)
    check('shield guard', seen[-1]['guarding'] and seen[-1]['shield'] and seen[-1]['guard_carry'] > .5,
          guard_carry=round(seen[-1]['guard_carry'], 2))
    shot('guard')
    live.press('jump'); live.press('jump_release')
    seen = yield from watch(.8)
    check('parry (jump while guarding, shield)', 'Parry' in actions(seen), actions=actions(seen))
    live.press('guard_release')
    L.set_preference('shield', 1. if st['shield'] else 0.)
    yield from wait(.5)
    # A Bokoblin standing still a step ahead takes the combo.
    here = L.player_transform().translation
    yaw = math.radians(L.player_transform().rotation.rotator().yaw)
    target = L.ground_at(unreal.Vector(here.x + math.cos(yaw) * 130., here.y + math.sin(yaw) * 130., here.z))
    L.botw_spawn('Bokoblin', target, math.degrees(yaw) + 180., 'idle')
    yield from wait(.5)
    before = state()['hits']
    for _ in range(4):
        live.press('attack'); live.press('attack_release')
        yield from wait(.45)
    yield from wait(1.)
    check('blade strikes a creature', state()['hits'] > before, hits=state()['hits'] - before)
    L.botw_clear()
    live.press('weapon')
    seen = yield from watch(1.2)
    check('sheathe', 'SheatheSword' in actions(seen) and not seen[-1]['armed'], actions=actions(seen))
    live.press('guard')
    seen = yield from watch(1.4)
    check('the guard button draws the sword', 'DrawSword' in actions(seen) and seen[-1]['armed'] and seen[-1]['guarding'],
          actions=actions(seen))
    live.press('guard_release'); live.press('weapon')
    yield from wait(1.2)


def glide():
    place(SHORE, LAKE)
    yield from until(settled, 6.)
    yield from wait(.5)
    stamina = state()['stamina']
    L.launch(unreal.Vector(0, 0, 1700))
    yield from until(lambda s: s['vz'] > 500., 1.)      # the launch takes effect on the next movement tick
    yield from until(lambda s: s['vz'] < 50., 3.)
    start = L.player_transform().translation
    live.press('jump'); live.press('jump_release')
    s, t = yield from until(lambda s: s['mode'] == 'glide' and s['glider'], .3)
    if s is None:   # the merged set's first press in the air is the double jump: the next, at its top, opens it
        yield from until(lambda s: s['vz'] < 50., 1.5)
        live.press('jump'); live.press('jump_release')
        s, t = yield from until(lambda s: s['mode'] == 'glide' and s['glider'], .6)
    check('open the paraglider at the top of a throw', s is not None, after=round(t, 2))
    shot('glide_open')
    live.drive(1., 0., 'run')
    seen = yield from watch(2.5)
    steady = seen[len(seen) // 2:]
    sink = sum(s['vz'] for s in steady) / len(steady)
    speed = sum(s['speed'] for s in steady) / len(steady)
    check('glide forward', -260. < sink < -60. and speed > 300. and all(s['mode'] == 'glide' for s in seen),
          sink=round(sink), speed=round(speed), actions=actions(seen))
    check('gliding uses stamina', seen[-1]['stamina'] < stamina, stamina=round(seen[-1]['stamina'], 3))
    shot('glide')
    yaw0 = seen[-1]['glide_yaw']
    live.drive(.3, 1., 'run')
    seen = yield from watch(1.2)
    turned = (seen[-1]['glide_yaw'] - yaw0 + 180.) % 360. - 180.
    check('steer right', turned > 30., turned=round(turned, 1), actions=actions(seen))
    # The stick is read from the camera: line the camera up behind the glider, as a player would, before pulling back.
    pc.set_control_rotation(unreal.Rotator(0, -12, seen[-1]['glide_yaw']))
    live.drive(-1., 0., 'run')
    seen = yield from watch(1.2)
    check('brake', seen[-1]['speed'] < speed - 100., speed=round(seen[-1]['speed']))
    live.drive(1., 0., 'run')
    yield from wait(.5)
    live.press('jump'); live.press('jump_release')
    s, _ = yield from until(lambda s: s['mode'] == 'air', .4)
    check('close the paraglider', s is not None and not s['glider'])
    yield from wait(.35)
    live.press('jump'); live.press('jump_release')
    s, _ = yield from until(lambda s: s['mode'] == 'glide', .4)
    check('open it again in the air', s is not None)
    s, t = yield from until(lambda s: s['mode'] in ('swim', 'ground', 'climb'), 30.)
    here = L.player_transform().translation
    flown = math.hypot(here.x - start.x, here.y - start.y) / 100.
    check('glide down to the lake', s is not None and s['mode'] == 'swim' and not s['glider'], flown_m=round(flown, 1),
          mode=s and s['mode'], seconds=round(t, 1))
    live.drive(0)


def swim():
    s = state()
    if s['mode'] != 'swim':
        place(OFFSHORE, LAKE)
        s, _ = yield from until(lambda s: s['mode'] == 'swim', 3.)
    check('swim', s is not None and s['mode'] == 'swim')
    yaw = L.player_transform().rotation.rotator().yaw
    pc.set_control_rotation(unreal.Rotator(0, -12, yaw))
    live.drive(1., 0., 'run')
    seen = yield from watch(2.)
    cruise = seen[-1]['speed']
    # The capsule's feet ride the surface; the swimming body hangs below them.
    check('swim forward at the surface', cruise > 100. * st['size'] and all(s['mode'] == 'swim' and abs(s['feet'] - s['water']) < 30. for s in seen[30:]),
          speed=round(cruise), feet_from_surface=round(seen[-1]['feet'] - seen[-1]['water'], 1), actions=actions(seen))
    shot('swim')
    live.press('dash')
    seen = yield from watch(1.)
    check('swim dash', 'SwimDash' in actions(seen) and max(s['speed'] for s in seen) > cruise + 60.,
          top=round(max(s['speed'] for s in seen)), actions=actions(seen))
    here = L.player_transform().translation
    home = yaw_to((here.x / 100., -here.y / 100.), SHORE)
    pc.set_control_rotation(unreal.Rotator(0, -12, home))
    s, t = yield from until(lambda s: s['mode'] == 'ground' or s['action'] in ('SwimOut', 'SwimOutHigh', 'ClimbGrab'), 40.)
    check('swim back to the shore', s is not None, action=s and s['action'], seconds=round(t, 1))
    yield from until(grounded, 4.)
    live.drive(0)


def climb():
    # The steep bank west of the trail: run into it, climb it and stand up on its flat top.
    place(*BANK)
    yield from until(settled, 6.)
    live.drive(1., 0., 'run')
    s, t = yield from until(lambda s: s['mode'] == 'climb', 6.)
    check('grab a steep bank by running into it', s is not None, after=round(t, 2), wall=s and s.get('wall'))
    if s is not None:
        low = z(); stamina = state()['stamina']
        shot('climb')
        seen = yield from watch(20., lambda s: s['mode'] == 'ground' and live.drive(0))   # a smaller body climbs slower
        gain = max(s['z'] for s in seen) - low
        # Standing on the top, not back at the foot after a fall (both end on the ground).
        top = seen[-1]['z'] - low
        check('climb up and over the top', gain > 150. and top > 150. and seen[-1]['mode'] == 'ground', gain=round(gain),
              top=round(top), actions=actions(seen)[-6:], mode=seen[-1]['mode'])
        check('climbing uses stamina', min(s['stamina'] for s in seen) < stamina)
    live.drive(0)
    yield from wait(.5)
    # The cabin's wall, its window sill standing out of it: grab it, and hold on under the roof's eave.
    place((-50.3, 220.7), CABIN)
    yield from until(settled, 6.)
    live.drive(1., 0., 'run')
    s, t = yield from until(lambda s: s['mode'] == 'climb', 6.)
    check('grab a wall by running into it', s is not None, after=round(t, 2))
    if s is not None:
        seen = yield from watch(7.)
        check('hold on under the eave', seen[-1]['mode'] == 'climb' and seen[-1]['action'] == 'ClimbWait',
              actions=actions(seen))
        # Let go: jump with the stick pulled back.
        live.drive(-1., 0., 'run'); live.press('jump'); live.press('jump_release')
        yield from wait(.3)
    live.drive(0)
    yield from until(settled, 6.)


def plunge():
    place(*RUN)
    yield from until(settled, 6.)
    health = state()['health']
    L.launch(unreal.Vector(0, 0, 1500))
    yield from until(lambda s: s['vz'] < 0., 3.)
    live.press('attack'); live.press('attack_release')
    seen = yield from watch(2.5)
    check('plunge attack from height', 'Plunge' in actions(seen) and min(s['vz'] for s in seen) <= -1150. and
          'PlungeLand' in actions(seen) and seen[-1]['health'] >= health, actions=actions(seen),
          vz=round(min(s['vz'] for s in seen)))
    yield from until(grounded, 4.)
    yield from wait(.5)
    L.launch(unreal.Vector(0, 0, 1250))
    seen = yield from watch(3.)
    check('hard landing from a high fall', 'HardLand' in actions(seen), actions=actions(seen))
    yield from until(grounded, 4.)
    if state()['armed']:
        live.press('weapon'); yield from wait(1.)


CHECKS = [('on_foot', on_foot), ('double_jump', double_jump), ('hops', hops), ('sword', sword), ('glide', glide), ('swim', swim), ('climb', climb),
          ('plunge', plunge)]
CHECKS = [c for c in CHECKS if c[0] in (globals().get('ONLY') or [c[0] for c in CHECKS])]


def steps():
    if state() == {}:
        L.switch_character(RIDER)
        yield from wait(2.)
    st['size'] = state().get('scale', .8) / .8     # the speeds checked are Link's (scale .8); a smaller body is slower
    st['shield'] = bool(state().get('shield'))
    st['moveset'] = 2. if state().get('legacy') else 0.
    for name, fn in CHECKS:
        st['check'] = name
        yield from fn()


def run(dt):
    # The world steps a fixed 1/60 s a frame however fast frames come: count its time, not the frame's (Slate's).
    dt = unreal.GameplayStatics.get_world_delta_seconds(L.game_world())
    if st.get('gen') is None:
        st['gen'] = steps(); next(st['gen'])
        return
    s = state()
    st['log'].append([st['check'], s.get('mode'), s.get('action'), round(z()), round(s.get('speed', 0)), round(s.get('vz', 0))])
    try:
        st['gen'].send(dt)
    except StopIteration:
        finish()


def finish():
    live.stop('botw_moves'); live.drive(0); L.fixed_step(0)
    failed = [c for c in st['checks'] if not c['ok']]
    json.dump(st['log'], open(os.path.join(OUT, 'log.json'), 'w'))
    json.dump({'passed': not failed, 'checks': st['checks'], 'failed': [f"{c['check']}: {c['name']}" for c in failed],
               'shots': st['shots']}, open(os.path.join(OUT, 'done.json'), 'w'), indent=1)
    unreal.log(f'BOTW MOVES COMPLETE {len(st["checks"]) - len(failed)}/{len(st["checks"])}')


L.fixed_step(60)
live.behave('botw_moves', run)
print('BOTW MOVES started', OUT, [c[0] for c in CHECKS])
