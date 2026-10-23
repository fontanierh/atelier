"""Keep owned mountain products and attributed export on the same carve."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME/'world'))
import yori  # noqa: E402,F401
import north_mountain_surface  # noqa: E402
from hidamari import mountains  # noqa: E402
from terrain_product import load  # noqa: E402
from terrain_sheet_fixture import inputs  # noqa: E402
from train import earthworks  # noqa: E402


@pytest.mark.parametrize('carved', [False, True])
def test_publication_keeps_both_stages_and_original_export_attributes(tmp_path, monkeypatch, carved):
    natural = inputs()
    before = {k: v.copy() for k, v in natural.items() if isinstance(v, np.ndarray)}
    ln = earthworks.Line({'samples': [
        dict(s=float(s), x=float(s), y=0., rail_z=100., ground_z=104., **{'class': 'cutting'})
        for s in range(0, 410, 10)]})
    monkeypatch.setattr(earthworks, 'line', lambda: None)
    final = earthworks.sheet(natural, step=6., ln=ln if carved else None)
    final_before = {k: v.copy() for k, v in final.items() if isinstance(v, np.ndarray)}
    calls = []
    def sheets(sampler):
        calls.append(sampler)
        return natural, final
    monkeypatch.setattr(mountains, 'sheets', sheets)
    sampler = object()
    assert north_mountain_surface.generate(sampler, tmp_path) is final
    assert calls == [sampler]
    for stage, sheet in [('natural', natural), ('final', final)]:
        product = load(tmp_path/(stage+'.npz'), owner='HD_NorthMountains', stage=stage, city=True)
        np.testing.assert_array_equal(product.vertices, sheet['vertices'])
        np.testing.assert_array_equal(product.triangles(), sheet['faces'])
        assert product.polygons() == sheet['faces'].tolist()
        assert not product.vertices.flags.writeable
        with pytest.raises(ValueError, match='mode mismatch'):
            load(tmp_path/(stage+'.npz'), owner='HD_NorthGate', stage=stage, city=True)
    for key, value in before.items():
        np.testing.assert_array_equal(natural[key], value)
    for key, value in final_before.items():
        np.testing.assert_array_equal(final[key], value)
    first = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    north_mountain_surface.generate(sampler, tmp_path)
    assert first == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert json.loads((tmp_path/'manifest.json').read_text())['owner'] == 'HD_NorthMountains'


def test_existing_mesh_adapter_returns_the_final_sheet(monkeypatch):
    natural, final = object(), object()
    calls = []
    def sheets(sampler):
        calls.append(sampler)
        return natural, final
    monkeypatch.setattr(mountains, 'sheets', sheets)
    sampler = object()
    assert mountains.mesh(sampler) is final
    assert calls == [sampler]


def test_sheet_boundary_preserves_authored_inputs_to_one_carve(monkeypatch):
    axes = np.array([40., 45., 50.]), np.array([-5., 0., 5.])
    x, y = np.meshgrid(*axes)
    z = 106.+.03*x+.02*y+.01*x*y
    monkeypatch.setattr(mountains, 'BOUNDS', (40., -5., 50., 5.))
    monkeypatch.setattr(mountains, 'STEP', 5.)
    monkeypatch.setattr(mountains, 'surface_grid', lambda sampler: (x, y, z))
    monkeypatch.setattr(mountains, 'snow', lambda x, y, sampler: np.full_like(x, .75))
    monkeypatch.setattr(mountains, 'apron_grids', lambda xs, ys: [])
    # The city's north edge (built HD_Terrain knots) lies outside this grid, so no vertex is inserted or snapped.
    from hidamari import layout
    monkeypatch.setattr(layout, 'city_north_edge', lambda: (np.array([300., 1420.]), np.array([0., 0.])))
    from megapark import gate
    monkeypatch.setattr(gate, 'cell_inside', lambda x, y, step: x == 45. and y == 0.)
    calls = []
    final = object()
    def carve(sheet):
        calls.append(sheet)
        return final
    monkeypatch.setattr(earthworks, 'sheet', carve)
    natural, actual_final = mountains.sheets(object())
    assert actual_final is final and calls == [natural]
    np.testing.assert_array_equal(natural['vertices'], np.stack([x, y, z], -1).reshape(-1, 3)[:8])
    np.testing.assert_array_equal(natural['faces'],
                                  [[0, 1, 4], [0, 4, 3], [1, 2, 5], [1, 5, 4], [3, 4, 7], [3, 7, 6]])
    assert natural['colours'].shape == (8, 4) and natural['normals'].shape == (8, 3)
    np.testing.assert_array_equal(natural['colours'][:, 3], .75)
    dy, dx = np.gradient(z, 5., 5.)
    expected_normals = np.stack([-dx, -dy, np.ones_like(z)], -1)
    expected_normals /= np.linalg.norm(expected_normals, axis=-1, keepdims=True)
    np.testing.assert_array_equal(natural['normals'], expected_normals.reshape(-1, 3)[:8])


def test_sheet_first_row_takes_the_city_north_edge_polyline(monkeypatch):
    """The foothills' first row carries the city's edge knots and its own edge vertices sit on that polyline, so
    both meshes share one edge; each first-row cell is still covered exactly once."""
    axes = np.array([40., 45., 50.]), np.array([-5., 0., 5.])
    x, y = np.meshgrid(*axes)
    z = 106.+.03*x+.02*y+.01*x*y
    monkeypatch.setattr(mountains, 'BOUNDS', (40., -5., 50., 5.))
    monkeypatch.setattr(mountains, 'STEP', 5.)
    monkeypatch.setattr(mountains, 'surface_grid', lambda sampler: (x, y, z))
    monkeypatch.setattr(mountains, 'snow', lambda x, y, sampler: np.full_like(x, .75))
    monkeypatch.setattr(mountains, 'apron_grids', lambda xs, ys: [])
    knots = np.array([40., 42., 45., 47.5, 50.]), np.array([100., 101., 102., 101.5, 103.])
    from hidamari import layout
    monkeypatch.setattr(layout, 'city_north_edge', lambda: knots)
    from megapark import gate
    monkeypatch.setattr(gate, 'cell_inside', lambda x, y, step: False)
    monkeypatch.setattr(earthworks, 'sheet', lambda sheet: sheet)
    natural, _ = mountains.sheets(object())
    V, F = natural['vertices'], natural['faces']
    edge = V[np.isclose(V[:, 1], -5.)]
    edge = edge[np.argsort(edge[:, 0])]
    np.testing.assert_array_equal(edge[:, 0], knots[0])
    np.testing.assert_allclose(edge[:, 2], knots[1])
    # Interior rows are untouched.
    np.testing.assert_array_equal(V[np.isclose(V[:, 1], 0.)][:, 2], z[1])
    tri = V[F]
    area = .5*((tri[:, 1, 0]-tri[:, 0, 0])*(tri[:, 2, 1]-tri[:, 0, 1])-(tri[:, 2, 0]-tri[:, 0, 0])*(tri[:, 1, 1]-tri[:, 0, 1]))
    assert (area > 0).all()                       # counter-clockwise, none degenerate
    assert np.isclose(area.sum(), 100.)           # the four 5 m cells, each covered exactly once
    assert natural['colours'].shape == (len(V), 4) and natural['normals'].shape == (len(V), 3)
    np.testing.assert_allclose(np.linalg.norm(natural['normals'], axis=1), 1.)
    # Placement (height()) stands on exactly these triangles, inside every face of every row.
    w = np.random.default_rng(3).dirichlet((1., 1., 1.), 25)
    points = np.einsum('kj,fjd->fkd', w, tri).reshape(-1, 3)
    np.testing.assert_allclose(mountains.height(points[:, 0], points[:, 1], object(), carved=False), points[:, 2],
                               atol=1e-9)


def test_normal_city_recipe_owns_all_mountain_products(tmp_path):
    from atelier import build, build_products
    recipe = build.load_recipe('yorimichi')
    graph = build_products.Graph(recipe.steps(SimpleNamespace(game='yorimichi', out=tmp_path, uproject=None)))
    step = graph.by_name['world.hidamari.geometry.HD_NorthMountains']
    for stage in ('natural', 'final', 'provenance'):
        name = 'terrain.HD_NorthMountains.'+stage
        assert graph.owners[name] == step.name
    assert step.heavy and step.cache
    assert GAME/'world/north_mountain_surface.py' in step.inputs
    assert GAME/'world/terrain_product.py' in step.inputs
