"""Island logical projections and recipe boundaries preserve independent owners."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from atelier.build import check_modules
GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'world'))
from terrain_sources import ASSETS, project, publish  # noqa: E402

spec = importlib.util.spec_from_file_location('island_atomic_recipe', GAME / 'terrain_atomic_build.py')
recipe = importlib.util.module_from_spec(spec); spec.loader.exec_module(recipe)


def world():
    return dict(n=3, size=6., road=[[0, 0, 0], [1, 1, 0]], road_width=2.,
                southwest=dict(lane=[[0, 0], [1, 1]], boats=[1]),
                rail_runs=[[[0, 0, 0, 1, 0], [1, 1, 0, 1, 0]]], anchors=[[[0, 0, 3]], [[1, 1, 3]]])


def test_unrelated_wire_and_southwest_decorations_stop_at_selected_projection():
    w = world(); original = project(w, city=True)
    w['anchors'][0][0][0] = 9.; w['southwest']['boats'] = [2]
    current = project(w, city=True)
    assert original['Wires'] != current['Wires']
    assert [k for k in ASSETS if original[k] != current[k]] == ['Wires']
    w['road_width'] = 8.
    after_road = project(w, city=True)
    assert [k for k in ASSETS if current[k] != after_road[k]] == ['Road']


def test_explicit_city_mode_changes_only_far_and_water_inputs():
    yes, no = project(world(), city=True), project(world(), city=False)
    assert [k for k in ASSETS if yes[k] != no[k]] == ['FarHills', 'Sea']
    with pytest.raises(ValueError): project(world(), city=1)


def test_optional_geometry_is_explicit_without_reconstructing_siblings(tmp_path):
    w = world(); del w['southwest']; del w['rail_runs']
    publish(w, np.zeros((3, 3)), tmp_path, city=False)
    assert recipe.selected(tmp_path) == ('Terrain', 'Road', 'Wires', 'FarHills', 'Sea')
    assert json.loads((tmp_path / 'Lane.json').read_text())['enabled'] is False
    assert json.loads((tmp_path / 'Guardrail.json').read_text())['enabled'] is False


@pytest.mark.parametrize('foreign', ['file', 'link', 'directory'])
def test_source_projection_refuses_foreign_tree_before_writes(tmp_path, foreign):
    root = tmp_path / 'data'; root.mkdir()
    if foreign == 'file': (root / 'keep').write_bytes(b'keep')
    elif foreign == 'directory': (root / 'heightmap.npy').mkdir()
    else:
        target = tmp_path / 'outside'; target.write_bytes(b'keep')
        (root / 'Terrain.json').symlink_to(target)
    with pytest.raises(ValueError): publish(world(), np.zeros((3, 3)), root, city=True)
    assert not (root / 'inventory.json').exists()
    if foreign == 'link': assert target.read_bytes() == b'keep'


def test_cold_and_warm_recipe_has_only_selected_data_edges(tmp_path):
    ctx = SimpleNamespace(out=tmp_path)
    cold = recipe.steps(ctx)
    assert cold[0].replan and cold[0].cache
    assert cold[-2].name == 'world.terrain' and cold[-1].name == 'world.terrain.meshes'
    assert len([s for s in cold if s.name.startswith('world.island.geometry.')]) == 7
    check_modules(cold)
    publish(world(), np.zeros((3, 3)), tmp_path / 'island-source-data', city=True)
    steps = recipe.steps(ctx)
    planners = [s for s in steps if s.name.startswith('world.island.geometry.')]
    assert len(planners) == 7
    for step in planners:
        key = step.name.rsplit('.', 1)[1]
        assert step.cache and step.commands[0].factory_startup and step.commands[0].threads == 3
        assert step.reads == ['island.source.' + key] + (
            ['island.heightmap'] if key in ('Terrain', 'Lane') else
            ['terrain.FarHills.final'] if key == 'FarHills' else [])
        assert not any('terrain.fbx' in str(p) for p in step.inputs)
    check_modules(steps)


def test_constructors_are_original_statement_slices_without_inline_exports():
    fixture = GAME / 'tests/fixtures/island-terrain-predecessor-283329c07.txt'
    old = ast.parse(fixture.read_text())
    original = next(n for n in old.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
    current = ast.parse((GAME / 'world/build_terrain.py').read_text())
    functions = {n.name: n for n in current.body if isinstance(n, ast.FunctionDef)}
    assert set(k.lower() for k in ASSETS) <= set(functions)
    assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                   and n.func.attr.startswith('export') for n in ast.walk(current))
    # Every original shape loop/conditional appears unchanged inside one selected constructor.
    boundary = fixture.read_text().splitlines().index('    # export terrain fbx') + 1
    old_shapes = [n for n in original.body if isinstance(n, (ast.For, ast.If)) and n.lineno < boundary]
    actual_shapes = [n for key in ASSETS for n in functions[key.lower()].body if isinstance(n, (ast.For, ast.If))]
    assert sorted(ast.dump(n) for n in old_shapes) == sorted(ast.dump(n) for n in actual_shapes)
    original_helpers = {n.name: ast.dump(n) for n in old.body if isinstance(n, ast.FunctionDef)
                        and n.name in ('obj', 'coastal_colours', 'rock_surface', 'ocean_mesh')}
    assert {k: ast.dump(functions[k]) for k in original_helpers} == original_helpers


def test_production_planner_uses_wider_far_backdrop_cells_only(monkeypatch, tmp_path):
    tree = ast.parse((GAME / 'world/plan_terrain.py').read_text())
    selected = [node for node in tree.body if (isinstance(node, ast.FunctionDef) and node.name == 'plan_selected')
                or (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ('OPTIONS', 'CELL_METRES')
                                                       for t in node.targets))]
    calls = []
    def plan(obj, output, **options): calls.append(options); return options
    monkeypatch.setitem(sys.modules, 'region_mesh_parts', SimpleNamespace(plan=plan))
    scope = dict(ASSETS=ASSETS)
    exec(compile(ast.Module(body=selected, type_ignores=[]), '<actual-island-planner>', 'exec'), scope)
    for key in ASSETS:
        result = scope['plan_selected'](SimpleNamespace(name=key), tmp_path)
        assert result['cell_metres'] == (512. if key == 'FarHills' else 128.)
    with pytest.raises(ValueError): scope['plan_selected'](SimpleNamespace(name='Foreign'), tmp_path)
    assert len(calls) == len(ASSETS)


def test_predecessor_fixture_is_bound_to_exact_immutable_git_source():
    # SHA256 of git show 283329c07:games/yorimichi/world/build_terrain.py.
    fixture = GAME / 'tests/fixtures/island-terrain-predecessor-283329c07.txt'
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == 'c00634b7dadc6ff98fe87ee4759f3a471dbe24cdf4c0c3d935fa835f6f9d6108'
