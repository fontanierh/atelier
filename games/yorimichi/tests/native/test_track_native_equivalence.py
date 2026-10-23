"""Pure fault injection for Track input/owner/receiving proof boundaries; no native jobs."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import track_native_equivalence as proof
from run_track_native_equivalence import strict_cleanup


def runtime():
    result = dict(meshes={}, pieces=[], instances=[])
    for n in range(137):
        name = f'SM_TK_Test_{n}'; levels = 3 if n < 112 else 2 if n == 112 else 1
        result['meshes'][name] = dict(lods=[f'meshes/{name}_LOD{k}.glb' for k in range(levels)],
            screen_sizes=[1., .3, .05][:levels], materials=['MI_B_wood'])
        result['pieces'].append(dict(name=name, collision=levels - 1 if n < 2 else -1))
    return result


def test_complete_code_inputs_accept_empty_init_without_weakening_artifact_rules(tmp_path):
    path = tmp_path / '__init__.py'; path.write_bytes(b'')
    proof.check_input(path, proof.sha(path))
    with pytest.raises(ValueError): proof.artifact(dict(path=str(path), sha256=proof.sha(path)))
    digest = proof.sha(path); path.write_bytes(b'changed')
    with pytest.raises(ValueError): proof.check_input(path, digest)
    path.unlink(); path.symlink_to(tmp_path / 'missing')
    with pytest.raises(ValueError): proof.check_input(path, digest)


def test_unreal_import_closure_is_stdlib_only_with_actual_bound_validators(tmp_path):
    code = r'''
import importlib.abc, importlib.util, json, pathlib, sys, types
native = pathlib.Path(sys.argv[1]); game = native.parents[1]
sys.path[:0] = [str(native), str(game/'unreal/Scripts')]
class BlockHost(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'atomic_equivalence' or fullname.split('.')[0] in ('numpy','mesh_ir') or fullname == 'atelier.mesh_ir':
            raise ModuleNotFoundError('host-only import forbidden: '+fullname)
sys.meta_path.insert(0, BlockHost())
unreal = types.ModuleType('unreal')
unreal.EditorAssetLibrary = types.SimpleNamespace()
unreal.MaterialEditingLibrary = types.SimpleNamespace()
unreal.AssetToolsHelpers = types.SimpleNamespace(get_asset_tools=lambda: object())
unreal.AssetRegistryHelpers = types.SimpleNamespace(get_asset_registry=lambda: object())
sys.modules['unreal'] = unreal
import track_native_equivalence as p
import atomic_equivalence_capture as capture
material = p.definitions(game/'unreal/Scripts/import_belmonte.py','actual_material_import')
owner_tree = p.owner_tree(game/'unreal/Scripts/import_belmonte_track.py',
    '/Game/AtelierValidation/Track_0123456789ab/Prerequisites/Materials')
owner = types.ModuleType('actual_track_owner'); owner.__file__ = str(game/'unreal/Scripts/import_belmonte_track.py')
exec(compile(owner_tree,owner.__file__,'exec'),owner.__dict__)
assert callable(capture.capture) and callable(material.parent) and callable(material.textures) and callable(material.surfaces)
assert callable(owner.main) and callable(owner.import_mesh)
assert 'numpy' not in sys.modules and 'atelier.mesh_ir' not in sys.modules and 'atomic_equivalence' not in sys.modules
folder = pathlib.Path(sys.argv[2]); path=folder/'exact.json';path.write_bytes(b'actual bound data')
row=dict(path=str(path),sha256=p.sha(path));assert p.artifact(row)==b'actual bound data'
for changed in [dict(row,sha256='0'*64),dict(path='relative',sha256=row['sha256'])]:
    try:p.artifact(changed)
    except ValueError:pass
    else:raise AssertionError('weakened exact artifact gate')
try:p.canonical(dict(value=float('nan')))
except ValueError:pass
else:raise AssertionError('nonfinite evidence admitted')
path.write_bytes(b'')
try:p.artifact(dict(path=str(path),sha256=p.sha(path)))
except ValueError:pass
else:raise AssertionError('empty geometry evidence admitted')
assert p.canonical({'b':(1,True,None),'a':.25})==b'{"a":0.25,"b":[1,true,null]}'
print('ACTUAL UNREAL IMPORT CLOSURE AND EXACT IO VERIFIED')
'''
    result = subprocess.run([sys.executable, '-I', '-S', '-c', code, str(HERE), str(tmp_path)],
                            cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'ACTUAL UNREAL IMPORT CLOSURE AND EXACT IO VERIFIED' in result.stdout


def test_generic_io_extraction_preserves_exact_original_validator_bodies():
    # Exact definition source identities recorded before extraction; no historical Git required by CI.
    expected = {
        'EvidenceError': '8456bcaf241ccc231f59b76d8101dc07264d6ccde6adfb996cc16e98e5677dea',
        'require': '0c0d05b86810d5dbd9590930b03b3b7c9c532d9d206b4190ac28a098012735c4',
        'finite': '5c90abd3835e00a61f275994091b717969965a44b49efde053c3a7ac23a52602',
        'canonical': '06d641bfd3cee30579d8f5ffea3cc20a357fbd809e46b6813914e342dc3a972c',
        'artifact': '0f191d319dd037ec93da355428f92725b8880fb04322a491a260f225e8a74cb0',
        'json_artifact': '71b3fc2cc0f4e7d0f3316c5d9a1a13884b161b1c9911bd0825cf318a6c8660f7',
        'source_binding': '85a8687efe7b7a0b51796cdbd650b8480abdd973c64c9115af4c8de93f74fa44',
        'component_bounds': '2f3cb8df42e15cc6ecf5474d6b8e219efef7d10f3007d7663b4733a3468b2fcd',
        'native_raw_set': 'b4ed43b62e87d11669f984aa05142b309d3e7805af1e1d4d107bf93bba0c514f',
        'compare_native': '93db0a2072d0d1d50dfc83453ab1a2931bb1d9d316131a80cba49cd1ac2e35dd',
    }
    tools = HERE.parents[1] / 'tools'
    found = {}
    for filename in ('atomic_equivalence_io.py', 'atomic_equivalence.py'):
        text = (tools / filename).read_text(); lines = text.splitlines()
        for node in ast.parse(text).body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in expected:
                body = '\n'.join(lines[node.lineno - 1:node.end_lineno]).encode()
                found[node.name] = hashlib.sha256(body).hexdigest()
    assert found == expected


def test_production_census_retains_every_authored_lod_but_never_injects_marker():
    value = runtime(); assert len(proof.runtime_inventory(value)) == 137
    assert sum(proof.runtime_inventory(value).values()) == 362
    for bad in ('missing', 'marker', 'lod', 'screen', 'escape'):
        changed = copy.deepcopy(value); first = next(iter(changed['meshes']))
        if bad == 'missing': changed['meshes'].pop(first)
        elif bad == 'marker': changed['meshes']['SM_TK_Marker'] = changed['meshes'].pop(first)
        elif bad == 'lod': changed['meshes'][first]['lods'].pop()
        elif bad == 'screen': changed['meshes'][first]['screen_sizes'][-1] = .3
        else: changed['meshes'][first]['lods'][0] = '../outside.glb'
        with pytest.raises(ValueError): proof.runtime_inventory(changed)


def test_two_literal_namespace_mapping_preserves_the_entire_real_importer_ast():
    path = HERE.parents[1] / 'unreal/Scripts/import_belmonte_track.py'
    original = proof.owner_tree(path)
    root = '/Game/AtelierValidation/Track_0123456789ab/Prerequisites/Materials'
    mapped = proof.owner_tree(path, root)
    assert ast.dump(original) != ast.dump(mapped)
    seen = []
    for node in ast.walk(mapped):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith(root):
            seen.append(node.value); node.value = '/Game/Belmonte/Materials' + node.value.removeprefix(root)
    assert len(seen) == 2 and ast.dump(original) == ast.dump(mapped)
    with pytest.raises(ValueError): proof.owner_tree(path, '/Game/Belmonte/Materials')


def test_changed_importer_refuses_before_loading_any_definition(tmp_path):
    original = HERE.parents[1] / 'unreal/Scripts/import_belmonte_track.py'
    changed = tmp_path / 'importer.py'; changed.write_bytes(original.read_bytes() + b'\nforeign_change = True\n')
    with pytest.raises(ValueError, match='exact reviewed'): proof.owner_tree(changed)


def test_deletion_observer_records_real_packages_without_replacing_api_results():
    root = '/Game/AtelierValidation/Track_0123456789ab/Library'; calls = []; owned = set()
    editor = SimpleNamespace(list_assets=lambda *args, **kw: [root + '/Source/Part.Part'],
        delete_directory=lambda path: calls.append(path) or False, save_loaded_asset=object())
    boundary = proof.ObserveDeletion(editor, root, owned)
    assert boundary.delete_directory(root + '/Source') is False
    assert calls == [root + '/Source'] and owned == {root + '/Source/Part'}
    assert boundary.save_loaded_asset is editor.save_loaded_asset
    with pytest.raises(ValueError): boundary.delete_directory('/Game/Foreign')
    assert len(calls) == 1


def actor_fixture(*, stuck=False, destroy=True, assigned=True):
    state = dict(mesh=object() if assigned else None, detach_calls=0, destroy_calls=0)
    def detach(value):
        assert value is None
        state['detach_calls'] += 1
        if state['mesh'] is None: return False  # UE reports no change for an already-null component.
        if not stuck: state['mesh'] = None
        return True
    component = SimpleNamespace(set_static_mesh=detach, get_editor_property=lambda name: state['mesh'])
    actor = SimpleNamespace(get_components_by_class=lambda cls: [component])
    def remove(value):
        assert value is actor
        state['destroy_calls'] += 1
        return destroy
    return actor, SimpleNamespace(destroy_actor=remove), state


def test_capture_failure_detaches_only_recorded_actors_and_preserves_original(tmp_path):
    actor, editor, state = actor_fixture(); recorded = [actor]
    foreign, _, foreign_state = actor_fixture()
    failure = RuntimeError('actual capture failed')
    with pytest.raises(RuntimeError) as caught:
        with proof.actor_scope(recorded, editor, object, tmp_path, lambda: {'packages': ['saved partial']}):
            raise failure
    assert caught.value is failure and recorded == []
    assert state['mesh'] is None and state['destroy_calls'] == state['detach_calls'] == 1
    assert foreign_state['detach_calls'] == foreign_state['destroy_calls'] == 0
    report = json.loads((tmp_path / 'failed-fixture-state.json').read_text())
    assert report['original_error']['message'] == 'actual capture failed'
    assert report['cleanup_failures'] == [] and report['remaining_own_actors'] == 0
    assert report['actor_cleanup_only'] and report['partial_namespace']['packages'] == ['saved partial']


@pytest.mark.parametrize('bad', ['null_readback', 'destruction'])
def test_cleanup_failure_is_reported_without_hiding_capture_failure(tmp_path, capsys, bad):
    actor, editor, state = actor_fixture(stuck=bad == 'null_readback', destroy=bad != 'destruction')
    recorded = [actor]; failure = LookupError('native query failure')
    with pytest.raises(LookupError) as caught:
        with proof.actor_scope(recorded, editor, object, tmp_path, lambda: {'packages': ['partial remains']}):
            raise failure
    assert caught.value is failure and recorded == [actor]
    assert 'TRACK OWN ACTOR CLEANUP FAILED' in capsys.readouterr().out
    assert any('TRACK OWN ACTOR CLEANUP FAILED' in note for note in failure.__notes__)
    report = json.loads((tmp_path / 'failed-fixture-state.json').read_text())
    assert report['original_error']['type'] == 'LookupError' and len(report['cleanup_failures']) == 1
    assert report['remaining_own_actors'] == 1 and report['packages_left_for_explicit_recovery']
    assert state['destroy_calls'] == (0 if bad == 'null_readback' else 1)


def test_cleanup_failure_without_primary_is_a_failure_not_success(tmp_path):
    actor, editor, _ = actor_fixture(destroy=False)
    with pytest.raises(RuntimeError, match='OWN ACTOR CLEANUP FAILED'):
        with proof.actor_scope([actor], editor, object, tmp_path, lambda: {}):
            pass
    report = json.loads((tmp_path / 'failed-fixture-state.json').read_text())
    assert report['original_error'] is None and report['cleanup_failures']


def test_failure_state_write_error_never_replaces_original_capture_failure(tmp_path, monkeypatch):
    actor, editor, _ = actor_fixture(); failure = RuntimeError('original capture failure')
    def refuse(*args): raise OSError('fixture reporting refused')
    monkeypatch.setattr(proof, 'atomic_json', refuse)
    with pytest.raises(RuntimeError) as caught:
        with proof.actor_scope([actor], editor, object, tmp_path, lambda: {}):
            raise failure
    assert caught.value is failure
    assert any('failure-state reporting: OSError' in note for note in failure.__notes__)


def test_successful_per_actor_cleanup_requires_reflected_null_readback():
    actor, editor, state = actor_fixture(); recorded = [actor]
    proof.release_actor(actor, editor, object, recorded)
    assert recorded == [] and state['mesh'] is None and state['destroy_calls'] == 1


def test_failure_before_mesh_assignment_still_destroys_recorded_actor(tmp_path):
    actor, editor, state = actor_fixture(assigned=False); recorded = [actor]
    failure = RuntimeError('failed before mesh assignment')
    with pytest.raises(RuntimeError) as caught:
        with proof.actor_scope(recorded, editor, object, tmp_path, lambda: {}):
            raise failure
    assert caught.value is failure and recorded == []
    assert state['detach_calls'] == 0 and state['destroy_calls'] == 1 and state['mesh'] is None
    report = json.loads((tmp_path / 'failed-fixture-state.json').read_text())
    assert report['cleanup_failures'] == [] and report['remaining_own_actors'] == 0


def test_cleanup_retry_after_detach_and_failed_destroy_preserves_original_failure(tmp_path):
    actor, editor, state = actor_fixture(); recorded = [actor]
    def remove(value):
        assert value is actor
        state['destroy_calls'] += 1
        return state['destroy_calls'] == 2
    editor.destroy_actor = remove
    with pytest.raises(ValueError, match='actor destroy failed') as caught:
        with proof.actor_scope(recorded, editor, object, tmp_path, lambda: {}):
            proof.release_actor(actor, editor, object, recorded)
    assert recorded == [] and state['mesh'] is None
    assert state['detach_calls'] == 1 and state['destroy_calls'] == 2
    report = json.loads((tmp_path / 'failed-fixture-state.json').read_text())
    assert report['original_error']['message'] == str(caught.value)
    assert report['cleanup_failures'] == [] and report['remaining_own_actors'] == 0


def test_actual_native_capture_and_retirement_stay_inside_failure_cleanup_boundary():
    source = Path(proof.__file__).read_text(); tree = ast.parse(source)
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'run_native')
    scopes = [n for n in ast.walk(function) if isinstance(n, ast.With)
              and any(ast.unparse(item.context_expr).startswith('actor_scope(') for item in n.items)]
    assert len(scopes) == 1
    calls = [ast.unparse(n.func) for n in ast.walk(scopes[0]) if isinstance(n, ast.Call)]
    assert 'capture.capture' in calls and 'release_actor' in calls and 'retire_owned' in calls


@pytest.mark.parametrize('bad', ['missing', 'bytes', 'size', 'link', 'directory', 'ground'])
def test_actual_material_inputs_refuse_without_creating_any_output(tmp_path, bad):
    textures = tmp_path / 'textures'; textures.mkdir(); path = textures / 'Ground.png'; path.write_bytes(b'actual donor bytes')
    report = dict(materials={'Ground': dict(name='MI_Ground', texture='Ground.png', atlas=False, terrain=True,
        water=False, white_vertex=False, colour=[1, 1, 1, 1], tint=[1, 1, 1, 1], layers={}, tile_m=1, brightness=1)},
        files={'textures/Ground.png': dict(sha256=proof.sha(path), size=path.stat().st_size)})
    assert proof.material_inputs(report, tmp_path) == (['MI_Ground'], {'Ground.png'})
    if bad == 'missing': path.unlink()
    elif bad == 'bytes': path.write_bytes(b'changed')
    elif bad == 'size': report['files']['textures/Ground.png']['size'] += 1
    elif bad == 'link': path.unlink(); path.symlink_to(tmp_path / 'external')
    elif bad == 'directory': path.unlink(); path.mkdir()
    else: report['materials']['Ground']['terrain'] = False
    with pytest.raises((ValueError, FileNotFoundError)): proof.material_inputs(report, tmp_path)
    assert {p.name for p in tmp_path.iterdir()} == {'textures'}


def paired_track_source_fixture(tmp_path, value):
    records = dict(original={}, current={})
    for name, levels in proof.runtime_inventory(value).items():
        mesh = '/Game/Fixture/' + name + '.' + name
        policy = tmp_path / (name + '.json')
        policy.write_text(json.dumps(dict(mesh=mesh, mesh_bounds=[[-1, -1, -1], [1, 1, 1]], bounds_scale=1,
            component_bounds=dict(origin=[0, 0, 0], extent=[1, 1, 1], sphere_radius=2), lod_coordinated=False)))
        kinds = ['ray_negative', 'capsule_negative']
        if proof.collision_lods(value)[name] >= 0: kinds += ['ray_positive', 'capsule_positive']
        row = dict(meshes=[mesh], component_policies=[dict(path=str(policy), sha256=proof.sha(policy))], policy_scope='fixture',
            **{k: [] for k in proof.FIELDS})
        row.update(render_lods={k: ['actual'] for k in range(levels)}, source_lods={k: ['saved'] for k in range(levels)},
            source_presence={k: {True} for k in range(levels)},
            probes=dict(logical=name, controls=[dict(kind=k, hit=None if k.endswith('_negative') else {'blocking': True}) for k in kinds]))
        records['original'][name] = row; records['current'][name] = copy.deepcopy(row)
    return records


@pytest.mark.parametrize('field', ['source_lods', 'render_lods', 'cooked', 'hulls', 'policy', 'settings', 'source_presence', 'sphere', 'probe'])
def test_paired_census_never_weakens_saved_geometry_or_bounds(tmp_path, monkeypatch, field):
    value = runtime(); records = paired_track_source_fixture(tmp_path, value)
    monkeypatch.setattr(proof, 'native_raw_set', lambda record, name: record)
    accepted = proof.compare(records, value)
    assert accepted['native_geometry_complete'] and accepted['meshes'] == 137 and accepted['authored_lods'] == 362
    assert not accepted['complete'] and not accepted['native_complete'] and not accepted['production_runtime_complete']
    name = next(iter(value['meshes'])); row = records['current'][name]
    if field == 'sphere':
        policy = tmp_path / 'changed.json'; old = json.loads(proof.artifact(row['component_policies'][0]))
        old['component_bounds']['sphere_radius'] = 2.1; policy.write_text(json.dumps(old))
        row['component_policies'] = [dict(path=str(policy), sha256=proof.sha(policy))]
    elif field == 'probe': row['probes']['controls'].pop()
    elif field in ('source_lods', 'render_lods'): row[field][0].append('changed actual corner')
    elif field == 'source_presence': row[field][0] = {False}
    else: row[field].append('changed actual evidence')
    with pytest.raises(ValueError): proof.compare(records, value)


@pytest.mark.parametrize('bad', ['bytes', 'link', 'directory', 'foreign'])
def test_host_cleanup_refuses_every_changed_member_before_any_unlink(tmp_path, bad):
    package = '/Game/AtelierValidation/Track_0123456789ab'
    content = tmp_path / 'Content'; root = content / package.removeprefix('/Game/'); root.mkdir(parents=True)
    first = root / 'First.uasset'; first.write_bytes(b'first actual fixture package')
    second = root / 'Second.uasset'; second.write_bytes(b'second actual fixture package')
    allowed = [package + '/First', package + '/Second']
    record = dict(root=str(root), remaining=proof.fixture_files(root, allowed, package), allowed_packages=allowed)
    if bad == 'bytes': second.write_bytes(b'changed')
    elif bad == 'link': second.unlink(); second.symlink_to(first)
    elif bad == 'directory': second.unlink(); second.mkdir()
    else: (root / 'Foreign.uasset').write_bytes(b'foreign')
    with pytest.raises(ValueError): strict_cleanup(dict(content=str(content), package=package), record)
    assert first.read_bytes() == b'first actual fixture package'


def private_fixture(tmp_path):
    root = tmp_path / 'proof'; engine = tmp_path / 'installed'
    (root / 'original/user').mkdir(parents=True); (root / 'current/user').mkdir(parents=True)
    (root / 'private-ddc').mkdir()
    pak = engine / 'Engine/DerivedDataCache/Compressed.ddp'; pak.parent.mkdir(parents=True); pak.write_bytes(b'installed')
    launch = proof.private_launch(root, 'original', engine)
    spec = dict(phase='original', output=str(root / 'original'), launch=launch)
    log = '\n'.join([
        "LogDerivedDataCache: Verbose: Parsing cache graph '" + launch['args'][3][5:] + "'...",
        'LogDerivedDataCache: Display: ../../../Engine/DerivedDataCache/Compressed.ddp: Opened pak cache for reading. (42 MiB)',
        'LogDerivedDataCache: V2Local: Using data cache path ' + launch['ddc_dir'] + ': Writable',
    ])
    return spec, log


def test_private_envelope_exact_args_distinct_userdirs_shared_persistent_ddc(tmp_path):
    spec, log = private_fixture(tmp_path); launch = proof.check_private_launch(spec)
    current = proof.private_launch(tmp_path / 'proof', 'current', tmp_path / 'installed')
    assert launch['ddc_dir'] == current['ddc_dir'] and launch['user_dir'] != current['user_dir']
    assert launch['args'] == ['-UserDir=' + launch['user_dir'], '-nowrite', '-NoZenAutoLaunch',
        '-DDC=(InstalledEnginePak,V2Local=(Type=FileSystem,Path=' + launch['ddc_dir'] + '))',
        '-DDC-NoDefaultGraph', '-LogCmds=LogDerivedDataCache Verbose', '-abslog=' + launch['startup_log']]
    result = proof.startup_ddc(launch, log)
    assert result['filesystems'] == [['V2Local', launch['ddc_dir'], 'Writable']]
    assert result['read_only_paks'] == [launch['engine_pak']] and result['cache_is_evidence'] is False
    (Path(launch['ddc_dir']) / 'untrusted-cached-bytes').write_bytes(b'not proof')
    assert proof.check_private_launch(spec) == launch  # Cache bytes are never compared or trusted.


@pytest.mark.parametrize('fault', ['missing_graph', 'other_graph', 'shared_path', 'readonly', 'missing_pak',
    'foreign_pak', 'write_pak', 'fallback', 'redirect', 'zen', 'extra_store'])
def test_private_startup_refuses_missing_foreign_fallback_and_unavailable_graph(tmp_path, fault):
    spec, text = private_fixture(tmp_path); launch = spec['launch']
    if fault == 'missing_graph': text = '\n'.join(text.splitlines()[1:])
    elif fault == 'other_graph': text += "\nLogDerivedDataCache: Verbose: Parsing cache graph 'Installed'..."
    elif fault == 'shared_path': text = text.replace(launch['ddc_dir'], '/shared/ddc')
    elif fault == 'readonly': text = text.replace(': Writable', ': ReadOnly')
    elif fault == 'missing_pak': text = '\n'.join(row for row in text.splitlines() if 'Opened pak' not in row)
    elif fault == 'foreign_pak': text = text.replace('../../../Engine/DerivedDataCache/Compressed.ddp', '/foreign/pak.ddp')
    elif fault == 'write_pak': text = text.replace('for reading.', 'for writing.')
    elif fault == 'fallback': text += '\nLogDerivedDataCache: Warning: Failed to create graph; Attempting default graph'
    elif fault == 'redirect': text += '\nLogDerivedDataCache: V2Local: Successfully redirected to Shared'
    elif fault == 'zen': text += '\nLogDerivedDataCache: ZenLocal: Using ZenServer HTTP service'
    else: text += '\nLogDerivedDataCache: Shared: Using data cache path /shared: Writable'
    with pytest.raises(ValueError): proof.startup_ddc(launch, text)


@pytest.mark.parametrize('fault', ['args', 'path', 'symlink', 'file', 'punctuation'])
def test_private_envelope_refuses_changed_or_linked_paths_before_native(tmp_path, fault):
    spec, _ = private_fixture(tmp_path); launch = spec['launch']
    if fault == 'args': launch['args'].remove('-DDC-NoDefaultGraph')
    elif fault == 'path': launch['ddc_dir'] = str(tmp_path / 'foreign')
    elif fault == 'punctuation':
        with pytest.raises(ValueError): proof.private_launch(tmp_path / 'bad,graph', 'original', tmp_path / 'installed')
        return
    else:
        path = Path(launch['ddc_dir']); path.rmdir()
        if fault == 'symlink': path.symlink_to(tmp_path / 'installed', target_is_directory=True)
        else: path.write_text('not a directory')
    with pytest.raises(ValueError): proof.check_private_launch(spec)


def test_actual_private_startup_checks_command_userdir_engine_and_log_before_assets(tmp_path):
    import shlex
    spec, log = private_fixture(tmp_path); launch = spec['launch']
    path = Path(launch['startup_log']); path.parent.mkdir(exist_ok=True); path.write_text(log)
    flushed=[]
    U = SimpleNamespace(SystemLibrary=SimpleNamespace(get_command_line=lambda: ' '.join(map(shlex.quote, launch['args'])),
        execute_console_command=lambda world,command:flushed.append((world,command))),
        Paths=SimpleNamespace(project_user_dir=lambda: launch['user_dir'], engine_dir=lambda: launch['engine_dir'],
            convert_relative_path_to_full=str))
    assert proof.receiving_startup(spec, U)['launch'] == launch
    assert flushed==[(None,'FLUSHLOG')]
    U.Paths.project_user_dir = lambda: str(tmp_path)
    with pytest.raises(ValueError): proof.receiving_startup(spec, U)
    U.Paths.project_user_dir = lambda: launch['user_dir']
    U.SystemLibrary.get_command_line = lambda: ' '.join(map(shlex.quote, launch['args'] + ['-DDC=Shared']))
    with pytest.raises(ValueError): proof.receiving_startup(spec, U)
    run = next(node for node in ast.parse(Path(proof.__file__).read_text()).body
               if isinstance(node, ast.FunctionDef) and node.name == 'run_native')
    calls = [node.func.id for node in ast.walk(run) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)]
    assert calls.index('receiving_startup') < calls.index('actor_scope')


def test_existing_unrealscript_passes_private_flags_as_exact_native_arguments(tmp_path):
    from atelier import build
    spec, _ = private_fixture(tmp_path); launch = spec['launch']
    ctx = SimpleNamespace(unreal_cmd=Path('/engine/UnrealEditor-Cmd'))
    command = build.UnrealScript(HERE / 'track_native_equivalence.py', 'not launched', null_rhi=True,
        args=('-nosound', '-noshaderworker', *launch['args']))
    argv = command._argv(ctx, Path('/fixture/Project.uproject'), command.script)
    assert argv[-len(launch['args']):] == launch['args']
    assert '-NullRHI' in argv and '-AllowStdOutLogVerbosity' in argv


@pytest.mark.parametrize('sides', [('original','current'), ('original',), ('current',)])
@pytest.mark.parametrize('fault', ['missing_lod', 'unavailable', 'empty_source', 'mixed_availability'])
def test_matching_missing_authored_track_source_lod_never_passes(tmp_path, monkeypatch, sides, fault):
    value=runtime();records=paired_track_source_fixture(tmp_path,value)
    monkeypatch.setattr(proof,'native_raw_set',lambda record,name:record)
    assert proof.compare(records,value)['native_geometry_complete']
    name=next(iter(value['meshes']))
    for side in sides:
        row=records[side][name]
        if fault=='missing_lod': row['source_lods'].pop(1);row['source_presence'].pop(1)
        elif fault=='unavailable': row['source_presence'][1]={False};row['source_lods'].pop(1)
        elif fault=='empty_source': row['source_lods'][1]=[]
        else: row['source_presence'][1]={True,False}
    with pytest.raises(ValueError,match='authored saved source LOD coverage'): proof.compare(records,value)
