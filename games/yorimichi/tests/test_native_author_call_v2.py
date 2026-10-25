"""The generic body calls real staged source with exact native-reference binding."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[1] / 'world/native_author_call_v2.py'
spec = importlib.util.spec_from_file_location('native_author_call_test', SOURCE)
body = importlib.util.module_from_spec(spec)
spec.loader.exec_module(body)
PACKAGE = '/Game/Materials/MI_Result'


def fixture(tmp_path, monkeypatch, text=None):
    folder = tmp_path / 'game/world'
    folder.mkdir(parents=True)
    (folder / 'factory.py').write_text(text or '''from helper import asset
if __name__ == '__main__':
    raise RuntimeError('main executed')
def make(parent, *, values):
    assert parent.get_path_name() == '/Game/Materials/M_Parent.M_Parent'
    assert values == {'tint': [1, 2, 3], 'enabled': True}
    return asset
''')
    (folder / 'helper.py').write_text("import unreal\nasset = unreal.result\n")
    calls = []
    result = SimpleNamespace(get_path_name=lambda: PACKAGE + '.MI_Result')
    parent = SimpleNamespace(get_path_name=lambda: '/Game/Materials/M_Parent.M_Parent')
    def load(path):
        calls.append(('load', path))
        return parent
    def save(asset, dirty_only):
        calls.append(('save', asset, dirty_only))
        return True
    unreal = SimpleNamespace(result=result, EditorAssetLibrary=SimpleNamespace(load_asset=load, save_loaded_asset=save))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    monkeypatch.delitem(sys.modules, 'helper', raising=False)
    context = SimpleNamespace(job_dir=tmp_path, outputs=[PACKAGE],
        inputs={'parent': 'staged/parent', 'transitive': 'staged/texture'},
        packages={'parent': ['/Game/Materials/M_Parent'], 'transitive': ['/Game/Textures/T_parent']},
        params={'settings': [], 'args': {'module': 'game/world/factory.py', 'function': 'make',
            'arguments': [{'native_input': 'parent'}],
            'keyword_arguments': {'values': {'tint': [1, 2, 3], 'enabled': True}}, 'expected_package': PACKAGE}})
    return context, unreal, calls


def test_staged_source_imports_actual_native_input_and_only_expected_final_save(tmp_path, monkeypatch):
    context, unreal, calls = fixture(tmp_path, monkeypatch)
    before = list(sys.path)
    body.run(context)
    assert sys.path == before
    assert calls == [('load', '/Game/Materials/M_Parent'), ('save', unreal.result, False)]
    assert 'factory' not in sys.modules


@pytest.mark.parametrize('field,value', [('function', 'main'), ('function', '__main__'),
    ('function', 'missing'), ('module', '../factory.py'), ('module', '/factory.py'),
    ('expected_package', '/Game/AtelierRaw/Result')])
def test_wrong_entry_path_or_output_refuses(tmp_path, monkeypatch, field, value):
    context, _, calls = fixture(tmp_path, monkeypatch)
    context.params['args'][field] = value
    with pytest.raises(ValueError):
        body.run(context)
    assert not any(row[0] == 'save' for row in calls)


@pytest.mark.parametrize('value', [{'native_input': 'missing'}, {'native_input': 'parent', 'fallback': '/Game/Other'},
                                  float('nan'), float('inf'), object()])
def test_unbound_reference_or_non_json_argument_refuses_before_module_exec(tmp_path, monkeypatch, value):
    context, _, calls = fixture(tmp_path, monkeypatch)
    context.params['args']['arguments'] = [value]
    with pytest.raises(ValueError):
        body.run(context)
    assert not calls


def test_no_namespace_fallback_for_data_or_multiple_packages(tmp_path, monkeypatch):
    context, _, calls = fixture(tmp_path, monkeypatch)
    for value in [[], ['/Game/A', '/Game/B']]:
        context.packages['parent'] = value
        with pytest.raises(ValueError):
            body.run(context)
    assert not calls


def test_wrong_returned_asset_and_save_failure_refuse_and_restore_import_path(tmp_path, monkeypatch):
    context, unreal, calls = fixture(tmp_path, monkeypatch)
    before = list(sys.path)
    unreal.result.get_path_name = lambda: '/Game/Wrong.Wrong'
    with pytest.raises(ValueError):
        body.run(context)
    assert not any(row[0] == 'save' for row in calls)
    assert sys.path == before
    unreal.result.get_path_name = lambda: PACKAGE + '.MI_Result'
    unreal.EditorAssetLibrary.save_loaded_asset = lambda *args: False
    with pytest.raises(RuntimeError):
        body.run(context)
    assert sys.path == before


def test_original_module_exception_propagates_and_restores_path(tmp_path, monkeypatch):
    context, _, calls = fixture(tmp_path, monkeypatch, "raise RuntimeError('original failure')\n")
    before = list(sys.path)
    with pytest.raises(RuntimeError, match='original failure'):
        body.run(context)
    assert sys.path == before
    assert not any(row[0] == 'save' for row in calls)


def test_imported_function_alias_is_not_an_original_source_entry(tmp_path, monkeypatch):
    context, _, calls = fixture(tmp_path, monkeypatch, 'from helper import make\n')
    (tmp_path / 'game/world/helper.py').write_text('def make(*args, **kwargs):\n    raise AssertionError("foreign entry")\n')
    with pytest.raises(ValueError, match='declared source'):
        body.run(context)
    assert not any(row[0] == 'save' for row in calls)
