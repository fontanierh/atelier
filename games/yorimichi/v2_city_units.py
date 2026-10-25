"""Current unreal.desktop city surface followers over the actual 86 logical planners."""
import ast
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

SCRIPT='games/yorimichi/world/city_finish_v2.py'
EMPTY='games/yorimichi/unreal/Scripts/import_city_surface_tiles.py'
LOD='games/yorimichi/unreal/Scripts/city_distance_lods.py'
ROSTER='games/yorimichi/unreal/Source/Yorimichi/CitySurfaceParents.h'
PARENT='games/yorimichi/world/city_parent_v2.py'


def _load(root,path,name):
    spec=importlib.util.spec_from_file_location(name,root/path);value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value


def _surface_policy(root):
    tree=ast.parse((root/'games/yorimichi/world/regions/hidamari/surfaces.py').read_text());scope={}
    nodes=[n for n in tree.body if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id in ('TEXTURED','RULES')]
    for node in nodes:scope[node.targets[0].id]=ast.literal_eval(node.value)
    if set(scope)!={'TEXTURED','RULES'}:raise ValueError('Missing original city surface policy')
    return scope['TEXTURED'],sorted({'flat','paint',*(slug for slug,_ in scope['RULES'])})


def attach_followers(geometry,natives,*,checkout):
    """@cc [owner:fontanierh,label:correctness] current-desktop-city-native-owners
    All 86 current logical city parents MUST use their actual D2 export/payload
    and a validated narrow parent-facts projection. Parent collision/material semantics MUST
    survive compact child slots. Textured parents conservatively stage the complete
    committed HDS palette and native closure; other parents their exact material.
    No generated scan, invented future ID, old main/cache/namespace/retirement or
    duplicate material owner MAY run. Desktop MUST NOT become World's prerequisite.
    """
    from atelier.source_imports import ImportScanner
    root=Path(checkout).resolve();factory=_load(root,'games/yorimichi/hidamari_build.py','city_original_factory')
    policy=_load(root,'games/yorimichi/city_atomic_products.py','city_original_policy')
    texture=_load(root,'games/yorimichi/v2_texture_units.py','city_texture_policy')
    island=_load(root,'games/yorimichi/v2_island_units.py','city_item_policy')
    original=factory.mesh_steps(SimpleNamespace(out=root/'build/yorimichi'))
    by_name={step.name:step for step in original};parents=tuple(policy.SOURCES)
    textured,slugs=_surface_policy(root)
    scanner=ImportScanner();code=set(texture._code(root))|{EMPTY,LOD,ROSTER}
    code.update(p.relative_to(root).as_posix() for p in scanner.local_imports(root/SCRIPT,
        (root/'platform/studio',root/'games/yorimichi',root/'games/yorimichi/world',root/'games/yorimichi/unreal/Scripts')))
    descriptor=json.loads((root/'games/yorimichi/unreal/Yorimichi.uproject').read_text())
    modules=[{'name':m['Name'],'kind':m['Type'],'loading_phase':m.get('LoadingPhase','Default')} for m in descriptor['Modules']]
    parent_code=sorted(p.relative_to(root).as_posix() for p in scanner.local_imports(root/PARENT,(root/'platform/studio',root/'games/yorimichi/world')))
    result=deepcopy(geometry);result.setdefault('units',[]);result.setdefault('staged_inputs',{});result.setdefault('content_slots',{})
    requirements=dict(result.get('module_requirements',{}));seen=set()
    candidates=[t for t in result['templates'] if t['unit_prefix'].startswith('world.hidamari.export.')]
    if len(candidates)!=len(parents):raise ValueError('City requires all 86 actual D2 parents exactly once')
    for template in candidates:
        parent=template['unit_prefix'].removeprefix('world.hidamari.export.');producer='world.hidamari.geometry.'+parent
        if (parent not in parents or parent in seen or template.get('followers') or template['producer']!=producer or template['group']!='geometry'
                or template['op']!={'kind':'blender_export_piece','version':'1'} or template['params'].get('format')!='fbx'):
            raise ValueError('City requires original unmodified FBX child templates')
        seen.add(parent);step=by_name.get(producer)
        product_name='hidamari.geometry.'+parent
        metadata=[(i,p) for i,p in enumerate(step.products) if p.name==product_name] if step else []
        if len(metadata)!=1 or len(metadata[0][1].paths)!=1 or metadata[0][1].optional_paths:
            raise ValueError('City requires its actual complete planner root Product: '+product_name)
        index,product=metadata[0]
        if index!=0:raise ValueError('City original planner root Product index changed')
        parent_id='unreal.city.parent.'+parent
        projection={'id':parent_id,'op':{'kind':'py_data','version':'1'},'script':PARENT,'code':parent_code,
            'inputs':[{'role':'content','name':'source','source':{'kind':'item','unit':producer,'item':'product'+str(index)},
                'whole':'The complete original plan and every payload validate before emitting only parent material/collision facts.'}],
            'params':{},'outputs':[{'id':'parent','logical_path':'/Internal/CityParents/'+parent,'class':'JsonData','destination':'store','files':[{'path':'plan.json','required':True}]}]}
        result['units'].append(projection);result['staged_inputs'][parent_id]={'source':'inputs/source'};result['content_slots']['source']=False
        is_textured=parent in textured or parent.startswith(('HD_Shop_','HD_ArcadeShop_','HD_House_'))
        wanted=(set(policy.piece_material_paths(parent,['HDS_'+s for s in slugs]).values()) if is_textured
            else set(policy.piece_material_paths(parent,['Palette']).values()))
        dependencies={}
        def add(path,inline=None):
            ref=inline if inline is not None else natives.get(path)
            if not isinstance(ref,dict) or ref.get('package')!=path or any(not isinstance(ref.get(k),str) or not ref[k] for k in ('unit','item')):
                raise ValueError('Missing exact supplied city native material/dependency: '+path)
            key=ref['unit'],ref['item']
            if key in dependencies:
                if dependencies[key][1]['package']!=path:raise ValueError('City native Item aliases packages')
                return
            slot='native'+str(len(dependencies));dependencies[key]=(slot,ref)
            for child in ref.get('dependencies',()):add(child if isinstance(child,str) else child['package'],None if isinstance(child,str) else child)
        for path in sorted(wanted):add(path)
        native={slot:ref['package'] for slot,ref in dependencies.values()}
        raw_package='/Game/_Raw/City/$piece';destination=policy.DESTINATION+'/$piece'
        raw={'id':'$export.raw','op':{'kind':'unreal.raw_import','version':'1'},'script':texture.OPS,'code':texture._code(root),
            'inputs':[{'role':'content','name':'source','source':{'kind':'item','unit':'$export','item':'asset'},'whole':'Raw import reads exactly the selected certified FBX and its receipt.'}],
            'params':{'op':'raw_import','kind':'static_mesh','source':'source','destination':raw_package,
                'settings':['-ForceDPCVars=Interchange.FeatureFlags.Import.FBX=0,Editor.AsyncStaticMeshCompilation=0']},'outputs':[island._item(raw_package,raw=True)]}
        inputs=[{'role':'content','name':'raw','source':{'kind':'item','unit':'$previous','item':'raw'},'whole':'Finish duplicates and validates the exact imported source package.'},
            {'role':'content','name':'source_export','source':{'kind':'item','unit':'$export','item':'asset'},'whole':'Current source primary and receipt certify this selected child.'},
            {'role':'content','name':'payload','source':{'kind':'group_member','unit':producer,'group':'geometry','piece':'$piece'},'whole':'All selected geometry/collision/channel facts are validated.'},
            {'role':'content','name':'parent','source':{'kind':'item','unit':parent_id,'item':'parent'},'whole':'Exact original parent material and whole collision policy are consumed.'},
            *({'role':'content','name':slot,'source':{'kind':'item','unit':ref['unit'],'item':ref['item']},
                'whole':('The complete committed palette is conservatively staged until generated slot selection can narrow native dependencies.' if is_textured else 'The exact original material and its declared native closure are staged.')}
              for slot,ref in dependencies.values())]
        finish={'id':'$export.finish','op':{'kind':'unreal.finish','version':'1'},'script':SCRIPT,'code':sorted(code),'inputs':inputs,
            'params':{'op':'finish','kind':'static_mesh','source':'raw','destination':destination,'package_sources':{'raw':raw_package},
                'args':{'parent':parent,'native_inputs':native},'settings':['-ForceDPCVars=Editor.AsyncStaticMeshCompilation=0']},'outputs':[island._item(destination,raw=False)]}
        template['followers']=[{'unit':raw,'staged_inputs':{'source':'inputs/source'}},{'unit':finish,'staged_inputs':{i['name']:'inputs/'+i['name'] for i in inputs}}]
        requirements[template['unit_prefix']]=modules
    if seen!=set(parents):raise ValueError('City logical source roster differs')
    result['module_requirements']=requirements
    return result
