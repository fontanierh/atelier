"""Game side of route.py: runs inside the running slice game through its live bridge, with PARAMS set by route.py.

It installs a post-tick callback that plays the route's steps on game frames (no round trip per step), samples the
player every SAMPLE seconds into PARAMS['out']/route.jsonl and, after the last step, writes PARAMS['out']/done.json
and removes itself. Nothing is saved.
"""
import json
import time
from pathlib import Path

import unreal as U

L, Y = U.LiveLibrary, U.YorimichiLive
OUT = Path(PARAMS['out'])
SAMPLE = 0.5
WALK_FROM = U.Vector(-24830, 10000, 1080)   # start_road (poses.json), on the village road down to the coast
WALK_YAW = 2.73                              # along the road's straight before its bend at x -21 320


def walk_start():
    ground = L.ground_at(WALK_FROM)
    L.teleport_player(U.Vector(ground.x, ground.y, ground.z + 100), WALK_YAW)


def skate_place():
    spawn = Y.skate_park_spawn()            # the skate pier's park spawn
    Y.skate_place(spawn.translation, spawn.rotation.rotator().yaw)


def push(on):
    Y.skate_input(U.Vector2D(0, 1 if on else 0), U.Vector2D(0, 0), on, False, False, 0, 0)


# (seconds after the previous step, phase recorded from here on, action)
STEPS = [
    (0, 'settle', lambda: (Y.skate_release(), Y.drive(U.Vector2D(0, 0), 1))),
    (0, 'settle', walk_start),
    (3, 'walk', lambda: Y.drive(U.Vector2D(0, 1), 1)),
    (5, 'walk_stop', lambda: Y.drive(U.Vector2D(0, 0), 1)),
    (1, 'mount', lambda: Y.skate_toggle()),
    (3, 'skate_place', skate_place),
    (2, 'skate', lambda: push(True)),
    (4, 'skate_coast', lambda: push(False)),
    (1, 'done', lambda: (Y.skate_release(), Y.skate_toggle())),
    (2, None, None),
]


def sample(phase, now):
    p = L.player()
    loc, vel = p.get_actor_location(), p.get_velocity()
    move = json.loads(Y.move_state() or '{}')
    skate = dict(f.split('=', 1) for f in Y.skate_state().split() if '=' in f)
    return {'t': round(now, 3), 'phase': phase, 'x': round(loc.x, 1), 'y': round(loc.y, 1), 'z': round(loc.z, 1),
            'speed': round(vel.length(), 1), 'movement_mode': p.get_movement_component().movement_mode.name,
            'move_mode': move.get('mode'), 'board': skate.get('board'),
            'fps': round(1 / max(U.GameplayStatics.get_world_delta_seconds(L.game_world()), 1e-3), 1)}


state = {'start': time.monotonic(), 'next_step': 0., 'step': 0, 'phase': 'settle', 'next_sample': 0., 'rows': []}
OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'route.jsonl').write_text('')


def tick(_dt):
    now = time.monotonic() - state['start']
    try:
        while state['step'] < len(STEPS) and now >= state['next_step']:
            wait, phase, action = STEPS[state['step']]
            if action:
                action()
            state['phase'] = phase or state['phase']
            state['step'] += 1
            if state['step'] < len(STEPS):
                state['next_step'] = now + STEPS[state['step']][0]
        if now >= state['next_sample']:
            row = sample(state['phase'], now)
            state['rows'].append(row)
            with (OUT / 'route.jsonl').open('a') as f:
                f.write(json.dumps(row) + '\n')
            state['next_sample'] = now + SAMPLE
        if state['step'] >= len(STEPS):
            U.unregister_slate_post_tick_callback(HANDLE)
            (OUT / 'done.json').write_text(json.dumps({'samples': len(state['rows'])}))
    except Exception as error:   # never leave a broken callback ticking
        U.unregister_slate_post_tick_callback(HANDLE)
        (OUT / 'done.json').write_text(json.dumps({'error': repr(error)}))


HANDLE = U.register_slate_post_tick_callback(tick)
print('route started', OUT)
