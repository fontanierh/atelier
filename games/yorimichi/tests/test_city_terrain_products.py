"""Publish city stages without another carve or changing final emissions."""
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME/'world'))
import city_terrain_surface  # noqa: E402
from city_terrain_fixture import CASES, evaluate  # noqa: E402
from terrain_product import load  # noqa: E402
from test_city_terrain_fixture import same_calls  # noqa: E402


@pytest.mark.parametrize('case', [case for case in CASES if case not in ('other_surface', 'city_pad')])
def test_paired_capture_preserves_final_and_only_reverts_coarse_carve(case):
    baseline = json.loads((GAME/'tests/fixtures/terrain-city-r8.json').read_text())['cases'][case]
    paired = evaluate(case, capture_natural=True)
    np.testing.assert_allclose(paired['vertices'], baseline['vertices'], rtol=0., atol=1.e-12)
    np.testing.assert_allclose(paired['colours'], baseline['colours'], rtol=0., atol=1.e-12)
    assert paired['keys'] == baseline['keys']
    assert paired['faces'] == [tuple(face) for face in baseline['faces']]
    same_calls(paired['calls'], baseline['calls'])  # Same height/colour calls and exactly one local carve.
    natural, final = np.asarray(paired['natural']['vertices']), np.asarray(paired['vertices'])
    assert paired['natural']['faces'] == paired['faces']
    np.testing.assert_array_equal(natural[:, :2], final[:, :2])
    if 'refinement' in case:
        np.testing.assert_array_equal(natural, final)  # Preserve the original uncarved fine patches.
    else:
        # The coarse grid uses the explicit fixture carve; inset paving keeps
        # its independent height evaluation and +.013m lift in both stages.
        for face, key in zip(paired['faces'], paired['keys']):
            ids = np.asarray(face)
            expected = 0. if key.startswith('hd_flag') else -1.25+.0003*natural[ids, 0]
            np.testing.assert_allclose(final[ids, 2]-natural[ids, 2], expected, rtol=0., atol=1.e-12)


def test_air_station_pad_is_captured_before_both_local_operations():
    """Natural is pre-carve and pre-pad; final keeps main's carve-then-pad emission."""
    from zeppelin.layout import city_pad
    paired = evaluate('city_pad', capture_natural=True)
    plain = evaluate('city_pad')
    np.testing.assert_array_equal(np.asarray(paired['vertices']), np.asarray(plain['vertices']))
    np.testing.assert_array_equal(np.asarray(paired['colours']), np.asarray(plain['colours']))
    assert paired['keys'] == plain['keys']
    assert paired['faces'] == plain['faces']
    natural, final = np.asarray(paired['natural']['vertices']), np.asarray(paired['vertices'])
    assert paired['natural']['faces'] == paired['faces']
    np.testing.assert_array_equal(natural[:, :2], final[:, :2])
    origin_z = 35.5
    weight = np.asarray(city_pad(natural[:, 0], natural[:, 1], 0.)) / origin_z
    carve_only = -1.25 + .0003 * natural[:, 0]
    delta = final[:, 2] - natural[:, 2]
    assert weight.max() > .9 and weight.min() == 0.  # The case crosses the pad and its control area.
    flat = weight == 0.
    np.testing.assert_allclose(delta[flat], carve_only[flat], rtol=0., atol=1.e-12)
    assert np.any(np.abs(delta[~flat] - carve_only[~flat]) > 1.e-6)


def test_city_publication_copies_geometry_and_returns_original_attributed_mesh(tmp_path):
    result = evaluate('paving', capture_natural=True)
    natural = SimpleNamespace(name='HD_Terrain', **result['natural'])
    final = SimpleNamespace(name='HD_Terrain', vertices=result['vertices'], faces=result['faces'],
                            colours=result['colours'], keys=result['keys'], uvs={'explicit': 'untouched'})
    before = copy.deepcopy((vars(natural), vars(final)))
    calls = []
    def producer():
        calls.append(True)
        return natural, final
    assert city_terrain_surface.generate(producer, tmp_path) is final
    assert calls == [True]
    assert (vars(natural), vars(final)) == before
    for stage, surface in [('natural', natural), ('final', final)]:
        product = load(tmp_path/(stage+'.npz'), owner='HD_Terrain', stage=stage, city=True)
        np.testing.assert_array_equal(product.vertices, surface.vertices)
        assert product.polygons() == [list(face) for face in surface.faces]
        assert not product.vertices.flags.writeable
        with pytest.raises(ValueError, match='mode mismatch'):
            load(tmp_path/(stage+'.npz'), owner='HD_Streets', stage=stage, city=True)
    first = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    city_terrain_surface.generate(producer, tmp_path)
    assert first == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    scope = json.loads((tmp_path/'manifest.json').read_text())['natural_scope']
    assert 'coarse-grid railway carve' in scope and 'air-station apron' in scope


def test_publication_rejects_another_surface_owner(tmp_path):
    other = SimpleNamespace(name='HD_Streets')
    with pytest.raises(ValueError, match='explicit HD_Terrain owner'):
        city_terrain_surface.generate(lambda: (other, other), tmp_path)
    assert not list(tmp_path.iterdir())


def test_normal_recipe_owns_all_city_ground_products(tmp_path):
    from atelier import build, build_products
    recipe = build.load_recipe('yorimichi')
    graph = build_products.Graph(recipe.steps(SimpleNamespace(game='yorimichi', out=tmp_path, uproject=None)))
    step = graph.by_name['world.hidamari.geometry.HD_Terrain']
    for stage in ('natural', 'final', 'provenance'):
        assert graph.owners['terrain.HD_Terrain.'+stage] == step.name
    assert GAME/'world/city_terrain_surface.py' in step.inputs
    assert GAME/'world/terrain_product.py' in step.inputs
    assert step.heavy and step.cache
