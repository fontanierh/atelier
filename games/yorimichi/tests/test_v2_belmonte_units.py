"""Actual Belmonte declarations and current per-package finish policy; no native jobs."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest
from atelier.build_v2.recipe_dependencies import extract

ROOT = Path(__file__).resolve().parents[3]; GAME = ROOT / 'games/yorimichi'
sys.path[:0] = [str(GAME), str(GAME / 'world'), str(GAME / 'world/regions')]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module


units = load('games/yorimichi/v2_belmonte_units.py', 'belmonte_units_test')
body = load(units.BODY, 'belmonte_body_test')


@pytest.fixture(scope='module')
def declaration():
    recipe = load('games/yorimichi/build.py', 'belmonte_recipe_test')
    rows = extract(recipe.steps(NS(out=ROOT/'build/yorimichi', game='yorimichi', uproject=GAME/'unreal/Yorimichi.uproject')),
                   checkout=ROOT, build_root=ROOT/'build')
    geometry = load('games/yorimichi/v2_geometry_templates.py', 'belmonte_templates_test').geometry_templates(rows, checkout=ROOT)
    source = json.loads((GAME/'assets/belmonte/source.json').read_bytes())
    paths = {'/Game/Belmonte/Materials/MI_BM_Ground'}
    paths.update('/Game/Belmonte/Materials/MI_BM_' + hashlib.sha256(p.encode()).hexdigest()[:12]
                 for row in source['placements'] for p in row['materials'])
    refs = {p: {'unit': 'actual.material.' + p.rsplit('/', 1)[-1], 'item': 'asset', 'package': p,
                'dependencies': ['/Game/Belmonte/Materials/M_Belmonte']} for p in paths}
    refs['/Game/Belmonte/Materials/M_Belmonte'] = {'unit': 'actual.parent', 'item': 'asset', 'package': '/Game/Belmonte/Materials/M_Belmonte'}
    return rows, geometry, refs


def test_actual_recipe_packet_ownership_and_complete_source_dependencies(declaration):
    rows, geometry, refs = declaration; before = deepcopy(geometry)
    result = units.attach_followers(geometry, rows=rows, checkout=ROOT, natives=refs)
    assert geometry == before and len(result['templates']) == 292
    assert set(result) >= {'units','staged_inputs','content_slots','packages','aliases','module_requirements','templates','groups','geometry','source_join'}
    projections = [u for u in result['units'] if u['id'].startswith('world.belmonte.render.')]
    assert len(projections) == 290
    for projection in projections:
        assert projection['op']['kind'] == 'recipe.python'
        assert projection['script'] == 'platform/studio/atelier/build_v2/recipe_job.py'
        assert projection['params']['geometry_root'] == 'output/geometry'
        assert projection['params']['recipe']['geometry']['encoding'] == 'encoded_glb'
        assert projection['outputs'][0]['class'] == 'Data'
    for template in [t for t in result['templates'] if t['unit_prefix'].startswith('world.belmonte.render_export.')]:
        raw, finish = [f['unit'] for f in template['followers']]
        assert raw['params']['destination'] == '/Game/_Raw/Belmonte/$piece'
        assert finish['outputs'][0]['logical_path'] == '/Game/Belmonte/Meshes/$piece'
        assert finish['inputs'][2]['source']['unit'] == template['producer']
        assert all((ROOT/p).is_file() for p in finish['code'])
        assert set(finish['params']['args']['bindings'].values()) <= set(finish['params']['args']['native_inputs'].values())
        assert any(p in finish['params']['args']['native_inputs'].values() for p in ('/Game/Belmonte/Materials/M_Belmonte','/Game/Belmonte/Materials/M_BelmonteJoin'))
        assert result['module_requirements'][template['unit_prefix']]
    hulls = [u for u in result['units'] if u['id'].startswith('unreal.belmonte.hull.finish.')]
    assert hulls and len(hulls) == sum('/Meshes/' in p for p in result['packages'])
    for hull in hulls:
        token = hull['params']['args']['source_export']['derived_items']['templates'][0]
        assert token['piece'].endswith('_Collision') and 'follower' not in token
        assert hull['outputs'][0]['logical_path'] in result['packages']
    raws = [u for u in result['units'] if u['id'].startswith('unreal.belmonte.hull.raw.')]
    assert len(raws) == len(hulls)
    for raw in raws:
        assert raw['script'] == units.OPS
        assert raw['params']['source'] == 'source'
        assert raw['params']['input_roots']['source']['archive_member'] == 'hull.tree.tar'
        source = next(u for u in result['units'] if u['id'] == raw['inputs'][0]['source']['unit'])
        assert source['op']['kind'] == 'recipe.python'
        assert source['params']['recipe']['commands'][0]['call']['defaults'][0]['derived_items']['templates'][0]['piece'].endswith('_Collision')
    assert {t['unit_prefix'] for t in result['templates']} <= {t['unit_prefix'] for t in result['geometry']['templates']}
    assert set(result['groups']) <= set(result['geometry']['groups'])
    authors = [u for u in result['units'] if u['op']['kind']=='unreal.author']
    assert any(u['outputs'][0]['logical_path']=='/Game/Racing/M_RacingTv' for u in authors)
    assert all(len(u['outputs'])==1 for u in authors)
    ground = next(u for u in authors if u['outputs'][0]['logical_path'].endswith('/MI_BM_Ground'))
    assert ground['params']['args']['parent_dependencies']
    assert result['source_join']['required'] and result['aliases']['unreal.belmonte'] == ['unreal.belmonte.complete']


@pytest.mark.parametrize('damage', ['missing_parent','changed_product','attached','wrong_format','material_product','texture_product'])
def test_changed_or_missing_declarations_refuse(declaration, damage):
    rows, geometry, refs = deepcopy(declaration)
    selected = next(t for t in geometry['templates'] if t['unit_prefix'].startswith('world.belmonte_models.export.'))
    if damage == 'missing_parent': geometry['templates'].remove(selected)
    elif damage == 'changed_product': next(r for r in rows if r['id'] == selected['producer'])['products'][0]['paths'] = ['foreign']
    elif damage == 'attached': selected['followers'] = [{}]
    elif damage == 'wrong_format': selected['op']['kind'] = 'blender_export_piece'
    elif damage == 'material_product': next(r for r in rows if r['id']=='world.belmonte.meshes')['products'][1]['paths']=['foreign']
    else: next(r for r in rows if r['id']=='world.belmonte')['products'][1]['paths']=['foreign']
    with pytest.raises(ValueError): units.attach_followers(geometry, rows=rows, checkout=ROOT, natives=refs)


class Props:
    def __init__(self, **values): self.values = values
    def get_editor_property(self, key): return self.values.get(key)
    def set_editor_property(self, key, value): self.values[key] = value
class Asset(Props):
    def __init__(self, path, **values): super().__init__(**values); self.path = path
    def get_path_name(self): return self.path + '.' + self.path.rsplit('/',1)[-1]
class Material(Asset): pass
class Mesh(Asset):
    def get_num_triangles(self, lod): return self.triangles
    def get_material(self, slot): return self.materials[slot]
    def set_material(self, slot, value): self.materials[slot] = value
    def get_bounding_box(self): return NS(min=NS(x=0., y=-100., z=0.), max=NS(x=100., y=0., z=100.))


def native_case(tmp_path, monkeypatch, *, piece='SM_BM_Test', hull=False, triangles=10, separate=False):
    package = '/Game/Belmonte/Meshes/'+piece; source = '/Game/_Raw/Belmonte/'+piece
    material = '/Game/Belmonte/Materials/'+('MI_BM_Ground' if hull else 'MI_Test')
    raw = Mesh(source, static_materials=[Props(imported_material_slot_name='BM_0_test')], body_setup=Props())
    raw.triangles = triangles; raw.materials = [None]
    assets = {source:raw, material:Material(material)}; state = NS(saves=[], lods=[], fail_save=False, bad_bounds=False)
    content = tmp_path/'Content'; content.mkdir()
    def duplicate(source, dest):
        mesh = deepcopy(assets[source]); mesh.path = dest; assets[dest] = mesh; return mesh
    def save(mesh, only_if_is_dirty):
        state.saves.append(mesh.path)
        path = content/(mesh.path.removeprefix('/Game/')+'.uasset'); path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(b'primary')
        return not state.fail_save
    settings = Props(distance_field_resolution_scale=1.)
    editor = NS(get_lod_build_settings=lambda m,i: settings, set_lod_build_settings=lambda m,i,s: None)
    unreal = NS(StaticMesh=Mesh, MaterialInterface=Material, StaticMeshEditorSubsystem=object(),
        load_module=lambda _: None, get_editor_subsystem=lambda _: editor,
        CollisionTraceFlag=NS(CTF_USE_COMPLEX_AS_SIMPLE='complex'),
        EditorAssetLibrary=NS(load_asset=assets.get, does_asset_exist=lambda p:p in assets, duplicate_asset=duplicate, save_loaded_asset=save))
    monkeypatch.setitem(sys.modules,'unreal',unreal)
    monkeypatch.setitem(sys.modules,'glb_mesh_validation',NS(options_match=lambda raw:True))
    collision = '/Game/Belmonte/Meshes/SM_BM_Parent_Collision' if separate else None
    inputs={'raw':'native','source_export':'source','native0':'native'}
    packages={'raw':[source],'source_export':[],'native0':[material]}
    if not hull: inputs['payload']='data'; packages['payload']=[]
    if separate:
        inputs['collision']='native'; packages['collision']=[collision]; assets[collision]=Mesh(collision)
    args={'piece':piece,'parent':'SM_BM_Parent','source_export':'source_export','hull':hull,
          'native_inputs':{'native0':material},'native_extra':[],'bindings':{'0':material},'collision':collision}
    if not hull: args['payload']='payload'
    context=NS(job_dir=str(tmp_path),content_dir=str(content),inputs=inputs,packages=packages,outputs=[package],
        data_outputs=['data/reports/'+piece+'.json'], params={'op':'finish','kind':'static_mesh','source':'raw','destination':package,'package_sources':{'raw':source},'args':args})
    facts={'triangles':triangles,'bounds':[[0.,0.,0.],[1.,1.,1.]],'slots':['BM_0_test']}
    meta={'entry':{'collision':{} } if separate else {},'slots':['BM_0_test']}
    if separate: meta['entry']['collision']={'path':'glb/SM_BM_Parent_Collision.glb'}
    monkeypatch.setattr(body,'source_facts',lambda c,a:(facts,meta,b''))
    monkeypatch.setattr(body,'generate_terrain_lods',lambda c,m,u:state.lods.append(m.path))
    monkeypatch.setattr(body,'lods_match',lambda m,p:bool(state.lods))
    return context,state,assets,settings


@pytest.mark.parametrize('piece,hull,triangles,separate',[
    ('SM_BM_Test',False,10,False),('SM_BM_Test',False,10,True),('SM_BM_Test_Collision',True,10,False),
    ('SM_BM_BT_Terrain_0_0',False,12001,False),('SM_BM_BT_Terrain_4_4',False,12000,False),
    ('SM_BM_BT_Terrain_1_1_Piece1',False,12001,False)])
def test_original_behavior_body(tmp_path,monkeypatch,piece,hull,triangles,separate):
    context,state,assets,settings=native_case(tmp_path,monkeypatch,piece=piece,hull=hull,triangles=triangles,separate=separate)
    mesh=body.run(context)
    assert state.saves==[context.outputs[0]] and assets[context.packages['raw'][0]].materials == [None]
    assert mesh.materials[0] is assets[context.packages['native0'][0]]
    if hull: assert settings.values['distance_field_resolution_scale']==0.
    else:
        assert mesh.values['body_setup'].values=={'collision_trace_flag':'complex','double_sided_geometry':True}
        if piece.startswith('SM_BM_BT_Terrain_'): assert mesh.values['allow_cpu_access']==(piece in body.CPU)
        assert bool(state.lods)==(piece.startswith('SM_BM_BT_Terrain_') and triangles>12000)
        assert mesh.values['complex_collision_mesh'] is (assets[context.params['args']['collision']] if separate else None)


@pytest.mark.parametrize('damage',['material','slot','triangles','save','membership','fresh'])
def test_invalid_native_finish_refuses(tmp_path,monkeypatch,damage):
    context,state,assets,settings=native_case(tmp_path,monkeypatch)
    raw=assets[context.packages['raw'][0]]
    if damage=='material': assets[context.packages['native0'][0]]=Mesh(context.packages['native0'][0])
    elif damage=='slot': raw.values['static_materials']=[Props(imported_material_slot_name='wrong')]
    elif damage=='triangles': raw.triangles-=1
    elif damage=='save': state.fail_save=True
    elif damage=='membership': context.inputs['foreign']='x'; context.packages['foreign']=[]
    else: assets[context.outputs[0]]=Mesh(context.outputs[0])
    with pytest.raises(ValueError): body.run(context)


class DataContext:
    def __init__(self, inputs, output, params, outputs=()):
        self.inputs = inputs; self.output_dir = output; self.params = params; self.outputs = outputs
        output.mkdir(parents=True)
    def input(self, name): return Path(self.inputs[name])
    def output(self, name):
        assert name in self.outputs
        return self.output_dir / name


def actual_plan(tmp_path):
    from belmonte import model_sources, plan_model
    source = json.loads((GAME/'assets/belmonte/source.json').read_bytes())
    entry = next(r for r in source['meshes'] if r['triangles'] < 1000 and r.get('collision') and not r['name'].startswith('SM_BM_BT_Terrain_'))
    definition = tmp_path/(entry['name']+'.json')
    definition.write_text(json.dumps(model_sources.project({'meshes':[entry]})[entry['name']]))
    plan = tmp_path/'plan'
    plan_model.main(['--asset',entry['name'],'--definition',str(definition),'--library',str(GAME/'assets/belmonte'),'--output',str(plan)])
    return entry, plan


@pytest.mark.parametrize('damage',[None,'packet','receipt','foreign'])
def test_actual_encoded_export_current_source_validation(tmp_path, damage):
    import shutil
    entry, plan = actual_plan(tmp_path)
    parent=entry['name']; payload=tmp_path/'payload'; payload.mkdir()
    shutil.copyfile(plan/(parent+'.mesh'),payload/(parent+'.mesh'))
    stage=load('games/yorimichi/world/stage_encoded_export_v2.py','belmonte_export_test')
    export=DataContext({'payload':payload},tmp_path/'export',
        {'payload_member':parent+'.mesh','payload_encoding':'encoded_glb','payload_role':'render'},[parent+'.glb','export.json'])
    stage.run(export)
    context=NS(job_dir=str(tmp_path), inputs={'source_export':str(export.output_dir),'payload':str(payload)}, packages={'source_export':[],'payload':[]})
    args={'piece':parent,'parent':parent,'hull':False,'source_export':'source_export','payload':'payload'}
    if damage=='packet': (payload/(parent+'.mesh')).write_bytes(b'changed')
    if damage=='receipt': (export.output_dir/'export.json').write_text('{}')
    if damage=='foreign': (payload/'Foreign.mesh').write_bytes(b'foreign')
    if damage:
        with pytest.raises((ValueError,KeyError)): body.source_facts(context,args)
    else:
        facts,meta,data=body.source_facts(context,args)
        assert facts['triangles']==entry['triangles'] and data==(GAME/'assets/belmonte'/entry['path']).read_bytes()


@pytest.mark.parametrize('damage',[False,True])
def test_render_projection_validates_complete_plan_before_role_selection(tmp_path,damage):
    from atelier.build_v2.recipe_job import pack_root
    import encoded_region_plan
    entry,plan=actual_plan(tmp_path); source=tmp_path/'source/products';source.mkdir(parents=True)
    if damage: (plan/(entry['name']+'_Collision.mesh')).write_bytes(b'changed')
    pack_root(plan,source/'0-0.tree.tar')
    context=DataContext({'source':source.parent},tmp_path/'output',{'parent':entry['name'],'geometry_root':'geometry'})
    members=load(units.MEMBERS,'belmonte_members_test')
    if damage:
        with pytest.raises(ValueError): members.run(context)
        assert not (context.output_dir/'geometry').exists()
    else:
        members.run(context)
        result=encoded_region_plan.validate(context.output_dir/'geometry')
        assert result['source_collision_triangles']==0 and all(p['role']=='render' for p in result['pieces'])


@pytest.mark.parametrize('damage', [False, True])
def test_render_projection_runs_authored_recipe_and_geometry_validation(tmp_path, monkeypatch, declaration, damage):
    import shutil
    import encoded_region_plan
    from atelier.build_v2 import recipe_job
    entry, plan = actual_plan(tmp_path)
    rows, geometry, refs = declaration
    result = units.attach_followers(geometry, rows=rows, checkout=ROOT, natives=refs)
    unit = next(u for u in result['units'] if u['id'] == 'world.belmonte.render.' + entry['name'])
    view = tmp_path / 'view'
    view.mkdir()
    for relative in unit['code']:
        destination = view / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    shutil.copytree(plan, view / 'source-plan')
    if damage:
        (view / 'source-plan' / (entry['name'] + '_Collision.mesh')).write_bytes(b'changed')
    output = tmp_path / 'recipe-output'
    output.mkdir()
    monkeypatch.chdir(view)
    monkeypatch.syspath_prepend(str(view))
    # recipe_job restores argv/env itself; keep its import-path additions local to this test.
    monkeypatch.setattr(sys, 'path', list(sys.path))
    context = NS(params=unit['params'], output_dir=output)
    if damage:
        with pytest.raises(ValueError):
            recipe_job.run(context)
        assert not (output / 'geometry').exists()
        assert not (output / 'render.tree.tar').exists()
    else:
        recipe_job.run(context)
        projected = encoded_region_plan.validate(output / 'geometry')
        assert projected['parent'] == entry['name']
        assert projected['source_collision_triangles'] == 0
        assert all(piece['role'] == 'render' for piece in projected['pieces'])
        restored = tmp_path / 'restored'
        recipe_job.unpack_root(output / 'render.tree.tar', restored)
        assert recipe_job.inventory(restored) == recipe_job.inventory(output / 'geometry')


@pytest.mark.parametrize('damage',[False,True])
def test_material_members_validate_every_pixel_and_descriptor_before_publication(tmp_path,damage):
    members=load(units.MEMBERS,'belmonte_material_members_test')
    pixels=tmp_path/'pixels';pixels.mkdir();raw=b'actual-produced-pixels';filename='T_BM_0123456789ab.png';(pixels/filename).write_bytes(raw)
    spec={'name':'MI_BM_Ground','texture':filename}
    value={'schema':1,'materials':{'Ground':spec},'bindings':{'SM_BM_Test':['material']},
           'files':{'textures/'+filename:{'sha256':hashlib.sha256(raw).hexdigest(),'size':len(raw)}}}
    source=tmp_path/'materials.json';source.write_text(json.dumps(value))
    if damage: (pixels/filename).write_bytes(b'changed')
    for kind in ('materials','textures'):
        output=tmp_path/kind
        if damage:
            with pytest.raises(ValueError): members.project_materials(source,pixels,output,kind)
            assert not output.exists()
        else:
            members.project_materials(source,pixels,output,kind)
            assert {p.name for p in output.iterdir()}==({'MI_BM_Ground.json'} if kind=='materials' else {filename})


@pytest.mark.parametrize('damage', [None, 'selection', 'bytes', 'role', 'foreign'])
def test_selected_hull_recipe_source_reaches_fixed_raw_input(tmp_path, damage):
    import shutil
    from atelier.build_v2 import recipe_job, unreal_inputs, unreal_ops
    entry, plan = actual_plan(tmp_path)
    piece = entry['name'] + '_Collision'
    payload = tmp_path / 'payload'
    payload.mkdir()
    shutil.copyfile(plan / (piece + '.mesh'), payload / (piece + '.mesh'))
    stage = load('games/yorimichi/world/stage_encoded_export_v2.py', 'belmonte_hull_export_test')
    export = DataContext({'payload': payload}, tmp_path / 'export',
        {'payload_member': piece + '.mesh', 'payload_encoding': 'encoded_glb', 'payload_role': 'collision'},
        [piece + '.glb', 'export.json'])
    stage.run(export)
    members = load(units.MEMBERS, 'belmonte_hull_members_test')
    children = [(NS(products=[NS(paths=(export.output_dir,))]), piece)]
    if damage == 'selection': children[0] = (children[0][0], entry['name'])
    elif damage == 'bytes': (export.output_dir / (piece + '.glb')).write_bytes(b'changed')
    elif damage == 'foreign': (export.output_dir / 'Foreign.glb').write_bytes(b'foreign')
    elif damage == 'role':
        path = export.output_dir / 'export.json'
        receipt = json.loads(path.read_bytes()); receipt['metadata']['role'] = 'render'
        path.write_text(json.dumps(receipt))
    projected = tmp_path / 'projected'
    if damage:
        with pytest.raises(ValueError): members.project_hull(children, projected, entry['name'])
        assert not projected.exists()
        return
    members.project_hull(children, projected, entry['name'])
    job = tmp_path / 'job'; source = job / 'inputs/source'; source.mkdir(parents=True)
    recipe_job.pack_root(projected, source / 'hull.tree.tar')
    content = job / 'Content'; content.mkdir()
    runtime = job / 'runtime'; runtime.mkdir()
    staged = unreal_inputs.stage_inputs(job, [{'name': 'source', 'path': 'inputs/source', 'identity': {'state': 'digest'}}],
        content, runtime_dir=runtime, root_bindings={'source': {'archive_member': 'hull.tree.tar', 'name': piece}})
    context = NS(inputs=staged['inputs'], packages=staged['packages'], job_dir=str(job), params={'source': 'source'})
    selected = Path(unreal_ops._input(context, 'source'))
    assert selected.name == piece + '.glb'
    assert selected.read_bytes() == (export.output_dir / selected.name).read_bytes()


@pytest.mark.parametrize('action',['parent','join_parent','instance','ground_instance','tv'])
def test_original_material_and_tv_bodies_own_one_package(tmp_path,monkeypatch,action):
    import shutil
    import types
    scripts=tmp_path/'games/yorimichi/unreal/Scripts';scripts.mkdir(parents=True)
    for name in ('import_belmonte','atmosphere','sea_look','ground_grain','racing_tv_material'):
        shutil.copyfile(GAME/'unreal/Scripts'/(name+'.py'),scripts/(name+'.py'))
    class Texture(Asset): pass
    class Instance(Material): pass
    class Enum:
        def __getattr__(self,name): return name
    class FakeUE(types.ModuleType):
        def __getattr__(self,name):
            if name.startswith('MaterialExpression') or name=='CustomInput': return Props
            value=Enum();setattr(self,name,value);return value
    ue=FakeUE('unreal');assets={};state=NS(nodes=[],scalars={},vectors={},textures={},saves=[])
    content=tmp_path/'Content';content.mkdir()
    def loaded(path):
        if path.startswith('/Engine/'): assets.setdefault(path,Texture(path))
        return assets.get(path)
    def create(name,folder,cls,factory):
        asset=cls(folder+'/'+name);assets[asset.path]=asset;return asset
    def save(asset,*a,**kw):
        path=content/(asset.path.removeprefix('/Game/')+'.uasset');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'primary')
        state.saves.append(asset.path);return True
    def expression(material,cls,*args):
        node=Props();state.nodes.append(node);return node
    mel=NS(delete_all_material_expressions=lambda m:None,create_material_expression=expression,
        connect_material_expressions=lambda *a:True,connect_material_property=lambda *a:True,recompile_material=lambda m:None,
        clear_all_material_instance_parameters=lambda m:None,set_material_instance_parent=lambda m,p:m.values.update(parent=p),
        set_material_instance_scalar_parameter_value=lambda m,k,v:state.scalars.update({k:v}),
        set_material_instance_vector_parameter_value=lambda m,k,v:state.vectors.update({k:v}),
        set_material_instance_texture_parameter_value=lambda m,k,v:state.textures.update({k:v}),update_material_instance=lambda m:None)
    ue.Material=Material;ue.MaterialInterface=Material;ue.MaterialInstanceConstant=Instance;ue.Texture=Texture
    ue.MaterialFactoryNew=lambda:None;ue.MaterialInstanceConstantFactoryNew=lambda:None
    ue.LinearColor=lambda *a:tuple(a);ue.MaterialEditingLibrary=mel;ue.AssetToolsHelpers=NS(get_asset_tools=lambda:NS(create_asset=create))
    ue.EditorAssetLibrary=NS(load_asset=loaded,does_asset_exist=lambda p:p in assets,save_loaded_asset=save,make_directory=lambda p:True)
    ue.load_asset=loaded;ue.log=lambda s:None
    monkeypatch.setitem(sys.modules,'unreal',ue)
    # Each staged support module is loaded against this current mock, independently.
    monkeypatch.delitem(sys.modules,'sea_look',raising=False)
    package='/Game/Belmonte/Materials/'+{'parent':'M_Belmonte','join_parent':'M_BelmonteJoin','instance':'MI_BM_0123456789ab','ground_instance':'MI_BM_Ground','tv':'unused'}[action]
    if action=='tv': package='/Game/Racing/M_RacingTv'
    args={'action':'instance' if action=='ground_instance' else action};inputs={};packages={}
    def token(slot,piece): return {'derived_items':{'root':'derived','members':[{'slot':slot,'piece':piece,'root':'derived/'+piece}]}}
    if action=='join_parent':
        texture='/Game/Belmonte/Textures/T_BM_0123456789ab';assets[texture]=Texture(texture)
        args['texture']=token('texture','T_BM_0123456789ab');inputs['texture']='native';packages['texture']=[texture]
    if action in ('instance','ground_instance'):
        ground=action=='ground_instance';name=package.rsplit('/',1)[-1]
        base='/Game/Belmonte/Materials/'+('M_BelmonteJoin' if ground else 'M_Belmonte');assets[base]=Material(base)
        spec={'name':name,'texture':None,'colour':[.2,.3,.4],'tint':[1.,1.,1.],'layers':{},'tile_m':4.,'white_vertex':True,
              'terrain':False,'brightness':.9,'atlas':False,'water':True,'join':ground}
        folder=tmp_path/'spec';folder.mkdir();(folder/(name+'.json')).write_text(json.dumps({'source':'Ground' if ground else 'source','spec':spec}))
        args.update(name=name,source_name='Ground' if ground else 'source',spec=token('spec',name),texture=None,parent_package=base)
        inputs={'parent':'native','spec':str(folder)};packages={'parent':[base],'spec':[]}
        if ground:
            texture='/Game/Belmonte/Textures/T_BM_0123456789ab';assets[texture]=Texture(texture)
            args['parent_dependencies']=[token('parent_texture','T_BM_0123456789ab')]
            inputs['parent_texture']='native';packages['parent_texture']=[texture]
    context=NS(job_dir=str(tmp_path),content_dir=str(content),params={'args':args},inputs=inputs,packages=packages,outputs=[package])
    asset=body.run(context)
    assert asset.path==package and set(state.saves)=={package}
    if action=='instance':
        assert state.scalars['Roughness']==.25 and state.scalars['Tile']==4. and state.scalars['WhiteVertex']==1.
        assert state.vectors['Colour']==(.2,.3,.4,1.)
    if action=='ground_instance': assert not state.scalars and asset.values['parent'].path.endswith('M_BelmonteJoin')
    if action=='tv':
        assert asset.values['shading_model']=='MSM_UNLIT' and asset.values['blend_mode']=='BLEND_OPAQUE'
        assert any('2.2' in n.values.get('code','') for n in state.nodes)
    if action=='parent': assert any('weights /=' in n.values.get('code','') for n in state.nodes)
    if action=='join_parent': assert any('groundDetail' in n.values.get('code','') for n in state.nodes)


@pytest.mark.parametrize('damage',[None,'render','hull','material','texture','tv','report','runtime'])
def test_complete_gate_requires_all_actual_finished_items(tmp_path,damage):
    members=load(units.MEMBERS,'belmonte_complete_test')
    name='SM_BM_Test';hull=name+'_Collision'
    geometry=tmp_path/'geometry.json';geometry.write_text(json.dumps({'meshes':[{'name':name,'triangles':10,'collision':{'path':'glb/'+hull+'.glb'}}]}))
    runtime=tmp_path/'runtime.json';runtime.write_text(json.dumps({'groups':[{'asset':'/Game/Belmonte/Meshes/'+name+'.'+name,'plant':False}]}))
    palette=tmp_path/'materials.json';palette.write_text(json.dumps({'materials':{'Ground':{'name':'MI_BM_Ground','texture':'T_BM_0123456789ab.png'}}}))
    def native(root,relative):
        path=root/('content/Game/'+relative+'.uasset');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'fixture-native-item');return path
    def child(root): return NS(products=[NS(paths=[root])])
    asset=tmp_path/'asset';asset_file=native(asset,'Belmonte/Meshes/'+name)
    hull_asset=tmp_path/'hull';hull_file=native(hull_asset,'Belmonte/Meshes/'+hull)
    report_root=tmp_path/'report';hull_report_root=tmp_path/'hullreport'
    for root,piece,is_hull in ((report_root,name,False),(hull_report_root,hull,True)):
        path=root/('data/reports/'+piece+'.json');path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'name':piece,'hull':is_hull,'triangles':10,'bounds_cm':[0.]*6,'bounds_error_cm':0.}))
    mats={}
    for key in ('MI_BM_Ground','M_Belmonte','M_BelmonteJoin'):
        root=tmp_path/key;native(root,'Belmonte/Materials/'+key);mats[key]=root
    texture=tmp_path/'texture';texture_file=native(texture,'Belmonte/Textures/T_BM_0123456789ab')
    tv=tmp_path/'tv';tv_file=native(tv,'Racing/M_RacingTv')
    render=[(child(report_root),name)];hulls={hull:(hull_asset,hull_report_root)}
    if damage=='render': asset_file.unlink()
    if damage=='hull': hull_file.unlink()
    if damage=='material': mats.pop('MI_BM_Ground')
    if damage=='texture': texture_file.unlink()
    if damage=='tv': tv_file.unlink()
    if damage=='report': (report_root/('data/reports/'+name+'.json')).write_text('{}')
    if damage=='runtime': runtime.write_text(json.dumps({'groups':[{'asset':'/Game/Other.Other','plant':False}]}))
    output=tmp_path/'complete'
    args=(geometry,runtime,render,hulls,mats,[(child(texture),'T_BM_0123456789ab')],tv,output,[(child(asset),name)],palette)
    if damage:
        with pytest.raises(ValueError): members.complete(*args)
        assert not output.exists()
    else:
        members.complete(*args)
        assert json.loads((output/'import-report.json').read_bytes())=={name:{'triangles':10,'bounds_cm':[0.]*6,'collision_hulls':True}}
