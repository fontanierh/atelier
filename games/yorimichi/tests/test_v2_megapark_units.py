"""Actual MegaPark rows and D2 templates, keyed generated members, per-package units and fake-editor bodies."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace as NS

import numpy as np
import pytest
from atelier import mesh_ir
from atelier.build_v2.recipe_dependencies import extract
from atelier.export_manifest import publish_receipt

ROOT = Path(__file__).resolve().parents[3]; GAME = ROOT / 'games/yorimichi'
sys.path[:0] = [str(GAME), str(GAME / 'world'), str(GAME / 'world/regions')]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


units = load('games/yorimichi/v2_megapark_units.py', 'megapark_units_test')
body = load(units.SCRIPT, 'megapark_body_test')
RESTYLE = {'unit': 'world.megapark_restyle', 'item': 'output0',
           'root': {'archive_member': 'outputs/0.tree.tar', 'name': 'textures'}}


@pytest.fixture(scope='module')
def rows():
    """The actual MegaPark rows; reads/needs on producers outside the family are dropped only for extraction."""
    factory = load('games/yorimichi/build.py', 'megapark_build_test')
    ctx = NS(game='yorimichi', out=ROOT / 'build/yorimichi', uproject=None)
    steps = [s for s in factory.world_steps(ctx) + factory.unreal_steps(ctx) if 'megapark' in s.name and 'craterpark' not in s.name]
    names, produced = {s.name for s in steps}, {p.name for s in steps for p in s.products}
    for step in steps:
        step.reads = [r for r in step.reads if r in produced]; step.needs = [n for n in step.needs if n in names]
        step.after = [n for n in step.after if n in names]
    return extract(steps, checkout=ROOT, build_root=ROOT / 'build')


@pytest.fixture(scope='module')
def catalogue():
    return units.catalogue(ROOT)


def members(catalogue):
    textures = list(catalogue[0])
    return {'materials': {'0xa1': {'alpha': 0, 'textures': {'diffuse': '0x2c70170a001d0133', 'lightmap': textures[1]}},
                          '0xb2': {'alpha': 1, 'textures': {'diffuse': textures[2], 'normal': textures[3], 'transparent': textures[2]}}}}


@pytest.fixture(scope='module')
def library(rows, catalogue):
    return units.megapark_units(rows, checkout=ROOT, members=members(catalogue), natives={'restyle': RESTYLE})


def test_committed_rosters_and_restyle_set(catalogue):
    textures, render, collision, seam = catalogue
    restyle = units.restyled(ROOT)
    assert len(textures) == 405 and len(render) == 50 and len(collision) == 29 and seam == ['SM_MP_Seam', 'UC_MP_Seam']
    assert restyle['0x2c70170a001d0133'] == '2c70170a001d0133.png' and set(restyle) <= set(textures)


def test_generated_material_roster_is_required(rows):
    with pytest.raises(units.DynamicMembership):
        units.megapark_units(rows, checkout=ROOT)


def test_library_units_bind_original_texture_material_and_level_policy(rows, library, catalogue):
    by_id = {u['id']: u for u in library['units']}
    assert len(by_id) == 2 * (405 + 4) + 3 + 2 + 1
    rock = by_id['unreal.megapark.texture.raw.T_2c70170a001d0133']
    assert rock['inputs'][0]['source'] == {'kind': 'item', 'unit': RESTYLE['unit'], 'item': RESTYLE['item']}
    assert rock['params']['source_member'] == '2c70170a001d0133.png' and rock['params']['input_roots'] == {'source': RESTYLE['root']}
    plain = next(t for t in catalogue[0] if t not in units.restyled(ROOT))
    raw = by_id[f'unreal.megapark.texture.raw.T_{plain[2:]}']
    assert raw['inputs'][0]['source'] == {'kind': 'file', 'path': f'{units.SOURCE}/{catalogue[0][plain]}'}
    lightmap = list(catalogue[0])[1]
    props = by_id[f'unreal.megapark.texture.T_{lightmap[2:]}']['params']['properties']
    assert props['srgb'] is False and props['address_x'] == {'unreal_enum': 'TextureAddress.TA_CLAMP'}
    normal = by_id[f'unreal.megapark.texture.T_{list(catalogue[0])[3][2:]}']['params']['properties']
    assert normal == {'srgb': False, 'compression_settings': {'unreal_enum': 'TextureCompressionSettings.TC_NORMALMAP'}}
    default = by_id['unreal.megapark.texture.raw.T_DefaultNormal']
    library_row = next(r for r in rows if r['id'] == 'world.megapark')
    index = library_row['products'][0]['paths'].index('build/yorimichi/megapark/normal.png')
    assert default['params']['input_roots']['source'] == {'archive_member': f'products/0-{index}.tree.tar', 'name': 'normal.png'}
    masked = by_id['unreal.megapark.instance.b2']
    names = {i['source']['unit'] for i in masked['inputs']}
    assert 'unreal.megapark.material.M_RetailMasked' in names and 'unreal.megapark.material.M_RetailOpaque' not in names
    assert set(masked['params']['args']['textures']) == {'diffuse', 'normal', 'transparent'}
    assert masked['params']['input_roots']['restyle'] == {'archive_member': 'outputs/0.tree.tar', 'name': 'textures'}
    level = by_id['unreal.megapark.level']
    assert level['outputs'][0]['files'][0]['path'] == 'content/Game/MegaPark/Maps/SuperUltraMegaPark.umap'
    templates = level['params']['args']['pieces']['derived_items']['templates']
    assert len(templates) == 50 + 29 and all(t['follower'] == 1 and t['item'] == 'asset' for t in templates)
    for unit in by_id.values():
        produced = {i['source']['unit'] for i in unit['inputs'] if i['source']['kind'] == 'item'} - {r['id'] for r in rows} - {RESTYLE['unit']}
        assert produced <= set(by_id) and unit['id'] not in produced
        assert set(library['staged_inputs'][unit['id']]) == {i['name'] for i in unit['inputs']}


@pytest.mark.parametrize('damage', ['alpha', 'role', 'tid', 'restyle', 'importer'])
def test_noncanonical_members_or_sources_refuse(rows, catalogue, damage):
    rows, roster, refs = deepcopy(rows), members(catalogue), {'restyle': RESTYLE}
    if damage == 'alpha': roster['materials']['0xa1']['alpha'] = 3
    elif damage == 'role': roster['materials']['0xa1']['textures']['emissive'] = list(catalogue[0])[0]
    elif damage == 'tid': roster['materials']['0xa1']['textures']['diffuse'] = '0xmissing'
    elif damage == 'restyle': refs = {}
    else: rows = [r for r in rows if r['id'] != 'unreal.megapark']
    with pytest.raises(units.Unsupported):
        units.megapark_units(rows, checkout=ROOT, members=roster, natives=refs)


@pytest.fixture(scope='module')
def geometry(rows):
    return load('games/yorimichi/v2_geometry_templates.py', 'megapark_templates_test').geometry_templates(rows, checkout=ROOT)


def test_every_parent_but_the_seed_gets_original_piece_followers(rows, geometry, library):
    result = units.attach_followers(geometry, library['packages'], rows=rows, checkout=ROOT)
    templates = {t['unit_prefix'].removeprefix('world.megapark.export.'): t for t in result['templates']
                 if t['unit_prefix'].startswith('world.megapark.export.')}
    assert not templates['SM_MP_ImportSeed'].get('followers') and len([t for t in templates.values() if t.get('followers')]) == 81
    raw, finish = [f['unit'] for f in templates['UC_MP_Seam']['followers']]
    assert raw['params']['fbx'] == units.FBX and raw['params']['fbx']['remove_degenerates'] is False
    assert raw['params']['fbx']['vertex_color_import_option'] == {'unreal_enum': 'VertexColorImportOption.IGNORE'}
    args = finish['params']['args']
    assert args['collision'] is True and set(args['materials']) == {'0xa1', '0xb2'}
    producer = next(r for r in rows if r['id'] == 'world.megapark.geometry.UC_MP_Seam')
    index = [p['id'] for p in producer['products']].index('megapark.metadata.UC_MP_Seam')
    assert finish['params']['input_roots'] == {'metadata': {'archive_member': f'products/{index}-0.tree.tar', 'name': 'UC_MP_Seam.json'}}
    assert {i['name']: i['source'] for i in finish['inputs']}['metadata']['item'] == f'product{index}'
    assert finish['outputs'][0]['logical_path'] == '/Game/MegaPark/Meshes/$piece'
    assert all((ROOT / p).is_file() for p in finish['code'])
    assert geometry == load('games/yorimichi/v2_geometry_templates.py', 'megapark_templates_again').geometry_templates(rows, checkout=ROOT)


@pytest.mark.parametrize('damage', ['natives', 'partial', 'attached'])
def test_followers_refuse_missing_roster_or_family(rows, geometry, library, damage):
    geometry, natives = deepcopy(geometry), dict(library['packages'])
    park = [t for t in geometry['templates'] if t['unit_prefix'].startswith('world.megapark.export.SM_MP_')]
    if damage == 'natives': natives = {p: v for p, v in natives.items() if '/MI_' not in p}
    elif damage == 'partial': geometry['templates'].remove(park[0])
    else: park[0]['followers'] = [{}]
    with pytest.raises(units.Unsupported):
        units.attach_followers(geometry, natives, rows=rows, checkout=ROOT)


# ---- native bodies --------------------------------------------------------------------------------------------------

class Props:
    def __init__(self, **values): self.values = dict(values)
    def get_editor_property(self, key): return self.values[key]
    def set_editor_property(self, key, value): self.values[key] = value
class Asset(Props):
    def __init__(self, path, **values): super().__init__(**values); self.path = path
    def get_path_name(self): return self.path + '.' + self.path.rsplit('/', 1)[-1]
class Texture(Asset): pass
class Material(Asset): pass
class Instance(Material): pass
class Mesh(Asset):
    def get_num_triangles(self, lod): return self.triangles
    def get_bounding_box(self): return NS(min=NS(**dict(zip('xyz', self.low))), max=NS(**dict(zip('xyz', self.high))))
class Anything:
    def __getattr__(self, name): return name


def editor(tmp_path, monkeypatch, assets):
    state = NS(saves=[], scalars={}, textures={}, built=[])
    content = tmp_path / 'Content'; content.mkdir(exist_ok=True)
    def create(name, folder, cls, factory):
        asset = cls(folder + '/' + name, base_property_overrides=Props()); assets[asset.path] = asset; return asset
    def duplicate(path, target):
        source = assets[path]
        result = Mesh(target, **{k: v for k, v in source.values.items() if k != 'body_setup'}, body_setup=Props())
        result.values['static_materials'] = [Props(**s.values) for s in source.values['static_materials']]
        result.triangles, result.low, result.high = source.triangles, source.low, source.high
        assets[target] = result; return result
    def save(asset, only_if_dirty=True):
        primary = content / (asset.path.removeprefix('/Game/') + '.uasset'); primary.parent.mkdir(parents=True, exist_ok=True)
        primary.write_bytes(b'p'); state.saves.append(asset.path); return True
    graph = NS(delete_all_material_expressions=lambda m: None, create_material_expression=lambda *a: Props(),
               connect_material_expressions=lambda *a: True, connect_material_property=lambda *a: True,
               layout_material_expressions=lambda m: None, recompile_material=lambda m: None, update_material_instance=lambda m: None,
               set_material_instance_parent=lambda m, p: m.set_editor_property('parent', p),
               set_material_instance_texture_parameter_value=lambda m, k, v: state.textures.setdefault(m.path, {}).update({k: v}),
               set_material_instance_scalar_parameter_value=lambda m, k, v: state.scalars.setdefault(m.path, {}).update({k: v}))
    lod = Props(use_full_precision_u_vs=False, remove_degenerates=True, distance_field_resolution_scale=1.)
    fake = Anything()
    unreal = NS(Texture=Texture, Material=Material, MaterialInterface=Material, MaterialInstanceConstant=Instance, StaticMesh=Mesh,
        MaterialFactoryNew=lambda: None, MaterialInstanceConstantFactoryNew=lambda: None, CustomInput=Props,
        LinearColor=lambda *v: v, MaterialEditingLibrary=graph, BlendMode=NS(BLEND_OPAQUE='o', BLEND_MASKED='m', BLEND_TRANSLUCENT='t'),
        MaterialProperty=fake, CustomMaterialOutputType=fake, MaterialSamplerType=fake,
        **{name: name for name in ('MaterialExpressionScalarParameter', 'MaterialExpressionCustom', 'MaterialExpressionTextureCoordinate',
                                   'MaterialExpressionMultiply', 'MaterialExpressionTextureSampleParameter2D',
                                   'MaterialExpressionVertexNormalWS', 'MaterialExpressionWorldPosition',
                                   'MaterialExpressionConstant3Vector', 'StaticMeshEditorSubsystem')},
        CollisionTraceFlag=NS(CTF_USE_COMPLEX_AS_SIMPLE='complex_as_simple'), load_module=lambda name: None,
        get_editor_subsystem=lambda cls: NS(get_lod_build_settings=lambda m, i: lod,
                                            set_lod_build_settings=lambda m, i, s: state.built.append((m.path, dict(s.values)))),
        AssetToolsHelpers=NS(get_asset_tools=lambda: NS(create_asset=create)),
        EditorAssetLibrary=NS(load_asset=assets.get, does_asset_exist=lambda p: p in assets, duplicate_asset=duplicate,
                              save_loaded_asset=save))
    monkeypatch.setitem(sys.modules, 'unreal', unreal)
    scripts = tmp_path / body.SCRIPTS; scripts.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / body.SCRIPTS / 'import_megapark.py', scripts / 'import_megapark.py')
    return state, content


def defaults(assets):
    slots, inputs = {}, {}
    for name in ('T_DefaultWhite', 'T_DefaultLinear', 'T_DefaultBlack', 'T_DefaultNormal'):
        path = '/Game/MegaPark/Textures/' + name; assets[path] = Texture(path)
        slots[name] = 'd_' + name; inputs['d_' + name] = ('n', [path])
    return slots, inputs


def context(tmp_path, params, inputs, outputs):
    return NS(job_dir=str(tmp_path.resolve()), content_dir=str(tmp_path / 'Content'), inputs={k: v[0] for k, v in inputs.items()},
              packages={k: v[1] for k, v in inputs.items()}, outputs=outputs, params=params)


def write(tmp_path, index, name, value):
    path = tmp_path / f'item-{index}' / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(value)); return str(path)


def test_parent_is_the_original_graph(tmp_path, monkeypatch):
    assets = {}; slots, inputs = defaults(assets); editor(tmp_path, monkeypatch, assets)
    mat = body.run(context(tmp_path, {'args': {'action': 'parent', 'alpha': 1, 'defaults': slots}, 'settings': []}, inputs,
                           ['/Game/MegaPark/Materials/M_RetailMasked']))
    assert mat.values['blend_mode'] == 'm' and mat.values['two_sided'] is True and mat.values['opacity_mask_clip_value'] == .5


@pytest.mark.parametrize('seam,agree', [(False, True), (True, True), (False, False)])
def test_instance_matches_original_parameters(tmp_path, monkeypatch, seam, agree):
    assets = {}; slots, inputs = defaults(assets); state, _ = editor(tmp_path, monkeypatch, assets)
    parent = Material('/Game/MegaPark/Materials/M_RetailOpaque'); assets[parent.path] = parent
    rock = Texture('/Game/MegaPark/Textures/T_2c70170a001d0133'); light = Texture('/Game/MegaPark/Textures/T_00000000000000aa')
    assets.update({rock.path: rock, light.path: light})
    spec = {'alpha_mode': 0, 'retail_texture_ids': {'diffuse': '0x2c70170a001d0133', 'lightmap': '0x00000000000000aa'},
            'retail_parameters': {'detailNormalUVScale': ['4']}, **({'seam': True} if seam else {})}
    inputs.update(parent=('n', [parent.path]), t_d=('n', [rock.path]), t_l=('n', [light.path]),
                  build=(write(tmp_path, 0, 'build.json', {'materials': {'0xa1': spec}}), []),
                  restyle=(write(tmp_path, 1, 'textures.json', {'textures': {}, 'lightmaps': {'0x00000000000000aa': 2.5}}), []))
    args = {'action': 'instance', 'key': '0xa1', 'alpha': 0 if agree else 1, 'parent': 'parent',
            'textures': {'diffuse': 't_d', 'lightmap': 't_l'}, 'defaults': slots, 'build': 'build', 'restyle': 'restyle'}
    ctx = context(tmp_path, {'args': args, 'settings': []}, inputs, ['/Game/MegaPark/Materials/MI_a1'])
    if not agree:
        with pytest.raises(ValueError):
            body.run(ctx)
        return
    mi = body.run(ctx)
    scalars = state.scalars[mi.path]
    assert scalars['Moss'] == 1. and scalars['LightmapNorm'] == 2.5 and scalars['DetailScale'] == 4. and scalars['HasLightmap'] == 1.
    assert ('SpecularScale' in scalars) == seam and state.textures[mi.path]['Diffuse'] is rock
    assert state.textures[mi.path]['Normal'] is assets['/Game/MegaPark/Textures/T_DefaultNormal']
    assert mi.values['base_property_overrides'].values == {'override_two_sided': True, 'two_sided': True}


def piece_case(tmp_path, monkeypatch, *, parent='SM_MP_Seam', one_sided=False):
    piece = parent + '_0'
    source = tmp_path / 'source'; payload = tmp_path / 'payload'; source.mkdir(); payload.mkdir()
    mesh = dict(positions=[[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]], faces=[[0, 1, 2]], normals=[[0., 0., 1.]] * 3,
                materials=[1], smooth=[False], uvs=[('UVMap', [[0., 0.], [1., 0.], [0., 1.]])], colours=[])
    packet = mesh_ir.encode(mesh, key=piece, slots=['0xa1', '0xb2'], matrix=np.eye(4).tolist(), options={}, collisions=[])
    (payload / (piece + '.npz')).write_bytes(packet)
    (source / (piece + '.fbx')).write_bytes(b'fbx')
    publish_receipt(source, key=piece, primary=piece + '.fbx', triangles=1, bounds=[[0, 0, 0], [1, 1, 0]],
                    metadata={'geometry_sha256': hashlib.sha256(packet).hexdigest()})
    origin = [10., 20., 30.]
    metadata = write(tmp_path, 3, parent + '.json', {'schema': 1, 'entry': {'name': parent, 'native_origin': origin,
                                                                           'one_sided': one_sided}, 'materials': {}})
    raw_path = '/Game/_Raw/MegaPark/Meshes/' + piece
    raw = Mesh(raw_path, static_materials=[Props(imported_material_slot_name='0xb2')]); raw.triangles = 1
    # Blender (x, y, z) -> park frame (x, z, -y) + origin, then ue(): (x, z, y) * 100, minus the origin's ue().
    raw.low, raw.high = (0., -100., 0.), (100., 0., 0.)
    assets = {raw_path: raw, **{f'/Game/MegaPark/Materials/MI_{k}': Instance(f'/Game/MegaPark/Materials/MI_{k}') for k in ('a1', 'b2')}}
    state, content = editor(tmp_path, monkeypatch, assets)
    inputs = {'raw': ('r', [raw_path]), 'source_export': (str(source), []), 'payload': (str(payload), []), 'metadata': (metadata, []),
              'native0': ('n', ['/Game/MegaPark/Materials/MI_a1']), 'native1': ('n', ['/Game/MegaPark/Materials/MI_b2'])}
    args = {'action': 'mesh', 'parent': parent, 'collision': parent.startswith('UC_'), 'payload': 'payload',
            'source_export': 'source_export', 'metadata': 'metadata', 'materials': {'0xa1': 'native0', '0xb2': 'native1'},
            'native_inputs': {'native0': '/Game/MegaPark/Materials/MI_a1', 'native1': '/Game/MegaPark/Materials/MI_b2'}}
    dest = '/Game/MegaPark/Meshes/' + piece
    return state, assets, context(tmp_path, {'op': 'finish', 'kind': 'static_mesh', 'source': 'raw', 'destination': dest,
                                             'package_sources': {'raw': raw_path}, 'args': args, 'settings': []}, inputs, [dest])


@pytest.mark.parametrize('parent,one_sided', [('SM_MP_Seam', False), ('UC_MP_Seam', False), ('UC_MP_Seam', True)])
def test_piece_finish_keeps_original_mesh_policy(tmp_path, monkeypatch, parent, one_sided):
    state, assets, ctx = piece_case(tmp_path, monkeypatch, parent=parent, one_sided=one_sided)
    mesh = body.run(ctx)
    assert mesh.values['allow_cpu_access'] is True and state.built[0][1] == {
        'use_full_precision_u_vs': True, 'remove_degenerates': False, 'distance_field_resolution_scale': 0.}
    assert mesh.values['body_setup'].values == {'collision_trace_flag': 'complex_as_simple',
                                                'double_sided_geometry': parent.startswith('UC_') and not one_sided}
    bound = mesh.values['static_materials'][0].values.get('material_interface')
    assert bound is (None if parent.startswith('UC_') else assets['/Game/MegaPark/Materials/MI_b2'])
    assert state.saves == [mesh.path]


@pytest.mark.parametrize('damage', ['triangles', 'bounds', 'slot', 'metadata', 'payload', 'fresh'])
def test_piece_finish_refuses_changed_sources(tmp_path, monkeypatch, damage):
    state, assets, ctx = piece_case(tmp_path, monkeypatch)
    raw = assets[ctx.params['package_sources']['raw']]
    if damage == 'triangles': raw.triangles = 2
    elif damage == 'bounds': raw.high = (101., 0., 0.)
    elif damage == 'slot': raw.values['static_materials'] = [Props(imported_material_slot_name='0xa1')]
    elif damage == 'metadata': Path(ctx.inputs['metadata']).write_text(json.dumps({'schema': 1, 'entry': {'name': 'Other'}}))
    elif damage == 'payload': (Path(ctx.inputs['payload']) / 'SM_MP_Seam_0.npz').write_bytes(b'other')
    else: assets[ctx.outputs[0]] = Mesh(ctx.outputs[0])
    with pytest.raises(Exception):
        body.run(ctx)
