"""Complete Village native membership refuses corrupted and foreign source products."""
import importlib.util
import json
from pathlib import Path

import pytest

from atelier.export_manifest import sha

GAME = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('village_atomic_products_test', GAME / 'village_atomic_products.py')
products = importlib.util.module_from_spec(spec); spec.loader.exec_module(products)


def fixture(out):
    root = out / 'village'; root.mkdir()
    assets = out / 'atomic_regions/village/assets'; assets.mkdir(parents=True)
    groups, receipts = {}, []
    for key in products.ASSETS:
        path = assets / (key + '.fbx'); path.write_bytes(key.encode())
        row = dict(name=key, triangles=12, collision_hulls=0, min=[0., 0., 0.], max=[1., 1., 1.],
                   uv_channels=['UVMap'], sha256=sha(path), geometry_sha256='a'*64)
        groups[key] = dict(source_triangles=12, source_collision_hulls=0, source_collision_vertices=[],
            collision='complex_as_simple' if key == 'Village_Ground' else 'simple_and_complex',
            slots=['VillagePalette'], pieces=[row])
        receipts.append(dict(schema=1, asset=key, primary=key + '.fbx', triangles=12, sha256=row['sha256'],
            bounds=[row['min'], row['max']], metadata=dict(slots=['VillagePalette'], collision_hulls=0,
                                                          uv_channels=['UVMap'], geometry_sha256='a'*64)))
    value = dict(schema=1, complete=True, parents=groups)
    library = dict(schema=1, complete=True, exports=receipts)
    def write():
        (root / 'atomic-manifest.json').write_text(json.dumps(value))
        (assets / 'manifest.json').write_text(json.dumps(library))
    write(); return value, library, write


def test_complete_village_retains_ground_and_nonblocking_zero_hull_prop_roles(tmp_path):
    fixture(tmp_path)
    groups = products.read(tmp_path)
    assert len(groups) == 12 and groups['Village_Ground']['collision'] == 'complex_as_simple'
    assert groups['Village_Planting']['collision'] == 'simple_and_complex'
    assert not groups['Village_Planting']['source_collision_hulls']


@pytest.mark.parametrize('changed', ['missing', 'extra', 'linked', 'bytes', 'budget', 'material', 'role',
                                    'hull-owner', 'family', 'receipt', 'uv', 'bounds'])
def test_native_inputs_refuse_incomplete_or_changed_bounded_members(tmp_path, changed):
    value, library, write = fixture(tmp_path)
    assets = tmp_path / 'atomic_regions/village/assets'
    group = value['parents']['Village_Planting']; row = group['pieces'][0]
    if changed == 'missing': (assets / 'Village_Planting.fbx').unlink()
    elif changed == 'extra': (assets / 'Foreign.fbx').write_bytes(b'keep')
    elif changed == 'linked':
        path = assets / 'Village_Planting.fbx'; path.unlink(); path.symlink_to(assets / 'Village_Ground.fbx')
    elif changed == 'bytes': (assets / 'Village_Planting.fbx').write_bytes(b'changed')
    elif changed == 'budget': row['triangles'] = 32769
    elif changed == 'material': group['slots'] = ['Other']
    elif changed == 'role': group['collision'] = 'complex_as_simple'
    elif changed == 'hull-owner': row['collision_hulls'] = 1
    elif changed == 'family': del value['parents']['Village_TeaHouse']
    elif changed == 'receipt': library['exports'] = []
    elif changed == 'uv': row['uv_channels'] = []
    elif changed == 'bounds': row['min'][0] = float('nan')
    write()
    with pytest.raises((ValueError, KeyError, OSError)): products.read(tmp_path)
