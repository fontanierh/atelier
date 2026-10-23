"""Disabled-owner admission, unchanged canonical query data and independent LOD tasks."""
import ast
import importlib.util
import json
from pathlib import Path
import random
import sys
from types import SimpleNamespace

import pytest

from atelier.build import check_modules

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'world'))
import yori  # noqa: E402,F401
from hidamari_stable.atomic_sources import publish  # noqa: E402
from hidamari_stable.catalogue import SOURCES, PARENTS, context_key, selected  # noqa: E402
from hidamari_stable.query_samples import Recorder, Lookup  # noqa: E402
import numpy as np  # noqa: E402


def contexts():
    return dict(schema=1, complete=True, contexts={context_key(key): json.loads(json.dumps(random.Random(i).getstate()))
        for i, key in enumerate(SOURCES)})


def test_disabled_production_owner_refuses_before_any_generated_artifact(tmp_path):
    output = tmp_path / 'output'
    with pytest.raises(ValueError, match='disabled'): publish(contexts(), output, enabled=False)
    assert not output.exists()


def test_semantic_random_state_edit_changes_only_its_selected_product(tmp_path):
    value = contexts(); output = tmp_path / 'output'; publish(value, output, enabled=True)
    before = {path.name: path.read_bytes() for path in output.iterdir()}
    key = SOURCES[0]; value['contexts'][context_key(key)] = json.loads(json.dumps(random.Random(123).getstate()))
    publish(value, output, enabled=True)
    assert [path.stem for path in output.iterdir() if before[path.name] != path.read_bytes()] == [key]


def test_incomplete_semantic_or_lod_state_is_not_synthesized(tmp_path):
    value = contexts(); del value['contexts'][context_key(SOURCES[-1])]
    with pytest.raises(ValueError, match='Incomplete'): publish(value, tmp_path / 'output', enabled=True)
    assert not (tmp_path / 'output').exists()


def test_invalid_last_context_refuses_before_any_current_product_is_replaced(tmp_path):
    value = contexts(); value['contexts'][context_key(SOURCES[-1])] = [3, [], None]
    with pytest.raises(ValueError, match='Invalid'): publish(value, tmp_path / 'output', enabled=True)
    assert not (tmp_path / 'output').exists()


def test_old_anchor_query_and_collision_body_is_unchanged():
    fixture = GAME / 'tests/fixtures/stable-predecessor-283329c07.txt'
    old = next(n for n in ast.parse(fixture.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == 'placements')
    current = next(n for n in ast.parse((GAME / 'world/regions/hidamari_stable/placement_data.py').read_text()).body
                   if isinstance(n, ast.FunctionDef) and n.name == 'placements')
    current.args.args.pop(); current.body.pop(0)
    assert ast.dump(current, include_attributes=False) == ast.dump(old, include_attributes=False)


def test_barn_shell_extraction_preserves_the_exact_immutable_body_and_call_order():
    original = ast.parse((GAME / 'tests/fixtures/stable-predecessor-283329c07.txt').read_text())
    current = ast.parse((GAME / 'world/regions/hidamari_stable/build.py').read_text())
    before = {node.name: node for node in original.body if isinstance(node, ast.FunctionDef)}
    after = {node.name: node for node in current.body if isinstance(node, ast.FunctionDef)}
    shell = after['barn_shell']
    assert ast.dump(ast.Module(body=shell.body, type_ignores=[]), include_attributes=False) == ast.dump(
        ast.Module(body=before['barn'].body[:-1], type_ignores=[]), include_attributes=False)
    assert [ast.unparse(node) for node in after['barn'].body] == ['barn_shell(m, lod)', 'roof(m, lod)']
    for key in set(before) - {'barn', 'main', 'export_glb'}:
        assert ast.dump(before[key], include_attributes=False) == ast.dump(after[key], include_attributes=False), key


def test_all_semantic_lods_are_complete_factory_tasks_without_sibling_export_reads(tmp_path):
    spec = importlib.util.spec_from_file_location('stable_atomic_recipe_test', GAME / 'stable_atomic_build.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    steps = module.steps(SimpleNamespace(out=tmp_path))
    planners = [step for step in steps if step.name.startswith('world.hidamari_stable.geometry.')]
    assert len(planners) == len(SOURCES) == 24 and len(PARENTS) == 10
    assert all(step.explicit for step in steps)
    for step in planners:
        key = step.name.rsplit('.', 1)[1]
        assert selected(key)[0] in PARENTS
        assert step.cache and step.commands[0].factory_startup and step.commands[0].threads == 3
        assert step.reads == ['stable.source.' + key] + (
            ['stable.queries.' + key]
            if key in ('SM_HS_Road', 'SM_HS_RoadSign') else [])
        assert not any('exports' in read or 'atomic' in read for read in step.reads)
    check_modules(steps)


def test_height_queries_retain_float64_bits_and_refuse_unseen_points():
    sample = lambda x, y, carved=True: np.asarray(x, dtype='f8') * .123456789123 + np.asarray(y, dtype='f8')
    recorder = Recorder(sample)
    x, y = np.array([1., -0.]), np.array([2., 3.])
    expected = recorder(x, y, carved=False)
    current = Lookup(json.loads(json.dumps(recorder.value())))
    assert current(x, y, carved=False).tobytes() == expected.tobytes()
    current.complete()
    with pytest.raises(ValueError, match='undeclared'): current(x + .000000001, y, carved=False)
    with pytest.raises(ValueError, match='undeclared'): current(x, y, carved=True)


def test_stale_selected_query_does_not_silently_survive_constructor_changes():
    recorder = Recorder(lambda x, y, carved=True: np.asarray(x, dtype='f8') + np.asarray(y, dtype='f8'))
    recorder([1.], [2.]); recorder([2.], [3.])
    current = Lookup(recorder.value()); current([1.], [2.])
    with pytest.raises(ValueError, match='unused'): current.complete()


def test_native_base_admission_uses_lod0_when_an_assembled_lower_lod_extends_outside_it():
    source = GAME / 'unreal/Scripts/import_stable_atomic.py'
    tree = ast.parse(source.read_text())
    tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name in ('cm_bounds', 'lod_bounds_match', 'validate_raw')]
    selected_lods = []
    def observed(mesh, lod):
        selected_lods.append(lod)
        return json.dumps({'min': [0, -200, 0], 'max': [100, 0, 300]} if lod == 0 else
                          {'min': [-1000, -2000, -3000], 'max': [1000, 2000, 3000]})
    namespace = dict(json=json, collision_options_match=lambda _: True, unreal=SimpleNamespace(HidamariStableMeshComponent=SimpleNamespace(measure_lod_bounds=observed)),
        glb_mesh_validation=SimpleNamespace(source_matches=lambda *args: True, options_match=lambda *args: True))
    exec(compile(tree, str(source), 'exec'), namespace)
    class Mesh:
        def get_num_triangles(self, _): return 4
        def get_num_lods(self): return 3
        def get_editor_property(self, _):
            return [SimpleNamespace(get_editor_property=lambda _: 'M_HS_Stable')]
        def get_bounding_box(self): raise AssertionError('Asset union bounds must not replace selected LOD0')
    row = dict(name='SM_HS_Barn_LOD0', triangles=4, slots=['M_HS_Stable'], bounds=[[0, 0, 0], [1, 2, 3]])
    assert namespace['validate_raw'](Mesh(), 'source.glb', row, 'out') and selected_lods == [0]
    assert not namespace['lod_bounds_match'](Mesh(), row['bounds'], 1)
    assert selected_lods == [0, 1]
