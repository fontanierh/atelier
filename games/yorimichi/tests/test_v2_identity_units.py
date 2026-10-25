"""Declared network identity matches the original bytes without mutable Content scans."""
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace as NS

import pytest
from atelier.build import Call, Step
from atelier.build_v2 import recipe_job
from atelier.build_v2.recipe_dependencies import extract

ROOT = Path(__file__).resolve().parents[3]; GAME = ROOT / 'games/yorimichi'
sys.path[:0] = [str(GAME), str(GAME / 'world')]
import v2_identity_units as units  # noqa: E402
import identity_v2 as body  # noqa: E402
import network_identity as original  # noqa: E402


def write(root, name, data):
    path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data); return path


@pytest.fixture
def case(tmp_path):
    native = tmp_path / 'native'
    write(native, 'content/Game/Maps/World.umap', b'map bytes')
    write(native, 'content/Game/Japan/Mesh.uasset', b'asset bytes')
    write(native, 'content/Game/Japan/Mesh.uexp', b'sidecar bytes')
    write(native, 'content/Game/Japan/Mesh.m.ubulk', b'more bytes')
    write(native, 'content/Game/Japan/Mesh.uptnl', b'optional key-bound bytes')
    data = tmp_path / 'data'; write(data, 'world.json', b'{"world":"current"}\r\n')
    write(data, 'Network/session.json', b'old identity must not recurse')
    write(data, 'NetworkSibling/record.json', b'keep this byte exact\r\n')
    write(data, 'Saved/ignored.json', b'ignored metadata')
    repo = tmp_path / 'repo'
    source = write(repo, 'games/yorimichi/unreal/Source/Game/Code.cpp', b'current\r\ncode\r\n')
    expected_content = repo / 'games/yorimichi/unreal/Content'
    shutil.copytree(native / 'content/Game', expected_content)
    shutil.copytree(data, expected_content / 'Data')
    expected = original.create(repo, expected_content, io.StringIO())
    report = tmp_path / 'outputs/runtime-content.json'
    body.content([native], [], [('Data', data)], report)
    return NS(native=native, data=data, repo=repo, source=source, expected=expected, report=report,
              code=[('games/yorimichi/unreal/Source/Game/Code.cpp', source)], output=tmp_path / 'outputs/session.json')


def test_exact_original_sha1_signature_code_normalization_and_self_exclusion(case):
    body.network([case.native], [], [('Data', case.data)], case.code, case.report, case.output)
    assert json.loads(case.output.read_bytes()) == case.expected
    inventory = json.loads(case.report.read_bytes())
    assert any(row['path'].endswith('.uptnl') for row in inventory['files'])
    assert not any(row['path'].startswith('Data/Network/') for row in inventory['files'])
    assert any(row['path'] == 'Data/NetworkSibling/record.json' for row in inventory['files'])


@pytest.mark.parametrize('damage', ['world', 'map', 'duplicate', 'native_link', 'data_link', 'foreign', 'changed', 'code_link'])
def test_missing_ambiguous_aliased_or_changed_identity_inputs_refuse(case, tmp_path, damage):
    roots = [case.native]; code = list(case.code)
    if damage == 'world': (case.data / 'world.json').unlink()
    if damage == 'map': (case.native / 'content/Game/Maps/World.umap').unlink()
    if damage == 'duplicate': roots += [case.native]
    if damage == 'native_link':
        path = case.native / 'content/Game/Japan/Mesh.uasset'; path.unlink(); path.symlink_to(case.source)
    if damage == 'data_link': (case.data / 'linked.json').symlink_to(case.source)
    if damage == 'foreign': write(case.native, 'foreign.json', b'not Native content')
    if damage == 'changed': (case.data / 'world.json').write_bytes(b'changed')
    if damage == 'code_link':
        path = tmp_path / 'alias.cpp'; path.symlink_to(case.source); code[0] = (code[0][0], path)
    with pytest.raises(ValueError):
        body.network(roots, [], [('Data', case.data)], code, case.report, case.output)
    assert not case.output.exists()


def test_expanded_native_items_use_actual_selected_roots(case):
    case.report.unlink()
    expanded = [[(NS(products=[NS(paths=[case.native])]), 'World')]]
    body.content([], expanded, [('Data', case.data)], case.report)
    body.network([], expanded, [('Data', case.data)], case.code, case.report, case.output)
    assert json.loads(case.output.read_bytes()) == case.expected


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


@pytest.fixture(scope='module')
def rows():
    policy = load(units.POLICY, 'identity_original_policy')
    steps = [Step('data.content', [Call('archive_retired_content', policy.archive)], inputs=[ROOT / units.POLICY], outputs=[ROOT / units.INVENTORY]),
             Step('data.network', [Call('network_identity', original.stage)], inputs=[ROOT / units.ORIGINAL], outputs=[ROOT / units.SESSION])]
    return extract(steps, checkout=ROOT, build_root=ROOT / 'build', import_roots=(ROOT / 'platform/studio', GAME))


def owners():
    return [{'id': 'native.world', 'outputs': [{'id': 'map', 'logical_path': '/Game/Maps/World', 'class': 'Map',
        'files': [{'path': 'content/Game/Maps/World.umap', 'required': True}]}]},
        {'id': 'raw.ignore', 'outputs': [{'id': 'raw', 'logical_path': '/Game/_Raw/World', 'class': 'RawStaticMesh', 'files': []}]}]


def data_refs():
    return [{'unit': 'data.stage', 'item': 'world', 'file': 'world.tree.tar', 'path': units.CONTENT + 'Data/world.json'},
            {'unit': 'data.network', 'item': 'old', 'file': 'old.tree.tar', 'path': units.SESSION}]


def test_constructor_binds_actual_code_and_owner_roots_without_network_recursion(rows):
    result = units.identity_units(rows, checkout=ROOT, native_units=owners(), geometry={'templates': []}, data=data_refs())
    content, network = result['units']
    assert result['session'] == {'unit': 'data.network', 'item': 'session', 'file': 'session.tree.tar', 'path': units.SESSION}
    assert content['id'] == 'data.content' and network['id'] == 'data.network'
    for unit in result['units']:
        assert unit['outputs'][0]['destination'] == 'store'
        assert not any(i['source'].get('unit') in ('data.network', 'raw.ignore') for i in unit['inputs'])
    assert any(i['source'].get('unit') == 'data.content' for i in network['inputs'])
    sources = {i['source']['path'] for i in network['inputs'] if i['source']['kind'] == 'file'}
    assert sources == {p.relative_to(ROOT).as_posix() for p in original.code_files(ROOT)}
    assert all(network['params']['recipe']['paths'][p].startswith('inputs/code') for p in sources)
    assert units.ORIGINAL in network['code'] and units.BODY in network['code']


@pytest.mark.parametrize('damage', ['missing', 'self', 'overlap', 'outside', 'raw_only'])
def test_constructor_refuses_missing_or_conflicting_declared_members(rows, damage):
    rows, refs, native = deepcopy(rows), data_refs(), owners()
    if damage == 'missing': rows.pop()
    if damage == 'self': refs[0]['path'] = '../outside'
    if damage == 'overlap': refs.append({**refs[0], 'file': 'all.tree.tar', 'path': units.CONTENT + 'Data/world.json/nested'})
    if damage == 'outside': refs[0]['path'] = 'build/world.json'
    if damage == 'raw_only': native = native[1:]
    with pytest.raises(ValueError): units.identity_units(rows, checkout=ROOT, native_units=native, geometry={'templates': []}, data=refs)


def test_real_recipe_view_and_callback_emit_decoded_session_item(tmp_path, rows, monkeypatch):
    declared = units.identity_units(rows, checkout=ROOT, native_units=owners(), geometry={'templates': []}, data=data_refs())
    completed = {}
    for unit in declared['units']:
        job = tmp_path / unit['id']; job.mkdir(); output = job / 'output'; output.mkdir()
        for path in unit['code']:
            destination = job / path; destination.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ROOT / path, destination)
        incoming = []
        for item in unit['inputs']:
            slot, source = item['name'], item['source']; staged = job / 'inputs' / slot
            incoming.append({'path': 'inputs/' + slot})
            if source['kind'] == 'file':
                staged.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ROOT / source['path'], staged)
            elif source['unit'] == 'native.world': write(staged, 'content/Game/Maps/World.umap', b'map')
            elif source['unit'] == 'data.stage':
                original_file = job / 'source-world.json'; original_file.write_text('{"world":"owned"}')
                staged.mkdir(parents=True); recipe_job.pack_root(original_file, staged / 'world.tree.tar')
            elif source['unit'] == 'data.content':
                staged.mkdir(parents=True); shutil.copyfile(completed['data.content'], staged / 'inventory.tree.tar')
            else: raise AssertionError(source)
        (job / '.recipe-runtime').mkdir()
        context = NS(params=unit['params'], output_dir=output)
        view, _, _ = recipe_job.prepare_view({'params': unit['params'], 'code': unit['code'], 'inputs': incoming}, job)
        with monkeypatch.context() as scope:
            scope.chdir(view)
            scope.setattr(sys, 'path', [p for p in sys.path if not str(p).startswith(str(GAME))])
            scope.delitem(sys.modules, 'network_identity', raising=False)
            recipe_job.run(context)
        artifact = output / unit['outputs'][0]['files'][0]['path']; completed[unit['id']] = artifact
        decoded = job / 'decoded'; recipe_job.unpack_root(artifact, decoded)
        if unit['id'] == 'data.network':
            result = json.loads(decoded.read_bytes())
            assert [r['path'] for r in result['files']] == ['world.json']
            assert result['code'] == original.code_identity(ROOT)


def test_constructor_captures_actual_finished_template_item_and_excludes_raw(rows):
    raw = {'id': 'raw', 'logical_path': '/Game/_Raw/$piece', 'class': 'RawStaticMesh'}
    finished = {'id': 'asset', 'logical_path': '/Game/Japan/$piece', 'class': 'StaticMesh'}
    template = {'producer': 'world.parts', 'group': 'geometry', 'unit_prefix': 'world.parts.export',
                'followers': [{'unit': {'outputs': [raw]}}, {'unit': {'outputs': [finished]}}]}
    result = units.identity_units(rows, checkout=ROOT, native_units=[], geometry={'templates': [template]}, data=data_refs())
    binding = result['units'][0]['params']['recipe']['commands'][0]['call']
    descriptor = binding['defaults'][1][0]['derived_items']
    assert descriptor['templates'] == [{'producer': 'world.parts', 'group': 'geometry',
                                      'unit_prefix': 'world.parts.export', 'follower': 1, 'item': 'asset'}]
    assert not any(i['source']['kind'] == 'item' and i['source']['unit'] == 'raw' for i in result['units'][0]['inputs'])
