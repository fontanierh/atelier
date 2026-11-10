"""Prepared sky/painterly graphs compared with the pinned donor functions; no Unreal or package writes.

The existing recorder gives each expression a distinct identity, so the comparison covers which node is wired where,
not only a sequence of property values. Donor code comes from the committed V2 originals, without importing V1 modules.
"""
import ast
import hashlib
import importlib.util
import inspect
import math
from pathlib import Path

import pytest

from test_master_skatepark import World, Token, fake_unreal
from test_master_skatepark import planner, records

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / 'assets/adopted/japan/materials/base-materials/source/unreal/Scripts'
DONOR_PINS = {
    'shared_materials.py': '8cf144f9752bffe771bbddfe984091ad4c288259bc00abba4a64fad5d6678720',
    'painterly_kernel.py': '70f9be7d03f23727829837b2334f3a84691de5bda4189a164c09868feac48077',
    'material_assets.py': '4f48db1203b44c5abca932291ce323f7247a655753167a5f72dfefe5ac4be50f',
}
FAMILY = planner.load_families()['japan_sky_painterly']
MASTERS = {master['builder']: master for master in FAMILY['masters']}
SPEC = importlib.util.spec_from_file_location('v2_sky_painterly_masters', planner.builder_path(FAMILY))
BUILDERS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDERS)


def donor_functions(name, *names):
    """Compile only named functions, without the donor's imports, module-level actions or unrelated world builders."""
    data = (SOURCES / name).read_bytes()
    assert hashlib.sha256(data).hexdigest() == DONOR_PINS[name], name
    tree = ast.parse(data, filename=name)
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in functions} == set(names)
    return compile(ast.Module(body=functions, type_ignores=[]), name, 'exec')


def graph(log):
    """Ignore creation and donor diagnostics; retain every setting, expression identity, connection and compile call."""
    setup = {'does_asset_exist', 'get_asset_tools', 'MaterialFactoryNew', 'create_asset', 'get_editor_property', 'log'}
    return [entry for entry in log if entry[0] not in setup]


def donor_graph(builder):
    world = World()
    unreal = fake_unreal(world)
    mel = unreal.MaterialEditingLibrary
    namespace = {'unreal': unreal, 'MEL': mel, 'LOG': unreal.log, 'math': math,
                 'create': lambda *_: Token(world, 'asset'),
                 'save_material': lambda material: mel.recompile_material(material)}
    exec(donor_functions('material_assets.py', 'node', 'link', 'opt'), namespace)
    if builder == 'sky_material':
        exec(donor_functions('shared_materials.py', 'master'), namespace)
        namespace['master']('M_Sky', unlit=True, fixed_tex=Token(world, '/Game/Japan/Textures/T_sky'))
    else:
        exec(donor_functions('painterly_kernel.py', 'kernel', 'shader'), namespace)
        namespace['painterly_shader'] = namespace['shader']
        exec(donor_functions('shared_materials.py', 'painterly_material'), namespace)
        namespace['painterly_material']()
    return graph(world.log)


def builder_graph(builder, monkeypatch):
    world = World()
    monkeypatch.setattr(BUILDERS, 'unreal', fake_unreal(world))
    master = MASTERS[builder]
    reads = {package: Token(world, package) for package in master['reads']}
    getattr(BUILDERS, builder)(master['package'], reads, **master['arguments'])
    return graph(world.log), world.log


def test_sky_graph_equals_the_pinned_original_and_painterly_keeps_all_nodes_and_parameters(monkeypatch):
    """@cc [owner:fontanierh,label:correctness] sky-painterly-original-graph
    M_Sky matches the donor graph verbatim; M_Painterly preserves every donor SceneTexture, runtime scalar parameter,
    named connection and compilation while adding [branch] sky and near-zero weight early-outs to the Custom HLSL.
    """
    actual_sky, sky_calls = builder_graph('sky_material', monkeypatch)
    assert actual_sky == donor_graph('sky_material')
    actual_paint, paint_calls = builder_graph('painterly_material', monkeypatch)
    donor_paint = donor_graph('painterly_material')
    strip_code = lambda entries: [e for e in entries if not (e[0] == 'set_editor_property' and e[2][0] == "'code'")]
    assert strip_code(actual_paint) == strip_code(donor_paint)
    forbidden = {'save_loaded_asset', 'save_asset', 'import_asset_tasks', 'import_asset', 'AssetImportTask', 'load_asset'}
    for calls in (sky_calls, paint_calls):
        assert not forbidden & {name for name, _, _ in calls}
        assert [name for name, _, _ in calls].count('recompile_material') == 1


def test_sky_requires_its_declared_texture_before_touching_the_destination(monkeypatch):
    world = World()
    monkeypatch.setattr(BUILDERS, 'unreal', fake_unreal(world))
    master = MASTERS['sky_material']
    with pytest.raises(KeyError, match='T_sky'):
        BUILDERS.sky_material(master['package'], {}, **master['arguments'])
    assert world.log == []


def test_painterly_preserves_the_donor_kernel_and_adds_sky_and_weight_early_outs():
    namespace = {'math': math}
    exec(donor_functions('painterly_kernel.py', 'kernel', 'shader'), namespace)
    assert BUILDERS.kernel() == namespace['kernel']()
    shader = BUILDERS.painterly_shader()
    assert '[branch] if (SceneZ.r > 500000.0 || SceneZ.r > SkyDepth * 0.85 || (weight <= 0.005' in shader
    assert '[branch] if (weight > 0.005)' in shader
    taps = BUILDERS.kernel()
    assert len(taps) == 21
    assert all(sum(weights[sector] for _, _, weights in taps) == pytest.approx(1.0) for sector in range(8))


def test_prepared_records_pin_the_self_contained_builder_and_owned_reads(tmp_path):
    for master in FAMILY['masters']:
        builder = getattr(BUILDERS, master['builder'])
        inspect.signature(builder).bind(master['package'], {read: object() for read in master['reads']}, **master['arguments'])
        path = tmp_path / master['id'] / 'asset.toml'
        path.parent.mkdir(parents=True)
        path.write_text(planner.record_text(FAMILY, master, planner.builder_sha(FAMILY)))
        asset = records.load_asset(path)
        assert asset.kind == 'material-master' and asset.authority == 'generated'
        assert [(source.path, source.sha256) for source in asset.sources] == [
            ('src/sky_painterly_masters.py', planner.builder_sha(FAMILY))]
        assert [output.package for output in asset.outputs] == [master['package']]
        assert asset.input_dependencies == master['inputs']
        inputs = {dep: {output.package for output in records.load_asset(ROOT / 'assets' / dep / 'asset.toml').outputs}
                  for dep in master['inputs']}
        assert records.material_input_problems(asset, inputs) == []
        assert set(master['reads']) <= set().union(*inputs.values())


def test_preparation_moves_only_sky_and_painterly_from_the_fourteen_package_checkpoint():
    packages = {master['package'] for master in FAMILY['masters']}
    assert packages == {'/Game/Japan/Materials/M_Sky', '/Game/Japan/Materials/M_Painterly'}
    kept = set(FAMILY['keeps'])
    assert not kept & packages
    # Other families may move these later; their keeps reconciliation must never expand this family's scope.
    remaining_at_preparation = {
        'MPC_Wind', 'M_CoastRock', 'M_Foliage', 'M_ForestGround', 'M_ForestImpostor', 'M_Grass',
        'M_HarborWater', 'M_NorthGate', 'M_NorthMountains', 'M_Painted', 'M_Sea', 'M_Village',
    }
    assert kept <= {f'/Game/Japan/Materials/{name}' for name in remaining_at_preparation}
    assert set(planner.fallback_ids(FAMILY)) == {master['id'] for master in FAMILY['masters']}


def test_builder_has_no_runtime_source_tree_dependency():
    tree = ast.parse(planner.builder_path(FAMILY).read_text())
    imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    assert all(isinstance(node, ast.Import) and all(alias.name in {'math', 'unreal'} for alias in node.names)
               for node in imports)
