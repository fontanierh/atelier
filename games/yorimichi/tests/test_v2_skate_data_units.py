"""Actual skate declarations and fake-native body checks over decoded source ROOTs."""
import ast
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace as NS

import pytest
from atelier.build_v2.recipe_dependencies import extract

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'games/yorimichi'
sys.path.insert(0, str(GAME))
import v2_skate_data_units as units  # noqa: E402


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


body = module(ROOT / units.SCRIPT, 'skate_data_body_test')


@pytest.fixture
def rows():
    path = GAME / 'build.py'; recipe = module(path, 'skate_data_recipe_test')
    namespace = {**vars(recipe), 'out': ROOT / 'build/yorimichi', 'ctx': NS()}
    calls = {n.args[0].value: n for n in ast.walk(ast.parse(path.read_bytes())) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == 'Step' and n.args
             and isinstance(n.args[0], ast.Constant) and n.args[0].value in ('skate.runtime', 'unreal.skate_data')}
    steps = [eval(compile(ast.Expression(calls[name]), str(path), 'eval'), namespace)
             for name in ('skate.runtime', 'unreal.skate_data')]
    return extract(steps, checkout=ROOT, build_root=ROOT / 'build')


def test_actual_source_rows_have_complete_single_package_owners_and_installed_verification(rows):
    before = deepcopy(rows); result = units.author_units(rows, checkout=ROOT)
    assert rows == before
    assert len(result['units']) == 29
    runtime, *middle, verify = result['units']; motion = middle[-1]; banks = middle[:-1]
    assert len(banks) == 26
    assert runtime['params']['args']['action'] == 'runtime' and motion['params']['args']['action'] == 'motion'
    assert verify['params']['args']['action'] == 'verify'
    assert len(motion['inputs']) == 27 and len(verify['inputs']) == 29
    assert [u['params']['args']['bank'] for u in banks] == list(range(26))
    assert result['aliases'] == {'unreal.skate_data': [u['id'] for u in result['units']]}
    descriptor = json.loads((GAME / 'unreal/Yorimichi.uproject').read_text())
    expected_modules = [{'name': m['Name'], 'kind': m['Type'], 'loading_phase': m['LoadingPhase']} for m in descriptor['Modules']]
    for unit in result['units']:
        assert unit['op'] == {'kind': 'unreal.author', 'version': '1'}
        assert unit['inputs'][0]['source'] == {'kind': 'item', 'unit': 'skate.runtime', 'item': 'output1'}
        assert unit['params']['input_roots'] == {'source': {'archive_member': 'outputs/1.tree.tar', 'name': 'package'}}
        assert result['module_requirements'][unit['id']] == expected_modules
        assert {units.SCRIPT, units.SAVE, units.SCRIPTS + 'verify_data.py'} <= set(unit['code'])
        assert all((ROOT / p).is_file() for p in unit['code'])
        item, = unit['outputs']; assert item['destination'] == 'checkout'
        if unit is verify:
            assert item['class'] == 'JsonData' and item['files'] == [{'path': 'data/verify.json',
                'install_path': 'build/yorimichi/skate-data/verify.json', 'required': True}]
        else:
            assert item['class'] == 'DataAsset' and len(item['files']) == 6
            assert item['files'][0]['required'] and item['files'][0]['path'].endswith('.uasset')
            assert all('install_path' in f for f in item['files'])
    assert len(result['packages'][units.MOTION]['dependencies']) == 26
    assert 'build/yorimichi/skate-data/verify.json' in result['packages']


@pytest.mark.parametrize('damage', ['producer', 'outputs', 'command', 'product', 'missing'])
def test_incomplete_or_changed_original_rows_refuse(rows, damage):
    if damage == 'producer': rows[0]['commands'][0]['args'][1]['path'] = 'build/other'
    elif damage == 'outputs': rows[1]['outputs'].pop()
    elif damage == 'command': rows[1]['commands'][2]['marker'] = 'other'
    elif damage == 'product': rows[0]['products'] = [{'id': 'x'}]
    else: rows.pop(0)
    with pytest.raises(units.Unsupported): units.author_units(rows, checkout=ROOT)
    assert units.author_units([], checkout=ROOT)['aliases'] == {}


class Asset:
    def __init__(self, path): self.path = path
    def get_path_name(self): return self.path + '.' + self.path.rsplit('/', 1)[-1]
class Runtime(Asset): pass
class Motion(Asset): pass
class Bank(Asset): pass


@pytest.fixture
def editor(tmp_path, monkeypatch):
    source = tmp_path / 'runtime/package'; source.mkdir(parents=True)
    manifest = {'version': 1, 'clips': 129, 'files': {f'animation/clips/0/{i}.skate': {} for i in range(129)}}
    (source / 'package-manifest.json').write_text(json.dumps(manifest))
    save = tmp_path / units.SAVE; save.parent.mkdir(parents=True); shutil.copyfile(ROOT / units.SAVE, save)
    content = tmp_path / 'Content'; content.mkdir()
    assets, calls = {}, []
    def create(action, path, cls): calls.append((action, path)); assets[path] = cls(path); return ''
    def runtime(source, folder): return create('runtime', folder + '/RuntimeData', Runtime)
    def bank(source, index, path): return create('bank' + str(index), path, Bank)
    def motion(source, path): return create('motion', path, Motion)
    def save(asset, only_if_is_dirty=False):
        path = content / (asset.path.removeprefix('/Game/') + '.uasset'); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'primary'); calls.append(('save', asset.path)); return True
    report = {'schema': 2, 'runtime_schema': 1, 'asset': units.MOTION + '.MotionData',
              'runtime_asset': units.RUNTIME + '.RuntimeData', 'clips': 129, 'frames': 300, 'bone_samples': 600,
              'replay_steps': 7200, 'replay_cases': 12, 'exact': True, 'negative_control': True,
              'invalid_record_controls': 3, 'runtime_files': 7, 'runtime_bytes': 1000, 'runtime_exact': True,
              'runtime_negative_control': True, 'runtime_invalid_record_controls': 3,
              'banks': [body._bank(b) + f'.Bank_{b:03d}' for b in range(2)]}
    settings = NS(values={'motion_data': object(), 'runtime_data': object()})
    original_settings = dict(settings.values)
    settings.get_editor_property = settings.values.__getitem__
    settings.set_editor_property = settings.values.__setitem__
    def verify(source):
        assert settings.values == {'motion_data': units.MOTION + '.MotionData', 'runtime_data': units.RUNTIME + '.RuntimeData'}
        return json.dumps(report), ''
    unreal = NS(SkateSettings='SkateSettings', get_default_object=lambda cls: settings, SoftObjectPath=str,
        SkateRuntimeData=Runtime, SkateMotionData=Motion, SkateMotionBank=Bank,
        EditorAssetLibrary=NS(load_asset=assets.get, does_asset_exist=lambda p: p in assets, save_loaded_asset=save),
        SkateDataLibrary=NS(import_runtime=runtime, import_motion_bank=bank, import_motion_index=motion,
                            verify_to_json=verify))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    return NS(root=tmp_path, source=source, content=content, assets=assets, calls=calls, unreal=unreal, report=report, settings=settings, original_settings=original_settings)


def context(editor, action, bank=0):
    args = {'action': action, 'clips': 129, 'bank_count': 2}
    package = units.RUNTIME if action == 'runtime' else (units.MOTION if action == 'motion' else body._bank(bank))
    if action == 'verify': args['configured_assets'] = {'motion_data': units.MOTION + '.MotionData', 'runtime_data': units.RUNTIME + '.RuntimeData'}
    if action != 'verify': args['package'] = package
    if action == 'bank': args['bank'] = bank
    inputs, packages = {'source': str(editor.source)}, {'source': []}
    if action in ('motion', 'verify'):
        for b in range(2):
            path = body._bank(b); slot = f'bank{b:03d}'; editor.assets[path] = Bank(path)
            inputs[slot], packages[slot] = 'native', [path]
    if action == 'verify':
        for slot, path, cls in (('runtime', units.RUNTIME, Runtime), ('motion', units.MOTION, Motion)):
            editor.assets[path] = cls(path); inputs[slot], packages[slot] = 'native', [path]
    return NS(job_dir=str(editor.root), content_dir=str(editor.content), inputs=inputs, packages=packages,
              outputs=[] if action == 'verify' else [package], data_outputs=(body.REPORT,) if action == 'verify' else (),
              params={'args': args, 'settings': [], 'input_roots': {'source': {'archive_member': 'outputs/1.tree.tar', 'name': 'package'}}})


@pytest.mark.parametrize('action', ['runtime', 'bank', 'motion'])
def test_author_calls_only_selected_native_api_and_produces_actual_owned_primary(editor, action):
    case = context(editor, action, bank=1); package = case.outputs[0]
    built = body.run(case)
    assert built.path == package
    assert editor.calls == [(action if action != 'bank' else 'bank1', package), ('save', package)]
    assert (editor.content / (package.removeprefix('/Game/') + '.uasset')).is_file()


def test_verifier_returns_complete_original_report_in_memory_and_writes_nothing(editor):
    case = context(editor, 'verify'); before = set(editor.root.rglob('*'))
    assert body.run(case) == {body.REPORT: editor.report}
    assert editor.calls == [] and set(editor.root.rglob('*')) == before
    assert editor.settings.values == editor.original_settings


@pytest.mark.parametrize('damage', ['source', 'bank_missing', 'native_path', 'output', 'existing'])
def test_roster_native_and_output_mismatches_refuse_before_authoring(editor, damage):
    case = context(editor, 'motion')
    if damage == 'source': case.params['args']['clips'] = 130
    elif damage == 'bank_missing': del case.inputs['bank001']
    elif damage == 'native_path': case.packages['bank000'] = [units.RUNTIME]
    elif damage == 'output': case.outputs = [units.RUNTIME]
    else: editor.assets[units.MOTION] = Motion(units.MOTION)
    with pytest.raises(ValueError): body.run(case)
    assert editor.calls == []


@pytest.mark.parametrize('result', [None, False, True, 'failed'])
def test_import_uses_original_bool_out_error_convention(editor, result):
    case = context(editor, 'runtime')
    editor.unreal.SkateDataLibrary.import_runtime = lambda *args: result
    with pytest.raises(RuntimeError): body.run(case)
    assert editor.calls == []


@pytest.mark.parametrize('damage', ['result', 'exact', 'banks', 'finite', 'controls'])
def test_verifier_refuses_incomplete_or_nonfinite_native_evidence(editor, damage):
    case = context(editor, 'verify')
    if damage == 'result': editor.unreal.SkateDataLibrary.verify_to_json = lambda source: None
    elif damage == 'exact': editor.report['runtime_exact'] = False
    elif damage == 'banks': editor.report['banks'].pop()
    elif damage == 'finite': editor.report['frames'] = float('nan')
    else: editor.report['replay_cases'] = 1
    with pytest.raises((ValueError, RuntimeError)): body.run(case)
    assert editor.calls == []
    assert editor.settings.values == editor.original_settings


def test_source_archive_index_comes_from_actual_producer_output_row(rows):
    rows[0]['outputs'].reverse()
    unit = units.author_units(rows, checkout=ROOT)['units'][0]
    assert unit['inputs'][0]['source']['item'] == 'output0'
    assert unit['params']['input_roots']['source']['archive_member'] == 'outputs/0.tree.tar'


def test_declared_complete_root_binding_decodes_actual_archive_before_body(rows, editor):
    from atelier.build_v2 import recipe_job, unreal_inputs
    unit = units.author_units(rows, checkout=ROOT)['units'][0]
    frozen = editor.root / 'inputs/source'
    archive = frozen / unit['params']['input_roots']['source']['archive_member']
    archive.parent.mkdir(parents=True)
    recipe_job.pack_root(editor.source, archive)
    original = archive.read_bytes()
    runtime = editor.root / '.unreal-runtime'; runtime.mkdir()
    prepared = unreal_inputs.stage_inputs(editor.root,
        [{'name': 'source', 'path': 'inputs/source', 'identity': {'state': 'digest'}}], editor.content,
        runtime_dir=runtime, output_packages=[units.RUNTIME], root_bindings=unit['params']['input_roots'])
    case = context(editor, 'runtime')
    case.inputs, case.packages = prepared['inputs'], prepared['packages']
    built = body.run(case)
    assert built.path == units.RUNTIME
    assert Path(case.inputs['source']).is_relative_to(runtime)
    assert (Path(case.inputs['source']) / 'package-manifest.json').is_file()
    assert archive.read_bytes() == original


def test_missing_primary_cannot_complete_a_native_author(editor):
    case = context(editor, 'runtime')
    editor.unreal.EditorAssetLibrary.save_loaded_asset = lambda *args, **kwargs: True
    with pytest.raises(RuntimeError, match='regular primary'):
        body.run(case)


def test_verifier_restores_original_configured_asset_cdo_when_native_api_raises(editor):
    case = context(editor, 'verify')
    def fail(source): raise RuntimeError('native failure')
    editor.unreal.SkateDataLibrary.verify_to_json = fail
    with pytest.raises(RuntimeError, match='native failure'): body.run(case)
    assert editor.settings.values == editor.original_settings


def test_verifier_refuses_config_paths_that_differ_from_declared_native_items(editor):
    case = context(editor, 'verify')
    case.params['args']['configured_assets']['motion_data'] = '/Game/Other.Other'
    with pytest.raises(ValueError, match='configured assets'): body.run(case)
    assert editor.settings.values == editor.original_settings
