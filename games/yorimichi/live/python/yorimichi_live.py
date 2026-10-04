"""In-game helpers for the live bridge. The game imports this as `live` when the bridge starts; the agent sends Python
through `atelier live` (platform/studio/atelier/live.py), which runs in the game's shared namespace, so `live.spawn(...)` etc. are at hand.

Units are Unreal's: centimetres, yaw in degrees. Paths are relative to the repository root.
"""
import math
import os
import time
import unreal

class _Verbs:
    """Yorimichi's live verbs (unreal.YorimichiLive) first, then the platform's (unreal.LiveLibrary)."""
    def __getattr__(self, name):
        for library in (unreal.YorimichiLive, unreal.LiveLibrary):
            if hasattr(library, name):
                return getattr(library, name)
        raise AttributeError(name)


L = _Verbs()
ROOT = L.live_root()


def v(x, y, z=0.0):
    return unreal.Vector(float(x), float(y), float(z))


def player():
    """(location, yaw) of the player."""
    t = L.player_transform()
    return t.translation, t.rotation.rotator().yaw


def here():
    loc, yaw = player()
    return {'x': round(loc.x), 'y': round(loc.y), 'z': round(loc.z), 'yaw': round(yaw, 1)}


def ground(x, y, z=0.0):
    return L.ground_at(v(x, y, z))


def in_front(distance=300.0, side=0.0):
    """Ground point `distance` cm ahead of the player and `side` cm to its right."""
    loc, yaw = player()
    r = math.radians(yaw)
    return ground(loc.x + math.cos(r) * distance - math.sin(r) * side, loc.y + math.sin(r) * distance + math.cos(r) * side, loc.z)


def aim(distance=3000.0):
    return L.aim_point(distance)


def facing_player(at):
    """Yaw that turns a prop's front (+X) toward the player."""
    loc, _ = player()
    return math.degrees(math.atan2(loc.y - at.y, loc.x - at.x))


def size(glb):
    """Model size in cm before scaling (x, y, z)."""
    s = L.model_size(glb)
    return (round(s.x, 1), round(s.y, 1), round(s.z, 1))


def spawn(id, glb, at=None, yaw=None, scale=None, height=None, collision='box', overlay='workshop'):
    """Place a GLB in the running game. `at`: None = 3 m in front of the player, 'aim' = where the camera looks,
    (x, y) / (x, y, z) / Vector = that ground point. `height` (m) scales the model to that height; `yaw` defaults to
    facing the player. Returns the prop actor."""
    if at is None:
        at = in_front()
    elif at == 'aim':
        at = aim()
    elif not isinstance(at, unreal.Vector):
        at = ground(*at)
    if scale is None:
        scale = 1.0
        if height:
            s = L.model_size(glb)
            scale = height * 100.0 / max(s.z, 1e-3)
    if yaw is None:
        yaw = facing_player(at)
    prop = L.spawn_model(id, glb, at, float(yaw), float(scale), collision, overlay or '')
    if prop is None:
        raise RuntimeError(f'spawn failed for {id} ({glb}); see the game log')
    return prop


def move(id, at=None, yaw=None):
    prop = L.find_prop(id)
    if prop is None:
        raise KeyError(id)
    if at is not None:
        at = at if isinstance(at, unreal.Vector) else (aim() if at == 'aim' else ground(*at))
        prop.set_actor_location(at, False, False)
    if yaw is not None:
        prop.set_actor_rotation(unreal.Rotator(0.0, 0.0, float(yaw)), False)
    return prop


def remove(id):
    return L.remove_prop(id)


def props():
    return list(L.prop_ids())


def save(overlay='workshop'):
    return L.save_overlay(overlay)


def say(text, seconds=4.0):
    L.say(str(text), float(seconds))


def teleport(at, yaw=0.0):
    at = at if isinstance(at, unreal.Vector) else ground(*at)
    return L.teleport_player(at, float(yaw))


def drive(forward=1.0, right=0.0, gait='run'):
    """Hold the stick: forward/right in -1..1 relative to the camera, gait 'walk', 'run' or 'sprint'. drive(0) stops."""
    return L.drive(unreal.Vector2D(float(right), float(forward)), {'walk': 0, 'run': 1, 'sprint': 2}[gait])


def press(button):
    """Press a button as the player would: 'jump', 'jump_release', 'roll' or 'crouch' (toggles)."""
    return L.press(str(button))


def sword():
    """Draw or sheathe the sword."""
    return L.toggle_sword()


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


# ---- behaviours: small per-frame functions, hot-swappable by name
_behaviours = {}
_tick = None


def _run(dt):
    for name, fn in list(_behaviours.items()):
        try:
            fn(dt)
        except Exception as error:   # a broken behaviour is dropped, not allowed to spam every frame
            unreal.log_warning(f'live behaviour {name} removed: {error}')
            _behaviours.pop(name, None)


def behave(name, fn):
    """Run fn(dt) every frame under `name`; calling again replaces it."""
    global _tick
    _behaviours[name] = fn
    if _tick is None:
        _tick = unreal.register_slate_post_tick_callback(_run)
    return name


def stop(name=None):
    if name is None:
        _behaviours.clear()
    else:
        _behaviours.pop(name, None)
