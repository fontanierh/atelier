"""Native inputs retain geometry without duplicating unused LODs or giant strings."""
import ast
from copy import deepcopy
from pathlib import Path


def writer():
    from atelier import mesh_geometry as G
    script = Path(__file__).resolve().parents[1] / 'unreal/Scripts/build_foliage_system.py'
    function = next(node for node in ast.parse(script.read_text()).body
                    if isinstance(node, ast.FunctionDef) and node.name == 'write_representations')
    namespace = {'G': G}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(script), 'exec'), namespace)
    return namespace['write_representations']


def product():
    level = dict(vertices=[dict(p=point, n=[0., 0., 1.], c=[1., .5, 0., 1.],
                               uv=[.25, .75], uvs=[[.25, .75], [3., .375]])
                           for point in ([1.25, -2., 3.], [2., -2., 3.], [1.25, -1., 3.])],
                 faces=[dict(v=[0, 1, 2], s=4)])
    return dict(source='/Game/Test.Plant', screens=[1., .24, .07, .018],
                levels=[deepcopy(level) for _ in range(4)], shadow=deepcopy(level),
                patch=deepcopy(level), coverage=[{'canopy': [1., 2., 3.]}])


def test_native_documents_preserve_all_geometry_and_only_required_fields(tmp_path):
    from atelier import mesh_geometry as G
    prepared = product()
    before = deepcopy(prepared)
    paths, geometry = writer()(prepared, tmp_path/'mesh.json', 2)
    for role, levels in dict(optimized=prepared['levels'],shadow=[prepared['shadow']],patch=[prepared['patch']]).items():
        assert G.file_digest(paths[role]) == geometry[role] == G.expected_digest(levels, 2)
    assert prepared == before


def test_validated_visual_and_shadow_are_not_serialized_for_a_patch_only_repair(tmp_path):
    from atelier import mesh_geometry as G
    prepared = product()
    paths, geometry = writer()(prepared, tmp_path/'mesh.json', 2, ['patch'])
    assert set(paths) == set(geometry) == {'patch'}
    assert list(tmp_path.iterdir()) == [paths['patch']]
    assert G.file_digest(paths['patch']) == G.expected_digest([prepared['patch']],2)


def test_no_missing_variants_write_no_transport(tmp_path):
    assert writer()(product(),tmp_path/'mesh.json',2,[]) == ({},{})
    assert not list(tmp_path.iterdir())
