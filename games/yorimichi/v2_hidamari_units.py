"""Remaining non-North Hidamari material and fitted-prop owners; city tiles are independent."""
import ast
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

SCRIPT='games/yorimichi/world/hidamari_finish_v2.py'
SCRIPTS='games/yorimichi/unreal/Scripts/'
MAT='/Game/Japan/Hidamari/Materials/'
TEX='/Game/Japan/Hidamari/Textures/'


def _load(root,path,name):
    spec=importlib.util.spec_from_file_location(name,root/path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def attach_followers(geometry,natives,*,checkout):
    """@cc [owner:fontanierh,label:correctness] remaining-hidamari-world-ownership
    This family MUST cover the actual 48 independently declared prop/conifer source
    parents and original remaining material factories. City surface geometry and
    North MUST stay with their independent owners. Conifer base finishes MUST
    capture all three actual native LOD Items; no future IDs, generated discovery,
    old main, cache, namespace scan or partial whole-World alias MAY be invented.
    """
    from atelier.source_imports import ImportScanner
    root=Path(checkout).resolve();factory=_load(root,'games/yorimichi/hidamari_prop_build.py','hd_prop_factory')
    texture=_load(root,'games/yorimichi/v2_texture_units.py','hd_texture_policy')
    island=_load(root,'games/yorimichi/v2_island_units.py','hd_item_policy')
    rows=factory.steps(SimpleNamespace(out=root/'build/yorimichi'))
    sources={}
    for name in factory.members():
        selected=[s for s in rows if s.name=='world.hidamari_props.geometry.'+name]
        if len(selected)!=1:raise ValueError('Missing original Hidamari prop producer')
        found=[(i,p) for i,p in enumerate(selected[0].products) if p.name=='hidamari.prop_data.'+name]
        if len(found)!=1 or len(found[0][1].paths)!=1 or found[0][1].optional_paths:raise ValueError('Hidamari selected prop data Product differs')
        sources[name]={'unit':selected[0].name,'item':'product'+str(found[0][0]),'file':'products/'+str(found[0][0])+'-0.tree.tar','member':'record.json'}
    tree=ast.parse((root/'games/yorimichi/tools/hidamari_textures.py').read_text())
    surfaces=ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SURFACES' for t in n.targets)))
    scanner=ImportScanner();code=set(texture._code(root))
    for source in (SCRIPT,):
        code.update(p.relative_to(root).as_posix() for p in scanner.local_imports(root/source,
            (root/'platform/studio',root/'games/yorimichi',root/'games/yorimichi/world',root/'games/yorimichi/unreal/Scripts')))
    result=deepcopy(geometry);result.setdefault('units',[]);result.setdefault('staged_inputs',{});result.setdefault('content_slots',{})
    refs=dict(natives)
    def append(unit):
        result['units'].append(unit);result['staged_inputs'][unit['id']]={i['name']:'inputs/'+i['name'] for i in unit['inputs']}
        result['content_slots'].update({i['name']:False for i in unit['inputs']})
    def image(package,source,*,member=None,archive=None,mirror=False):
        name=package.rsplit('/',1)[-1];raw_id='unreal.hidamari.texture.raw.'+name;unit_id='unreal.hidamari.texture.'+name
        raw_package='/Game/_Raw/HidamariTextures/'+name
        params={'op':'raw_import','kind':'texture','source':'source','destination':raw_package}
        if archive:params.update(source_member=member,input_roots={'source':{'archive_member':archive,'name':'source'}})
        append({'id':raw_id,'op':{'kind':'unreal.raw_import','version':'1'},'script':texture.OPS,'code':texture._code(root),
            'inputs':[{'role':'content','name':'source','source':source}],'params':params,'outputs':[texture._output(raw_package,raw=True)]})
        props={'srgb':True,'max_texture_size':1024,'lod_group':{'unreal_enum':'TextureGroup.TEXTUREGROUP_WORLD'}}
        if mirror:
            props.pop('lod_group');props.update(power_of_two_mode={'unreal_enum':'TexturePowerOfTwoSetting.STRETCH_TO_POWER_OF_TWO'},
                mip_gen_settings={'unreal_enum':'TextureMipGenSettings.TMGS_SIMPLE_AVERAGE'},address_x={'unreal_enum':'TextureAddress.TA_MIRROR'},address_y={'unreal_enum':'TextureAddress.TA_MIRROR'})
        append({'id':unit_id,'op':{'kind':'unreal.finish','version':'1'},'script':texture.OPS,'code':texture._code(root),
            'inputs':[{'role':'content','name':'raw','source':{'kind':'item','unit':raw_id,'item':'raw_texture'}}],
            'params':{'op':'finish','kind':'texture','source':'raw','destination':package,'package_sources':{'raw':raw_package},'properties':props},'outputs':[texture._output(package,raw=False)]})
        refs[package]={'unit':unit_id,'item':'texture','package':package}
    for prefix in ('Arcade','Harbor'):
        for key in ('timber','paving'):
            image('/Game/Japan/Textures/T_'+prefix+'_'+key,{'kind':'file','path':'games/yorimichi/world/regions/hidamari/textures/'+key+'.png'},mirror=True)
    for key in surfaces:
        image(TEX+'T_HD_'+key,{'kind':'item','unit':'world.hidamari_textures','item':'output0'},member=key+'.png',archive='outputs/0.tree.tar')
    for name in (*factory.PROPS,*factory.TREES):
        ref=sources[name];image(TEX+'T_'+name,{'kind':'item','unit':ref['unit'],'item':ref['item']},member=name+'.png',archive=ref['file'])
    def material(package,family,function,arguments=(),keywords=None,dependencies=(),data=None,extra=None):
        complete={}
        def add(path):
            if path in complete:return
            ref=refs.get(path)
            if not isinstance(ref,dict) or ref.get('package')!=path:raise ValueError('Missing exact supplied Hidamari native dependency: '+path)
            complete[path]=ref
            for child in ref.get('dependencies',()):add(child if isinstance(child,str) else child['package'])
        for path in dependencies:add(path)
        native={};inputs=[]
        for i,(path,ref) in enumerate(complete.items()):
            slot='native'+str(i);native[slot]=path;inputs.append({'role':'content','name':slot,'source':{'kind':'item','unit':ref['unit'],'item':ref['item']}})
        if data:inputs.append({'role':'content','name':'data','source':{'kind':'item','unit':data['unit'],'item':data['item']}})
        output=island._item(package,raw=False);output['class']='MaterialInstance' if function=='instance' else 'Material'
        unit_id='unreal.hidamari.material.'+package.rsplit('/',1)[-1]
        append({'id':unit_id,'op':{'kind':'unreal.author','version':'1'},'script':SCRIPT,'code':sorted(code|{SCRIPTS+family+'.py'}),'inputs':inputs,
            'params':{'args':{'op':'material','package':package,'family':family,'function':function,'arguments':list(arguments),'keywords':keywords or {},
                'native_inputs':native,'data':({'slot':'data','file':data['file'],'member':data['member']} if data else None),**(extra or {})},'settings':[]},'outputs':[output]})
        refs[package]={'unit':unit_id,'item':'asset','package':package,'dependencies':list(complete)}
    for name,function,args in (('M_PlazaWater','water_material',()),('M_PondWater','water_material',('M_PondWater',)),('M_PlazaPaving','paving_material',())):
        deps=('/Game/Japan/Textures/T_Arcade_paving',) if name=='M_PlazaPaving' else ()
        material('/Game/Japan/Materials/'+name,'plaza_material',function,args,dependencies=deps)
    for paving in (False,True):
        material('/Game/Japan/Materials/'+('M_ArcadePaving' if paving else 'M_Arcade'),'arcade_material','material',keywords={'paving':paving},
            dependencies=('/Game/Japan/Textures/T_Arcade_'+('paving' if paving else 'timber'),))
    for water in (False,True):
        material('/Game/Japan/Materials/'+('M_HarborWater' if water else 'M_Harbor'),'harbor_material','material',keywords={'water':water},
            dependencies=() if water else tuple('/Game/Japan/Textures/T_Harbor_'+k for k in ('paving','timber')))
    parent=MAT+'M_HDCity';default=TEX+'T_HD_plaster'
    material(parent,'city_material','parent',dependencies=(default,))
    palette_data={'unit':'world.hidamari_textures','item':'output0','file':'outputs/0.tree.tar','member':'textures.json'}
    for key in (*surfaces,'flat'):
        material(MAT+'MI_HD_'+key,'city_material','instance',dependencies=(parent,TEX+'T_HD_'+(key if key!='flat' else 'plaster')),data=palette_data,extra={'key':key})
    for name in (*factory.PROPS,*factory.TREES):
        material(MAT+'MI_'+name,'city_material','instance',dependencies=(parent,TEX+'T_'+name),data=sources[name],extra={'key':name,'prop':True})
    requirements=dict(result.get('module_requirements',{}));descriptor=json.loads((root/'games/yorimichi/unreal/Yorimichi.uproject').read_text())
    modules=[{'name':m['Name'],'kind':m['Type'],'loading_phase':m.get('LoadingPhase','Default')} for m in descriptor['Modules']]
    candidates=[t for t in result['templates'] if t['unit_prefix'].startswith('world.hidamari_props.export.')]
    if len(candidates)!=len(factory.members()):raise ValueError('Hidamari requires exactly 48 unique source templates')
    selected={t['unit_prefix'].removeprefix('world.hidamari_props.export.'):t for t in result['templates'] if t['unit_prefix'].startswith('world.hidamari_props.export.')}
    if set(selected)!=set(factory.members()):raise ValueError('Hidamari requires all 48 declared fitted source parents')
    for name,template in selected.items():
        if template.get('followers') or template['group']!='geometry' or template['op']!={'kind':'blender_export_piece','version':'1'} or template['producer']!='world.hidamari_props.geometry.'+name or template['params'].get('format')!='fbx':raise ValueError('Hidamari requires unmodified original whole FBX templates')
        parameter='games/yorimichi/assets/hidamari/prop-export-parameters/'+name+'.json';definition=json.loads((root/parameter).read_text());base=definition['parent'];level=definition['lod']
        package=('/Game/Japan/Hidamari/PropLODs/'+base+'/' if level else '/Game/Japan/Assets/')+'$piece';raw_package='/Game/_Raw/Hidamari/$piece'
        mi=MAT+'MI_'+base;needed={}
        def add_native(path):
            if path in needed:return
            ref=refs[path];needed[path]=ref
            for child in ref.get('dependencies',()):add_native(child)
        add_native(mi);native={};incoming=[]
        for index,(path,ref) in enumerate(needed.items()):
            slot='native'+str(index);native[slot]=path;incoming.append({'role':'content','name':slot,'source':{'kind':'item','unit':ref['unit'],'item':ref['item']}})
        lods=[]
        if name in factory.TREES:
            lods={'derived_items':{'root':'hidamari-lods/'+name,'templates':[{'producer':selected[name+'_LOD'+str(i)]['producer'],'group':'geometry',
                'unit_prefix':selected[name+'_LOD'+str(i)]['unit_prefix'],'follower':1,'item':'asset'} for i in range(1,4)]}}
        raw={'id':'$export.raw','op':{'kind':'unreal.raw_import','version':'1'},'script':texture.OPS,'code':texture._code(root),
            'inputs':[{'role':'content','name':'source','source':{'kind':'item','unit':'$export','item':'asset'}}],
            'params':{'op':'raw_import','kind':'static_mesh','source':'source','destination':raw_package,
                'settings':['-ForceDPCVars=Interchange.FeatureFlags.Import.FBX=false,Editor.AsyncStaticMeshCompilation=0']},'outputs':[island._item(raw_package,raw=True)]}
        inputs=[{'role':'content','name':'raw','source':{'kind':'item','unit':'$previous','item':'raw'}},
            {'role':'content','name':'source_export','source':{'kind':'item','unit':'$export','item':'asset'}},
            {'role':'content','name':'payload','source':{'kind':'group_member','unit':template['producer'],'group':'geometry','piece':'$piece'}},
            {'role':'content','name':'data','source':{'kind':'item','unit':sources[name]['unit'],'item':sources[name]['item']}},
            {'role':'content','name':'definition','source':{'kind':'file','path':parameter}},*incoming]
        lod_records=[]
        if name in factory.TREES:
            for i in range(1,4):
                ref=sources[name+'_LOD'+str(i)];slot='lod_data'+str(i)
                inputs.append({'role':'content','name':slot,'source':{'kind':'item','unit':ref['unit'],'item':ref['item']}})
                lod_records.append({'slot':slot,'file':ref['file'],'member':'record.json'})
        finish={'id':'$export.finish','op':{'kind':'unreal.finish','version':'1'},'script':SCRIPT,'code':sorted(code),'inputs':inputs,
            'params':{'op':'finish','kind':'static_mesh','source':'raw','destination':package,'package_sources':{'raw':raw_package},
                'args':{'op':'prop','name':name,'base':base,'level':level,'native_inputs':native,'material':mi,'lods':lods,'lod_records':lod_records,
                    'data':{'slot':'data','file':sources[name]['file'],'member':'record.json'}},'settings':['-ForceDPCVars=Editor.AsyncStaticMeshCompilation=0']},'outputs':[island._item(package,raw=False)]}
        template['followers']=[{'unit':raw,'staged_inputs':{'source':'inputs/source'}},{'unit':finish,'staged_inputs':{i['name']:'inputs/'+i['name'] for i in inputs}}]
        requirements[template['unit_prefix']]=modules
    result['module_requirements']=requirements;result.setdefault('packages',{}).update({p:r for p,r in refs.items() if p not in natives})
    result['composition_requirements']=['unreal.city_tiles','world.hidamari_props']
    return result
