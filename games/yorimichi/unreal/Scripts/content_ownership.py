"""The one build step that writes each Unreal Content package two steps once saved.

The step cache publishes a run by the files it saved, so a package written by two
steps can never be restored independently for both: whichever runs second sees the
other's version and the pair stays local forever. This table names the producer of
every package that more than one import used to save. The other imports may load
those packages but must not save them.

`unreal.world` owns all seven. Its city pass imports `terrain.fbx` with fresh slots,
calls `sand_material` and `coast_instance`, writes `M_Village` through the village
import, and calls `sea_plane` for the sea plane and `M_Sea`. `unreal.southwest` now
only places its props with the village material it loads, and `unreal.lake` only
places the lake's own meshes.

`duplicate_writers` is the checker the game test runs over this table, so a second
producer is a test failure rather than a silently shared package.
"""

PRODUCERS = (
    ('unreal.world', ('/Game/Japan/Terrain',
                      '/Game/Japan/Assets/Sea',
                      '/Game/Japan/Materials/MI_Coast',
                      '/Game/Japan/Materials/MI_Sand',
                      '/Game/Japan/Materials/M_ForestGround',
                      '/Game/Japan/Materials/M_Sea',
                      '/Game/Japan/Materials/M_Village')),
)


def writers(pairs=PRODUCERS):
    """package path -> every step that declares it, in declaration order."""
    out = {}
    for step, paths in pairs:
        for path in paths:
            out.setdefault(path, []).append(step)
    return out


def duplicate_writers(pairs=PRODUCERS):
    """package path -> steps, for every package with more than one declared writer."""
    return {path: steps for path, steps in writers(pairs).items() if len(steps) > 1}


def owner(path):
    """The step that writes a declared shared package, or None when it is not shared."""
    steps = writers().get(path, ())
    if len(steps) > 1:
        raise ValueError(f'{path} is declared by {steps}; exactly one step must own it')
    return steps[0] if steps else None
