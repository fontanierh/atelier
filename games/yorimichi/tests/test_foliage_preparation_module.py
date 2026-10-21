"""Preparation library changes must stop at their actual native consumers."""
import json
from pathlib import Path
import re
from types import SimpleNamespace

from atelier import build, unreal_modules

GAME = Path(__file__).resolve().parents[1]
SOURCE = GAME/'unreal/Source'
PREPARATION = 'YorimichiFoliagePreparation'
IMPORT = 'YorimichiImport'


def recipe(tmp_path):
    ctx = SimpleNamespace(game='yorimichi', out=tmp_path, logs=tmp_path/'logs',
                          stamps=tmp_path/'stamps', uproject=None)
    return {step.name: step for step in build.load_recipe('yorimichi').steps(ctx)}


def test_actual_graph_keeps_preparation_out_of_raw_imports(tmp_path):
    steps = recipe(tmp_path)
    build.check_modules(list(steps.values()))
    owner = steps['unreal.foliage_system']
    command, = owner.commands
    assert command.modules == (PREPARATION,)
    assert 'unreal.module.'+PREPARATION in owner.needs
    assert tmp_path/'unreal-modules'/f'{PREPARATION}.json' in owner.inputs
    raw = [step for step in steps.values() if step.name != owner.name
           and any(isinstance(command, build.UnrealScript) for command in step.commands)]
    assert len(raw) >= 37
    for step in raw:
        assert 'unreal.module.'+PREPARATION not in step.needs, step.name
        for command in step.commands:
            if isinstance(command, build.UnrealScript):
                assert PREPARATION not in command.modules, step.name
    assert all('unreal.module.'+IMPORT in steps[name].needs
               for name in ('unreal.world', 'unreal.belmonte', 'unreal.brinecove',
                            'unreal.foliage.Tree_Broad_A'))


def test_changed_preparation_binary_preserves_raw_keys_and_isolated_descriptors(tmp_path, monkeypatch):
    steps = recipe(tmp_path/'output')
    descriptor = json.loads((GAME/'unreal/Yorimichi.uproject').read_text())
    modules = {row['Name'] for row in descriptor['Modules']}
    assert PREPARATION in modules and IMPORT in modules
    project = tmp_path/'project/Yorimichi.uproject'
    project.parent.mkdir()
    descriptor['AdditionalPluginDirectories'] = []
    descriptor['Plugins'] = []
    project.write_text(json.dumps(descriptor))
    binaries = project.parent/'Binaries/Mac'
    binaries.mkdir(parents=True)
    libraries = {name: name+'.dylib' for name in modules}
    (binaries/'UnrealEditor.modules').write_text(json.dumps({'BuildId': 'fixture', 'Modules': libraries}))
    for name, filename in libraries.items():
        (binaries/filename).write_text(name+' compiled bytes')
    # Model linked game libraries from their actual native dependency declarations.
    dependencies = {}
    for name in modules:
        declarations = (SOURCE/name/(name+'.Build.cs')).read_text()
        dependencies[name+'.dylib'] = [item+'.dylib' for item in re.findall(r'"(\w+)"', declarations)
                                       if item in modules]
    monkeypatch.setattr(unreal_modules, 'links', lambda path: dependencies[Path(path).name])
    assert unreal_modules.closure(project, [IMPORT]) == {IMPORT}
    assert unreal_modules.closure(project, [PREPARATION]) == {PREPARATION}
    for name in (IMPORT, PREPARATION):
        with unreal_modules.descriptor(project, [name]) as (isolated, excluded):
            assert [row['Name'] for row in json.loads(isolated.read_text())['Modules']] == [name]
            other = PREPARATION if name == IMPORT else IMPORT
            assert any(Path(path).name == libraries[other] for path in excluded)

    def keys():
        done = {'unreal.module.'+name: unreal_modules.record(project, name, tmp_path/(name+'.json'))
                for name in modules}
        return {name: build.fingerprint(steps[name], done) for name in
                ('unreal.world', 'unreal.belmonte', 'unreal.brinecove',
                 'unreal.foliage.Tree_Broad_A', 'unreal.foliage_system')}
    before = keys()
    (binaries/libraries[PREPARATION]).write_text('changed palette, snapshot or variant builder')
    after = keys()
    assert {name for name in before if before[name] != after[name]} == {'unreal.foliage_system'}
    (binaries/libraries[IMPORT]).write_text('changed raw role certification')
    changed = keys()
    assert all(changed[name] != after[name] for name in before if name != 'unreal.foliage_system')
