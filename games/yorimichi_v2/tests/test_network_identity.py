"""The multiplayer content manifest (tools/package/network_identity.py) against the code that reads and the build that
names it: Yorimichi.Build.cs's code digest, JapanNetwork::Identity's checks, the runtime data lock and unreal.package."""
import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

GAME = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(GAME / 'tools' / 'package'))
sys.path.insert(0, str(GAME / 'tools' / 'content'))
import network_identity as ni  # noqa: E402
import records  # noqa: E402

BUILD_CS = GAME / 'unreal/Source/Yorimichi/Yorimichi.Build.cs'
NETWORK = GAME / 'unreal/Source/Yorimichi/Network'


def _cs_strings(name):
    block = re.search(rf'string\[\] {name} = \{{(.*?)\}};', BUILD_CS.read_text(), re.S).group(1)
    return re.findall(r'"([^"]+)"', block)


def test_the_code_digest_enumerates_what_build_cs_enumerates():
    """@cc [owner:fontanierh,label:correctness] network-code-identity-mirror
    The Python code digest uses Build.cs's roots, suffixes and ignored names, and JapanNetwork's protocol and manifest
    path; a drift between them makes every package's manifest disagree with its compiled YORIMICHI_NETWORK_BUILD_ID."""
    assert tuple(_cs_strings('Roots')) == ni.CODE_ROOTS
    assert set(_cs_strings('Extensions')) == ni.CODE_SUFFIXES
    assert set(_cs_strings('Ignored')) == ni.IGNORED
    assert 'Path.Combine(Root, "games/yorimichi_v2/unreal"), "*.uproject"' in BUILD_CS.read_text()
    assert re.search(rf'constexpr int32 Protocol = {ni.PROTOCOL};', (NETWORK / 'JapanNetwork.h').read_text())
    source = (NETWORK / 'JapanNetwork.cpp').read_text()
    assert 'Root / TEXT("Network/session.json")' in source and ni.MANIFEST == 'Data/Network/session.json'
    assert 'File.StartsWith(TEXT("Network/"))' in source


def test_the_code_digest_equals_a_current_compiled_header():
    """When a compiled identity header is newer than every code file, it names exactly this digest."""
    headers = sorted((GAME / 'unreal/Intermediate/BuildIdentity').glob('*/YorimichiBuildIdentity.h'))
    newest = max(p.stat().st_mtime for p in ni.code_files())
    current = [h for h in headers if h.stat().st_mtime >= newest]
    if not current:
        pytest.skip('no compiled identity header newer than the source')
    code = ni.code_identity()
    for header in current:
        assert f'#define YORIMICHI_NETWORK_BUILD_ID "{code}"' in header.read_text(), header


def _tree(tmp_path):
    content = tmp_path / 'Content'
    (content / 'Data/map').mkdir(parents=True)
    (content / 'Data/world.json').write_text('{}')
    (content / 'Data/map/map.json').write_text('{"a": 1}')
    (content / 'Data/.DS_Store').write_bytes(b'x')
    (content / 'V2/Maps').mkdir(parents=True)
    (content / 'V2/Maps/Slice.umap').write_bytes(b'map')
    (content / 'V2/M_A.uasset').write_bytes(b'asset')
    (content / 'V2/notes.txt').write_text('not a package')
    return content


def _signature_as_cpp(result):
    """JapanNetwork::Identity's recomputation, written independently of network_identity.signature."""
    data = hashlib.sha1()
    for entry in sorted(result['files'], key=lambda e: e['path']):
        data.update(entry['path'].encode() + b'\0' + (entry['sha1'] + '\n').encode())
    payload = f'{ni.PROTOCOL}\n{result["code"]}\n{result["assets"]}\n{data.hexdigest()}\n'
    return hashlib.sha1(payload.encode()).hexdigest()


def test_the_manifest_lists_every_data_file_and_signs_what_the_game_checks(tmp_path, monkeypatch):
    """@cc [owner:fontanierh,label:correctness] network-manifest-matches-runtime
    The manifest lists every file under Data except Network/ and desktop metadata, each with its SHA1, digests the
    imported packages, and carries the signature JapanNetwork::Identity recomputes; a rewrite of an unchanged tree
    keeps the same bytes."""
    monkeypatch.setattr(ni, 'code_identity', lambda repo=ni.REPO: 'c' * 40)
    content = _tree(tmp_path)
    first = ni.write(content=content)
    assert [f['path'] for f in first['files']] == ['map/map.json', 'world.json']
    assert first['files'][1]['sha1'] == hashlib.sha1(b'{}').hexdigest()
    assert first['packages'] == 2 and len(first['assets']) == 40 and len(first['signature']) == 40
    assert first['signature'] == _signature_as_cpp(first)
    path = content / ni.MANIFEST
    assert json.loads(path.read_text()) == first
    before = path.stat().st_mtime_ns
    assert ni.write(content=content) == first and path.stat().st_mtime_ns == before
    # The manifest's own folder never enters it, so writing it does not change the next signature.
    assert ni.manifest(content=content)['signature'] == first['signature']
    (content / 'Data/map/map.json').write_text('{"a": 2}')
    assert ni.manifest(content=content)['signature'] != first['signature']


def test_the_manifest_refuses_a_tree_without_world_data_or_a_map(tmp_path, monkeypatch):
    monkeypatch.setattr(ni, 'code_identity', lambda repo=ni.REPO: 'c' * 40)
    content = _tree(tmp_path)
    (content / 'V2/Maps/Slice.umap').unlink()
    with pytest.raises(ValueError):
        ni.manifest(content=content)


def test_the_generated_manifest_is_not_runtime_data_to_pin(tmp_path):
    """check.py pins every runtime data file; the per-build manifest is excluded there and ignored by Git."""
    game = tmp_path
    data = game / 'unreal/Content/Data'
    (data / 'Network').mkdir(parents=True)
    (data / 'world.json').write_text('{}')
    (data / 'Network/session.json').write_text('{}')
    assert records.data_files(game) == ['Data/world.json']
    assert 'unreal/Content/Data/Network/' in (GAME / '.gitignore').read_text().splitlines()


def test_unreal_package_writes_the_manifest_before_it_cooks():
    text = (GAME / 'build.py').read_text()
    step = text[text.index("Step('unreal.package'"):]
    order = [step.index(name) for name in ("Call('check_package_inputs'", "Call('network_identity'", 'UnrealPackage(')]
    assert order == sorted(order)
