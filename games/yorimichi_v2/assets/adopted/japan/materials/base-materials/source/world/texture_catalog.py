"""The exact independent outputs of the island texture generator. No source files are generated here."""
import json
from pathlib import Path


# key: (legacy filename, generator, additional source assets)
TEXTURES = {
    'leaf_broad': ('T_leaf_broad.png', 'atlas', ()),
    'leaf_cedar': ('T_leaf_cedar.png', 'atlas', ()),
    'leaf_pine': ('T_leaf_pine.png', 'atlas', ()),
    'leaf_ochre': ('T_leaf_ochre.png', 'atlas', ()),
    'leaf_maple': ('T_leaf_maple.png', 'small_leaf_atlas', ()),
    'leaf_ginkgo': ('T_leaf_ginkgo.png', 'small_leaf_atlas', ()),
    'leaf_ochre_small': ('T_leaf_ochre_small.png', 'small_leaf_atlas', ()),
    'leaf_small': ('T_leaf_small.png', 'small_leaf_atlas', ()),
    'litter': ('T_litter.png', 'litter', ()),
    'cloudmask': ('T_cloudmask.png', 'cloudmask', ()),
    'flower': ('T_flower.png', 'flower_atlas', ()),
    'rooftile': ('T_rooftile.jpg', 'rooftile', ()),
    'grass': ('T_grass.png', 'grass', ()),
    'bark_olive': ('T_bark_olive.jpg', 'bark', ('tree-bark.jpg',)),
    'bark': ('T_bark.jpg', 'bark', ('tree-bark.jpg',)),
    'road': ('T_road.jpg', 'road', ()),
    'ground': ('T_ground.jpg', 'ground', ()),
    'ground_detail': ('T_ground_detail.png', 'ground_detail', ('tuscan-ground.jpg', 'tuscan-ground.provenance.json')),
    'sky': ('T_sky.png', 'sky', ()),
    'water': ('T_water.jpg', 'water', ()),
    'concrete': ('T_concrete.jpg', 'concrete', ()),
    'white': ('T_white.png', 'white', ()),
}


def load_spec(path):
    """Read only the selected texture settings; siblings are not action inputs."""
    value = json.loads(Path(path).read_text())
    if (not isinstance(value, dict) or set(value) != {'schema', 'options'} or
            type(value['schema']) is not int or value['schema'] != 1 or type(value['options']) is not dict):
        raise ValueError('Expected texture spec schema 1 and options')
    return value['options']
