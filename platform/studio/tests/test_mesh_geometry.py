import copy
import hashlib
import json
import struct

import pytest

from atelier import mesh_geometry as M


def level():
    return {'vertices': [{'p': [i, i + .25, -i], 'n': [0., 0., 1.], 'c': [1., .5, .25, 1.],
                          'uv': [i / 2., 0.], 'uvs': [[i / 2., 0.], [.1, .2]]} for i in range(3)],
            'faces': [{'s': 2, 'v': [0, 1, 2]}]}


def test_protocol_matches_independent_little_endian_stream():
    data = level()
    payload = b'ATELIER-MESH-1\n' + struct.pack('<III', 1, 2, 1) + struct.pack('<I', 2)
    for vertex in data['vertices']:
        payload += struct.pack('<14f', *vertex['p'], *vertex['n'], *vertex['c'], *vertex['uvs'][0], *vertex['uvs'][1])
    assert M.expected_digest([data], 2) == hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize('field,index', [('p', 0), ('n', 1), ('c', 2), ('uvs', 0)])
def test_every_attribute_enters_digest(field, index):
    original = level()
    changed = copy.deepcopy(original)
    if field == 'uvs':
        changed['vertices'][0][field][1][index] += .01
    else:
        changed['vertices'][0][field][index] += .01
    assert M.expected_digest([original], 2) != M.expected_digest([changed], 2)


def test_winding_slots_lods_and_channels_enter_digest():
    original = level()
    changed = copy.deepcopy(original)
    changed['faces'][0]['v'].reverse()
    base = M.expected_digest([original], 2)
    assert base != M.expected_digest([changed], 2)
    changed = copy.deepcopy(original)
    changed['faces'][0]['s'] += 1
    assert base != M.expected_digest([changed], 2)
    assert base != M.expected_digest([original, original], 2)
    assert base != M.expected_digest([original], 1)


def test_uv_fallback_is_native_build_variant_fallback():
    data = level()
    for vertex in data['vertices']:
        del vertex['uvs']
    explicit = copy.deepcopy(data)
    for vertex in explicit['vertices']:
        vertex['uvs'] = [vertex['uv'], vertex['uv']]
    assert M.expected_digest([data], 2) == M.expected_digest([explicit], 2)


@pytest.mark.parametrize('bad', [float('nan'), float('inf'), 1e100, True, '1'])
def test_invalid_float_refuses(bad):
    data = level()
    data['vertices'][0]['p'][0] = bad
    with pytest.raises(ValueError):
        M.expected_digest([data], 2)


@pytest.mark.parametrize('channels', [0, 9, True, 1.5])
def test_invalid_channels_refuse(channels):
    with pytest.raises(ValueError):
        M.expected_digest([level()], channels)


def fixture(tmp_path):
    content = tmp_path / 'Content'
    (content / 'Variants').mkdir(parents=True)
    for suffix in M.SIDECARS:
        (content / ('Variants/One' + suffix)).write_bytes(suffix.encode())
    args = dict(identity='1' * 64, policy='2' * 64, content_root=content)
    return content, tmp_path / 'units' / 'one.json', args


def test_unit_is_only_a_complete_byte_checked_hint(tmp_path):
    content, path, args = fixture(tmp_path)
    record = M.save_unit(path, **args, assets=['/Game/Variants/One'], geometry={'visual': '3' * 64}, metadata={'row': 1})
    assert len(record['files']) == len(M.SIDECARS)
    assert M.load_unit(path, **args, assets=['/Game/Variants/One']) == record
    assert set(record) == {'schema', 'identity', 'policy', 'assets', 'geometry', 'metadata', 'files'}
    (content / 'Variants/One.uexp').write_bytes(b'changed')
    assert M.load_unit(path, **args, assets=['/Game/Variants/One']) is None


@pytest.mark.parametrize('change', ['remove', 'add', 'identity', 'policy', 'schema', 'malformed', 'geometry'])
def test_changed_or_invalid_unit_is_a_normal_miss(tmp_path, change):
    content, path, args = fixture(tmp_path)
    # Begin with only the primary, then verify absence is part of closure.
    for suffix in M.SIDECARS[1:]:
        (content / ('Variants/One' + suffix)).unlink()
    record = M.save_unit(path, **args, assets=['/Game/Variants/One'], geometry={'visual': '3' * 64}, metadata={})
    if change == 'remove':
        (content / 'Variants/One.uasset').unlink()
    elif change == 'add':
        (content / 'Variants/One.upayload').write_bytes(b'new sidecar')
    elif change == 'malformed':
        path.write_text('[]')
    else:
        record[change] = 'different'
        path.write_text(json.dumps(record))
    assert M.load_unit(path, **args, assets=['/Game/Variants/One']) is None


@pytest.mark.parametrize('target', ['primary', 'sidecar', 'directory', 'record'])
def test_linked_or_dangling_member_refuses(tmp_path, target):
    content, path, args = fixture(tmp_path)
    M.save_unit(path, **args, assets=['/Game/Variants/One'], geometry={'visual': '3' * 64}, metadata={})
    if target == 'directory':
        directory = content / 'Variants'
        directory.rename(content / 'Elsewhere')
        directory.symlink_to(content / 'Elsewhere', target_is_directory=True)
    else:
        selected = path if target == 'record' else content / ('Variants/One' + ('.uasset' if target == 'primary' else '.upayload'))
        selected.unlink()
        selected.symlink_to(tmp_path / 'missing')
    assert M.load_unit(path, **args, assets=['/Game/Variants/One']) is None


@pytest.mark.parametrize('asset', ['/Game/../Other', '/Game/A.Object', '/Game//A', '/Other/A'])
def test_invalid_package_paths_refuse(tmp_path, asset):
    with pytest.raises(ValueError):
        M.package_inventory(tmp_path, [asset])


def test_failed_save_keeps_prior_hint(tmp_path):
    content, path, args = fixture(tmp_path)
    prior = M.save_unit(path, **args, assets=['/Game/Variants/One'], geometry={'visual': '3' * 64}, metadata={})
    with pytest.raises(ValueError):
        M.save_unit(path, **args, assets=['/Game/Variants/One'], geometry={'visual': 'invalid'}, metadata={})
    assert M.load_unit(path, **args, assets=['/Game/Variants/One']) == prior


def test_expected_asset_closure_cannot_be_shrunk_by_hint(tmp_path):
    content, path, args = fixture(tmp_path)
    M.save_unit(path, **args, assets=['/Game/Variants/One'], geometry={'visual': '3' * 64}, metadata={})
    assert M.load_unit(path, **args, assets=['/Game/Variants/One', '/Game/Variants/MissingShadow']) is None


def test_refused_linked_parent_creates_no_external_directories(tmp_path):
    content, path, args = fixture(tmp_path)
    external = tmp_path / 'external'
    external.mkdir()
    linked = tmp_path / 'linked'
    linked.symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError):
        M.save_unit(linked / 'new' / 'unit.json', **args, assets=['/Game/Variants/One'], geometry={'visual': '3' * 64}, metadata={})
    assert list(external.iterdir()) == []
