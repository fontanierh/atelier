"""Contract prose must leave compilation current without hiding a real native build edit."""
from pathlib import Path
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


def test_recipe_selects_all_original_compile_roots_and_keeps_build_prerequisite(tmp_path):
    ctx = SimpleNamespace(out=tmp_path, uproject=tmp_path / 'Yorimichi.uproject')
    step = next(s for s in RECIPE.steps(ctx) if s.name == 'unreal.compile')
    assert step.inputs == [ctx.uproject]
    assert step.needs == ['skate.runtime']
    provider, = step.deferred_inputs
    assert provider.settings == ((RECIPE.SOURCE, RECIPE.GAME / 'unreal/Config',
                                  RECIPE.GAME / 'unreal/Plugins', paths.ENGINE_PLUGINS),)
    observed = build_deferred.observe(step)
    assert RECIPE.SOURCE / 'Yorimichi/Yorimichi.Build.cs' in observed.paths
    assert not any(p.name == 'CONTRACTS' for p in observed.members)
    assert RECIPE.SOURCE / 'Yorimichi/Yorimichi.Build.cs' in observed.members


def test_missing_root_remains_an_explicit_compile_input(tmp_path):
    missing = tmp_path / 'missing'
    assert RECIPE.compile_inputs.files((missing,)) == [missing]
