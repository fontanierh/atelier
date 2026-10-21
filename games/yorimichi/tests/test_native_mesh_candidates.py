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
    for name in ('mesh_reuse.py', 'unreal_mesh_reuse.py', 'checkpoint_candidates.py'):
        assert RECIPE.paths.STUDIO / 'atelier' / name in ferry.inputs
    world = steps['unreal.world']
    assert world.candidate_scope.directories == (RECIPE.GAME / 'unreal/Content/Japan/Assets',)
    assert all(Path(path).is_relative_to(RECIPE.GAME / 'unreal/Content') for path in ferry.candidate_scope.directories)
