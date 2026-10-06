"""Skate showreel: a line of shots at the skate pier, filmed inside the running game.

    atelier live py "TAKE='take1'" && atelier live py - < games/yorimichi/scenarios/skate_showreel.py
    ... wait for build/yorimichi/skatefilm/<take>/done.json, then:
    python games/yorimichi/scenarios/skate_mix_showreel.py build/yorimichi/skatefilm/<take>

Runs in the game's Python (the live bridge). Every shot is scripted skate. input (the same Flick-It gestures a player
makes) at a fixed 60 fps step, so capture stalls do not change the ride; every second frame is saved as a JPG (30 fps
video). The sounds the game starts are logged with their frame (audio.json) and the board's loops every frame
(loops.csv); skate_mix_showreel.py rebuilds the soundtrack from them.
"""
import json, math, os
import unreal

L = live.L
TAKE = globals().get('TAKE', 'take1')
OUT = os.path.join(os.environ.get('ATELIER_BUILD_ROOT') or os.path.join(live.ROOT, 'build'), 'yorimichi/skatefilm', TAKE)
os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT):
    if f.endswith('.jpg') or f in ('done.json', 'audio.json'): os.remove(os.path.join(OUT, f))
PARK = json.load(open(os.path.join(live.ROOT, 'games/yorimichi/world/regions/skatepark/park.json')))
OX, OY, OZ = PARK['origin']


def ue(lx, ly, lz=0.0):
    return unreal.Vector((OX + lx) * 100, -(OY + ly) * 100, (OZ + lz) * 100)


# (name, start (x, y) park metres, heading degrees ccw from east, launch cm/s, seconds, camera, events)
# camera: ('follow',) or ('hold', pitch, yaw) ; events: (time, inputs) or (time, ('flick', name, left, load))
SHOTS = [
    ('push and kickflip', (-28, 38), 0, 0, 5.0, ('follow',),
     [(0.0, {'push': True}), (2.4, {}), (2.8, ('flick', 'kickflip', (0, 0), .22))]),
    ('flat bar 50-50, kickflip out', (-36, 43), 0, 520, 4.2, ('follow',),
     [(0.98, ('flick', 'ollie', (0, 0), .16)), (1.95, ('flick', 'kickflip', (0, 0), .12))]),
    ('boardslide', (-4.5, 43), 0, 500, 4.0, ('hold', -6, 35),
     [(0.98, ('flick', 'ollie', (1, 0), .16)), (1.32, {})]),
    ('bowl air', (29, -10), 0, 900, 4.8, ('hold', -8, 40),
     [(0, {'grab_right': True}), (1.5, {})]),
    ('vert melon', (57, 25), 0, 960, 4.6, ('hold', -3, 90),
     [(1.2, {'grab_left': True}), (1.6, {})]),
    ('handrail', (-64, 25.5), 0, 520, 3.6, ('follow',),
     [(1.8, ('flick', 'ollie', (0, 0), .2))]),
    ('360 flip', (-12, 38), 0, 520, 2.9, ('hold', -6, 40),
     [(0.5, ('flick', '360_flip', (0, 0), .2))]),
    ('powerslide', (-12, 38), 0, 760, 2.9, ('follow',),
     [(0.8, {'slide': True}), (2.4, {})]),
]
SETTLE = 24          # frames standing still at the start of a shot while the camera settles (not recorded)


def expand(events):
    """Timeline of (time, inputs) with flicks as their stick key points."""
    out = []
    for when, what in events:
        if isinstance(what, tuple) and what[0] == 'flick':
            pts = live.FLICKS[what[1]]; left = what[2]; load = what[3]
            out.append((when, {'right': pts[0], 'left': left}))
            t = when + load
            for p in pts[1:]:
                out.append((t, {'right': p, 'left': left})); t += 1 / 30
            out.append((t, {'right': (0, 0), 'left': left}))
        else:
            out.append((when, what))
    return sorted(out, key=lambda e: e[0])


state = {'shot': -1, 'f': 0, 'sim': 0, 'film': 0, 'timeline': [], 'camera': [], 'loops': [], 'marks': []}
pc = unreal.GameplayStatics.get_player_controller(L.game_world(), 0)
cm = unreal.GameplayStatics.get_player_camera_manager(L.game_world(), 0)


def start_shot(i):
    name, (x, y), heading, speed, seconds, cam, events = SHOTS[i]
    g = L.ground_at(ue(x, y, 3.0))
    live.skate_input()                     # neutral scripted controls: the player's hands stay off the board
    L.skate_place(g, -heading)
    pc.set_control_rotation(unreal.Rotator(0, cam[1] if cam[0] == 'hold' else -8, -(cam[2] if cam[0] == 'hold' else heading)))
    state.update(shot=i, f=0, timeline=expand(events))
    state['marks'].append({'shot': name, 'film_frame': state['film'], 'sim_frame': state['sim']})


def run(dt):
    if state['shot'] < 0: start_shot(0)
    i = state['shot']; name, _, heading, speed, seconds, cam, _ = SHOTS[i]
    f = state['f']; state['f'] += 1
    if cam[0] == 'hold':
        L.hold_camera(.5); pc.set_control_rotation(unreal.Rotator(0, cam[1], -cam[2]))
    if f < SETTLE:
        live.skate_input(); return
    if f == SETTLE:
        h = math.radians(heading); L.skate_launch(unreal.Vector(speed * math.cos(h), -speed * math.sin(h), 0))
    t = (f - SETTLE) / 60.0
    inputs = {}
    for when, what in state['timeline']:
        if when <= t: inputs = what
    live.skate_input(**inputs)
    L.audio_frame(state['sim'])
    state['loops'].append(L.skate_loops().strip())
    if state['sim'] % 2 == 0:
        L.screenshot(os.path.join(OUT, 'frame_%05d.jpg' % state['film']))
        loc = cm.get_camera_location(); rot = cm.get_camera_rotation()
        state['camera'].append('%d,%.1f,%.1f,%.1f,%.2f' % (state['film'], loc.x, loc.y, loc.z, rot.yaw))
        state['film'] += 1
    state['sim'] += 1
    if t >= seconds:
        if i + 1 < len(SHOTS): start_shot(i + 1)
        else: finish()


def finish():
    live.stop('showreel')
    live.skate_release(); L.film_hud(False); L.fixed_step(0)
    n = L.audio_log('stop', os.path.join(OUT, 'audio.json'))
    open(os.path.join(OUT, 'camera.csv'), 'w').write('frame,x,y,z,yaw\n' + '\n'.join(state['camera']) + '\n')
    open(os.path.join(OUT, 'loops.csv'), 'w').write('\n'.join(state['loops']) + '\n')
    json.dump({'film_frames': state['film'], 'sim_frames': state['sim'], 'fps_sim': 60, 'fps_film': 30, 'sounds': n, 'shots': state['marks']},
              open(os.path.join(OUT, 'done.json'), 'w'), indent=1)


L.film_hud(True); L.fixed_step(60); L.audio_log('start')
live.behave('showreel', run)
print('SHOWREEL started', OUT)
