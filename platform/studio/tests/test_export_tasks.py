"""Atomic mesh products cannot certify an entire region or hide sibling writes."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from atelier import export_tasks as tasks


def exported(tmp_path):
    root = tmp_path / 'asset'; root.mkdir()
    (root / 'Part.fbx').write_bytes(b'fixture mesh')
    tasks.publish_receipt(root, key='Part', primary='Part.fbx', triangles=12,
                          bounds=[[0, 0, 0], [1, 1, 1]])
    return root


def test_receipt_requires_exact_single_mesh_membership(tmp_path):
    root = exported(tmp_path)
    assert tasks.validate(root, key='Part')['triangles'] == 12
    (root / 'Unrelated.fbx').write_bytes(b'not owned')
    with pytest.raises(ValueError, match='membership'):
        tasks.validate(root, key='Part')


@pytest.mark.parametrize('change', ['payload', 'limit', 'bounds', 'identity'])
def test_invalid_export_never_validates(tmp_path, change):
    root = exported(tmp_path)
    value = json.loads((root / 'export.json').read_text())
    if change == 'payload': (root / 'Part.fbx').write_bytes(b'changed')
    elif change == 'limit': value['triangles'] = tasks.TRIANGLE_LIMIT + 1
    elif change == 'bounds': value['bounds'][1][0] = -1
    else: value['asset'] = 'Other'
    (root / 'export.json').write_text(json.dumps(value))
    with pytest.raises(ValueError): tasks.validate(root, key='Part')


def test_linked_ancestor_is_refused_before_writes(tmp_path):
    external = tmp_path / 'external'; external.mkdir()
    linked = tmp_path / 'linked'; linked.symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError): tasks.real_directory(linked / 'child', create=True)
    assert list(external.iterdir()) == []


def test_recipe_has_separate_complete_owners_and_explicit_cached_launch(tmp_path):
    ctx = SimpleNamespace(out=tmp_path)
    assets = [tasks.Asset('One', Path('One.npz')),
              tasks.Asset('Two', Path('Two.npz'))]
    steps = tasks.steps(ctx, prefix='world.region', assets=assets, script=Path('export.py'))
    assert len(steps) == 2
    assert steps[0].products[0].paths != steps[1].products[0].paths
    assert Path('Two.npz') not in steps[0].inputs
    assert Path('One.npz') not in steps[1].inputs
    assert all(s.cache and s.commands[0].factory_startup and s.commands[0].threads == 3 for s in steps)


def test_case_aliases_cannot_create_two_owners(tmp_path):
    assets = [tasks.Asset(n, Path('geometry.npz')) for n in ('Part', 'PART')]
    with pytest.raises(ValueError, match='unique'):
        tasks.steps(SimpleNamespace(out=tmp_path), prefix='region', assets=assets, script=Path('export.py'))
