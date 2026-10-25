"""Original four Kart rigid mesh followers, independent material and authored runtime data."""
from copy import deepcopy
import importlib.util
from pathlib import Path

FINISH='games/yorimichi/world/kart_finish_v2.py'
DATA='games/yorimichi/world/kart_data_v2.py'
CALL='games/yorimichi/world/native_author_call_v2.py'
MATERIAL_SOURCE='games/yorimichi/unreal/Scripts/kart_material.py'
IDENTITY='games/yorimichi/tools/kart_grip_editor/source_identity.py'
MATERIAL='/Game/Japan/Kart/M_Kart'
MATERIAL_UNIT='unreal.kart.material.M_Kart'
DATA_UNIT='unreal.kart.data'


def _load(root,path,name):
    spec=importlib.util.spec_from_file_location(name,root/path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def attach_followers(geometry,natives,*,checkout):
    """@cc [owner:fontanierh,label:correctness] original-kart-native-and-data-owners
    All four original rigid Kart parents MUST consume their own selected export and
    payload, with the original independent M_Kart factory. Runtime data MUST bind
    actual cockpit/manifest Product Items and every committed playable profile and
    model receipt selected by the original character declarations. No generated
    discovery, monolithic import, native inventory, guessed grip or alias MAY run.
    """
    from types import SimpleNamespace
    from atelier.source_imports import ImportScanner
    root=Path(checkout).resolve()
    factory=_load(root,'games/yorimichi/vehicle_atomic_build.py','kart_original_factory')
    sources=_load(root,'games/yorimichi/world/vehicle_sources.py','kart_original_sources')
    identity=_load(root,IDENTITY,'kart_original_identity')
    texture=_load(root,'games/yorimichi/v2_texture_units.py','kart_texture_policy')
    island=_load(root,'games/yorimichi/v2_island_units.py','kart_item_policy')
    roster=tuple(sources.FAMILIES['kart']['builders'])
    original=factory.steps(SimpleNamespace(out=root/'build/yorimichi'),'kart')
    def product(owner,name):
        steps=[s for s in original if s.name==owner]
        found=[(i,p) for i,p in enumerate(steps[0].products) if p.name==name] if len(steps)==1 else []
        if len(found)!=1 or found[0][1].optional_paths:raise ValueError('Kart actual source Product owner differs: '+name)
        expected=['cockpit.json'] if name=='vehicle_kart.cockpit' else ['assets','manifest.json']
        if sorted(p.name for p in found[0][1].paths)!=sorted(expected):raise ValueError('Kart complete source ROOT declaration differs')
        return {'unit':owner,'item':'product'+str(found[0][0])}
    cockpit=product('world.kart.sources','vehicle_kart.cockpit');manifest=product('world.kart','vehicle_kart.library')
    scanner=ImportScanner()
    def code(path):
        return {p.relative_to(root).as_posix() for p in scanner.local_imports(root/path,
            (root/'platform/studio',root/'games/yorimichi',root/'games/yorimichi/world',root/'games/yorimichi/unreal/Scripts'))}
    material_output=island._item(MATERIAL,raw=False);material_output['class']='Material'
    material={'id':MATERIAL_UNIT,'op':{'kind':'unreal.author','version':'1'},'script':CALL,
        'code':sorted(set(texture._code(root))|code(CALL)|code(MATERIAL_SOURCE)),'inputs':[],
        'params':{'args':{'module':MATERIAL_SOURCE,'function':'material','arguments':[],'keyword_arguments':{},'expected_package':MATERIAL},'settings':[]},
        'outputs':[material_output]}
    result=deepcopy(geometry);result.setdefault('units',[]).append(material)
    result.setdefault('staged_inputs',{})[MATERIAL_UNIT]={};result.setdefault('content_slots',{})
    result.setdefault('packages',{})[MATERIAL]={'unit':MATERIAL_UNIT,'item':'asset','package':MATERIAL}
    inputs=[{'role':'content','name':slot,'source':{'kind':'item',**ref}} for slot,ref in (('cockpit',cockpit),('manifest',manifest))]
    playable=identity.playable_ids()
    definitions=sorted((root/'games/yorimichi/assets/characters').glob('*/character.toml'))
    for definition in definitions:
        name=definition.parent.name
        for role,path,optional in [('definition',definition,False),('adventure',definition.with_name('adventure.toml'),True)]:
            inputs.append({'role':'content','name':role+'.'+name,'source':{'kind':'file','path':path.relative_to(root).as_posix(),**({'optional':True} if optional else {})}})
    for name in playable:
        for role,path in (('grip',identity.profile_path(name)),('model',identity.model_path(name))):
            if not path.is_file() or path.is_symlink():raise ValueError('Missing committed Kart '+role+' source: '+name)
            inputs.append({'role':'content','name':role+'.'+name,'source':{'kind':'file','path':path.relative_to(root).as_posix()}})
    for incoming in inputs:
        incoming['whole']='The complete declared source is validated and copied for the original Kart runtime data.'
    files=['cockpit.json','prepared-models.json',*('grips/'+name+'.json' for name in playable)]
    data={'id':DATA_UNIT,'op':{'kind':'py_data','version':'1'},'script':DATA,
        'code':sorted(code(DATA)|{IDENTITY,'platform/studio/atelier/build_v2/recipe_job.py'}),'inputs':inputs,'params':{},
        'outputs':[{'id':'data'+str(i),'logical_path':'/Game/Data/kart/'+name,'class':'JsonData','destination':'checkout',
                    'files':[{'path':name,'install_path':'games/yorimichi/unreal/Content/Data/kart/'+name,'required':True}]} for i,name in enumerate(files)]}
    result['units'].append(data);result['staged_inputs'][DATA_UNIT]={i['name']:'inputs/'+i['name'] for i in inputs}
    result['content_slots'].update({i['name']:False for i in inputs})
    result.setdefault('data_targets',[]).append(DATA_UNIT)
    requirements=dict(result.get('module_requirements',{}));seen=set()
    import json
    modules=[{'name':m['Name'],'kind':m['Type'],'loading_phase':m.get('LoadingPhase','Default')} for m in json.loads((root/'games/yorimichi/unreal/Yorimichi.uproject').read_text())['Modules']]
    finish_code=sorted(set(texture._code(root))|code(FINISH))
    for template in result['templates']:
        if not template['unit_prefix'].startswith('world.vehicle_kart.export.'):continue
        parent=template['unit_prefix'].removeprefix('world.vehicle_kart.export.')
        if (parent not in roster or parent in seen or template['producer']!='world.vehicle_kart.geometry.'+parent
                or template['group']!='geometry' or template['op']!={'kind':'blender_export_piece','version':'1'}
                or template['params'].get('format')!='fbx' or template.get('followers')):
            raise ValueError('Kart followers require each original rigid FBX parent exactly once')
        seen.add(parent);raw_package='/Game/_Raw/Kart/$piece';destination='/Game/Japan/Kart/$piece'
        raw={'id':'$export.raw','op':{'kind':'unreal.raw_import','version':'1'},'script':texture.OPS,'code':texture._code(root),
            'inputs':[{'role':'content','name':'source','source':{'kind':'item','unit':'$export','item':'asset'}}],
            'params':{'op':'raw_import','kind':'static_mesh','source':'source','destination':raw_package,
                'settings':['-ForceDPCVars=Interchange.FeatureFlags.Import.FBX=0,Editor.AsyncStaticMeshCompilation=0']},'outputs':[island._item(raw_package,raw=True)]}
        native_inputs=[{'role':'content','name':'raw','source':{'kind':'item','unit':'$previous','item':'raw'}},
            {'role':'content','name':'source_export','source':{'kind':'item','unit':'$export','item':'asset'}},
            {'role':'content','name':'payload','source':{'kind':'group_member','unit':template['producer'],'group':'geometry','piece':'$piece'}},
            {'role':'content','name':'material','source':{'kind':'item','unit':MATERIAL_UNIT,'item':'asset'}}]
        finish={'id':'$export.finish','op':{'kind':'unreal.finish','version':'1'},'script':FINISH,'code':finish_code,'inputs':native_inputs,
            'params':{'op':'finish','kind':'static_mesh','source':'raw','destination':destination,'package_sources':{'raw':raw_package},
                'args':{'parent':parent,'source_export':'source_export','payload':'payload','material':'material'},
                'settings':['-ForceDPCVars=Editor.AsyncStaticMeshCompilation=0']},'outputs':[island._item(destination,raw=False)]}
        template['followers']=[{'unit':raw,'staged_inputs':{'source':'inputs/source'}},
            {'unit':finish,'staged_inputs':{i['name']:'inputs/'+i['name'] for i in native_inputs}}]
        requirements[template['unit_prefix']]=modules
    if seen!=set(roster):raise ValueError('Kart requires its complete four-parent source family')
    result['module_requirements']=requirements
    return result
