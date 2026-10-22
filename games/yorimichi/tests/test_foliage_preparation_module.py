"""Actual preparation libraries and saved packages control foliage rebuilds."""
import json
from dataclasses import replace
from pathlib import Path
import re
from types import SimpleNamespace

from atelier import build, build_deferred, unreal_modules

GAME = Path(__file__).resolve().parents[1]
PREPARATION = 'YorimichiFoliagePreparation'
IMPORT = 'YorimichiImport'


def recipe(out):
    ctx = SimpleNamespace(game='yorimichi', out=out, logs=out/'logs',
                          stamps=out/'stamps', uproject=None)
    return {step.name: step for step in build.load_recipe('yorimichi').steps(ctx)}


def test_real_graph_orders_importers_without_hashing_their_action_identities(tmp_path):
    steps = recipe(tmp_path)
    build.check_modules(list(steps.values()))
    owner = steps['unreal.foliage_system']
    assert set(owner.needs) == set(unreal_modules.needs((IMPORT, PREPARATION)))
    for name in ('unreal.compile', 'unreal.world', 'unreal.belmonte', 'unreal.brinecove', 'data.stage'):
        assert name in owner.after
    assert all(command.modules == (IMPORT, PREPARATION) for command in owner.commands)
    assert set(steps['unreal.foliage_residency'].needs) == set(unreal_modules.needs((PREPARATION, IMPORT)))
    for name in ('unreal.world', 'unreal.belmonte', 'unreal.brinecove', 'unreal.foliage.Tree_Broad_A'):
        assert 'unreal.module.'+PREPARATION not in steps[name].needs
    assert not (GAME/'unreal/Source/Yorimichi/Dev/FoliageResidencyBuilder.cpp').exists()
    descriptor = json.loads((GAME/'unreal/Yorimichi.uproject').read_text())
    assert next(row for row in descriptor['Modules'] if row['Name'] == PREPARATION)['Type'] == 'Editor'
    assert PREPARATION not in (GAME/'unreal/Source/Yorimichi.Target.cs').read_text()


def test_real_native_records_and_deferred_membership_rekey_only_consumed_data(tmp_path, monkeypatch):
    output = tmp_path/'output'
    output.mkdir()
    steps = recipe(output)
    owner = steps['unreal.foliage_system']
    project = tmp_path/'project/Yorimichi.uproject'
    project.parent.mkdir()
    descriptor = json.loads((GAME/'unreal/Yorimichi.uproject').read_text())
    descriptor['AdditionalPluginDirectories'] = []
    descriptor['Plugins'] = []
    project.write_text(json.dumps(descriptor))
    modules = {row['Name'] for row in descriptor['Modules']}
    binaries = project.parent/'Binaries/Mac'
    binaries.mkdir(parents=True)
    libraries = {name: name+'.dylib' for name in modules}
    (binaries/'UnrealEditor.modules').write_text(json.dumps({'BuildId': 'fixture', 'Modules': libraries}))
    dependencies = {}
    for name, filename in libraries.items():
        (binaries/filename).write_text(name+' compiled bytes')
        declarations = (GAME/'unreal/Source'/name/(name+'.Build.cs')).read_text()
        dependencies[filename] = [item+'.dylib' for item in re.findall(r'"(\w+)"', declarations) if item in modules]
    monkeypatch.setattr(unreal_modules, 'links', lambda path: dependencies[Path(path).name])
    assert unreal_modules.closure(project, (PREPARATION, IMPORT)) == {PREPARATION, IMPORT}
    with unreal_modules.descriptor(project, (PREPARATION, IMPORT)) as (isolated, excluded):
        assert {row['Name'] for row in json.loads(isolated.read_text())['Modules']} == {PREPARATION, IMPORT}
        assert any(Path(path).name == libraries['Yorimichi'] for path in excluded)
    # Real source membership provider; only its root is redirected to a temporary receiver.
    provider, = owner.deferred_inputs
    content = project.parent/'Content'
    content.mkdir()
    owner.deferred_inputs = [replace(provider, settings=(content,))]
    def fingerprint():
        done = {unreal_modules.module_step(name): unreal_modules.record(project, name,
                output/'unreal-modules'/(name+'.json')) for name in modules}
        observation = build_deferred.observe(owner)
        return build.fingerprint(owner, done, observation=observation)
    before = fingerprint()
    (binaries/libraries['Yorimichi']).write_text('unrelated changed gameplay')
    assert fingerprint() == before
    (binaries/libraries[PREPARATION]).write_text('changed compiled reducer or codec')
    changed = fingerprint()
    assert changed != before
    (binaries/libraries[IMPORT]).write_text('changed compiled raw classification or snapshot')
    raw_changed = fingerprint()
    assert raw_changed != changed
    mesh = content/'NewRegion/Tree.uasset'
    mesh.parent.mkdir()
    mesh.write_bytes(b'new complete imported source package')
    assert fingerprint() != raw_changed
    previous = fingerprint()
    mesh.write_bytes(b'changed imported source geometry or material binding')
    assert fingerprint() != previous

    previous = fingerprint()
    mesh.with_suffix('.uptnl').write_bytes(b'new supported native sidecar')
    assert fingerprint() != previous
    previous = fingerprint()
    mesh.with_suffix('.uptnl').unlink()
    assert fingerprint() != previous
