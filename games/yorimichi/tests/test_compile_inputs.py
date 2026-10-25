"""Contract prose must leave compilation current without hiding a real native build edit."""
from pathlib import Path
import os
from types import SimpleNamespace

import pytest

from atelier import build, build_deferred, paths
from test_volcano_layers import RECIPE


def compile_step(root):
    return build.Step('compile', [build.UnrealCompile('Editor')], deferred_inputs=[
        build.DeferredInputs('editor-source-files', RECIPE.compile_inputs.files, ((root,),),
                             support=(Path(RECIPE.compile_inputs.__file__), Path(RECIPE.build_inputs.__file__)))])


def test_contract_edits_leave_compile_current_but_native_membership_and_bytes_do_not(tmp_path):
    root = tmp_path / 'Source'; root.mkdir()
    native = root / 'Module'; native.mkdir()
    cpp = native / 'Actor.cpp'; cpp.write_text('native1')
    step = compile_step(root)
    before = build.fingerprint(step, {})
    contract = native / 'CONTRACTS'; contract.write_text('agent rule1')
    assert build.fingerprint(step, {}) == before
    contract.write_text('agent rule2')
    assert build.fingerprint(step, {}) == before
    contract.unlink()
    assert build.fingerprint(step, {}) == before
    cpp.write_text('native2')
    changed = build.fingerprint(step, {})
    assert changed != before
    resource = native / 'unknown.resource'; resource.write_bytes(b'read by a build rule')
    assert build.fingerprint(step, {}) != changed
    resource.unlink()
    assert build.fingerprint(step, {}) == changed


@pytest.mark.parametrize('relative', ['Module/Module.Build.cs', 'Editor.Target.cs', 'Public/API.h',
                                     'Shader.usf', 'Config/DefaultEngine.ini', 'Plugin.uplugin',
                                     'Resources/Icon.png'])
def test_native_rules_headers_config_shaders_descriptors_and_resources_are_inputs(tmp_path, relative):
    root = tmp_path / 'Source'; root.mkdir()
    source = root / relative; source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b'first')
    step = compile_step(root)
    first = build.fingerprint(step, {})
    source.write_bytes(b'second')
    assert build.fingerprint(step, {}) != first


def test_selected_compile_keeps_legacy_generated_exclusions_and_refuses_links(tmp_path):
    root = tmp_path / 'Source'; root.mkdir()
    source = root / 'Module.cpp'; source.write_text('native')
    assert RECIPE.compile_inputs.files((root,)) == [source]
    for name in ('Intermediate', 'Binaries', 'Saved', 'DerivedDataCache', '__pycache__'):
        folder = root / name; folder.mkdir(); (folder / 'generated.cpp').write_text('generated')
    (root / 'README.md').write_text('documentation')
    assert RECIPE.compile_inputs.files((root,)) == [source]
    (root / 'Linked.h').symlink_to(source)
    with pytest.raises(ValueError, match='Linked editor compile input'):
        RECIPE.compile_inputs.files((root,))


@pytest.mark.parametrize('name', ['unreal.compile', 'unreal.cook', 'data.network'])
def test_recipe_selects_all_original_native_roots_and_keeps_other_inputs(tmp_path, name):
    ctx = SimpleNamespace(out=tmp_path, uproject=tmp_path / 'Yorimichi.uproject')
    step = next(s for s in RECIPE.steps(ctx) if s.name == name)
    assert ctx.uproject in step.inputs
    if name == 'unreal.compile':
        assert step.inputs == [ctx.uproject, *RECIPE.compile_inputs.files(RECIPE.native_source_inputs().settings[0])]
        assert any(path.name == 'AtelierCore.uplugin' for path in step.inputs)
        assert step.needs == ['skate.runtime']
    elif name == 'unreal.cook':
        assert RECIPE.TOOLS / 'package_cook.py' in step.inputs
        assert step.cook_recovery and step.checkpoint_restore
        assert 'data.network' in step.needs
    else:
        assert RECIPE.GAME / 'network_identity.py' in step.inputs
        assert any(p.name == 'content' for p in step.deferred_inputs)
    if name == 'unreal.compile':
        assert not step.deferred_inputs
        build_deferred.validate(step)
        provider = RECIPE.native_source_inputs()
    else:
        provider, = [p for p in step.deferred_inputs if p.name == 'native-source-files']
    assert provider.settings == ((RECIPE.SOURCE, RECIPE.GAME / 'unreal/Config',
                                  RECIPE.GAME / 'unreal/Plugins', paths.ENGINE_PLUGINS),)
    selected = build.Step('selection', [], deferred_inputs=[provider])
    observed = build_deferred.observe(selected)
    assert RECIPE.SOURCE / 'Yorimichi/Yorimichi.Build.cs' in observed.paths
    assert not any(p.name == 'CONTRACTS' for p in observed.members)
    assert RECIPE.SOURCE / 'Yorimichi/Yorimichi.Build.cs' in observed.members


def test_missing_root_remains_an_explicit_compile_input(tmp_path):
    missing = tmp_path / 'missing'
    assert RECIPE.compile_inputs.files((missing,)) == [missing]


@pytest.mark.parametrize('name', ['Native.md', 'CONTRACTS'])
def test_documentation_named_directory_keeps_native_descendants(tmp_path, name):
    folder = tmp_path / name; folder.mkdir()
    code = folder / 'Actor.cpp'; code.write_text('native')
    assert RECIPE.compile_inputs.files((tmp_path,)) == [code]
    step = compile_step(tmp_path)
    before = build.fingerprint(step, {})
    code.write_text('changed')
    assert build.fingerprint(step, {}) != before


def test_special_members_and_unreadable_trees_refuse(tmp_path, monkeypatch):
    special = tmp_path / 'input.pipe'; os.mkfifo(special)
    with pytest.raises(ValueError, match='Non-regular editor compile input'):
        RECIPE.compile_inputs.files((tmp_path,))
    special.unlink()
    original = Path.iterdir

    def unreadable(path):
        if path == tmp_path:
            raise PermissionError('unreadable source tree')
        return original(path)

    monkeypatch.setattr(Path, 'iterdir', unreadable)
    with pytest.raises(PermissionError, match='unreadable source tree'):
        RECIPE.compile_inputs.files((tmp_path,))
