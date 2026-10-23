"""Assembly consumes small independent bytes without rebuilding or concealing geometry."""
import json
from pathlib import Path

import pytest

from atelier import export_assembly as assembly
from atelier.export_tasks import publish_receipt


def item(tmp_path, key, payload=b'validated source'):
    root = tmp_path / key
    root.mkdir()
    (root / (key + '.fbx')).write_bytes(payload)
    publish_receipt(root, key=key, primary=key + '.fbx', triangles=12,
                    bounds=[[0, 0, 0], [1, 1, 1]])
    return assembly.Item(key, root)


def test_independent_bytes_assemble_and_unchanged_sibling_is_not_rewritten(tmp_path):
    one, two = item(tmp_path, 'One'), item(tmp_path, 'Two')
    target = tmp_path / 'assembled'
    assembly.assemble([one, two], target)
    previous = (target / 'Two.fbx').stat().st_mtime_ns
    (one.root / 'One.fbx').write_bytes(b'changed one')
    publish_receipt(one.root, key='One', primary='One.fbx', triangles=13,
                    bounds=[[0, 0, 0], [1, 1, 1]])
    result = assembly.assemble([one, two], target)
    assert (target / 'One.fbx').read_bytes() == b'changed one'
    assert (target / 'Two.fbx').stat().st_mtime_ns == previous
    assert [row['asset'] for row in result['exports']] == ['One', 'Two']
    assert json.loads((target / 'manifest.json').read_text()) == result
    assembly.assemble([two], target)
    assert not (target / 'One.fbx').exists()


def test_incomplete_last_source_refuses_before_first_destination_write(tmp_path):
    one, two = item(tmp_path, 'One'), item(tmp_path, 'Two')
    (two.root / 'Two.fbx').unlink()
    target = tmp_path / 'assembled'
    with pytest.raises(ValueError): assembly.assemble([one, two], target)
    assert not target.exists()


@pytest.mark.parametrize('kind', ['file', 'broken', 'ancestor'])
def test_linked_destination_never_changes_external_bytes(tmp_path, kind):
    one = item(tmp_path, 'One')
    outside = tmp_path / 'outside'; outside.mkdir()
    sentinel = outside / 'sentinel'; sentinel.write_bytes(b'untouched')
    target = tmp_path / 'assembled'
    if kind == 'ancestor':
        target.symlink_to(outside, target_is_directory=True)
    else:
        target.mkdir()
        (target / 'One.fbx').symlink_to(sentinel if kind == 'file' else outside / 'missing')
    with pytest.raises(ValueError): assembly.assemble([one], target)
    assert sentinel.read_bytes() == b'untouched'
    assert sorted(p.name for p in outside.iterdir()) == ['sentinel']


def test_case_aliases_refuse_before_destination_exists(tmp_path):
    one = item(tmp_path, 'One')
    target = tmp_path / 'assembled'
    with pytest.raises(ValueError): assembly.assemble([one, assembly.Item('ONE', Path('unused'))], target)
    assert not target.exists()
