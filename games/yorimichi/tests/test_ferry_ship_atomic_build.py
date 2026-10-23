"""The ferry ship hook exposes separate planners and validates complete file-only assembly."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier.atomic_files import atomic_json
from atelier.export_manifest import publish_receipt

GAME = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_ship_graph_has_selected_factories_complete_auxiliary_data_and_cached_collision(tmp_path):
    module = load('ferry_atomic_recipe_test', GAME / 'ferry_ship_atomic_build.py')
    sources = load('ferry_sources_recipe_test', GAME / 'world/regions/ferry/ship_sources.py')
    rows = {row.name: row for row in module.steps(SimpleNamespace(out=tmp_path))}
    for key in sources.BUILDERS:
        step = rows['world.ferry_ship.geometry.' + key]
        assert step.cache and step.heavy
        assert step.reads == ['ferry_ship.source.' + key]
        assert {product.name for product in step.products} == {'ferry_ship.geometry.' + key, 'ferry_ship.query.' + key}
        command, = step.commands
        assert command.factory_startup and command.threads == 3
        assert '--asset' in command.args and key in command.args
        assert GAME / 'assets/vehicles/ferry/build.py' not in step.inputs
    collision = rows['world.ferry_ship.collision']
    assert collision.cache and collision.commands[0].factory_startup and collision.commands[0].threads == 3
    assert collision.reads == ['ferry_ship.source.FY_Collision', 'ferry_ship.collision_data']
    assert GAME / 'assets/vehicles/ferry/build.py' not in collision.inputs
    assert rows['world.ferry_ship.geometry'].replan
    audit = rows['world.ferry_ship.audit']
    assert {product.name for product in audit.products} == {'ferry_ship.audit', 'ferry_ship.collision_data', 'ferry_ship.deck_layout'}


def fixture(tmp_path):
    module = load('ferry_atomic_products_test', GAME / 'ferry_ship_atomic_products.py')
    groups, ownership, meshes = {}, {}, {}
    for key in module.sources.BUILDERS:
        names = [key + '_PieceA', key + '_PieceB'] if key == 'FY_Hull' else [key]
        groups[key] = names
        pieces = []
        for name in names:
            folder = tmp_path / 'exports/world.ferry_ship.export' / name
            folder.mkdir(parents=True); (folder / (name + '.fbx')).write_bytes(name.encode())
            publish_receipt(folder, key=name, primary=name + '.fbx', triangles=12, bounds=[[0, 0, 0], [1, 1, 1]])
            pieces.append(dict(name=name, triangles=12, min=[0, 0, 0], max=[1, 1, 1]))
        ownership[key] = dict(source_triangles=12 * len(names), source_collision_hulls=0, pieces=pieces)
        meshes[key] = dict(triangles=12 * len(names), vertices=8, materials=['test'], min=[0, 0, 0], max=[1, 1, 1], open_edges=0, flipped_parts=0)
    collision = tmp_path / 'exports/world.ferry_ship.collision/FY_Collision'
    collision.mkdir(parents=True); (collision / 'FY_Collision.fbx').write_bytes(b'whole authored collision')
    publish_receipt(collision, key='FY_Collision', primary='FY_Collision.fbx', triangles=12,
                    bounds=[[0, 0, 0], [1, 1, 1]], metadata=dict(collision_hulls=3))
    atomic_json(tmp_path / 'atomic_regions/ferry_ship/logical-pieces.json', dict(schema=1, parents=groups, ownership=ownership))
    atomic_json(tmp_path / 'ferry/ship-audit.json', dict(schema=1, complete=True, meshes=meshes,
        **{key: {} for key in ('dimensions', 'boarding_openings', 'decks', 'stair', 'deck_audit')}))
    atomic_json(tmp_path / 'ferry/deck_layout.json', {})
    atomic_json(tmp_path / 'ferry/ship-source-data/FY_Hull.json', dict(materials=dict(test=[[1, 2, 3], .5, 0])))
    return module


def test_assembly_copies_complete_physical_roster_and_keeps_logical_identity(tmp_path):
    module = fixture(tmp_path)
    value = module.assemble(tmp_path)
    assert 'FY_Hull' not in value['meshes']
    assert value['meshes']['FY_Hull_PieceA']['logical_parent'] == 'FY_Hull'
    assert value['logical_meshes']['FY_Hull']['triangles'] == 24
    assert value['collision']['convex_hulls'] == 3
    files = tmp_path / 'ferry/atomic-assets'
    assert not (files / 'FY_Hull.fbx').exists()
    assert (files / 'FY_Hull_PieceA.fbx').read_bytes() == b'FY_Hull_PieceA'
    old = (files / 'FY_Hull_PieceA.fbx').stat().st_mtime_ns
    module.assemble(tmp_path)
    assert (files / 'FY_Hull_PieceA.fbx').stat().st_mtime_ns == old


@pytest.mark.parametrize('defect', ['missing', 'corrupt', 'foreign', 'incomplete'])
def test_bad_assembly_refuses_before_destination_mutation(tmp_path, defect):
    module = fixture(tmp_path)
    path = tmp_path / 'exports/world.ferry_ship.export/FY_Hull_PieceA/FY_Hull_PieceA.fbx'
    if defect == 'missing': path.unlink()
    elif defect == 'corrupt': path.write_bytes(b'changed')
    elif defect == 'foreign': path.with_name('foreign.fbx').write_bytes(b'foreign')
    else:
        metadata = tmp_path / 'atomic_regions/ferry_ship/logical-pieces.json'
        value = json.loads(metadata.read_text()); del value['parents']['FY_Masts']; atomic_json(metadata, value)
    with pytest.raises((ValueError, FileNotFoundError)):
        module.assemble(tmp_path)
    assert not (tmp_path / 'ferry/atomic-assets').exists()
