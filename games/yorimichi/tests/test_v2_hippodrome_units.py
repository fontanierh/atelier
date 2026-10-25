"""unreal.hippodrome followers on the actual export templates, the paint projection, and bodies on a fake editor."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace as NS

import pytest
from atelier.build_v2.file_groups import emit
from atelier.build_v2.recipe_dependencies import extract

ROOT = Path(__file__).resolve().parents[3]
GAME = ROOT / 'games/yorimichi'
sys.path.insert(0, str(GAME))
import v2_geometry_templates as geometry_templates  # noqa: E402
import v2_hippodrome_units as units  # noqa: E402
from v2_texture_units import Unsupported  # noqa: E402


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


members = load(units.BODY, 'hippodrome_members_test')
body = load(units.SCRIPT, 'hippodrome_body_test')
SURFACE_PARENTS, STRUCTURE_PARENTS = units.parents(ROOT)
SPECS = units.surface_specs(ROOT)
# The classes the native controller (platform/build-v2/src/unreal_controller.rs) admits for authored assets.
AUTHORED = {'Material', 'MaterialInstance', 'MaterialParameterCollection', 'Map', 'Blueprint', 'BlendSpace1D',
            'AdventureMoveSet', 'AnimBoneCompressionSettings', 'WandererDefinition', 'SoundAttenuation', 'DataAsset', 'JsonData'}
OTHERS = {'Data', 'RawTexture', 'Texture', 'RawStaticMesh', 'StaticMesh'}


@pytest.fixture(scope='module')
def actual():
    spec = importlib.util.spec_from_file_location('hippodrome_recipe', GAME / 'build.py')
    recipe = importlib.util.module_from_spec(spec); sys.modules['hippodrome_recipe'] = recipe; spec.loader.exec_module(recipe)
    context = NS(uproject=GAME / 'unreal/Yorimichi.uproject', out=ROOT / 'build/yorimichi')
    steps = [s for s in recipe.hippodrome_steps(context) if 'stable' not in s.name]
    names, products = {s.name for s in steps}, {p.name for s in steps for p in s.products}
    for step in steps:
        step.needs = [n for n in step.needs if n in names]; step.after = []
        step.reads = [r for r in step.reads if r in products]
    rows = extract(steps, checkout=ROOT, build_root=ROOT / 'build')
    return rows, geometry_templates.geometry_templates(rows, checkout=ROOT)


@pytest.fixture(scope='module')
def declared(actual):
    return units.attach_followers(actual[1], rows=actual[0], checkout=ROOT)


def test_every_child_and_owner_from_the_actual_rows(declared):
    assert len(SURFACE_PARENTS) == 6 and len(STRUCTURE_PARENTS) == 4 and sorted(SPECS) == ['HD_Dirt', 'HD_Grass', 'HD_Rail', 'HD_Stone']
    found = {u['id']: u for u in declared['units']}
    assert sorted(found) == sorted([
        'unreal.hippodrome.material.M_HD_Structure', 'unreal.hippodrome.texture.raw.T_Grass', 'unreal.hippodrome.texture.T_Grass',
        'unreal.hippodrome.texture.raw.T_Dirt', 'unreal.hippodrome.texture.T_Dirt', 'hippodrome.members.paints',
        'unreal.hippodrome.data', 'unreal.hippodrome.record', *(f'unreal.hippodrome.material.M_{k}' for k in SPECS)])
    raw = found['unreal.hippodrome.texture.raw.T_Grass']
    assert raw['params']['source_member'] == 'T_HD_Grass.png' and raw['inputs'][0]['source']['unit'] == 'world.hippodrome.textures'
    assert found['unreal.hippodrome.texture.T_Grass']['params']['args'] == {'action': 'texture'}
    assert {i['name'] for i in found['unreal.hippodrome.material.M_HD_Stone']['inputs']} == set()
    assert found['unreal.hippodrome.material.M_HD_Dirt']['params']['args']['texture'] == 'texture'
    paints = found['hippodrome.members.paints']
    assert paints['inputs'][0]['source'] == {'kind': 'item', 'unit': 'world.hippodrome', 'item': 'product0'} and 'whole' in paints['inputs'][0]
    data = found['unreal.hippodrome.data']['outputs'][0]
    assert data['destination'] == 'checkout' and data['files'][0]['install_path'] == units.DATA_FILE
    templates = {t['unit_prefix']: t for t in declared['geometry']['templates']}
    ground = templates[units.PREFIX + 'SM_HD_Ground']
    raw, finish = (f['unit'] for f in ground['followers'])
    assert raw['params'] == {'op': 'raw_import', 'kind': 'static_mesh', 'source': 'source', 'destination': '/Game/_Raw/Hippodrome/$piece'}
    assert finish['params']['destination'] == '/Game/Hippodrome/$piece' and sorted(finish['params']['args']['surfaces']) == sorted(SPECS)
    stand = templates[units.PREFIX + 'SM_HD_Grandstand']['followers'][1]['unit']
    join = stand['params']['args']['paint']['derived_items']['templates'][0]
    assert join['piece'] == '$piece' and join['follower'] == 2 and join['unit_prefix'] == 'unreal.hippodrome.paints'
    assert 'surfaces' not in stand['params']['args'] and {i['name'] for i in stand['inputs']} == {'raw', 'export', 'master'}
    (paint,) = declared['templates']
    assert [f['unit']['id'] for f in paint['followers']] == ['$export.raw', '$export.finish', '$export.paint']
    assert paint['followers'][2]['unit']['outputs'][0]['logical_path'] == '/Game/Hippodrome/Meshes/$piece/MI_$piece'
    record = found['unreal.hippodrome.record']['params']['args']['meshes'][0]['derived_items']['templates']
    assert len(record) == 10 and all(t['follower'] == 1 and t['item'] == 'mesh' for t in record)
    assert declared['aliases']['unreal.hippodrome'] == tuple(found)


def test_emitted_output_classes_are_registered(declared):
    followers = [f['unit'] for t in [*declared['geometry']['templates'], *declared['templates']] for f in t.get('followers', ())]
    for unit in [*declared['units'], *followers]:
        allowed = AUTHORED if unit['op']['kind'] == 'unreal.author' else OTHERS
        assert {o['class'] for o in unit['outputs']} <= allowed, unit['id']
    for unit in [*declared['units'], *followers]:
        if unit['op']['kind'] == 'unreal.author' and unit['outputs'][0]['class'] == 'JsonData':
            assert len(unit['outputs']) == 1, 'the worker encodes exactly one returned JSON output per job'


@pytest.mark.parametrize('damage', ['importer', 'template', 'product'])
def test_declaration_drift_refuses(actual, damage):
    rows, geometry = deepcopy(actual[0]), deepcopy(actual[1])
    found = {r['id']: r for r in rows}
    if damage == 'importer':
        found['unreal.hippodrome']['commands'][0]['env'] = [['X', '1']]
    elif damage == 'template':
        geometry['templates'] = [t for t in geometry['templates'] if not t['unit_prefix'].endswith('SM_HD_ToteBoard')]
    else:
        found['world.hippodrome.textures']['products'][0]['paths'] = ['build/yorimichi/other']
    with pytest.raises(Unsupported):
        units.attach_followers(geometry, rows=rows, checkout=ROOT)


# ---- projection -----------------------------------------------------------------------------------------------------

PNG = b'\x89PNG\r\n\x1a\n' + b'p' * 8


def glb(*, image=True, materials=1):
    binary = bytearray(struct.pack('<9f', 0, 0, 0, 1, 0, 0, 0, 1, 0)); views = [{'buffer': 0, 'byteOffset': 0, 'byteLength': 36}]
    doc = {'asset': {'version': '2.0'}, 'materials': [{'name': f'Tripo_{i}', 'pbrMetallicRoughness': {}} for i in range(materials)]}
    if image:
        views.append({'buffer': 0, 'byteOffset': 36, 'byteLength': len(PNG)}); binary += PNG
        doc.update(images=[{'mimeType': 'image/png', 'bufferView': 1}], textures=[{'source': 0}])
        doc['materials'][0]['pbrMetallicRoughness']['baseColorTexture'] = {'index': 0}
    doc.update(bufferViews=views, buffers=[{'byteLength': len(binary)}])
    while len(binary) % 4:
        binary += b'\0'
    text = json.dumps(doc).encode(); text += b' ' * (-len(text) % 4)
    total = 12 + 8 + len(text) + 8 + len(binary)
    return (struct.pack('<4sII', b'glTF', 2, total) + struct.pack('<I4s', len(text), b'JSON') + text
            + struct.pack('<I4s', len(binary), b'BIN\x00') + bytes(binary))


@pytest.fixture
def region(tmp_path):
    root = tmp_path / 'region'; (root / 'glb').mkdir(parents=True)
    pieces = {'SM_HD_Ground': ('HD_Grass', glb(image=False, materials=1)), 'SM_HD_Grandstand_Piece00': ('Tripo_0', glb()),
              'SM_HD_Grandstand_Piece01': ('Tripo_0', glb())}
    report = {}
    for name, (material, data) in pieces.items():
        (root / 'glb' / f'{name}.glb').write_bytes(data)
        report[name] = {'material': material, 'sha256': hashlib.sha256(data).hexdigest(), 'triangles': 1, 'min': [0, 0, 0], 'max': [1, 1, 0]}
    (root / 'hippodrome.json').write_text(json.dumps({'meshes': [{'name': n} for n in pieces]}))
    (root / 'build-report.json').write_text(json.dumps({'meshes': report}))
    return root


def test_paint_members_are_each_structure_childs_own_map(region, tmp_path):
    value = members.members(region, sorted(SPECS))
    assert sorted(value) == ['SM_HD_Grandstand_Piece00', 'SM_HD_Grandstand_Piece01']
    assert value['SM_HD_Grandstand_Piece00'] == {'name': 'SM_HD_Grandstand_Piece00', 'material': 'Tripo_0', 'mime': 'image/png', 'image': PNG}
    members.project(region, sorted(SPECS), tmp_path / 'out')
    manifest = emit(tmp_path / 'out', tmp_path / 'files', parent='Hippodrome_paints', extensions=['.json'])
    assert len(manifest['pieces']) == 2
    selected = tmp_path / 'selected'; selected.mkdir()
    (selected / 'SM_HD_Grandstand_Piece01.json').write_bytes((tmp_path / 'out/SM_HD_Grandstand_Piece01.json').read_bytes())
    members.select(selected, tmp_path / 'member', 'SM_HD_Grandstand_Piece01')
    assert (tmp_path / 'member/SM_HD_Grandstand_Piece01.png').read_bytes() == PNG
    assert json.loads((tmp_path / 'member/export.json').read_text())['primary'] == 'SM_HD_Grandstand_Piece01.png'


@pytest.mark.parametrize('damage', ['stale', 'unpainted', 'roster'])
def test_paint_projection_refuses_regions_that_differ(region, damage):
    if damage == 'stale':
        (region / 'glb/SM_HD_Grandstand_Piece00.glb').write_bytes(glb(materials=1) + b'')
        report = json.loads((region / 'build-report.json').read_text()); report['meshes']['SM_HD_Grandstand_Piece00']['sha256'] = '0' * 64
        (region / 'build-report.json').write_text(json.dumps(report))
    elif damage == 'unpainted':
        data = glb(image=False)
        (region / 'glb/SM_HD_Grandstand_Piece00.glb').write_bytes(data)
        report = json.loads((region / 'build-report.json').read_text())
        report['meshes']['SM_HD_Grandstand_Piece00']['sha256'] = hashlib.sha256(data).hexdigest()
        (region / 'build-report.json').write_text(json.dumps(report))
    else:
        (region / 'hippodrome.json').write_text(json.dumps({'meshes': [{'name': 'SM_HD_Ground'}]}))
    with pytest.raises(ValueError):
        members.members(region, sorted(SPECS))


# ---- bodies ---------------------------------------------------------------------------------------------------------

def test_original_functions_are_read_without_the_top_level():
    specs, module = body.original((ROOT / units.ORIGINAL).read_text())
    assert specs == SPECS and [f.name for f in module.body] == ['surface', 'structure_material', 'restyle']


class Asset:
    def __init__(self, path, **props): self.path, self.props = path, dict(props)
    def get_path_name(self): return self.path + '.' + self.path.rsplit('/', 1)[1]
    def get_editor_property(self, key): return self.props[key]
    def set_editor_property(self, key, value): self.props[key] = value
class Texture2D(Asset): pass
class Material(Asset): pass
class MaterialInstanceConstant(Asset): pass
class Box(NS): pass
class StaticMesh(Asset):
    def get_num_triangles(self, lod): return self.props['triangles']
    def set_material(self, index, material): self.props['material'] = material
    def get_material(self, index): return self.props.get('material')
    def get_bounding_box(self): return self.props['box']


class Anything:
    def __getattr__(self, name): return Anything()
    def __call__(self, *args, **kwargs): return Anything()


@pytest.fixture
def editor(tmp_path):
    assets, saves = {}, []
    def duplicate(source, destination):
        assets[destination] = type(assets[source])(destination, **deepcopy({k: v for k, v in assets[source].props.items() if k != 'box'}),
                                                  **({'box': assets[source].props['box']} if 'box' in assets[source].props else {}))
        return assets[destination]
    def create(name, folder, cls, factory):
        assets[f'{folder}/{name}'] = cls(f'{folder}/{name}'); return assets[f'{folder}/{name}']
    params = {}
    MEL = NS(set_material_instance_texture_parameter_value=lambda i, n, t: params.__setitem__((i.path, n), t),
             get_material_instance_texture_parameter_value=lambda i, n: params.get((i.path, n)),
             clear_all_material_instance_parameters=lambda i: [params.pop(k) for k in list(params) if k[0] == i.path],
             set_material_instance_parent=lambda i, m: i.set_editor_property('parent', m), update_material_instance=lambda i: None,
             delete_all_material_expressions=lambda m: None, create_material_expression=lambda *a: Anything(),
             connect_material_property=lambda *a: True, layout_material_expressions=lambda m: None, recompile_material=lambda m: None)
    library = NS(load_asset=lambda p: assets.get(p), does_asset_exist=lambda p: p in assets, duplicate_asset=duplicate,
                 save_loaded_asset=lambda a, *_: saves.append(a.path) or True)
    unreal = NS(EditorAssetLibrary=library, Texture2D=Texture2D, Material=Material, MaterialInstanceConstant=MaterialInstanceConstant,
                StaticMesh=StaticMesh, MaterialEditingLibrary=MEL, MaterialFactoryNew=lambda: None,
                MaterialInstanceConstantFactoryNew=lambda: None,
                AssetToolsHelpers=NS(get_asset_tools=lambda: NS(create_asset=create)),
                CollisionTraceFlag=NS(CTF_USE_COMPLEX_AS_SIMPLE='complex'), LinearColor=lambda *a: a,
                **{n: Anything() for n in ('MaterialExpressionTextureSample', 'MaterialExpressionConstant3Vector', 'MaterialExpressionConstant',
                                           'MaterialSamplerType', 'MaterialProperty')})
    job = tmp_path / 'job'
    (job / units.ORIGINAL).parent.mkdir(parents=True)
    (job / units.ORIGINAL).write_bytes((ROOT / units.ORIGINAL).read_bytes())
    return NS(assets=assets, saves=saves, unreal=unreal, job=job, params=params)


def context(editor, outputs, inputs, packages, params, data=()):
    roots = {}
    for slot, value in inputs.items():
        path = editor.job / 'inputs' / slot
        path.mkdir(parents=True, exist_ok=True)
        if value is not None:
            (path / value[0]).write_text(json.dumps(value[1]))
        roots[slot] = str(path)
    return NS(outputs=outputs, inputs=roots, packages=packages, params=params, job_dir=str(editor.job), data_outputs=data)


def test_surface_runs_the_original_function_on_its_declared_texture(editor):
    editor.assets['/Game/Hippodrome/Textures/T_Grass'] = Texture2D('/Game/Hippodrome/Textures/T_Grass')
    args = {'action': 'surface', 'key': 'HD_Grass', 'texture': 'texture'}
    job = context(editor, {'/Game/Hippodrome/Materials/M_HD_Grass': {}}, {'texture': None},
                  {'texture': ['/Game/Hippodrome/Textures/T_Grass']}, {'args': args, 'settings': []})
    material = body.surface(job, editor.unreal, args)
    assert material.path == '/Game/Hippodrome/Materials/M_HD_Grass' and material.props['two_sided'] is False
    assert editor.saves == ['/Game/Hippodrome/Materials/M_HD_Grass']
    args = {'action': 'surface', 'key': 'HD_Stone'}
    job = context(editor, {'/Game/Hippodrome/Materials/M_HD_Stone': {}}, {}, {}, {'args': args, 'settings': []})
    assert body.surface(job, editor.unreal, args).props['two_sided'] is True


def test_paint_is_the_restyled_instance_on_the_structure_master(editor):
    master = editor.assets[units.STRUCTURE] = Material(units.STRUCTURE)
    folder = '/Game/Hippodrome/Meshes/SM_HD_Grandstand'
    texture = editor.assets[f'{folder}/T_SM_HD_Grandstand'] = Texture2D(f'{folder}/T_SM_HD_Grandstand')
    args = {'action': 'paint', 'name': 'SM_HD_Grandstand', 'texture': 'texture', 'master': 'master'}
    job = context(editor, {f'{folder}/MI_SM_HD_Grandstand': {}}, {'texture': None, 'master': None},
                  {'texture': [texture.path], 'master': [master.path]}, {'args': args, 'settings': []})
    instance = body.paint(job, editor.unreal, args)
    assert instance.props['parent'] is master and editor.params == {(instance.path, 'BaseColorTexture'): texture}


def test_mesh_checks_its_own_receipt_and_binds_the_named_surface(editor):
    for key in SPECS:
        editor.assets[f'/Game/Hippodrome/Materials/M_{key}'] = Material(f'/Game/Hippodrome/Materials/M_{key}')
    box = NS(min=NS(x=0., y=-200., z=0.), max=NS(x=100., y=-100., z=50.))
    editor.assets['/Game/_Raw/Hippodrome/SM_HD_Ground'] = StaticMesh('/Game/_Raw/Hippodrome/SM_HD_Ground', triangles=12, box=box,
                                                                     static_materials=[1], body_setup=Asset('body'))
    receipt = {'asset': 'SM_HD_Ground', 'triangles': 12, 'metadata': {'triangles': 12, 'material': 'HD_Grass', 'min': [0, 1, 0], 'max': [1, 2, .5]}}
    args = {'action': 'mesh', 'piece': 'SM_HD_Ground', 'export': 'export', 'surfaces': {k: 'surface_' + k for k in SPECS}}
    params = {'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': '/Game/Hippodrome/SM_HD_Ground', 'args': args}
    def job(value):
        return context(editor, {'/Game/Hippodrome/SM_HD_Ground': {}},
                       {'raw': None, 'export': ('export.json', value), **{'surface_' + k: None for k in SPECS}},
                       {'raw': ['/Game/_Raw/Hippodrome/SM_HD_Ground'], **{'surface_' + k: [f'/Game/Hippodrome/Materials/M_{k}'] for k in SPECS}},
                       params)
    mesh = body.mesh(job(receipt), editor.unreal, args)
    assert mesh.props['material'] is editor.assets['/Game/Hippodrome/Materials/M_HD_Grass']
    assert mesh.props['body_setup'].props == {'collision_trace_flag': 'complex', 'double_sided_geometry': True}
    editor.assets.pop('/Game/Hippodrome/SM_HD_Ground')
    wrong = deepcopy(receipt); wrong['metadata']['max'] = [1, 3, .5]
    with pytest.raises(ValueError, match='unit/axis'):
        body.mesh(job(wrong), editor.unreal, args)


def test_data_and_record_each_own_one_json(editor):
    job = context(editor, {}, {'region': ('hippodrome.json', {'meshes': []})}, {}, {'args': {}}, data=('data/hippodrome.json',))
    assert body.data(job, editor.unreal, {'region': 'region'}) == {'data/hippodrome.json': {'meshes': []}}
    with pytest.raises(ValueError, match='only its report'):
        body.record(job, editor.unreal, {'region': 'region', 'meshes': []})
