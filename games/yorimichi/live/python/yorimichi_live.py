"""Yorimichi's in-game helpers for the live bridge, imported as `live` when the bridge starts. The game-independent
helpers (spawn, move, teleport, behave, ...) come from the bridge's atelier_live module; this adds Yorimichi's verbs
(unreal.YorimichiLive, looked up before the platform's).

Units are Unreal's: centimetres, yaw in degrees. Paths are relative to the repository root.
"""
import math
import os
import time
import unreal
from atelier_live import *   # noqa: F401,F403
from atelier_live import L, ROOT, ground, in_front, player, v   # noqa: F401  (named for readers and linters)

L.libraries.insert(0, unreal.YorimichiLive)


def drive(forward=1.0, right=0.0, gait='run'):
    """Hold the stick: forward/right in -1..1 relative to the camera, gait 'walk', 'run' or 'sprint'. drive(0) stops."""
    return L.drive(unreal.Vector2D(float(right), float(forward)), {'walk': 0, 'run': 1, 'sprint': 2}[gait])


def press(button):
    """Press a button as the player would: Live_Press lists them (jump, jump_release, roll, crouch toggles, attack, wave, bike...)."""
    return L.press(str(button))


def preference(key, value):
    """Set a settings.txt value live as the menu would, e.g. preference('skate_gravity', .8) (docs/SKATE.md, Skate feel menu)."""
    return L.set_preference(str(key), float(value))


def sword():
    """Draw or sheathe the sword."""
    return L.toggle_sword()


def bike():
    """Get the bike out and on it, or (stopped) get off and park it (docs/BIKE.md). Ride it with drive(); press('jump')
    hops, press('crouch') skid-stops, press('attack') rings the bell, press('wave') waves."""
    return L.press('bike')


def bike_state():
    return L.bike_state()


def skate():
    """Get on or off the board (skate. controls, docs/SKATE.md)."""
    return L.skate_toggle()


def skate_input(left=(0, 0), right=(0, 0), push=False, brake=False, slide=False, grab_left=False, grab_right=False):
    """Hold skate. controls until skate_release(): sticks are (x right, y away from the player) in -1..1; the triggers
    (grab_left, grab_right) are True or a pull in 0..1, a crouch on the ground and a grab in the air."""
    return L.skate_input(unreal.Vector2D(float(left[0]), float(left[1])), unreal.Vector2D(float(right[0]), float(right[1])),
                         bool(push), bool(brake), bool(slide), float(grab_left), float(grab_right))


def skate_release():
    """Give the board controls back to the player."""
    stop('skate_script')
    return L.skate_release()


def skate_state():
    return L.skate_state()


def skate_place(at, yaw=0.0):
    """Put the rider on the board, stopped, at a ground point (unreal.Vector or (x, y) in cm)."""
    at = at if isinstance(at, unreal.Vector) else ground(*at)
    return L.skate_place(at, float(yaw))


def skate_park():
    """Put the rider on the board at the skate pier's spawn."""
    t = L.skate_park_spawn()
    return L.skate_place(t.translation, t.rotation.rotator().yaw)


# Retail skater.pat paths; input API uses Y up, PAT uses Y down.
# Basic flips start at a full crouch inside the tolerance circle, outside the manual band.
FLICKS = {
    'ollie': [(0.0, -1.0), (0.0, 1.0)],   # canonical straight flick works in both stances
    'nollie': [(-0.005714, 0.988571), (-0.005714, -1.0)],
    'kickflip': [(0.0, -1.0), (0.908571, 0.417143)],
    'heelflip': [(-0.1, -0.94), (-0.68, 0.714286)],
    'shove': [(0.257143, -0.942857), (0.862857, -0.451429), (0.908571, 0.36)],
    'fs_shove': [(-0.2, -0.965714), (-0.851429, -0.52), (-0.942857, 0.28)],
    '360_shove': [(-0.874286, -0.485714), (0.165714, -0.988571), (0.954286, -0.245714)],
    'fs_360_shove': [(0.862857, -0.485714), (-0.165714, -0.988571), (-0.965714, -0.257143)],
    'varial_kickflip': [(-0.702857, -0.702857), (0.234286, -0.954286), (0.851429, 0.508571)],
    'varial_heelflip': [(0.725714, -0.702857), (-0.131429, -0.977143), (-0.497143, 0.84)],
    'hardflip': [(0.737143, -0.668571), (-0.142857, -0.988571), (0.6, 0.771429)],
    'inward_heelflip': [(-0.714286, -0.714286), (0.211429, -0.977143), (-0.737143, 0.645714)],
    '360_flip': [(-0.965714, -0.268571), (-0.497143, -0.84), (0.211429, -0.988571), (0.908571, 0.405714)],
    'laser_flip': [(1.0, -0.177143), (0.657143, -0.76), (0.04, -0.988571), (-0.84, 0.485714)],
    '360_hardflip': [(0.977143, -0.177143), (0.577143, -0.817143), (-0.12, -0.988571), (0.702857, 0.691429)],
    '360_inward_heelflip': [(-0.977143, -0.177143), (-0.634286, -0.76), (0.051429, -0.977143), (-0.497143, 0.828571)],
}
# The original graph's regular stance mirrors the raw PAT names. These public helpers use regular stance.
FLICKS = {name: [(-x, y) for x, y in points] for name, points in FLICKS.items()}


def skate_script(steps, name='skate_script', done=None):
    """Play a list of (seconds, inputs dict) through skate_input, one after another, then release (unless the last
    step says keep=True). inputs: left, right, push, brake, slide, grab_left, grab_right."""
    queue = [(float(d), dict(i)) for d, i in steps]
    state = {'t': 0.0, 'i': 0}

    def run(dt):
        # One step at most per frame: a short step (a flick's middle point) is never skipped on a slow frame.
        if state['i'] < len(queue) and state['t'] >= queue[state['i']][0]:
            state['t'] = max(0.0, state['t'] - queue[state['i']][0])
            state['i'] += 1
        if state['i'] >= len(queue):
            last = queue[-1][1] if queue else {}
            stop(name)
            if not last.get('keep'):
                L.skate_release()
            if done:
                done()
            return
        inputs = {k: v for k, v in queue[state['i']][1].items() if k != 'keep'}
        skate_input(**inputs)
        state['t'] += dt
    return behave(name, run)


def flick(trick='ollie', left=(0, 0), load=0.18, step=0.03, then=None):
    """A Flick-It gesture: the first point is held for `load` seconds (the crouch), the rest for `step` each, then the
    stick returns to the centre. `left` holds the left stick through it (spins). `then` is a list of extra steps."""
    points = FLICKS[trick]
    steps = [(load, {'right': points[0], 'left': left})] + [(step, {'right': p, 'left': left}) for p in points[1:]]
    steps += [(0.12, {'right': (0, 0), 'left': left})] + list(then or [])
    return skate_script(steps)


def shot(path=None):
    """Request a screenshot (written on the next frame). Returns the absolute path."""
    path = path or os.path.join(os.environ.get('ATELIER_BUILD_ROOT') or os.path.join(ROOT, 'build'), 'yorimichi/live/shots', time.strftime('%Y%m%d_%H%M%S') + '.png')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    L.screenshot(path)
    return path


def hippodrome():
    """Visit the hippodrome by the grandstand."""
    return L.hippodrome_visit()
