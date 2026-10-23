"""All logical city parents stay separately imported bounded assets with exact ownership."""
import importlib
import json
from pathlib import Path

import numpy as np
import pytest

from atelier import mesh_ir
from atelier.export_manifest import publish_receipt, sha

GAME = Path(__file__).resolve().parents[1]


@pytest.fixture
def owner(monkeypatch):
    monkeypatch.syspath_prepend(str(GAME))
    monkeypatch.syspath_prepend(str(GAME / 'world'))
    return importlib.import_module('city_atomic_products')


def prepared(out, key):
    root = out / 'planned_exports/hidamari' / key
    root.mkdir(parents=True)
    matrix = np.eye(4)
    hull_matrix = matrix.copy(); hull_matrix[1, 3] = 2
    hull = dict(vertices=[[0,0,0], [1,0,0], [0,1,0], [0,0,1]],
                faces=[[0,1,2], [0,3,1], [0,2,3], [1,3,2]], matrix=hull_matrix.tolist())
    piece = dict(positions=[[0,0,0], [1,0,0], [0,1,0]], faces=[[0,1,2]], normals=[[0,0,1]]*3,
                 materials=[0], smooth=[False], uvs=[('UVMap', [[0,0], [1,0], [0,1]])], colours=[])
    payload = mesh_ir.encode(piece, key=key, slots=['Palette'], matrix=matrix.tolist(), options={}, collisions=[hull])
    path = root / (key + '.npz'); mesh_ir.write(path, payload)
    row = dict(name=key, payload=path.name, sha256=sha(path), triangles=1, polygons=1,
               min=[0,0,0], max=[1,1,0], collision_hulls=1)
    value = dict(schema=1, parent=key, complete=True, triangle_limit=32768, source_triangles=1,
                 source_polygons=1, source_collision_hulls=1, slots=['Palette'], matrix=matrix.tolist(), pieces=[row])
    (root / 'plan.json').write_text(json.dumps(value))
    export = out / 'individual' / key; export.mkdir(parents=True)
    (export / (key + '.fbx')).write_bytes(('mesh-' + key).encode())
    receipt = publish_receipt(export, key=key, primary=key + '.fbx', triangles=1,
                              bounds=[[0,0,0], [1,1,0]], metadata=dict(geometry_sha256=row['sha256'],
                              slots=['Palette'], polygons=1, collision_hulls=1, uv_channels=['UVMap']))
    return root, export, receipt


def test_source_metadata_retains_whole_authored_hull_frame_and_logical_bounds(tmp_path, owner):
    root, _, receipt = prepared(tmp_path, 'HD_ClockHall')
    row = owner.source_record(root, {'HD_ClockHall': receipt})
    assert row['source_bounds'] == dict(min=[0,0,0], max=[1,1,0])
    assert row['source_collision_vertices'] == [[[0,-200,0], [100,-200,0], [0,-300,0], [0,-200,100]]]
    assert row['source_material_slots'] == ['Palette']
    assert row['tiles'][0]['name'] == 'HD_ClockHall'


def test_same_counts_do_not_admit_an_export_of_another_geometry_input(tmp_path, owner):
    root, _, receipt = prepared(tmp_path, 'HD_ClockHall')
    receipt['metadata']['geometry_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='geometry input'):
        owner.source_record(root, {'HD_ClockHall': receipt})


def test_all86_assembly_keeps_small_assets_separate_and_unchanged_files_current(tmp_path, owner):
    from atelier.export_assembly import assemble, Item
    items = []
    for key in owner.SOURCES:
        _, export, _ = prepared(tmp_path, key)
        items.append(Item(key, export))
    assemble(items, tmp_path / 'atomic_regions/hidamari/assets')
    result = owner.assemble(tmp_path, lambda _: None)
    assert len(owner.production_groups(result)) == 86
    destination = tmp_path / 'city_surface_tiles/v1_128m'
    before = {str(p.relative_to(destination)): (sha(p), p.stat().st_mtime_ns) for p in destination.rglob('*.fbx')}
    assert len(before) == 86
    assert result['sources']['HD_ClockHall']['tiles'][0]['name'] == 'HD_ClockHall'
    owner.assemble(tmp_path, lambda _: None)
    assert before == {str(p.relative_to(destination)): (sha(p), p.stat().st_mtime_ns) for p in destination.rglob('*.fbx')}
    foreign = destination / 'Foreign.fbx'; foreign.write_bytes(b'preserve me')
    manifest = (destination / 'manifest.json').read_bytes()
    with pytest.raises(ValueError, match='Foreign'):
        owner.assemble(tmp_path, lambda _: None)
    assert foreign.read_bytes() == b'preserve me'
    assert (destination / 'manifest.json').read_bytes() == manifest


def test_small_native_name_is_owned_only_in_canonical_tag_and_budget_is_still_required(owner):
    key = 'HD_ClockHall'
    path = owner.DESTINATION + '/' + key + '.' + key
    previous = owner.owned_tiles([path, '/Game/Japan/Assets/' + key + '.' + key], owner.DESTINATION)
    assert previous[key] == [dict(name=key, asset=path)]
    assert owner.obsolete_assets(previous, {}, owner.DESTINATION) == [path]
    assert not any(owner.owned_tiles([path], owner.DESTINATION + '_Other').values())


@pytest.mark.parametrize('key,material', [
    ('HD_ArcadeTree', 'M_Arcade'), ('HD_NorthMountains', 'M_NorthMountains'),
    ('HD_NorthRockA', 'MI_NorthRockCaps'), ('HD_PlazaFloor', 'M_PlazaPaving'),
    ('HD_ArcadeFloor', 'M_ArcadePaving'), ('HD_Sea', 'M_HarborWater'),
    ('HD_Boat', 'M_Harbor'), ('HD_InlandWater', 'M_PondWater'), ('HD_House_A', 'M_Village')])
def test_materials_follow_logical_parent_not_piece_suffix(owner, key, material):
    # Pick the actual committed spelling for generated letter/number families.
    if key not in owner.SOURCES:
        prefix = 'HD_NorthRock' if key.startswith('HD_NorthRock') else 'HD_House_'
        key = next(name for name in owner.SOURCES if name.startswith(prefix))
    assert owner.piece_material_paths(key, ['Palette']) == {'Palette': '/Game/Japan/Materials/' + material}
