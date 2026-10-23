"""Production graph declarations keep logical planners and each export independently owned."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import build

GAME = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('region_atomic_graph', GAME / 'region_exports.py')
graph = importlib.util.module_from_spec(spec)
spec.loader.exec_module(graph)


def logical(key='One'):
    return graph.LogicalAsset(key, GAME / 'world/regions/hidamari/plan_asset.py',
                              args=('--asset', key, '--city', 'city.json'))


def write_plan(out, key, pieces):
    root = out / 'planned_exports/fixture' / key
    root.mkdir(parents=True)
    value = dict(schema=1, parent=key, complete=True, triangle_limit=32768,
                 source_triangles=sum(count for _, count in pieces),
                 pieces=[dict(name=name, payload=name + '.npz', triangles=count) for name, count in pieces])
    (root / 'plan.json').write_text(json.dumps(value))
    return root


def test_cold_recipe_contains_required_planners_not_successful_empty_region(tmp_path):
    ctx = SimpleNamespace(out=tmp_path)
    steps = graph.steps(ctx, region='fixture', assets=[logical(), logical('Two')])
    assert [s.name for s in steps] == ['world.fixture.geometry.One', 'world.fixture.geometry.Two',
                                       'world.fixture.geometry', 'world.fixture.assembled']
    assert all(not s.replan and s.cache and s.commands[0].factory_startup and s.commands[0].threads == 3
               for s in steps[:2])
    assert steps[-2].replan and steps[-1].needs == ['world.fixture.geometry']
    assert steps[-2].reads == [s.products[0].name for s in steps[:2]]
    with pytest.raises(ValueError, match='Missing logical geometry'):
        steps[-1].commands[0].fn(ctx, None)
    assert not (tmp_path / 'atomic_regions').exists()


def test_completed_plan_discovers_per_piece_payloads_without_sibling_inputs(tmp_path):
    write_plan(tmp_path, 'One', [('One_cell_0_0', 12), ('One_cell_1_0', 24)])
    write_plan(tmp_path, 'Two', [('Two', 6)])
    ctx = SimpleNamespace(out=tmp_path)
    steps = graph.steps(ctx, region='fixture', assets=[logical(), logical('Two')])
    exports = [s for s in steps if '.export.' in s.name]
    assert len(exports) == 3
    for step in exports:
        assert step.cache and len(step.products) == 1
        payloads = [p for p in step.inputs if p.suffix == '.npz']
        assert len(payloads) == 1 and payloads[0].stem == step.name.split('.')[-1]
        assert not step.needs and not step.reads
        assert step.after == ['world.fixture.geometry']
    assert steps[-1].reads == [s.products[0].name for s in exports]
    build.check_modules(steps)


@pytest.mark.parametrize('pieces', [[('One', 32769)], [('One', 0)], [('One', 12), ('ONE', 12)]])
def test_bad_inventory_cannot_admit_unbounded_or_duplicate_exports(tmp_path, pieces):
    root = write_plan(tmp_path, 'One', pieces)
    with pytest.raises(ValueError): graph.inventory(root, 'One')


def test_changed_inventory_never_silently_assembles_the_old_roster(tmp_path):
    root = write_plan(tmp_path, 'One', [('One', 12)])
    ctx = SimpleNamespace(out=tmp_path)
    steps = graph.steps(ctx, region='fixture', assets=[logical()])
    value = json.loads((root / 'plan.json').read_text())
    value['pieces'][0].update(name='New', payload='New.npz')
    (root / 'plan.json').write_text(json.dumps(value))
    with pytest.raises(ValueError, match='roster changed'):
        steps[-1].commands[0].fn(ctx, None)
    assert not (tmp_path / 'atomic_regions').exists()
