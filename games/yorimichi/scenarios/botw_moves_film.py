"""Move set review film: every move of the player's merged move set (UBotwMoveSet: Link's moves with Cairo's double jump;
Link, or Cairo with it), shot by shot, close up.

    atelier play yorimichi -- -rider=Link -nofox -nosound -ForceDPCVars=r.Streaming.PoolSize=200 -RenderOffscreen -ForceRes
    atelier live py "TAKE='link1'; WHO='Link'" && atelier live py - < games/yorimichi/scenarios/botw_moves_film.py
    ... wait for build/yorimichi/botw/moves_film/<take>/done.json, then:
    python games/yorimichi/scenarios/botw_moves_film_cut.py build/yorimichi/botw/moves_film/review.mp4 <take>[:<sections>] ...

The game runs under the memory guard as for botw_moves.py (720p at half scale, set through the live bridge first).
Link at the lake also needs r.Streaming.PoolSize 120 and r.ViewDistanceScale 0.8 to stay under the guard's limit.

Sections, each a run of labelled shots: on foot (idle, walk, run, sprint, sprinting out of stamina, crouch, the jumps
and landings, the hard landing); the sprint alone, with its dust and speed lines; the double jump (standing, running,
turned right round by the stick, and into the paraglider); the equipment close up (the sword and shield carried on the back from the side and
from behind, crouched, and the paraglider in both hands from the front and the side); lock-on and the dodges (strafing, side hops, backflips); the sword (draw, combo,
charged spin, dash attack, jump attack, sneakstrike, plunge); the sword guard without the shield (raised, a blow
blocked, the sword parry) and the shield (guard, parry, the perfect dodge's flurry rush, sheathe) against a Bokoblin
that attacks, the "Shield" setting switched off and on for them; getting hit (from the front, behind and the side, fall damage, the
knockdown at no health); the paraglider (open, glide, steer, brake, close, reopen falling, land; stamina running out);
swimming (swim, tread, dash, climb out; sinking out of stamina); climbing (grab, the eight directions, climb jumps
until tired, a grab from the air, let go, kick off, over the top).

Runs at a fixed 60 fps step and saves every second step as a JPG (30 fps, real time). frames.json gives each saved
frame its section, label and the move set's state (action, mode, stamina, health), which botw_moves_film_cut.py draws
over the picture. audio.json is the game's audio log, each sound at the saved frame it starts on (-1 between shots),
which botw_moves_film_cut.py --audio mixes under the picture. A section that fails is logged in done.json and the film goes on with the next. Optional globals:
TAKE; WHO, the name on the captions ('Link' or 'Cairo'); ONLY, the sections to film; REHEARSE, no frames. The film
leaves the "Shield" setting as it found it.
Film each character in its own game (-rider=Link or -rider=CairoBotw).
"""
import json, math, os, traceback
import unreal

L = live.L
TAKE = globals().get('TAKE', 'take1')
REHEARSE = globals().get('REHEARSE', False)
WHO = globals().get('WHO')
OUT = os.path.join(os.environ.get('ATELIER_BUILD_ROOT') or os.path.join(live.ROOT, 'build'), 'yorimichi/botw/moves_film', TAKE)
os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT):
    if f.endswith('.jpg') or f.endswith('.json'):
        os.remove(os.path.join(OUT, f))
pc = unreal.GameplayStatics.get_player_controller(L.game_world(), 0)
MV = unreal.MegaParkValidation
LAKE = (-90., 235., 75.)              # the forest lake: centre (island metres) and water height
SHORE = (-54., 223.)                  # its safe shore beside the cabin
RUN = ((-26., 239.), (0., 239.))      # 26 m of open, nearly flat ground east of the lake (at most 6 degrees), heading east
CLIFF = ((-28., 210.), (-34., 216.))  # 4 m out from a steep bank (55-58 degrees, 4.5 m, a flat top), facing it square
LANDING = (-44., 220.)                # open ground east of the shore, for the paraglider to come down on
SWIM = (-66., 232.)                   # deep water 4 m north of the moored rowboat, the swim heading out west
LANDFALL = (-61.5, 232.5)             # shallows north of the boat, on the way back to the rock-free shore
ROSTER = os.path.join(live.ROOT, 'games/yorimichi/unreal/Content/Data/botw/roster.json')
BOKOBLIN = next(c for c in json.load(open(ROSTER))['characters'] if c['name'] == 'Bokoblin')
ATTACK = BOKOBLIN['roles']['attack']
# A Bokoblin's blow lands when its attack clip is 45 % through (ABotwCreature::Think).
BLOW = .45 * BOKOBLIN['clips'][ATTACK]['length']


def ue(x, y, z=0.):
    """Island metres (x east, y north) to Unreal cm."""
    return unreal.Vector(x * 100., -y * 100., z * 100.)


def wrap(a):
    return (a + 180.) % 360. - 180.


def yaw_to(a, b):
    return math.degrees(math.atan2(-(b[1] - a[1]), b[0] - a[0]))


def state():
    return json.loads(L.move_state())


def here():
    return L.player_transform().translation


def facing():
    return L.player_transform().rotation.rotator().yaw


st = {'frames': [], 'marks': [], 'errors': [], 'sim': 0, 'film': 0, 'rec': False, 'label': '', 'section': '',
      'cam': None, 'size': 1., 'who': ''}


# ---------------------------------------------------------------------------------------------------------- timing

def wait(seconds):
    t = 0.
    while t < seconds:
        t += (yield)


def frames(n):
    """n steps whatever the world's time dilation (the flurry rush slows the world, not the player)."""
    for _ in range(n):
        yield


def until(test, timeout):
    """Steps until test(state) holds: (state, seconds), or (None, seconds) at the timeout."""
    t = 0.
    while t < timeout:
        s = state()
        if test(s):
            return s, t
        t += (yield)
    return None, t


def grounded(s):
    return s.get('mode') == 'ground' and not s.get('driving')


def settled(s):
    return grounded(s) and s.get('action') == 'None' and s.get('speed', 0.) < 5. and not s.get('down')


# ---------------------------------------------------------------------------------------------------------- filming

def label(text):
    """The caption for what follows; recording on."""
    st['label'] = text; st['rec'] = True
    st['marks'].append({'section': st['section'], 'label': text, 'film_frame': st['film']})
    unreal.log(f'BOTW FILM {st["who"]} | {st["section"]} | {text}')


def cut():
    st['rec'] = False


def camera(dist=2.6, rel=40., h=.35, up=.15, fov=45., track=None, lag=.14, turn=.05, water=False):
    """A camera `dist` m from the player (times the body's size), `rel` degrees round from where it faces now (0 in
    front, 180 behind), `h` m above its middle, aimed `up` m above it. It follows the player's position; with
    track='facing' or 'velocity' it also swings round to stay at `rel` from the facing or the way it moves. With
    water=True, `h` and `up` count from the lake's surface while swimming (the capsule floats above it, the body hangs
    below it)."""
    st['cam'] = dict(dist=dist, rel=rel, h=h, up=up, fov=fov, track=track, lag=lag, turn=turn, water=water,
                     yaw=facing() + rel, snap=True)


def update_camera():
    c = st['cam']
    if not c:
        return
    p = here(); k = st['size'] * 100.
    want = None
    if c['track'] == 'facing':
        want = facing() + c['rel']
    elif c['track'] == 'velocity':
        v = L.player().get_velocity()
        if math.hypot(v.x, v.y) > 60.:
            want = math.degrees(math.atan2(v.y, v.x)) + c['rel']
    if want is not None:
        c['yaw'] = want if c['snap'] else c['yaw'] + wrap(want - c['yaw']) * c['turn']
    r = math.radians(c['yaw'])
    base = LAKE[2] * 100. if c['water'] and state().get('mode') == 'swim' else p.z
    cam = [p.x + math.cos(r) * c['dist'] * k, p.y + math.sin(r) * c['dist'] * k, base + c['h'] * k]
    # Never under the ground (traced down from just above the player, so not onto a tree's crown).
    g = L.ground_at(unreal.Vector(cam[0], cam[1], p.z + 300. - 2000.))
    cam[2] = max(cam[2], g.z + 50.)
    aim = [p.x, p.y, base + c['up'] * k]
    if c['snap']:
        c['pos'], c['aim'], c['snap'] = cam, aim, False
    else:
        c['pos'] = [a + (b - a) * c['lag'] for a, b in zip(c['pos'], cam)]
        c['aim'] = [a + (b - a) * min(1., c['lag'] * 1.8) for a, b in zip(c['aim'], aim)]
    MV.review_camera(unreal.Vector(*c['pos']), unreal.Vector(*c['aim']), c['fov'])


# ---------------------------------------------------------------------------------------------------------- staging

def place(at, toward, height=None):
    """Stand the player at `at` (island metres) facing `toward`, the stick's frame behind it; then let it settle."""
    yaw = yaw_to(at, toward)
    live.drive(0)
    L.teleport_player(ue(at[0], at[1], height if height is not None else LAKE[2]), yaw)
    pc.set_control_rotation(unreal.Rotator(0, -12, yaw))
    yield from wait(.2)
    yield from until(settled, 6.)


def look(yaw):
    """Turn the stick's frame (the player camera's yaw) to `yaw`."""
    pc.set_control_rotation(unreal.Rotator(0, -12, yaw))


def tap(button):
    live.press(button)
    if button in ('jump', 'attack', 'guard'):
        live.press(button + '_release')


def ahead(distance, side=0.):
    """The ground `distance` cm ahead of the player and `side` cm to its right."""
    p = here(); r = math.radians(facing())
    return L.ground_at(unreal.Vector(p.x + math.cos(r) * distance - math.sin(r) * side,
                                     p.y + math.sin(r) * distance + math.cos(r) * side, p.z))


def spawn(distance, mode='idle', side=0., turn=180.):
    """A Bokoblin `distance` cm ahead, facing the player (turn=180) or away from it (turn=0)."""
    return L.botw_spawn('Bokoblin', ahead(distance, side), facing() + turn, mode)


def creature(actor):
    for c in json.loads(L.botw_list() or '[]'):
        if c['actor'] == actor:
            return c
    return None


def toward_actor(actor):
    c = creature(actor); p = here()
    return math.degrees(math.atan2(c['location'][1] - p.y, c['location'][0] - p.x)) if c else facing()


def armed(on):
    if state().get('armed') != on:
        tap('weapon')
        yield from wait(1.2)


def turn_to(yaw, seconds=.3):
    """Turn the player to face `yaw` with a short walk that way."""
    look(yaw); live.drive(1., 0., 'walk')
    yield from wait(seconds)
    live.drive(0)


def next_blow(actor, lead, timeout=8.):
    """Wait for `actor`'s next attack to start, then until `lead` s before its blow lands; True if it came."""
    c = creature(actor)
    was, t = c and c['clip'], 0.    # an attack already under way is not the next one
    while t < timeout:
        c = creature(actor)
        now = c and c['clip']
        if now == ATTACK and was != ATTACK:
            yield from wait(max(0., BLOW - lead))
            return True
        was = now
        t += (yield)
    return False


def drain(target):
    """Sprint in a circle until the stamina is down to `target` rings (off camera); a sprint stops draining at once."""
    cut()
    yaw = facing(); t = 0.
    live.drive(1., 0., 'sprint')
    while state()['stamina'] > target and t < 30.:
        yaw += 100. / 60.; look(yaw)
        t += (yield)
    live.drive(0)


def refill():
    """Off camera, until the stamina is full again (an exhausted character waits for every ring)."""
    cut(); live.drive(0)
    yield from until(lambda s: not s['exhausted'] and s['stamina'] >= st['rings'] - .01, 15.)


# --------------------------------------------------------------------------------------------------------- sections

def on_foot():
    yield from place(*RUN)
    camera(3.0, 140., .3, .1)
    label(f'Idle: {kit()} carried on the back')
    yield from wait(2.5)
    camera(3.0, 70., .35, .15)
    label('Walk')
    live.drive(1., 0., 'walk'); yield from wait(3.)
    label('Run')
    live.drive(1., 0., 'run'); yield from wait(2.5)
    cut(); live.drive(0)
    yield from place(*RUN)
    camera(3.6, 70., .4, .15)
    label('Sprint: uses stamina')
    live.drive(1., 0., 'sprint'); yield from wait(3.)
    label('Stop')
    live.drive(0); yield from wait(1.2)
    yield from drain(.35)               # a short sprint: a pine stands 39 m along the run
    yield from place(*RUN)
    camera(3.6, 70., .4, .15)
    label('Sprint until the stamina runs out: back to a run until the wheel refills')
    live.drive(1., 0., 'sprint')
    yield from until(lambda s: s['exhausted'], 8.)
    yield from wait(2.2)
    live.drive(0); yield from wait(1.)
    yield from refill()
    yield from place(*RUN)
    camera(2.6, 60., .3, .0)
    label('Crouch')
    tap('crouch'); yield from wait(1.)
    label('Sneak (crouched walk)')
    live.drive(1., 0., 'walk'); yield from wait(2.5)
    live.drive(0); yield from wait(.5)
    label('Stand up')
    tap('crouch'); yield from wait(1.)
    cut()
    yield from place(*RUN)
    camera(3.0, 80., .3, .3)
    label('Standing jump and landing')
    tap('jump'); yield from wait(1.8)
    label('Running jump and running landing')
    live.drive(1., 0., 'run'); yield from wait(1.)
    tap('jump'); yield from wait(1.6)
    live.drive(0); yield from wait(.8)
    cut()
    yield from place(*RUN)
    camera(4.0, 70., .6, .3)
    label('A fall of about 8 m: hard landing')
    L.launch(unreal.Vector(0, 0, 1250)); yield from wait(.2)
    yield from until(grounded, 4.)
    yield from wait(2.2)


def gear():
    yield from place(*RUN)
    camera(1.7, 90., .25, .2)
    label(f'{kit().capitalize()} carried on the back, from the side')
    yield from wait(2.)
    camera(1.7, 180., .35, .25)
    label('From behind')
    yield from wait(2.)
    camera(1.7, 115., .1, .0)
    label('Crouched: ' + ('the shield stays on the back' if state().get('shield') else 'the sword stays on the back'))
    tap('crouch'); yield from wait(2.5)
    tap('crouch'); yield from wait(.8)
    cut()
    yield from place(*RUN)
    L.launch(unreal.Vector(0, 0, 2000))   # stick released, it glides down slowly onto the open run
    yield from until(lambda s: s['vz'] > 500., 1.)
    yield from until(lambda s: s['vz'] < 80., 4.)
    yield from open_glider()
    camera(2.2, 25., .45, .55, track='facing', turn=.3)
    label('The paraglider in both hands, from the front')
    yield from wait(2.5)
    camera(2.2, 95., .45, .55, track='facing', turn=.3)
    label('From the side')
    yield from wait(2.5)
    cut()
    yield from until(lambda s: s['mode'] != 'glide', 15.)
    if state()['mode'] == 'glide':
        tap('jump')
    yield from until(grounded, 8.)


def open_glider():
    """Jump in the air until the paraglider opens: in the merged set the first press may be the double jump, so the
    next one comes at its top."""
    tap('jump')
    s, _ = yield from until(lambda s: s['mode'] == 'glide', .3)
    if s is None:
        yield from until(lambda s: s['vz'] < 80., 1.5)
        tap('jump')
        yield from until(lambda s: s['mode'] == 'glide', .6)


def kit():
    return 'sword and shield' if state().get('shield') else 'sword'


def shield_setting(on):
    """The "Shield" setting, as the menu sets it (the move set takes it at once)."""
    L.set_preference('shield', 1. if on else 0.)
    yield from wait(.1)


def sprint():
    yield from place(*RUN)
    camera(5.2, 80., .45, .2, track='velocity', turn=.05)
    label("Link's sprint: dust at the heels, speed lines streaming past")
    live.drive(1., 0., 'sprint'); yield from wait(3.2)
    label('Stop')
    live.drive(0); yield from wait(1.2)
    cut()
    yield from refill()


def double_jump():
    yield from place(*RUN)
    camera(3.6, 80., .6, .6)
    label("Double jump: jump again in the air, Cairo's forward somersault")
    tap('jump'); yield from wait(.35)
    tap('jump'); yield from wait(2.)
    cut()
    yield from place(*RUN)
    camera(4.4, 95., .6, .5, track='velocity', turn=.06)
    label('Running double jump')
    live.drive(1., 0., 'run'); yield from wait(1.)
    tap('jump'); yield from wait(.3)
    tap('jump'); yield from wait(1.5)
    live.drive(0); yield from wait(.8)
    cut()
    yield from place(*RUN)
    camera(4.6, 90., .7, .5)
    label('Double jump with the stick back: all the speed turned right round')
    live.drive(1., 0., 'run'); yield from wait(1.)
    tap('jump'); yield from wait(.3)
    live.drive(-1., 0., 'run'); tap('jump'); yield from wait(1.)
    live.drive(0); yield from wait(1.2)
    cut()
    yield from place(*RUN)
    camera(4.6, 80., .8, .7)
    label('Jump, double jump, then jump again: the paraglider')
    tap('jump'); yield from wait(.3)
    tap('jump'); yield from wait(.15)   # the launch takes effect on the next movement tick
    yield from until(lambda s: s['vz'] < 60., 1.5)
    tap('jump')
    yield from until(lambda s: s['mode'] == 'glide', .6)
    live.drive(1., 0., 'run')
    yield from until(lambda s: s['mode'] != 'glide', 6.)
    live.drive(0)
    yield from until(grounded, 4.)
    yield from wait(1.)


def sword_guard():
    yield from shield_setting(False)
    yield from place(*RUN)
    camera(2.6, 30., .3, .3)
    label('No shield (the default): the guard button draws the sword and raises it')
    live.press('guard'); yield from wait(2.2)
    camera(3.4, 130., .5, .25)
    bok = spawn(450., 'scripted')
    camera(3.4, 60., .4, .3)
    label('Sword raised while locked on and strafing')
    for right in (-1., 1.):
        live.drive(0., right, 'walk'); yield from wait(1.3)
    live.drive(0); yield from wait(.4)
    live.press('guard_release')
    cut(); L.botw_clear()
    yield from place(*RUN)
    yield from armed(True)
    bok = spawn(320., 'camp')
    camera(3.6, 62., .4, .35)
    label("The sword guard blocks a Bokoblin's blow")
    live.press('guard')
    yield from next_blow(bok, -.1)
    yield from wait(1.4)
    for attempt in range(3):
        label('Sword parry: jump while guarding, just before the blow lands' + (' (again)' if attempt else ''))
        before = state()['parries']
        if (yield from next_blow(bok, .07)):
            tap('jump')
        yield from wait(1.6)
        if state()['parries'] > before:
            break
    live.press('guard_release')
    cut(); L.botw_clear()


def dodges():
    yield from place((-12., 239.), RUN[1])    # mid-run: the backflips land on open ground, not in the trees west of it
    bok = spawn(600., 'scripted')
    yield from wait(.3)
    camera(3.4, 135., .5, .2)
    label('Lock-on (guard button held): strafe walking')
    live.press('guard')
    for fwd, right, secs in ((0., -1., 1.3), (0., 1., 1.3), (-1., 0., 1.), (1., 0., 1.)):
        live.drive(fwd, right, 'walk'); yield from wait(secs)
    label('Lock-on: strafe running')
    for fwd, right, secs in ((0., -1., 1.2), (0., 1., 1.2), (-1., 0., .9), (1., 0., .9)):
        live.drive(fwd, right, 'run'); yield from wait(secs)
    live.drive(0); yield from wait(.6)
    camera(3.6, 150., .5, .3)
    label('Side hop left (dodge, stick left)')
    live.drive(0., -1., 'run'); tap('dodge'); yield from wait(.2); live.drive(0); yield from wait(1.)
    label('Side hop right (dodge, stick right)')
    live.drive(0., 1., 'run'); tap('dodge'); yield from wait(.2); live.drive(0); yield from wait(1.)
    label('Backflip (dodge, stick back)')
    live.drive(-1., 0., 'run'); tap('dodge'); yield from wait(.2); live.drive(0); yield from wait(1.4)
    live.press('guard_release'); yield from wait(.4)
    label('Dodge without lock-on: backflip')
    tap('dodge'); yield from wait(1.6)
    cut(); L.botw_clear()


def sword():
    yield from place(*RUN)
    camera(2.4, 40., .3, .25)
    label('Draw the sword: sword held' + (', shield on the arm' if state().get('shield') else ''))
    tap('weapon'); yield from wait(1.6)
    camera(3.2, 70., .35, .2)
    label('Run with the sword drawn')
    live.drive(1., 0., 'run'); yield from wait(2.); live.drive(0); yield from wait(.8)
    cut()
    yield from place(*RUN)
    bok = spawn(140., 'scripted')
    yield from wait(.4)
    camera(3.0, 75., .4, .2)
    label('Four-cut combo on a Bokoblin')
    for _ in range(4):
        tap('attack'); yield from wait(.42)
    yield from wait(1.6)
    cut(); L.botw_clear()
    yield from place(*RUN)
    camera(3.0, 35., .4, .2)
    label('Charged spin attack: hold to charge')
    live.press('attack'); yield from wait(1.5)
    label('Charged spin attack: release')
    live.press('attack_release'); yield from wait(2.)
    cut()
    yield from place(*RUN)
    camera(3.8, 75., .4, .2)
    label('Dash attack (attack while sprinting)')
    live.drive(1., 0., 'sprint'); yield from wait(1.3)
    tap('attack'); yield from wait(.3); live.drive(0); yield from wait(1.6)
    cut()
    yield from place(*RUN)
    camera(3.4, 80., .4, .4)
    label('Jump attack (attack just after a jump)')
    tap('jump'); yield from wait(.15)
    tap('attack'); yield from wait(2.2)
    cut()
    yield from place(*RUN)
    bok = spawn(380., 'idle', turn=0.)
    yield from wait(.4)
    camera(3.2, 110., .4, .1)
    label('Sneak up behind an unaware Bokoblin')
    tap('crouch'); yield from wait(.6)
    live.drive(1., 0., 'walk')
    t = 0.
    while t < 8.:
        c = creature(bok)
        if c and math.hypot(c['location'][0] - here().x, c['location'][1] - here().y) < 135.:
            break
        t += (yield)
    live.drive(0)
    label('Sneakstrike')
    tap('attack'); yield from wait(2.6)
    cut(); L.botw_clear()
    yield from place(*RUN)
    bok = spawn(170., 'scripted', side=60.)
    yield from wait(.4)
    camera(5.0, 80., .2, .5, track=None)
    label('Plunge attack from high up (attack while falling)')
    L.launch(unreal.Vector(0, 0, 1500))
    yield from until(lambda s: s['vz'] > 500., 1.)
    yield from until(lambda s: s['vz'] < 0., 3.)
    tap('attack')
    yield from until(grounded, 4.)
    yield from wait(2.2)
    cut(); L.botw_clear()


def shield():
    yield from shield_setting(True)
    yield from place(*RUN)
    yield from armed(True)
    bok = spawn(450., 'scripted')
    yield from wait(.4)
    camera(3.4, 130., .5, .25)
    label('Locked on with the sword drawn: shield raised while strafing')
    live.press('guard')
    for right in (-1., 1.):
        live.drive(0., right, 'walk'); yield from wait(1.4)
    live.drive(0); yield from wait(.4)
    live.press('guard_release')
    cut(); L.botw_clear()
    yield from place(*RUN)
    yield from armed(True)          # placing the player can sheathe the sword
    bok = spawn(320., 'camp')
    camera(3.4, 110., .5, .3)
    label('Shield guard blocks a Bokoblin\'s blow')
    live.press('guard')
    yield from next_blow(bok, -.1)
    yield from wait(1.4)
    for attempt in range(3):
        label('Parry: jump while guarding, just before the blow lands' + (' (again)' if attempt else ''))
        before = state()['parries']
        if (yield from next_blow(bok, .07)):
            tap('jump')
        yield from wait(1.6)
        if state()['parries'] > before:
            break
    for attempt in range(3):
        label('Perfect dodge: side hop just before the blow lands' + (' (again)' if attempt else ''))
        before = state()['dodges']
        if (yield from next_blow(bok, .13)):
            live.drive(0., 1., 'run'); tap('dodge')
        yield from frames(18); live.drive(0)    # steps, not seconds: a perfect dodge slows the world
        s = state()
        if s['flurry'] > 0.:
            label('Flurry rush: the world slows, every press a blow')
            n = 0
            while state()['flurry'] > 0. and n < 600:
                if n % 8 == 0:
                    tap('attack')
                n += 1
                yield from frames(1)
            yield from wait(1.6)
            break
        yield from wait(1.2)
    live.press('guard_release')
    cut(); L.botw_clear()
    yield from place(*RUN)
    yield from armed(True)
    camera(2.4, 40., .3, .25)
    label('Sheathe the sword')
    tap('weapon'); yield from wait(1.6)
    yield from shield_setting(st['shield'])


def hits():
    yield from place(*RUN)
    yield from armed(False)
    bok = spawn(320., 'camp')
    camera(3.6, 100., .5, .3)
    label('Hit from the front')
    yield from next_blow(bok, -.1)
    yield from wait(1.3)
    label('Hit from behind')
    yield from turn_to(toward_actor(bok) + 180.)
    yield from next_blow(bok, -.1)
    yield from wait(1.3)
    label('Hit from the side')
    yield from turn_to(toward_actor(bok) + 90.)
    yield from next_blow(bok, -.1)
    yield from wait(1.3)
    cut(); L.botw_clear()
    yield from place(*RUN)
    camera(5.0, 70., .3, .5)
    label('A fall of over 20 m: hard landing and fall damage')
    L.launch(unreal.Vector(0, 0, 2200)); yield from wait(.3)
    yield from until(grounded, 6.)
    yield from wait(2.4)
    cut()
    yield from until(settled, 4.)
    bok = spawn(320., 'camp')
    camera(3.8, 80., .5, .3)
    health = state()['health']           # a Bokoblin's blow takes 12
    label('A blow with no health left: knocked down, then up again healed' if health <= 0. else
          'A blow that takes the last of his health: knocked down, then up again healed' if health <= 12. else
          'A blow after the fall')
    yield from next_blow(bok, -.1)
    yield from until(lambda s: not s['down'] and s['action'] == 'None', 6.)
    yield from wait(.6)
    cut(); L.botw_clear()


def glide():
    yield from place(SHORE, LAKE)
    camera(4.2, 150., .8, .3)
    label('Launched up: jump in the air (the double jump), and again: the paraglider')
    L.launch(unreal.Vector(0, 0, 3200))   # high enough to glide out over the lake and back to the shore
    yield from until(lambda s: s['vz'] > 500., 1.)
    yield from until(lambda s: s['vz'] < 80., 4.)
    yield from open_glider()
    yield from wait(1.)
    camera(4.2, 160., .6, .3, track='facing', turn=.04)

    def fly(secs, fwd, right, behind=True):
        live.drive(fwd, right, 'run')
        t = 0.
        while t < secs and state()['mode'] == 'glide':
            if behind:
                look(state()['glide_yaw'])
            t += (yield)
    label('Glide (stick forward): uses stamina')
    yield from fly(2.5, 1., 0.)
    label('Steer right')
    yield from fly(1.6, .3, 1.)
    label('Steer left')
    yield from fly(1.6, .3, -1.)
    label('Glide with the stick released')
    yield from fly(1.2, 0., 0.)
    label('Brake (stick back)')
    yield from fly(1.3, -1., 0.)
    label('Close the paraglider (jump): falling')
    live.drive(0); tap('jump')
    yield from wait(.7)
    label('Open it again while falling fast')
    tap('jump')
    yield from until(lambda s: s['mode'] == 'glide', .6)
    yield from fly(1.4, 1., 0.)
    label('Back to the shore to land')
    s, t = state(), 0.
    while s['mode'] == 'glide' and t < 30.:
        p = here(); home = yaw_to((p.x / 100., -p.y / 100.), LANDING)
        a = wrap(home - s['glide_yaw'])
        look(s['glide_yaw']); live.drive(1. if abs(a) < 50. else .3, max(-1., min(1., a / 40.)), 'run')
        t += (yield); s = state()
    live.drive(0)
    label('Landed: the paraglider closes' if s['mode'] == 'ground' else 'Landed in the lake')
    yield from wait(2.)
    cut()
    yield from place(*RUN)
    yield from drain(.12)
    lake = yaw_to(RUN[0], LAKE)
    look(lake); L.launch(unreal.Vector(0, 0, 2400))
    camera(4.2, 150., .6, .3)
    label('Out of stamina: the paraglider opens, then closes (stamina drained by sprinting first)')
    yield from until(lambda s: s['vz'] > 500., 1.)     # the launch lands a step later
    yield from until(lambda s: s['vz'] < 80., 4.)
    yield from open_glider()
    live.drive(1., 0., 'run')
    s, t = state(), 0.
    while s['mode'] == 'glide' and t < 12.:
        look(lake); t += (yield); s = state()
    live.drive(0)
    yield from until(lambda s: s['mode'] != 'air', 8.)
    yield from wait(2.4)
    cut()
    yield from refill()


def swim():
    yield from place(SWIM, LAKE[:2], height=LAKE[2] - 1.)
    camera(3.0, 120., .8, .1, track='facing', turn=.05, water=True)
    yield from until(lambda s: s['mode'] == 'swim', 3.)
    yield from wait(.3)
    label('Swim')
    live.drive(1., 0., 'run'); yield from wait(2.6)
    label('Tread water (stick released)')
    live.drive(0); yield from wait(1.8)
    label('Swim dash (Dash): uses stamina')
    live.drive(1., 0., 'run')
    for _ in range(2):
        tap('dash'); yield from wait(1.)
    label('Swim back to the shore and climb out')
    s, t, goal = state(), 0., LANDFALL      # round the boat's north side, then up the shore
    while s['mode'] == 'swim' and t < 25.:
        p = (here().x / 100., -here().y / 100.)
        if math.dist(p, goal) < 2.:
            goal = SHORE
        look(yaw_to(p, goal))
        t += (yield); s = state()
    yield from until(grounded, 4.)
    live.drive(0); yield from wait(1.)
    cut()
    yield from place(*RUN)
    yield from drain(.4)
    L.teleport_player(ue(-72., 229., LAKE[2]), yaw_to((-72., 229.), LAKE))
    look(yaw_to((-72., 229.), LAKE))
    yield from until(lambda s: s['mode'] == 'swim', 3.)
    camera(3.0, 130., .8, .1, track='facing', turn=.05, water=True)
    label('Out of stamina in deep water (drained by sprinting, then swim dashes)')
    live.drive(1., 0., 'run')
    t = 0.
    while state()['action'] != 'SwimDie' and t < 15.:
        tap('dash'); yield from wait(.7); t += .7
    live.drive(0)
    label('Sinks, and is back on the last dry ground a little hurt')
    yield from until(lambda s: s['mode'] == 'ground', 8.)
    camera(3.0, 40., .4, .2)
    yield from wait(2.)
    cut()
    yield from refill()


def climb():
    yield from place(*CLIFF)
    camera(3.6, 150., .5, .3)
    label('Run into a steep cliff: grab it')
    live.drive(1., 0., 'run')
    s, _ = yield from until(lambda s: s['mode'] == 'climb', 6.)
    live.drive(0)
    if s is None:
        raise RuntimeError('no climb at the cliff')
    yield from wait(.8)
    camera(3.4, 155., .4, .4, lag=.1)
    # Up first, so that the climbs down that follow stay on the 4.5 m bank.
    for name, fwd, right, secs in (('up', 1., 0., 2.4), ('up and right', .7, .7, 1.), ('right', 0., 1., 1.2),
                                   ('down and right', -.7, .7, .8), ('up and left', .7, -.7, 1.), ('left', 0., -1., 1.2),
                                   ('down and left', -.7, -.7, .8), ('down', -1., 0., .6)):
        label('Climb ' + name)
        live.drive(fwd, right, 'run'); yield from wait(secs)
        if state()['mode'] != 'climb':
            break
    label('Hold on (stick released): climbing uses stamina')
    live.drive(0); yield from wait(1.4)
    # One jump up (the bank is 4.5 m tall), then sideways until the stamina runs out.
    for i, (name, fwd, right) in enumerate((('up', 1., 0.), ('right', 0., 1.), ('left', 0., -1.), ('right', 0., 1.),
                                            ('left', 0., -1.), ('right', 0., 1.), ('left', 0., -1.),
                                            ('right', 0., 1.), ('left', 0., -1.), ('right', 0., 1.))):
        if state()['mode'] != 'climb' or state()['exhausted']:
            break
        label('Climb jump ' + name + ' (jump while climbing): costs stamina')
        live.drive(fwd, right, 'run'); tap('jump'); yield from wait(.25); live.drive(0)
        yield from wait(1.)
    s, _ = yield from until(lambda s: s['mode'] != 'climb' or s['action'] == 'ClimbTired', 6.)
    label('Out of stamina: lets go and drops' if s and s['exhausted'] else 'Off the cliff')
    yield from until(lambda s: s['mode'] != 'climb', 4.)
    yield from until(grounded, 4.)
    yield from wait(1.4)
    yield from refill()
    yield from place(*CLIFF)
    camera(3.6, 120., .5, .4)
    label('Jump at the cliff: grabs it in the air')
    # Jump a body-sized stride from the bank's foot, 4.2 m ahead, so the jump meets the wall before it lands.
    start = here(); live.drive(1., 0., 'run')
    yield from until(lambda s: math.hypot(here().x - start.x, here().y - start.y) > 420. - 140. * st['size'], 3.)
    tap('jump')
    s, _ = yield from until(lambda s: s['mode'] == 'climb', 3.)
    live.drive(0)
    yield from wait(1.)
    camera(3.4, 155., .4, .4, lag=.1)
    if s is not None:
        live.drive(1., 0., 'run'); yield from wait(.8); live.drive(0)
        label('Let go (dodge button)')
        tap('dodge')
        yield from until(grounded, 4.)
        yield from wait(1.)
    label('Grab it again, and kick off backwards (jump with the stick back)')
    look(yaw_to(CLIFF[0], CLIFF[1]))
    live.drive(1., 0., 'run')
    s, _ = yield from until(lambda s: s['mode'] == 'climb', 4.)
    yield from wait(.9); live.drive(0); yield from wait(.4)
    live.drive(-1., 0., 'run'); tap('jump'); yield from wait(.3); live.drive(0)
    yield from until(grounded, 4.)
    yield from wait(1.)
    cut()
    yield from refill()
    yield from place(*CLIFF)
    camera(3.6, 150., .5, .4)
    label('Climb all the way up and over the top')
    live.drive(1., 0., 'run')
    yield from until(lambda s: s['mode'] == 'climb', 6.)
    camera(3.8, 160., .4, .6, lag=.1)
    s, _ = yield from until(lambda s: s['mode'] == 'ground' or s['action'] == 'ClimbTop', 25.)
    if s and s['action'] == 'ClimbTop':
        label('Pull up over the top')
    elif s is None or s['exhausted']:
        label('Out of stamina before the top: lets go')
    yield from until(grounded, 4.)
    live.drive(0)
    yield from wait(1.8)


SECTIONS = [('On foot', on_foot), ('Sprint', sprint), ('Double jump', double_jump), ('Equipment', gear), ('Lock-on and dodges', dodges),
            ('Sword', sword), ('Sword guard', sword_guard), ('Shield', shield), ('Getting hit', hits), ('Paraglider', glide),
            ('Swimming', swim), ('Climbing', climb)]
SECTIONS = [s for s in SECTIONS if s[0] in (globals().get('ONLY') or [s[0] for s in SECTIONS])]


def steps():
    s = state()
    st['size'] = s.get('scale', .8) / .8
    st['rings'] = max(1., round(s.get('stamina', 2.)))
    st['who'] = WHO or ('Link' if s.get('scale', .8) > .79 else 'Cairo')
    st['shield'] = bool(s.get('shield'))
    for name, fn in SECTIONS:
        st['section'] = name
        try:
            yield from fn()
        except Exception:
            st['errors'].append({'section': name, 'label': st['label'], 'error': traceback.format_exc()})
            unreal.log_warning(f'BOTW FILM section {name} failed: {traceback.format_exc()}')
        cut(); live.drive(0)
        for b in ('guard_release', 'attack_release', 'jump_release'):
            live.press(b)
        L.botw_clear()
        s = state()
        if s.get('mode') != 'ground':
            yield from until(grounded, 8.)
        if s.get('armed'):
            yield from armed(False)
        save()          # a game stopped later keeps the sections filmed so far


def run(dt):
    dt = unreal.GameplayStatics.get_world_delta_seconds(L.game_world())
    if st.get('gen') is None:
        st['gen'] = steps(); next(st['gen'])
        return
    try:
        st['gen'].send(dt)
    except StopIteration:
        return finish()
    update_camera()
    # Sounds start on the frame about to be saved; between shots they belong to no frame.
    L.audio_frame(st['film'] if st['rec'] else -1)
    if st['rec']:
        if st['sim'] % 2 == 0:
            if not REHEARSE:
                L.screenshot(os.path.join(OUT, 'frame_%05d.jpg' % st['film']))
            s = state()
            st['frames'].append([st['film'], st['section'], st['label'], s.get('action'), s.get('mode'),
                                 round(s.get('stamina', 0.), 3), bool(s.get('exhausted')), round(s.get('health', 0.), 1),
                                 bool(s.get('armed'))])
            st['film'] += 1
        st['sim'] += 1


def save():
    json.dump({'who': st['who'], 'rings': st.get('rings', 2.), 'frames': st['frames']}, open(os.path.join(OUT, 'frames.json'), 'w'))


def finish():
    live.stop('botw_moves_film'); live.drive(0); L.fixed_step(0)
    L.set_preference('shield', 1. if st.get('shield') else 0.)
    L.audio_log('stop', os.path.join(OUT, 'audio.json'))
    MV.restore_player_camera(); L.film_hud(False)
    save()
    json.dump({'who': st['who'], 'film_frames': st['film'], 'fps_film': 30, 'marks': st['marks'], 'errors': st['errors']},
              open(os.path.join(OUT, 'done.json'), 'w'), indent=1)
    unreal.log(f'BOTW FILM COMPLETE {st["who"]} {st["film"]} frames, {len(st["errors"])} failed sections')


L.film_hud(True); L.fixed_step(60); L.audio_log('start')
live.behave('botw_moves_film', run)
print('BOTW FILM started', OUT, [s[0] for s in SECTIONS])
