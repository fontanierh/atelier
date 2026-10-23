"""Selected terminal query closure, independent tasks and original route ownership."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import shutil

import pytest
from atelier.atomic_files import atomic_json
from atelier.export_manifest import publish_receipt

GAME = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, GAME / relative)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def test_normal_terminal_graph_has_one_selected_factory_per_mesh_and_original_collision_owners(tmp_path):
    module = load('terminal_atomic_graph_test', 'ferry_terminal_atomic_build.py')
    rows = {row.name: row for row in module.steps(SimpleNamespace(out=tmp_path), site_inputs=())}
    for key in module.MODELS:
        step = rows['world.ferry_terminals.geometry.' + key]
        assert step.cache and step.heavy
        assert step.reads == ['ferry_terminals.source.' + key]
        assert {product.name for product in step.products} == {'ferry_terminals.geometry.' + key, 'ferry_terminals.query.' + key}
        command, = step.commands
        assert command.factory_startup and command.threads == 3
        assert key in command.args
        assert GAME / 'assets/vehicles/ferry/terminals/build.py' not in step.inputs
    for key in ('FT_HD_Collision', 'FT_BC_Collision'):
        step = rows['world.ferry_terminals.collision.' + key]
        assert step.cache and step.commands[0].factory_startup and step.commands[0].threads == 3
        assert len(step.products) == 1
    assert rows['world.ferry_terminals.geometry'].replan
    assert rows['world.ferry_terminals.sources'].deferred_inputs
    assert rows['world.ferry_terminals.audit'].deferred_inputs
    assert 'world.hidamari_ferry_cut' in rows['world.ferry_terminals.sources'].needs


def fixture_source(program):
    return dict(schema=1, asset='FT_HD_Test', owner='hidamari', constructor='selected', program=program,
        parameters={}, ground=[dict(rectangle=[0., 0., 1., 1.], height=2.475)])


def fixture_primitives():
    return dict(schema=1, asset='primitives',
        ferry="from types import SimpleNamespace\nMATERIALS = {}\ndef Mesh(name): return SimpleNamespace(name=name)\n",
        terminal='MATERIALS = {}\nCOL = []\nBROW_COL = []\n')


def test_constructor_requires_every_exact_declared_query_and_no_foreign_owner():
    module = load('terminal_constructor_test', 'world/regions/ferry/terminal_constructor.py')
    source = fixture_source("def selected(kit, data):\n    m = kit.F.Mesh('FT_HD_Test')\n    z = kit.ground_under(kit.FS.load_world('hidamari'), 0., 0., 1., 1.)\n    return m, {'height': z}\n")
    _, mesh, data = module.construct(source, fixture_primitives())
    assert mesh.name == 'FT_HD_Test' and data['height'] == 2.475
    for changed in (source['program'].replace('1., 1.)', '1., 2.)'),
                    source['program'].replace("load_world('hidamari')", "load_world('brinecove')"),
                    "def selected(kit, data):\n    return kit.F.Mesh('FT_HD_Test'), {}\n"):
        with pytest.raises(ValueError): module.construct(dict(source, program=changed), fixture_primitives())


def test_selected_terminal_source_has_one_mesh_constructor_and_original_phase_order():
    hd = load('terminal_hd_test', 'world/regions/hidamari/ferry_terminal.py')
    bc = load('terminal_bc_test', 'world/regions/brinecove/ferry_terminal.py')
    assert list(hd.CONSTRUCTORS) == ['FT_HD_Jetty', 'FT_HD_Stage', 'FT_HD_Brow', 'FT_HD_WaitingHouse', 'FT_HD_Timetable']
    assert list(bc.CONSTRUCTORS) == ['FT_BC_Landing', 'FT_BC_Brow', 'FT_BC_Fenders', 'FT_BC_Pavilion', 'FT_BC_TicketHut', 'FT_BC_Props']
    import ast
    for module in (hd, bc):
        text = Path(module.__file__).read_text()
        functions = {node.name: node for node in ast.parse(text).body if isinstance(node, ast.FunctionDef)}
        for key, name in module.CONSTRUCTORS.items():
            constructors = [node for node in ast.walk(functions[name]) if isinstance(node, ast.Call)
                            and ast.unparse(node.func) == 'kit.F.Mesh']
            assert len(constructors) == 1 and ast.literal_eval(constructors[0].args[0]) == key


def test_one_house_height_edit_changes_its_geometry_and_exact_collision_data_only(tmp_path, monkeypatch):
    import numpy as np
    source = load('terminal_projection_edit_test', 'world/regions/ferry/terminal_sources.py')
    game = tmp_path / 'game'
    for owner in ('hidamari', 'brinecove'):
        target = game / 'world/regions' / owner / 'ferry_terminal.py'; target.parent.mkdir(parents=True)
        shutil.copyfile(GAME / 'world/regions' / owner / 'ferry_terminal.py', target)
    monkeypatch.setattr(source, 'GAME', game)
    real_load = source.load
    oracle = SimpleNamespace(FENDER=.6, HD=SimpleNamespace(QUAY_RAIL=2.9),
        rect_points=lambda x0, y0, x1, y1, step: [(x0, y0), (x1, y1)],
        levels=lambda world, points, ceiling: np.full(len(points), 2.475))
    monkeypatch.setattr(source, 'load', lambda name, path: oracle if Path(path) == source.KIT / 'site.py' else real_load(name, path))
    site = dict(ship=dict(sill_z=6.939), hidamari=dict(berth=dict(gate=[839.8, -139.4, 6.939], face=-138.8,
        quay_top_z=2.475, promenade_z=2.867, promenade_range=[2.8, 2.867], door_ground_z=2.475,
        timetable=[833.3, -122.5, 2.475])), brinecove=dict(berth=dict(gate=[-245., 25., 6.939], face=-244.5, pier_deck_z=5.2)))
    before = source.projections(site, dict(hidamari={}, brinecove={}))
    path = game / 'world/regions/hidamari/ferry_terminal.py'
    text = path.read_text(); assert text.count('wh = 2.9') == 1
    path.write_text(text.replace('wh = 2.9', 'wh = 2.95'))
    after = source.projections(site, dict(hidamari={}, brinecove={}))
    assert {key for key in before if before[key] != after[key]} == {'FT_HD_WaitingHouse', 'hidamari_collision'}
    assert before['FT_HD_WaitingHouse']['parameters']['wh'] == 2.9
    assert after['FT_HD_WaitingHouse']['parameters']['wh'] == after['hidamari_collision']['parameters']['wh'] == 2.95
    path.write_text(text)
    original_kit = source.KIT
    private_kit = tmp_path / 'kit'; private_kit.mkdir()
    kit_text = (original_kit / 'build.py').read_text()
    needle = 'm.beam((0.0, yy, 0.5), (L, yy, rise + 0.5), 0.04, 0.04, WHITE)'
    assert kit_text.count(needle) == 1
    (private_kit / 'build.py').write_text(kit_text.replace(needle, needle.replace('0.04, 0.04', '0.041, 0.04')))
    monkeypatch.setattr(source, 'KIT', private_kit)
    changed_brows = source.projections(site, dict(hidamari={}, brinecove={}))
    assert {key for key in before if before[key] != changed_brows[key]} == {'FT_HD_Brow', 'FT_BC_Brow'}


def test_final_harbor_queries_keep_original_probe_storage_and_loader_precision(tmp_path):
    import numpy as np
    source = load('terminal_query_precision_test', 'world/regions/ferry/terminal_sources.py')
    fs = source.load('terminal_original_loader_test', source.KIT / 'site.py')
    original = np.asarray([[[0, 0, 1], [1, 0, 1], [0, 1, 1]], [[2, 2, 3], [3, 2, 3], [2, 3, 3]]], dtype=np.float32)
    np.savez(tmp_path / 'world_hidamari.npz', ground=np.empty((0, 3, 3), dtype=np.float32), solid=original,
        solid_label=np.asarray([0, 1], dtype=np.int16), meta=json.dumps(dict(labels=['HD_Harbor', 'Other'], bounds=[0, 0, 4, 4])))
    world = fs.load_world('hidamari', out=tmp_path)
    assert world['ground'].dtype == world['solid'].dtype == np.float64
    matrix = np.eye(4); matrix[0, 3] = 1e-9
    surfaces = [dict(name='HD_Harbor', role='render', positions=original[0], triangles=np.asarray([[0, 1, 2]]), matrix=matrix)]
    value = source.final_world(world, surfaces)
    expected = np.asarray(source.region_query.triangles(surfaces), dtype=np.float32).astype(float)
    assert value['solid'].dtype == np.float64
    assert np.array_equal(value['solid'][0], original[1]) and np.array_equal(value['solid'][1:], expected)
    assert value['solid_label'].tolist() == [1, 0]


def assembly_fixture(tmp_path):
    module = load('terminal_atomic_products_test', 'ferry_terminal_atomic_products.py')
    groups, ownership, owners, walks = {}, {}, {}, {}
    for owner, prefix in (('hidamari', 'FT_HD_'), ('brinecove', 'FT_BC_')):
        meshes = {}
        for key in module.MODELS:
            if not key.startswith(prefix): continue
            hulls = [dict(vertices=[[0, 0, 0]])] if key.endswith('_Brow') else []
            groups[key] = [key]
            ownership[key] = dict(source_triangles=12, pieces=[dict(name=key, triangles=12, collision_hulls=len(hulls))])
            meshes[key] = dict(triangles=12, materials=['test'], open_edges=0, flipped_parts=0, authored_hulls=hulls)
            folder = tmp_path / 'exports/world.ferry_terminals.export' / key
            folder.mkdir(parents=True); (folder / (key + '.fbx')).write_bytes(key.encode())
            publish_receipt(folder, key=key, primary=key + '.fbx', triangles=12, bounds=[[0, 0, 0], [1, 1, 1]],
                            metadata=dict(slots=['test'], collision_hulls=len(hulls)))
        owners[owner] = dict(meshes=meshes, collision=dict(convex_hulls=1), seats=dict(count=1, failures=[]),
            mesh_order=(['FT_BC_Landing', 'FT_BC_Brow', 'FT_BC_Pavilion', 'FT_BC_TicketHut', 'FT_BC_Fenders', 'FT_BC_Props']
                        if owner == 'brinecove' else list(meshes)),
            coplanar=dict(count=0), carried=dict(groups=1, islands=1, failures=[], uncarried_groups=0, uncarried_islands=0),
            ship_clash=dict(pass_=True, clashes=[]), walk={'pass': True})
        owners[owner]['ship_clash'] = {'pass': True, 'clashes': []}
        walks[owner] = dict(audit=owners[owner]['walk'], ship_clash=owners[owner]['ship_clash'])
        key = prefix + 'Collision'; folder = tmp_path / 'exports/world.ferry_terminals.collision' / key
        folder.mkdir(parents=True); (folder / (key + '.fbx')).write_bytes(key.encode())
        publish_receipt(folder, key=key, primary=key + '.fbx', triangles=12, bounds=[[0, 0, 0], [1, 1, 1]],
                        metadata=dict(slots=[], collision_hulls=1, authored_hulls=[dict(vertices=[[0, 0, 0]])]))
    atomic_json(tmp_path / 'atomic_regions/ferry_terminals/logical-pieces.json', dict(schema=1, parents=groups, ownership=ownership))
    atomic_json(tmp_path / 'ferry/terminals/atomic-audit.json', dict(failures=[], terminals=owners, audit_fixtures=[dict(ok=True)]))
    atomic_json(tmp_path / 'ferry/terminals/walk.json', walks)
    return module


def test_terminal_file_assembly_retains_brow_native_frame_and_all_independent_bytes(tmp_path):
    module = assembly_fixture(tmp_path)
    manifest = module.assemble(tmp_path)
    assert set(manifest['terminals']['hidamari']['meshes']) == {key for key in module.MODELS if key.startswith('FT_HD_')}
    assert len(manifest['terminals']['hidamari']['meshes']['FT_HD_Brow']['authored_hulls']) == 1
    assert manifest['terminals']['brinecove']['mesh_order'] == ['FT_BC_Landing', 'FT_BC_Brow', 'FT_BC_Pavilion', 'FT_BC_TicketHut', 'FT_BC_Fenders', 'FT_BC_Props']
    assert (tmp_path / 'ferry/terminals/atomic-assets/FT_HD_Brow.fbx').read_bytes() == b'FT_HD_Brow'


@pytest.mark.parametrize('defect', ['missing', 'walk', 'hulls', 'audit'])
def test_terminal_assembly_rejects_incomplete_safety_or_membership_before_writes(tmp_path, defect):
    module = assembly_fixture(tmp_path)
    if defect == 'missing':
        (tmp_path / 'exports/world.ferry_terminals.export/FT_HD_Brow/FT_HD_Brow.fbx').unlink()
    elif defect == 'walk':
        (tmp_path / 'ferry/terminals/walk.json').write_text('{}')
    else:
        path = tmp_path / 'ferry/terminals/atomic-audit.json'; data = json.loads(path.read_text())
        if defect == 'hulls': data['terminals']['hidamari']['meshes']['FT_HD_Brow']['authored_hulls'] = []
        else: data['terminals']['hidamari']['carried']['failures'] = ['uncarried']
        atomic_json(path, data)
    with pytest.raises((ValueError, FileNotFoundError)):
        module.assemble(tmp_path)
    assert not (tmp_path / 'ferry/terminals/atomic-assets').exists()
