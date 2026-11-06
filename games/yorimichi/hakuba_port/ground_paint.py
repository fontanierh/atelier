"""The ground's colour where Yorimichi's terrain material paints it rather than its cells' colour, for `ground.py`.

Some terrain cells are ported in their slots' flat colours (`regions.far_hills`, `regions.belmonte`), which Yorimichi's
materials never draw: they paint the ground from where it lies, with code the source game shares. Each painter here
takes the map points a layer's cells cover (x east, y north, height, the up part of the ground's normal) and the
colour sampled from the cells, linear, and gives the colour Yorimichi draws there, linear; each material's detail grain
averages one and is left to Hakuba's ground detail.

- The far hills (`M_ForestGround`, `forest_ground.py`): the forest floor brightens over the 300 m north of Belmonte's
  southern join and gives way to the coast's sand and rock by the colour and coverage `shorelines.paint` bakes into
  its vertices (`build_terrain.coastal_colours`); its exposed rock faces (`M_CoastRock`) draw the geology colour
  `coastal_surface.face_colour` gives them. The sampled colour says how much of a point is rock, between the slots'
  two flats.
- Belmonte's valley (`M_Belmonte` terrain) blends its four layers by its vertices' weights, which its join carries
  out as the valley's own ground colours (`belmonte.source.terrain_colours`); its apron and north country
  (`M_BelmonteJoin`) draw the colours `belmonte.appearance.paint_join_data` gives their vertices: the valley's
  colours turning to the forest floor away from it, and in the north country the forest floor with the coast's.
  The railway's cuttings and banks recolour a few of those (`train.earthworks`), which the ground leaves out.
- Brinecove's natural ground (`M_BrinecoveTerrain`, `import_brinecove.py`) blends sand, meadow, forest floor and rock
  per pixel by height above the sea, slope and two value noises (`TERRAIN_WEIGHTS`, ported here), each layer its
  texture's mean, the rock under its far breakup; its paths and quays keep their sampled colour."""
import sys
from pathlib import Path

import functools

import numpy as np

WORLD = Path(__file__).resolve().parents[1] / 'world'
sys.path[:0] = [str(Path(__file__).resolve().parent), str(WORLD), str(WORLD / 'regions')]
import coastal_surface  # noqa: E402
import shorelines  # noqa: E402
from belmonte import appearance, layout, source, terrain  # noqa: E402
from regions import FAR_FOREST, FAR_ROCK  # noqa: E402



def far_hills(x, y, z, normal_z, sampled):
    rock = np.asarray(FAR_ROCK) - np.asarray(FAR_FOREST)
    share = np.clip(((sampled - np.asarray(FAR_FOREST)) @ rock) / (rock @ rock), 0.0, 1.0)[:, None]
    floor = appearance.far_palette(x, y)
    shore, cover = shorelines.paint(x, y, z, normal_z)
    forest = floor * (1 - cover[:, None]) + shore * cover[:, None]
    return forest * (1 - share) + coastal_surface.face_colour(x, y, z, normal_z) * share


def valley_colours(x, y):
    """The valley's ground colours, its rim's beyond its bounds, as its join reads them."""
    bounds = layout.BOUNDS
    return source.terrain_colours().colour(np.clip(x, bounds[0], bounds[2]) - layout.ORIGIN[0],
                                           np.clip(y, bounds[1], bounds[3]) - layout.ORIGIN[1])


def belmonte_valley(x, y, z, normal_z, sampled):
    return valley_colours(x, y)


def belmonte_apron(x, y, z, normal_z, sampled):
    weight = appearance.forest_weight(x, y)[:, None]
    outer = terrain.OUTER
    forest = appearance.far_palette(np.clip(x, outer[0], outer[2]), np.clip(y, outer[1], outer[3]))
    return valley_colours(x, y) * (1 - weight) + forest * weight


def belmonte_north_country(x, y, z, normal_z, sampled):
    return shorelines.colours(x, y, z, normal_z, appearance.far_palette(x, y))


BRINECOVE_TEXTURES = WORLD.parent / 'assets' / 'brinecove' / 'textures'
# M_BrinecoveTerrain's layers and the rock's breakup at a distance (its macro noise at its mean).
BRINECOVE_LAYERS = ('terrain_sand', 'terrain_meadow', 'terrain_forest', 'terrain_rock')
BRINECOVE_ROCK_BREAKUP = (0.97, 0.95, 0.925)


@functools.cache
def texture_mean(path):
    """An image's mean linear RGB."""
    from port import mean
    return np.asarray(mean(path))


def value_noise(x, y, scale, key):
    """`TERRAIN_WEIGHTS`'s value noise over cells `scale` metres wide, in the shader's single precision."""
    q = np.stack([x, y], -1).astype(np.float32) / np.float32(scale)
    cell, f = np.floor(q), q - np.floor(q)
    f = f * f * (3 - 2 * f)

    def corner(dx, dy):
        return np.modf(np.sin((cell + np.float32([dx, dy])) @ np.float32(key)) * np.float32(43758.5453))[0] % 1.0
    return ((1 - f[:, 1]) * ((1 - f[:, 0]) * corner(0, 0) + f[:, 0] * corner(1, 0))
            + f[:, 1] * ((1 - f[:, 0]) * corner(0, 1) + f[:, 0] * corner(1, 1)))


def smoothstep(low, high, t):
    t = np.clip((t - low) / (high - low), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def brinecove(x, y, z, normal_z, sampled):
    sand, meadow, forest_floor, rock_layer = (texture_mean(next(BRINECOVE_TEXTURES.glob(name + '.*')))
                                              for name in BRINECOVE_LAYERS)
    # Only the natural ground: the points of the terrain's own material, whose cells carry the meadow's mean.
    natural = np.abs(sampled - meadow).max(-1) < 0.004
    n1, n2 = value_noise(x, y, 37.0, (127.1, 311.7)), value_noise(x, y, 9.0, (269.5, 183.3))
    slope = 1 - np.clip(normal_z, 0.0, 1.0)
    rock_at = 0.36 + (0.1 - 0.36) * smoothstep(28.0, 45.0, z)
    rock = smoothstep(rock_at, rock_at + 0.16, slope + (n2 - 0.5) * 0.14)
    shore = (1 - smoothstep(1.1, 2.7, z + (n2 - 0.5) * 1.8)) * (1 - smoothstep(0.3, 0.55, slope)) * (1 - rock)
    green = (1 - rock) * (1 - shore)
    forest = smoothstep(0.3, 0.74, n1 + (n2 - 0.5) * 0.45) * 0.85
    colour = (shore[:, None] * sand + (green * (1 - forest))[:, None] * meadow
              + (green * forest)[:, None] * forest_floor
              + rock[:, None] * rock_layer * np.asarray(BRINECOVE_ROCK_BREAKUP))
    return np.where(natural[:, None], colour, sampled)


# Each painted layer's painter, by the start of its cells' prop names (`ground.LAYERS`).
PAINTERS = {'far-hills-cell-': far_hills, 'belmonte-bt-terrain-': belmonte_valley,
            'belmonte-north-apron-': belmonte_apron, 'belmonte-north-country-': belmonte_north_country,
            'brinecove-ground-': brinecove}
