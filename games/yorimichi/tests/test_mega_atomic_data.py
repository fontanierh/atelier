"""A final-surface data projection stops unrelated world edits before mesh export."""
import importlib
import importlib.util
from pathlib import Path

import numpy as np
import pytest
from types import SimpleNamespace


@pytest.fixture
def data(monkeypatch):
    world = Path(__file__).resolve().parents[1] / 'world'
    monkeypatch.syspath_prepend(str(world))
    monkeypatch.syspath_prepend(str(world / 'regions'))
    return importlib.import_module('mega.trail_data')


def test_projection_preserves_original_ordered_final_surface_samples(data):
    from village.layout import upper_surface
    path = np.array([[0., 0., 1.], [2., 1., 2.], [4., 0., 3.]])
    heights = np.arange(49, dtype=float).reshape(7, 7)
    tangent = np.gradient(path[:, :2], axis=0)
    tangent /= np.linalg.norm(tangent, axis=1)[:, None]
    normal = np.column_stack([-tangent[:, 1], tangent[:, 0]])
    expected = []
    # Frozen original producer loop, independent of the new projection helper.
    for i in range(len(path) - 1):
        for side in [-1, 1]:
            points = []
            for k, offset in [(i, 0), (i + 1, 0), (i + 1, side * 1.35), (i, side * 1.35)]:
                p = path[k, :2] + normal[k] * offset
                points.append((*p, float(upper_surface(heights, *p)) + .045))
            if side < 0:
                points.reverse()
            expected.append(points)
    actual = data.project({'mega': {'trail': path.tolist()}}, heights)
    assert np.array_equal(actual['polygons'], expected)


def test_unconsumed_world_fields_and_remote_height_samples_do_not_change_product(data):
    world = {'mega': {'trail': [[0., 0., 0.], [2., 0., 0.], [4., 0., 0.]]}}
    heights = np.zeros((21, 21))
    original = data.project(world, heights)
    world['instances'] = {'UnrelatedHouse': [[-200, 200, 30]]}
    world['mega']['unconsumed_annotation'] = 'new annotation'
    heights[0, 0] = 100
    assert data.project(world, heights) == original
    heights[10, 10] = 1
    assert data.project(world, heights) != original


def test_invalid_route_refuses_before_publication(data):
    with pytest.raises(ValueError, match='tangent'):
        data.project({'mega': {'trail': [[0., 0., 0.], [0., 0., 0.]]}}, np.zeros((3, 3)))


def test_ride_extraction_preserves_complete_original_construction_ast():
    import ast
    root = Path(__file__).resolve().parents[1] / 'world/regions/mega'
    original = ast.parse((root / 'build.py').read_text())
    main = next(n for n in original.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    start = next(i for i, n in enumerate(main.body) if isinstance(n, ast.Assign)
                 and ast.unparse(n) == "m = Mesh('Mega_Ramp')")
    stop = next(i for i, n in enumerate(main.body) if isinstance(n, ast.Assign)
                and ast.unparse(n) == 'objects = {}')
    moved = ast.parse((root / 'ride.py').read_text())
    build = next(n for n in moved.body if isinstance(n, ast.FunctionDef) and n.name == 'build')
    assert [ast.dump(n) for n in main.body[start:stop]] == [ast.dump(n) for n in build.body[1:-1]]
    assert ast.unparse(build.body[-1]) == 'return (m, trim)'


def test_ride_and_trim_do_not_depend_on_trail_or_world_data(tmp_path):
    game = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('mega_atomic_recipe', game / 'mega_build.py')
    recipe = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recipe)
    steps = {s.name: s for s in recipe.steps(SimpleNamespace(out=tmp_path.resolve()))}
    for key in ['Mega_Ramp', 'Mega_Trim']:
        step = steps['world.mega.geometry.' + key]
        assert not step.needs and not step.reads
        assert game / 'world/regions/mega/ride.py' in step.inputs
        assert game / 'world/regions/mega/trail_data.py' not in step.inputs
        assert tmp_path / 'heightmap.npy' not in step.inputs
    trail = steps['world.mega.geometry.Mega_Trail']
    assert trail.reads == ['mega.trail_data']
    assert game / 'world/regions/mega/ride.py' not in trail.inputs
    assert game / 'world/regions/mega/ramp.py' not in trail.inputs
    assert steps['world.mega.trail_data'].needs == ['world.layout']
