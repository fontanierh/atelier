"""Normal recipe discovery includes complete bounded candidate scopes and adapter code."""
from pathlib import Path
from types import SimpleNamespace

from test_volcano_layers import RECIPE


def test_regions_discover_report_and_complete_mesh_namespaces(tmp_path):
    steps = {step.name: step for step in RECIPE.steps(SimpleNamespace(out=tmp_path, uproject=None))}
    for region, namespace in [('belmonte', 'Belmonte'), ('brinecove', 'Brinecove')]:
        step = steps['unreal.' + region]
        assert step.candidate_scope.files == (tmp_path / region / 'build-report.json', tmp_path / region / 'runtime.json')
        assert step.candidate_scope.directories == (RECIPE.GAME / 'unreal/Content' / namespace / 'Meshes',)
        assert RECIPE.paths.STUDIO / 'atelier/unreal_mesh_reuse.py' in step.inputs
        assert RECIPE.paths.STUDIO / 'atelier/mesh_reuse.py' in step.inputs


def test_common_ferry_scope_includes_complete_package_folders_and_shared_code(tmp_path):
    steps = {step.name: step for step in RECIPE.steps(SimpleNamespace(out=tmp_path, uproject=None))}
    ferry = steps['unreal.ferry']
    root = RECIPE.GAME / 'unreal/Content/Ferry'
    assert set(ferry.candidate_scope.directories) == {root / 'Ship', root / 'Terminals'}
    for name in ('mesh_reuse.py', 'unreal_mesh_reuse.py', 'native_candidates.py', 'native_protocol.py'):
        assert RECIPE.paths.STUDIO / 'atelier' / name in ferry.inputs
    world = steps['unreal.world']
    assert world.candidate_scope.directories == (RECIPE.GAME / 'unreal/Content/Japan/Assets',)
    assert all(Path(path).is_relative_to(RECIPE.GAME / 'unreal/Content') for path in ferry.candidate_scope.directories)


def test_native_adapters_do_not_depend_on_unrelated_host_controller_code(tmp_path):
    steps = RECIPE.steps(SimpleNamespace(out=tmp_path, uproject=tmp_path / 'Fixture.uproject'))
    forbidden = {'build.py', 'build_plan.py', 'build_batches.py', 'build_checkpoints.py', 'build_zen.py',
                 'playtest.py', 'setup.py'}
    studio = RECIPE.paths.STUDIO / 'atelier'
    cascade = {step.name: sorted({Path(path).name for path in step.inputs if Path(path).is_relative_to(studio)
        and (Path(path).name in forbidden or Path(path).name.startswith(('release', 'artifact_')))})
        for step in steps if step.heavy}
    assert not {name: files for name, files in cascade.items() if files}
    # Keep the complete native protocol closure without host controllers.
    from atelier.native_protocol import runtime_files
    runtime = set(runtime_files())
    for step in steps:
        if studio / 'unreal_mesh_reuse.py' in step.inputs:
            assert runtime <= set(step.inputs), step.name
