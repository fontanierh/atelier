"""Stable shared asset names, independent of shader and geometry implementations.

Keep names separate from per-asset specifications: a parameter edit must not invalidate placement
or the world's ownership exclusions. Removing an ID deliberately retires it on the next world import.
"""
from pathlib import Path

SPEC_ROOT = Path(__file__).resolve().parents[1] / 'assets/foliage'

FOLIAGE = (
    'Tree_Broad_A',
    'Tree_Broad_B',
    'Tree_Broad_C',
    'Tree_Maple_A',
    'Tree_Maple_B',
    'Tree_Ginkgo',
    'Tree_Pine_A',
    'Tree_Pine_B',
    'Tree_Cedar_A',
    'Tree_Cedar_B',
    'Bush_Green_A',
    'Bush_Green_B',
    'Bush_Ochre_A',
    'Bush_Ochre_B',
    'Bush_Flower_A',
    'Bush_Flower_B',
    'Grass_A',
    'Grass_B',
)

TEXTURES = (
    'T_bark.jpg',
    'T_bark_olive.jpg',
    'T_cloudmask.png',
    'T_concrete.jpg',
    'T_flower.png',
    'T_grass.png',
    'T_ground.jpg',
    'T_ground_detail.png',
    'T_leaf_broad.png',
    'T_leaf_cedar.png',
    'T_leaf_ginkgo.png',
    'T_leaf_maple.png',
    'T_leaf_ochre.png',
    'T_leaf_ochre_small.png',
    'T_leaf_pine.png',
    'T_leaf_small.png',
    'T_litter.png',
    'T_road.jpg',
    'T_rooftile.jpg',
    'T_sky.png',
    'T_water.jpg',
    'T_white.png',
)

MATERIAL_SLOTS = (
    'LeafBroad',
    'LeafCedar',
    'LeafPine',
    'LeafOchre',
    'Grass',
    'LeafMaple',
    'LeafGinkgo',
    'LeafSmall',
    'Litter',
    'Flower',
    'LeafOchreSmall',
    'RoofTile',
    'Bark',
    'Concrete',
    'BarkOlive',
    'BarkTuscan',
    'Ground',
    'Road',
    'Water',
    'Sky',
    'Paint',
    'Stone',
    'Vermilion',
    'Plaster',
    'Tile',
    'Wood',
    'Feather',
    'FeatherDark',
    'Metal',
    'Rock',
    'Lattice',
    'Moss',
)

SHARED_MATERIALS = (
    'MPC_Wind', 'M_Painted', 'M_Foliage', 'M_Grass', 'M_Sky', 'M_CloudShadow', 'M_Painterly',
    *(f'MI_{name}' for name in MATERIAL_SLOTS),
)


def shared_packages():
    return (*('/Game/Japan/Textures/' + Path(name).stem for name in TEXTURES),
            *('/Game/Japan/Materials/' + name for name in SHARED_MATERIALS),
            '/Game/SeeThrough/MPC_SeeThrough')


def material_bindings():
    return {**{name: '/Game/Japan/Materials/MI_' + name for name in MATERIAL_SLOTS},
            '_cloud': '/Game/Japan/Materials/M_CloudShadow', '_painterly': '/Game/Japan/Materials/M_Painterly'}


def independently_owned(package):
    """@cc [owner:fontanierh,label:correctness] independent-world-package-owners
    The world purge MUST preserve independently produced shared materials, current foliage
    and the footstep library, attenuation and surface waves. It MUST NOT claim similarly
    named legacy siblings. Audio MUST have its own source and persisted-type dependencies.
    """
    if package in ('/Game/Japan/Audio/A_Footstep', '/Game/Japan/Audio/DA_Footsteps'):
        return True
    if package.startswith('/Game/Japan/Audio/Footsteps/'):
        return True
    if package in shared_packages() or package in {'/Game/Japan/Assets/' + name for name in FOLIAGE}:
        return True
    return any(package.startswith('/Game/Japan/FoliageLODs/' + name + '/') for name in FOLIAGE)


def check_material_namespace(slots, owner):
    """Region palettes cannot overwrite packages owned by the shared material action."""
    overlaps = set(slots) & set(MATERIAL_SLOTS)
    if overlaps:
        raise ValueError(f'{owner} overlaps shared material ownership: {sorted(overlaps)}')
