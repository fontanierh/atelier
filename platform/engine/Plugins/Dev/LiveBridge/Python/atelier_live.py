"""Game-independent helpers for the live bridge. The bridge imports a game's helper module as `live`; a game's module
starts with `from atelier_live import *` and adds its own verbs. A game without one gets this module as `live`. The agent
sends Python through `atelier live` (platform/studio/atelier/live.py), which runs in the game's shared namespace, so
`live.spawn(...)` etc. are at hand.

Units are Unreal's: centimetres, yaw in degrees. Paths are relative to the repository root.
"""
import math
import unreal


class Verbs:
    """Looks a verb up in each function library in turn. A game puts its own library first:
    `L.libraries.insert(0, unreal.MyGameLive)`."""
    def __init__(self):
        self.libraries = [unreal.LiveLibrary]
        if hasattr(unreal, 'AtelierFXLibrary'):   # audio_log, audio_frame (AtelierFX plugin)
            self.libraries.append(unreal.AtelierFXLibrary)

    def __getattr__(self, name):
        for library in self.__dict__.get('libraries', ()):
            if hasattr(library, name):
                return getattr(library, name)
        raise AttributeError(name)


L = Verbs()
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
