"""Pure producer boundary checks; receiving C++ fixture runs in the normal owner."""
import ast
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

GAME = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('foliage_residency_build', GAME / 'foliage_residency_build.py')
R = importlib.util.module_from_spec(spec)
spec.loader.exec_module(R)


def test_authored_trunk_uses_exact_unreal_endpoints_and_radius():
    assert R.trunk_bounds([.6, 1., 2., -.25, -3., 4., 2.21]) == [60., 100., -200., -25., -300., -400., 221.]
    assert R.trunk_bounds(None) == []


@pytest.mark.parametrize('values', [[], [1] * 6, [0, 0, 0, 0, 0, 0, 1],
    [True, 0, 0, 0, 0, 0, 1], [1, 0, 0, 0, 0, 0, 0], [1, 0, 0, 0, 0, float('inf'), 1]])
def test_invalid_authored_collision_refuses(values):
    with pytest.raises(ValueError):
        R.trunk_bounds(values)


def test_same_lod_selection_as_original_owner_including_bankers_rounding():
    assert R.source_lods(1, True) == [0, 0, 0, 0]
    assert R.source_lods(5, True) == [0, 1, 3, 4]
    assert R.source_lods(9, True) == [0, 3, 5, 8]
    assert R.source_lods(5, False) == [0, 0, 0, 0]
    assert len(R.species()) == 18 and 'Tree_Broad_A' in R.species()


def test_registry_proof_covers_carrier_canopy_shadow_old_patch_and_material_sidecars(tmp_path):
    row = dict(rigid=R.ROOT + '/id/Tree.Tree', optimized=R.ROOT + '/id/Tree_Canopy.Tree_Canopy',
               shadow=R.ROOT + '/id/Tree_Shadow.Tree_Shadow', patch='/Game/FoliageSystem/old_Patch.old_Patch')
    paths = R.assets(row) + [R.ROOT + '/Materials/M_CanopyNearInteraction']
    for package in paths:
        file = tmp_path / (package.removeprefix('/Game/') + '.uasset')
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(package.encode())
    sidecar = tmp_path / 'FoliageResident/id/Tree.ubulk'
    sidecar.write_bytes(b'bulk')
    report = dict(version=2, assets=[row], packages=R.inventory(tmp_path, [row]))
    registry = tmp_path / 'Data/foliage_residency/registry.json'
    registry.parent.mkdir(parents=True)
    registry.write_text(json.dumps(report))
    proof = tmp_path / 'report.json'
    proof.write_text(json.dumps(report))
    assert R.verify(tmp_path, proof)
    sidecar.write_bytes(b'changed')
    assert not R.verify(tmp_path, proof)
    sidecar.unlink()
    assert not R.verify(tmp_path, proof)


def interaction_function():
    path = GAME / 'unreal/Scripts/prepare_foliage_residency.py'
    function = next(n for n in ast.parse(path.read_text()).body if isinstance(n, ast.FunctionDef) and n.name == 'interaction_material')
    return compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec')


def test_owned_material_preserves_old_graph_adds_push_and_correct_cut_scale(tmp_path):
    import hashlib
    values = {}
    class Parameter:
        def get_editor_property(self, name):
            return 'CutScale'
        def set_editor_property(self, name, value):
            values[name] = value
    original = '/Game/FoliageSystem/Materials/M_CanopyNear'
    target = R.ROOT + '/Materials/M_CanopyNearInteraction'
    mpc = '/Game/Japan/Materials/MPC_Wind'
    writes, pushed = [], []
    digest = lambda path: {'near': 'a', 'mpc': 'b'}.get(path, path)
    material = object()
    editor = SimpleNamespace(does_asset_exist=lambda path: False,
        duplicate_asset=lambda source, destination: writes.append((source, destination)) or material,
        load_asset=lambda path: mpc, save_loaded_asset=lambda asset, dirty: True)
    graph = SimpleNamespace(get_material_expressions=lambda asset: [Parameter()], recompile_material=lambda asset: None)
    shared = SimpleNamespace(__file__=__file__, node=lambda: None, link=lambda: None, wind_graph=lambda asset, collection: pushed.append((asset, collection)))
    env = dict(Path=Path, hashlib=hashlib, json=json, __file__=__file__, OUT=tmp_path, CONTENT=tmp_path, R=R,
               G=SimpleNamespace(__file__=__file__, package_inventory=lambda *args: {'source': 'proof'}),
               F=SimpleNamespace(ROOT='/Game/FoliageSystem'), owner=SimpleNamespace(digest=digest),
               E=editor, M=graph, shared_materials=shared, interaction_current=lambda *args: True,
               U=SimpleNamespace(MaterialExpressionVectorParameter=Parameter, LinearColor=lambda *v: v),
               atomic_json=lambda path, value: path.write_text(json.dumps(value)))
    exec(interaction_function(), env)
    assert env['interaction_material']() is material
    assert writes == [(original, target)] and pushed == [(material, mpc)]
    assert values['default_value'] == (1., 1., 2., 1.)


def test_owner_imports_isolated_without_editable_site_or_controller_modules(tmp_path):
    import subprocess
    import sys
    code = """import sys,runpy
class Stub:
 def __getattr__(self,name):return Stub()
 def __call__(self,*a,**k):return Stub()
sys.modules['unreal']=Stub()
runpy.run_path(sys.argv[1],run_name='residency_import_check')
assert 'atelier.build' not in sys.modules
"""
    subprocess.run([sys.executable, '-I', '-S', '-c', code,
                    str(GAME / 'unreal/Scripts/prepare_foliage_residency.py')],
                   cwd=tmp_path, check=True, capture_output=True, text=True, timeout=10)


def test_passable_bush_carrier_does_not_disable_mixed_structure_collision():
    assert R.passable_plant('Bush_Green_A', {'bush'}, {'bush', 'green', 'a'})
    assert not R.passable_plant('Tree_A', {'tree'}, {'tree', 'a'})
    assert not R.passable_plant('TownBushes', {'bush'}, {'town', 'bushes'})
    assert not R.passable_plant('BushFence', {'bush'}, {'bush', 'fence'})


def test_fresh_plan_retains_missing_producer_dependency_without_certifying_it(tmp_path):
    report = tmp_path / 'not-yet-produced/report.json'
    assert R.dependency_inputs(tmp_path, report) == [report]
    assert not R.verify(tmp_path, report)


@pytest.mark.parametrize('name,words,tokens', [
    ('BushFences', {'bush'}, {'bush','fences'}), ('FlowerWalls', {'flower'}, {'flower','walls'}),
    ('BushPlanter', {'bush'}, {'bush'}), ('Pine_A', {'pine'}, {'pine','a'}),
    ('Maple_A', {'maple'}, {'maple','a'}), ('Ginkgo_A', {'ginkgo'}, {'ginkgo','a'}),
    ('Foliage_A', {'foliage'}, {'foliage','a'}), ('Plant_A', {'plant'}, {'plant','a'})])
def test_container_plural_tree_alias_and_unknown_semantics_preserve_collision(name, words, tokens):
    assert not R.passable_plant(name, words, tokens)


def test_declared_authored_hull_and_structural_material_witnesses():
    barrel=R.authored_spec('/Game/Belmonte/Meshes/SM_BM_BP_BarrelPlanter.SM_BM_BP_BarrelPlanter')
    assert barrel['collision']['path'].endswith('_Collision.glb')
    stand=R.authored_spec('/Game/Belmonte/Meshes/SM_BM_BP_FlowerStand.SM_BM_BP_FlowerStand')
    assert not stand.get('collision') and stand['slots']==['M_wood','M_vcol']
    with pytest.raises(ValueError):
        R.authored_spec('/Game/Other/SM_BM_BP_BarrelPlanter.SM_BM_BP_BarrelPlanter')
