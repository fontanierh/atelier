"""The extracted build must retain network permissions and the accepted runtime data."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1] / 'tools'
spec = importlib.util.spec_from_file_location('verify_network_package', HERE / 'verify_network_package.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def staged(tmp_path):
    data = tmp_path / 'Data'
    (data / 'Network').mkdir(parents=True)
    (data / 'world.json').write_bytes(b'{"island":1}')
    sha = hashlib.sha1((data / 'world.json').read_bytes()).hexdigest()
    records = hashlib.sha1(f'world.json\0{sha}\n'.encode()).hexdigest()
    code, assets = 'a' * 40, 'b' * 40
    signature = hashlib.sha1(f'1\n{code}\n{assets}\n{records}\n'.encode()).hexdigest()
    manifest = dict(protocol=1, code=code, assets=assets, signature=signature,
                    files=[dict(path='world.json', sha1=sha)])
    (data / 'Network/session.json').write_text(json.dumps(manifest))
    entitlements = {'com.apple.security.app-sandbox': True,
                    'com.apple.security.network.client': True, 'com.apple.security.network.server': True}
    return data, entitlements, f'1:{code}:{signature}', manifest


def test_matching_signed_network_data_passes(tmp_path):
    data, entitlements, identity, _ = staged(tmp_path)
    result = tool.check_data(data, entitlements, identity)
    assert result['manifest_claimed_identity'] == identity and result['data_files'] == 1
    assert result['sandboxed'] is True


@pytest.mark.parametrize('direction', ['client', 'server'])
def test_sandbox_requires_both_signed_network_permissions(tmp_path, direction):
    data, entitlements, identity, _ = staged(tmp_path)
    del entitlements['com.apple.security.network.' + direction]
    with pytest.raises(RuntimeError, match='entitlement'):
        tool.check_data(data, entitlements, identity)


@pytest.mark.parametrize('change', ['changed', 'missing', 'extra', 'wrong-build'])
def test_rejects_changed_missing_extra_and_other_build_data(tmp_path, change):
    data, entitlements, identity, _ = staged(tmp_path)
    if change == 'changed': (data / 'world.json').write_bytes(b'{"island":2}')
    if change == 'missing': (data / 'world.json').unlink()
    if change == 'extra': (data / 'extra.json').write_bytes(b'{}')
    if change == 'wrong-build': identity = '1:' + 'c' * 40 + ':' + 'd' * 40
    with pytest.raises(RuntimeError):
        tool.check_data(data, entitlements, identity)


@pytest.mark.parametrize('path', ['../outside', '/outside', 'a/../world.json', 'a\\world.json',
                                  'world.json\n', 'Network/session.json', './world.json', 'a//world.json'])
def test_manifest_cannot_escape_or_hash_itself(tmp_path, path):
    data, entitlements, identity, manifest = staged(tmp_path)
    manifest['files'][0]['path'] = path
    (data / 'Network/session.json').write_text(json.dumps(manifest))
    with pytest.raises(RuntimeError, match='path'):
        tool.check_data(data, entitlements, identity)


def test_duplicate_records_and_corrupt_signature_fail(tmp_path):
    data, entitlements, identity, manifest = staged(tmp_path)
    manifest['files'] *= 2
    (data / 'Network/session.json').write_text(json.dumps(manifest))
    with pytest.raises(RuntimeError, match='duplicate'):
        tool.check_data(data, entitlements, identity)
    manifest['files'].pop()
    manifest['signature'] = 'c' * 40
    (data / 'Network/session.json').write_text(json.dumps(manifest))
    with pytest.raises(RuntimeError, match='checksum'):
        tool.check_data(data, entitlements, identity)


def test_external_symlink_cannot_supply_packaged_data(tmp_path):
    data, entitlements, identity, _ = staged(tmp_path)
    external = tmp_path / 'external.json'
    (data / 'world.json').rename(external)
    (data / 'world.json').symlink_to(external)
    with pytest.raises(RuntimeError, match='external'):
        tool.check_data(data, entitlements, identity)


@pytest.mark.parametrize('entry', ['extra.json', 'nested'])
def test_network_directory_is_exact(tmp_path, entry):
    data, entitlements, identity, _ = staged(tmp_path)
    if entry == 'nested':
        (data / 'Network' / entry).mkdir()
    else:
        (data / 'Network' / entry).write_text('{}')
    with pytest.raises(RuntimeError, match='only a regular'):
        tool.check_data(data, entitlements, identity)


@pytest.mark.parametrize('target', ['external', 'internal'])
def test_symlinked_directories_are_rejected(tmp_path, target):
    data, entitlements, identity, _ = staged(tmp_path)
    folder = tmp_path / 'elsewhere' if target == 'external' else data / 'actual'
    folder.mkdir()
    (data / 'alias').symlink_to(folder, target_is_directory=True)
    with pytest.raises(RuntimeError, match='symlinked'):
        tool.check_data(data, entitlements, identity)


def test_unsandboxed_report_is_explicit(tmp_path):
    data, _, identity, _ = staged(tmp_path)
    assert tool.check_data(data, {}, identity)['sandboxed'] is False
