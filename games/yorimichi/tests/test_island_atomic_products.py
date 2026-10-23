"""Actual complete island assembled inventory is the sole native member admission."""
import copy
import importlib.util
import json
from pathlib import Path

import pytest

from atelier.export_manifest import sha

GAME = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('island_atomic_members', GAME / 'island_atomic_products.py')
products = importlib.util.module_from_spec(spec); spec.loader.exec_module(products)


def fixture(out):
    folder = out / 'atomic_regions/island'; assets = folder / 'assets'; assets.mkdir(parents=True)
    source = out / 'island-source-data'; source.mkdir()
    roster = [key for key in products.PARENTS if key in products.REQUIRED]
    (source / 'inventory.json').write_text(json.dumps(dict(schema=1, assets=roster)))
    parents, owners, receipts, sources = {}, {}, [], {}
    for key in roster:
        slots = list(products.MATERIALS[key]); path = assets / (key + '.fbx'); path.write_bytes(key.encode())
        tile = dict(name=key, triangles=1, polygons=1, collision_hulls=0, min=[0., 0., 0.], max=[1., 1., 0.])
        parents[key] = [key]
        owners[key] = dict(source_collision_hulls=0, matrix=products.IDENTITY, source_triangles=1,
                           source_polygons=1, slots=slots, pieces=[tile])
        receipts.append(dict(schema=1, asset=key, primary=path.name, sha256=sha(path), triangles=1,
            bounds=[tile['min'], tile['max']], metadata=dict(slots=slots, collision_hulls=0, polygons=1,
                                                          uv_channels=['UVMap'], geometry_sha256='a'*64)))
        sources[key] = dict(used_slots=slots, geometry_sha256='a'*64)
    logical = dict(schema=1, parents=parents, ownership=owners, exports=roster)
    manifest = dict(schema=1, complete=True, exports=receipts)
    (folder / 'receiving.json').write_text(json.dumps(dict(schema=1, complete=True, pieces=sources)))
    def write():
        (folder / 'logical-pieces.json').write_text(json.dumps(logical))
        (assets / 'manifest.json').write_text(json.dumps(manifest))
    write()
    return logical, manifest, write


def test_complete_roster_keeps_native_pieces_separate_and_ocean_nonblocking(tmp_path):
    fixture(tmp_path)
    groups = products.read(tmp_path)
    assert set(groups) == products.REQUIRED
    assert all(group['collision'] and group['cast_shadow'] for parent, group in groups.items() if parent != 'Sea')
    assert not groups['Sea']['collision'] and not groups['Sea']['cast_shadow']
    assert all(row['asset'].startswith(products.DESTINATION + '/')
               for group in groups.values() for row in group['pieces'])
    assert products.native_bounds(dict(min=[-1., -2., -3.], max=[4., 5., 6.])) == ([-100., -500., -300.], [400., 200., 600.])


@pytest.mark.parametrize('kind', ['missing', 'extra', 'linked', 'changed', 'slots', 'count', 'uv',
                                 'parent', 'frame', 'hulls', 'optional', 'over-budget', 'case-alias'])
def test_incomplete_or_changed_native_membership_refuses(tmp_path, kind):
    logical, manifest, write = fixture(tmp_path)
    assets = tmp_path / 'atomic_regions/island/assets'
    if kind == 'missing': (assets / 'Road.fbx').unlink()
    elif kind == 'extra': (assets / 'Foreign.fbx').write_bytes(b'keep')
    elif kind == 'linked':
        path = assets / 'Road.fbx'; path.unlink(); path.symlink_to(assets / 'Terrain.fbx')
    elif kind == 'changed': (assets / 'Road.fbx').write_bytes(b'changed')
    elif kind == 'slots': logical['ownership']['Road']['slots'] = ['Ground']
    elif kind == 'count': logical['ownership']['Road']['source_triangles'] = 2
    elif kind == 'uv': manifest['exports'][0]['metadata']['uv_channels'] = []
    elif kind == 'parent': del logical['parents']['Road']
    elif kind == 'frame': logical['ownership']['Road']['matrix'] = copy.deepcopy(products.IDENTITY); logical['ownership']['Road']['matrix'][0][3] = 1.
    elif kind == 'hulls': logical['ownership']['Road']['source_collision_hulls'] = 1
    elif kind == 'optional':
        path = tmp_path / 'island-source-data/inventory.json'
        path.write_text(json.dumps(dict(schema=1, assets=list(products.PARENTS))))
    elif kind == 'over-budget': logical['ownership']['Road']['pieces'][0]['triangles'] = 32769
    elif kind == 'case-alias': logical['parents']['Road'] += ['road']
    write()
    with pytest.raises((ValueError, FileNotFoundError)):
        products.read(tmp_path)
