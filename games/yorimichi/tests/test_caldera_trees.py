"""The caldera's conifers (world/regions/craterpark/v2/trees.py): four committed Tripo models, fitted with the Hidamari
props (world/regions/hidamari/props.py) and planted only by the crater floor round the editor park (editor_floor.py)."""
import hashlib
import json
from pathlib import Path
import re
import sys
import types

import numpy as np
import pytest

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'world' / 'regions'))
sys.path.insert(0, str(GAME / 'world'))
from craterpark.v2 import editor_floor as ef, trees as caldera  # noqa: E402
import yori  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_craterpark_editor_floor import GRID, GROUND, scene  # noqa: E402


def test_four_committed_models_black_pines_and_sugi_cedars():
    assert len(caldera.TREES) == 4
    assert sorted(caldera.family('pine')) == ['Tree_Caldera_BlackPine_A', 'Tree_Caldera_BlackPine_B']
    assert sorted(caldera.family('cedar')) == ['Tree_Caldera_Cedar_A', 'Tree_Caldera_Cedar_B']
    for key, (folder, family, height, crown) in caldera.TREES.items():
        # JapanWorld/SuperUltraMegaPark treat a Tree* key as a tree (camera fade, sway distance)
        assert key.startswith('Tree_Caldera_')
        glb = caldera.source(key)
        assert glb.read_bytes()[:4] == b'glTF', key
        # the source manifest records the committed model's checksum
        record = {d['file']: d for d in json.loads((glb.parents[1] / 'downloads.json').read_text())}
        assert record['raw/output_model_url.glb']['sha256'] == hashlib.sha256(glb.read_bytes()).hexdigest(), key
        assert 7. <= height <= 13. and 1.5 < crown < .6 * height, key
        assert not (glb.parents[1] / 'api-private').exists(), 'private provider records stay out of the assets'
    assert caldera.SCALE[0] < 1 < caldera.SCALE[1]


def test_lods_get_lighter_and_farther():
    shares = [s for s, _, _ in caldera.LODS]
    sizes = [z for _, z, _ in caldera.LODS]
    assert caldera.LODS[0] == (1., 1., None) and {how for *_, how in caldera.LODS[1:]} <= {'weld', 'shell'}
    assert all(a > b for a, b in zip(shares, shares[1:])) and all(a > b for a, b in zip(sizes, sizes[1:]))
    assert shares[-1] * 11000 < 400, 'the last LOD is a few hundred triangles'
    # the shells' trunks are decimated on their own, and what a LOD may float the planting sinks into the ground
    assert 0 < caldera.BASE[0] < .25 and 0 < caldera.BASE[1] < .5
    assert 0 < caldera.FLOAT < ef.TREE_SINK


def test_a_floating_lod_is_planted_under_the_ground_at_every_scale():
    """The planting sinks by scale: a LOD whose lowest point is just under FLOAT (BlackPine_B's far LOD stands
    0.14 m off its base) is still under flat ground at the largest and smallest scales."""
    flat = types.SimpleNamespace(ground=lambda x, z: np.zeros(len(x)), slope=lambda x, z: np.zeros(len(x)))
    for scale in caldera.SCALE:
        x, z, y, yaw, s = ef._planting(flat, 3., 4., 10., scale)
        assert s == round(scale, 3) and (x, z) == (300., 400.)
        assert y / 100 + caldera.FLOAT * scale < 0, (scale, y)


def test_only_the_crater_floor_plants_them():
    """The conifers are planted by editor_floor (park.json trees) and fitted by the props script, nowhere else: the
    island's own planting (city.json) and the other regions keep their trees."""
    users = set()
    for path in (GAME / 'world').rglob('*.py'):
        text = path.read_text()
        if 'Tree_Caldera' in text or re.search(r'craterpark\.v2 import .*\btrees\b|from \. import .*\btrees\b', text):
            users.add(path.relative_to(GAME / 'world').as_posix())
    assert users == {'regions/craterpark/v2/trees.py', 'regions/craterpark/v2/editor_floor.py',
                     'regions/hidamari/props.py', 'regions/hidamari/prop_parameters.py',
                     'regions/hidamari/prop_roster.py'}, users


def test_planted_only_inside_the_crater():
    """A crater whose crest is 120 m from the middle: every conifer stands inside it by the dressing's margin and its
    own crown."""
    site = ef.Site.flat(GROUND, GRID)
    site.inside = lambda x, z: 120. - np.hypot(x, z)
    site.foot = lambda x, z: 100. - np.hypot(x, z)
    _, summary = ef.build(scene(), GROUND, GRID, site, bake=False)
    assert summary['conifers'] > 10
    for name, items in summary['trees'].items():
        for x, z, _, _, scale in items:
            inside = float(site.inside(x / 100, z / 100))
            assert inside > ef.CREST_MARGIN + caldera.TREES[name][3] * scale - 1e-6, (name, inside)


PROPS = yori.OUT / 'hidamari' / 'props' / 'props.json'


@pytest.mark.skipif(not PROPS.exists(), reason='needs world.hidamari_props')
def test_fitted_trees_are_upright_textured_lodded_and_walk_through():
    props = json.loads(PROPS.read_text())
    for key, (_, _, height, crown) in caldera.TREES.items():
        info = props[key]
        assert abs(info['size'][2] - height) < .01, (key, 'height')
        assert info['crown'] <= crown * 1.02, (key, 'crown')
        assert info['boxes'] == 0, 'no collision'
        assert .5 < info['gain'] < 4, (key, 'gain')
        lods = info['lods']
        assert [s for _, s in lods] == [s for _, s, _ in caldera.LODS]
        tris = [t for t, _ in lods]
        assert tris[0] == info['triangles'] <= 12000 and all(a > b for a, b in zip(tris, tris[1:])), (key, tris)
        assert 100 <= tris[-1] <= 600, (key, 'last LOD', tris)
        for n in range(len(lods)):
            assert (PROPS.parent / (f'{key}.fbx' if n == 0 else f'{key}_LOD{n}.fbx')).stat().st_size > 1000
        assert (PROPS.parent / f'{key}.png').exists()
