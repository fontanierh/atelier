"""Sword trainer review film (docs/SWORD_TRAINER.md): Kaede in Momiji Hamlet, her menu, a bout at each level, every
opening and answer of hers, taking hits both ways (flinch, stagger, knockdown, guard break), and the end of a bout.

    atelier play yorimichi --memory-gib 13 -- -nofox -nosound -liveport=8872 -RenderOffscreen -ForceRes -ResX=1280 -ResY=720
    atelier live py "TAKE='kaede1'" && atelier live py - < games/yorimichi/scenarios/trainer_film.py
    ... wait for build/yorimichi/trainer_film/<take>/done.json, then:
    python games/yorimichi/scenarios/trainer_film_cut.py build/yorimichi/trainer_film/kaede.mp4 <take>

The player is driven by a small sparring script (closing in, combos, guard, a dodge now and then) so that Kaede has
someone to read; a side camera holds both fighters (perpendicular to the line between them, 5.5 m off), except the
approach, which is the game's own camera. Kaede's openings (combo, charged spin, dash, jump and double-jump attacks,
feint) and answers (guard, parry, dodge, perfect dodge into the flurry rush) are each forced once
(UYorimichiLive::TrainerForce) and filmed as their own labelled shot. Runs at a fixed 60 fps step and saves every
second step as a JPG (30 fps, real time); frames.json gives each frame its label and Kaede's state. Optional
globals: TAKE; ONLY, a list of section names; REHEARSE (no frames).
"""
import json, math, os, random, traceback
import unreal

L = live.L
YL = unreal.YorimichiLive
TAKE = globals().get('TAKE', 'kaede1')
ONLY = globals().get('ONLY')
REHEARSE = globals().get('REHEARSE', False)
OUT = os.path.join(os.environ.get('ATELIER_BUILD_ROOT') or os.path.join(live.ROOT, 'build'), 'yorimichi/trainer_film', TAKE)
os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT):
    if f.endswith('.jpg') or f.endswith('.png') or f.endswith('.json'):
        os.remove(os.path.join(OUT, f))
pc = unreal.GameplayStatics.get_player_controller(L.game_world(), 0)
MV = unreal.MegaParkValidation
rng = random.Random(7)
st = {'frames': [], 'errors': [], 'sim': 0, 'film': 0, 'rec': False, 'label': '', 'cam': None, 'bot': None, 'next': 0., 't': 0.}


def trainer():
    return json.loads(YL.trainer_state())


def player_moves():
    return json.loads(L.move_state()) if hasattr(L, 'move_state') else json.loads(YL.move_state())


def wait(seconds):
    t = 0.
    while t < seconds:
        t += (yield)


def until(test, timeout):
    t = 0.
    while t < timeout:
        if test():
            return True
        t += (yield)
    return False


def label(text):
    st['label'] = text; st['rec'] = True
    unreal.log(f'TRAINER FILM | {text}')


def cut():
    st['rec'] = False


# ------------------------------------------------------------------------------------------------- cameras

def side_camera():
    """Perpendicular to the line between the fighters, 5.5 m off, a little above head height, framing both."""
    p = L.player().get_actor_location(); k = trainer()['location']
    mx, my, mz = (p.x + k[0]) / 2, (p.y + k[1]) / 2, (p.z + k[2]) / 2
    dx, dy = k[0] - p.x, k[1] - p.y
    n = math.hypot(dx, dy) or 1.
    side = st.get('side', 1.)
    ex, ey = mx - dy / n * 550. * side, my + dx / n * 550. * side
    eye = unreal.Vector(ex, ey, mz + 120.)
    st['cam_eye'] = eye if st.get('cam_eye') is None else st['cam_eye'] * .9 + eye * .1     # eased
    at = unreal.Vector(mx, my, mz + 20.)
    MV.review_camera(st['cam_eye'], at, 55.)


def game_camera():
    st['cam'] = None; st['cam_eye'] = None
    MV.restore_player_camera()


# ------------------------------------------------------------------------------------------------- the player's hands

def player_bot(dt, style):
    """A sparring player: closes to cutting range, cuts in short combos, guards, sometimes dodges or charges."""
    p = L.player().get_actor_location(); k = trainer()['location']
    yaw = math.degrees(math.atan2(k[1] - p.y, k[0] - p.x))
    pc.set_control_rotation(unreal.Rotator(roll=0, pitch=-8, yaw=yaw))
    d = math.hypot(k[0] - p.x, k[1] - p.y)
    st['t'] += dt
    if style == 'passive':
        live.drive(0.); return
    if st['t'] < st['next']:
        return
    if d > 230.:
        live.press('guard_release'); live.drive(1., 0., 'run'); st['next'] = st['t'] + .15; return
    live.drive(0.)
    r = rng.random()
    if r < .55:
        for _ in range(rng.randint(1, 3)):
            live.press('attack'); live.press('attack_release')
        st['next'] = st['t'] + rng.uniform(.9, 1.5)
    elif r < .75:
        live.press('guard'); st['next'] = st['t'] + rng.uniform(.8, 1.4); st['release'] = st['next']
    elif r < .88:
        live.drive(rng.choice([-1., 1.]), 0., 'run'); live.press('dodge'); st['next'] = st['t'] + 1.
    else:
        live.press('attack'); st['charge_until'] = st['t'] + 1.3; st['next'] = st['t'] + 1.8
    if st.get('charge_until') and st['t'] > st['charge_until']:
        live.press('attack_release'); st['charge_until'] = None


def run_bot(seconds, style='spar', camera='side'):
    t = 0.
    while t < seconds:
        if st.get('release') and st['t'] > st['release']:
            live.press('guard_release'); st['release'] = None
        player_bot(dt := (yield), style)
        if camera == 'side':
            side_camera()
        t += dt


def start(level, her_shield=False, player_shield=False):
    L.set_preference('shield', 1. if player_shield else 0.)
    YL.trainer_bout(level, her_shield, player_shield)


def home():
    """The player 3.5 m in front of Kaede at her home, facing her."""
    YL.trainer_end()
    k = trainer()['location']
    yaw = math.radians(st['home_yaw'])
    L.teleport_player(L.ground_at(unreal.Vector(k[0] + math.cos(yaw) * 350., k[1] + math.sin(yaw) * 350., k[2] + 200.)), st['home_yaw'] + 180.)


# ------------------------------------------------------------------------------------------------- sections

def approach():
    """Walking up to Kaede in the hamlet, the game's camera; her prompt; her menu."""
    game_camera()
    k = trainer()['location']
    yaw = math.radians(st['home_yaw'])
    L.teleport_player(L.ground_at(unreal.Vector(k[0] + math.cos(yaw) * 1100., k[1] + math.sin(yaw) * 1100., k[2] + 300.)), st['home_yaw'] + 180.)
    pc.set_control_rotation(unreal.Rotator(roll=0, pitch=-10, yaw=st['home_yaw'] + 180.))
    yield from wait(2.)
    label('Momiji Hamlet: Kaede, the sword teacher')
    live.drive(1., 0., 'walk')
    yield from until(lambda: trainer().get('distance', 1e9) < 300. or math.hypot(*(lambda p, q: (p.x - q[0], p.y - q[1]))(L.player().get_actor_location(), trainer()['location'])) < 300., 9.)
    live.drive(0.)
    label('Interact (E / D-pad Down): "Talk to Kaede"')
    yield from wait(2.)
    live.press('interact')
    label('Her menu: the level, her shield, yours')
    yield from wait(1.)
    L.screenshot(os.path.join(OUT, 'menu.png'))
    yield from wait(2.5)
    YL.trainer_menu()   # closes it
    cut()


def bout(level, name, seconds, her_shield=False, player_shield=False):
    home()
    yield from wait(1.)
    st['side'] = rng.choice([-1., 1.]); st['cam_eye'] = None
    start(level, her_shield, player_shield)
    label(f'{name}: "Take your stance."')
    yield from run_bot(3., 'passive')
    label(f'A bout at {name}' + (' · she carries the shield' if her_shield else '') + (' · you carry the shield' if player_shield else ''))
    yield from run_bot(seconds)
    cut()


def showcase():
    """Each opening and each answer of Kaede's, forced once, at the Master level."""
    home(); yield from wait(.5)
    start(2)
    yield from run_bot(3., 'passive')
    for attack, text in (('combo', 'Her combo: up to four cuts'), ('charge', 'Her charged spin'), ('dash', 'Her dash attack (sprinting)'),
                         ('jump', 'Her jump attack'), ('double', 'Her double jump into a jump attack'), ('feint', 'A feint: in, then the backflip out')):
        YL.trainer_force(attack, '')
        label(text)
        yield from run_bot(3.2, 'passive')
        cut()
        yield from run_bot(.8, 'passive')
    for answer, text in (('guard', 'She guards your cut'), ('parry', 'She parries: you are thrown back'),
                         ('dodge', 'She side-hops or backflips away'), ('perfect', 'A perfect dodge: her flurry rush')):
        YL.trainer_force('', answer)
        label(text)
        t = 0.
        while t < 3.2:
            p = L.player().get_actor_location(); k = trainer()['location']
            d = math.hypot(k[0] - p.x, k[1] - p.y)
            yaw = math.degrees(math.atan2(k[1] - p.y, k[0] - p.x))
            pc.set_control_rotation(unreal.Rotator(roll=0, pitch=-8, yaw=yaw))
            if d > 200.:
                live.drive(1., 0., 'run')
            else:
                live.drive(0.)
                if t > .6 and not st.get('cut_done'):
                    for _ in range(3):
                        live.press('attack'); live.press('attack_release')
                    st['cut_done'] = True
            side_camera()
            t += (yield)
        st['cut_done'] = False
        cut()
    YL.trainer_end()


def close_in(seconds, act, answer=''):
    """The player closes to cutting range facing Kaede and does `act` (a generator of presses); her answer to every blow
    in the meantime is `answer` ('take', 'guard', or '' for her own choice)."""
    t, gen = 0., None
    while t < seconds:
        if answer:
            YL.trainer_force('', answer)
        p = L.player().get_actor_location(); k = trainer()['location']
        d = math.hypot(k[0] - p.x, k[1] - p.y)
        pc.set_control_rotation(unreal.Rotator(roll=0, pitch=-8, yaw=math.degrees(math.atan2(k[1] - p.y, k[0] - p.x))))
        st['d'] = d
        if gen is None and d > 190.:
            live.drive(1., 0., 'run')
        else:
            live.drive(0.)
            gen = gen or act()
            next(gen, None)
        side_camera()
        t += (yield)


def presses(*steps):
    """Presses spaced in seconds: ('attack', .35) presses attack and waits; ('hold', 1.3) holds it that long."""
    def act():
        for what, after in steps:
            if what == 'hold':
                # Charging, walking in until she is in reach of the spin.
                live.press('attack'); t = 0.
                while t < after or st['d'] > 170.:
                    if st['d'] > 150.:
                        live.drive(1., 0., 'walk')
                    t += unreal.GameplayStatics.get_world_delta_seconds(L.game_world()); yield
                    if t > after + 3.:
                        break
                live.press('attack_release')
            else:
                live.press(what); live.press(what + '_release')
                t = 0.
                while t < after:
                    t += unreal.GameplayStatics.get_world_delta_seconds(L.game_world()); yield
        while True:
            yield
    return act


def hits():
    """Taking hits, both ways: the flinch and the stagger from each side, the knockdown, the guard break."""
    home(); yield from wait(.5)
    start(0)
    yield from run_bot(3., 'passive')
    combo = presses(('attack', .45), ('attack', .45), ('attack', .45), ('attack', 1.))
    charge = presses(('hold', 1.3))
    for act, answer, text in ((combo, 'take', 'Kaede takes your combo: she flinches, the third cut and the last stagger her'),
                              (charge, 'take', 'A full charge knocks her down; she gets up the way she fell'),
                              (charge, 'guard', 'A full charge on her guard breaks it')):
        label(text)
        yield from close_in(5.5, act, answer)
        cut()
        yield from run_bot(.6, 'passive')
    YL.trainer_end()
    # Kaede's blows on the player, at full weight, the player standing or guarding, then turned side-on.
    home(); yield from wait(.5)
    start(2)
    yield from run_bot(3., 'passive')
    for attack, guard, side, text in (('combo', False, 0., 'Her combo on you: flinches, then the stagger'),
                                      ('combo', False, 90., 'From the side: the hits come from your left or right'),
                                      ('charge', True, 0., 'Her full charge on your guard breaks it'),
                                      ('charge', False, 0., 'Her full charge knocks you down')):
        YL.trainer_force(attack, '')
        if guard:
            live.press('guard')
        if side:
            p = L.player().get_actor_location(); k = trainer()['location']
            L.teleport_player(p, math.degrees(math.atan2(k[1] - p.y, k[0] - p.x)) + side)
        label(text)
        t = 0.
        while t < 4.:
            p = L.player().get_actor_location(); k = trainer()['location']
            if not side:
                pc.set_control_rotation(unreal.Rotator(roll=0, pitch=-8, yaw=math.degrees(math.atan2(k[1] - p.y, k[0] - p.x))))
            live.drive(0.); side_camera()
            t += (yield)
        if guard:
            live.press('guard_release')
        cut()
        yield from run_bot(1.5, 'passive')
    YL.trainer_end()


def finish_bout():
    """The end of a bout: Kaede at Master against a passive player, then her words and her bow."""
    home(); yield from wait(.5)
    start(2)
    label('The end of a bout: knocked down at no health')
    t = 0.
    while t < 30. and trainer()['bout'] in ('ready', 'fighting'):
        player_bot(dt := (yield), 'passive'); side_camera(); t += dt
    label(trainer()['bout'] == 'over' and 'Kaede: "Up you get. Guard, then strike."' or 'Over')
    yield from run_bot(5.5, 'passive')
    cut()


def steps():
    st['home_yaw'] = trainer()['location'] and math.degrees(math.atan2(0, 1))
    sections = [('approach', approach), ('gentle', lambda: bout(0, 'Gentle', 14.)), ('steady', lambda: bout(1, 'Steady', 16.)),
                ('master', lambda: bout(2, 'Master', 18., True, True)), ('showcase', showcase), ('hits', hits), ('end', finish_bout)]
    for name, fn in sections:
        if ONLY and name not in ONLY:
            continue
        try:
            L.fixed_step(60)
            yield from fn()
        except Exception:
            st['errors'].append({'section': name, 'label': st['label'], 'error': traceback.format_exc()})
            unreal.log_warning(f'TRAINER FILM {name} failed: {traceback.format_exc()}')
        cut(); live.drive(0); L.fixed_step(0)
        save()


def run(dt):
    dt = unreal.GameplayStatics.get_world_delta_seconds(L.game_world())
    if st.get('gen') is None:
        st['gen'] = steps(); next(st['gen'])
        return
    try:
        st['gen'].send(dt)
    except StopIteration:
        return finish()
    if st['rec'] and not REHEARSE:
        if st['sim'] % 2 == 0:
            L.screenshot(os.path.join(OUT, 'frame_%05d.jpg' % st['film']))
            k = trainer()
            rec = {key: k.get(key) for key in ('bout', 'level', 'intent', 'health', 'player_health', 'shield', 'action')}
            rec['player_action'] = player_moves().get('action')
            st['frames'].append([st['film'], st['label'], rec])
            st['film'] += 1
        st['sim'] += 1


def save():
    json.dump({'frames': st['frames'], 'errors': st['errors']}, open(os.path.join(OUT, 'frames.json'), 'w'))


def finish():
    live.stop('trainer_film'); live.drive(0); L.fixed_step(0)
    YL.trainer_end(); MV.restore_player_camera()
    save()
    json.dump({'frames': st['film'], 'errors': st['errors']}, open(os.path.join(OUT, 'done.json'), 'w'))
    unreal.log('TRAINER FILM DONE')


live.behave('trainer_film', run)
print('TRAINER FILM started', OUT)
