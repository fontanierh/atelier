"""Normal cold-graph MegaPark generated membership through existing FileSet templates."""
from copy import deepcopy
from pathlib import Path

from atelier.build import Call,Step
from atelier.build_v2.recipe_dependencies import extract
from atelier.build_v2.recipe_compiler import _binding
from atelier.source_imports import ImportScanner
from v2_geometry_templates import LIMITS
import v2_megapark_units as park

BODY='games/yorimichi/world/megapark_members_v2.py'
RECIPE='platform/studio/atelier/build_v2/recipe_job.py'
EMITTER='platform/studio/atelier/build_v2/file_groups.py'
VERIFIER='games/yorimichi/world/regions/megapark/verify_import.py'
MATERIALS='world.megapark.members.materials'
ROLES='world.megapark.members.roles'
PREFIX='unreal.megapark.member'


def _call(root,name,defaults):
    module=park._load(root,BODY,'megapark_members_callback_'+name);function=getattr(module,name);function.__defaults__=tuple(defaults)
    row=extract([Step('members',[Call(name,function)])],checkout=root,build_root=root/'build',
        import_roots=(root/'platform/studio',root/'games/yorimichi/world',root/'games/yorimichi/world/regions'))[0]
    return {'kind':'call','call':_binding(row['commands'][0]['fn'])}


def material_token():
    return {'derived_items':{'root':'build/v2-derived/megapark/materials','templates':[{'producer':MATERIALS,'group':'members','unit_prefix':PREFIX,'follower':0,'item':'asset'}]}}


def megapark_templates(rows,*,checkout,natives=None):
    """@cc [owner:fontanierh,label:correctness] cold-megapark-generated-native-members
    Actual complete build/restyle ROOTs MUST author FileSet members before keys.
    Every map texture has a fixed owner reading its own role member; every actual
    generated MI spec has one selected Data child and checkout author follower.
    Full native palette staging is conservative and explicit. Mesh/level/audit
    consumers MUST bind actual derived MI Items, never invented future IDs.
    The complete native audit gate MUST be returned for Root's required target join.
    """
    root=Path(checkout).resolve();rows=list(rows);by_id=park._check_original(root,rows)
    library,roots=park._product(by_id['world.megapark'],'megapark.library')
    if by_id['world.megapark_restyle']['outputs'][0]!=park.BUILD+'/textures':raise park.Unsupported('MegaPark requires the actual whole restyle directory ROOT')
    restyle={'unit':'world.megapark_restyle','item':'output0','root':{'archive_member':'outputs/0.tree.tar','name':'textures'}}
    fixed=park.megapark_units(rows,checkout=root,members={'materials':{},'texture_roles':{'unit':ROLES,'group':'members'}},natives={**(natives or {}),'restyle':restyle})
    scanner=ImportScanner();code=set()
    for source in (BODY,RECIPE,EMITTER):code.update(p.relative_to(root).as_posix() for p in scanner.local_imports(root/source,(root/'platform/studio',root/'games/yorimichi/world',root/'games/yorimichi/world/regions')))
    source_map=park.SOURCE+'/map.json';textures,render,collision,seam=park.catalogue(root)
    incoming=[park._item('build','world.megapark',library),park._item('restyle','world.megapark_restyle','output0'),
        {'role':'content','name':'map','source':{'kind':'file','path':source_map}}]
    paths={park.BUILD+'/build.json':'inputs/build/'+roots[park.BUILD+'/build.json'],park.BUILD+'/textures':'inputs/restyle/outputs/0.tree.tar',source_map:'inputs/map'}
    for index,(tid,png) in enumerate(textures.items()):
        slot='png'+str(index);path=park.SOURCE+'/'+png
        incoming.append({'role':'content','name':slot,'source':{'kind':'file','path':path}});paths[path]='inputs/'+slot
    for item in incoming:item['whole']='The original complete source and image checksums validate before selecting narrow generated members.'
    groups={};templates=[];projected=[]
    for kind,producer,parent in (('materials',MATERIALS,'MegaParkMaterials'),('roles',ROLES,'MegaParkTextureRoles')):
        folder='generated/'+kind
        contract={'id':'members','root':'files','root_param':'file_root','manifest':'plan.json','adapter_version':'d2.file-set/1','parent':parent,'encoding':'file_set','class':'Data','logical_namespace':'/Internal/MegaPark/'+kind,**LIMITS}
        projected.append({'id':producer,'op':{'kind':'recipe.python','version':'1'},'script':RECIPE,'code':sorted(code),'inputs':deepcopy(incoming),
            'params':{'file_root':'output/files','recipe':{'version':1,'paths':dict(paths),'commands':[_call(root,'project',(root/park.BUILD/'build.json',root/park.BUILD/'textures',root/source_map,root/folder,kind,tuple(park.restyled(root))))],
                'outputs':[{'kind':'tree','path':folder,'file':'members.tree.tar','required':True}],'verify':None,'file_group':{'source':folder,'parent':parent,'extensions':['.json']}}},
            'outputs':[{'id':'members','logical_path':'/Internal/MegaPark/'+kind,'class':'Data','destination':'store','files':[{'path':'members.tree.tar','required':True}]}],'output_groups':[contract]})
        groups[producer]={'contract':contract,'source':folder}
    packages=fixed['packages'];native_inputs=[park._native(ref) for ref in packages.values() if ref['package']!=park.LEVEL]
    native_by_path={ref['package']:park._native(ref)['name'] for ref in packages.values() if ref['package']!=park.LEVEL}
    output=park._output('asset',park.ROOT+'/Materials/$piece','MaterialInstance')
    author={'id':'$export.author','op':{'kind':'unreal.author','version':'1'},'script':park.SCRIPT,'code':park._code_closure(root),
        'inputs':[park._item('spec','$export','asset'),*deepcopy(native_inputs)],
        'params':{'input_roots':{'spec':{'archive_member':'member.tree.tar','name':'$piece.json'}},'args':{'action':'instance','spec':'spec','piece':'$piece',
            'parents':{str(i):native_by_path[park.ROOT+'/Materials/'+name] for i,name in enumerate(park.PARENTS)},
            'texture_inputs':{tid:native_by_path[park.ROOT+'/Textures/T_'+tid[2:]] for tid in textures},
            'defaults':{name:native_by_path[park.ROOT+'/Textures/'+name] for name in park.DEFAULTS}},'settings':[]},'outputs':[output]}
    templates.append({'producer':MATERIALS,'group':'members','unit_prefix':PREFIX,'op':{'kind':'recipe.python','version':'1'},'script':RECIPE,'code':sorted(code),
        'derive_payload':False,'payload_slot':'spec','staged_path':'inputs/spec','output_class':'Data','logical_namespace':'/Internal/MegaPark/SelectedSpecs','files':[{'path':'member.tree.tar','required':True}],
        'params':{'recipe':{'version':1,'paths':{'selected':'inputs/spec'},'commands':[_call(root,'copy_member',(root/'selected/$piece.json',root/'member.json'))],
            'outputs':[{'kind':'tree','path':'member.json','file':'member.tree.tar','required':True}],'verify':None}},
        'followers':[{'unit':author,'staged_inputs':{i['name']:'inputs/'+i['name'] for i in author['inputs']}}]})
    fixed['units']+=projected
    for unit in projected:fixed['staged_inputs'][unit['id']]={i['name']:'inputs/'+i['name'] for i in unit['inputs']}
    token=material_token();fixed['material_items']=token;fixed['templates']=templates;fixed['groups']=groups;fixed['content_slots']={i['name']:False for unit in fixed['units'] for i in unit['inputs']}
    fixed['module_requirements'][PREFIX]=park._modules(root,[])[0]
    level=next(unit for unit in fixed['units'] if unit['id']=='unreal.megapark.level')
    level['params']['args']['materials']=deepcopy(token);level['inputs']+=deepcopy(native_inputs);fixed['staged_inputs'][level['id']]={i['name']:'inputs/'+i['name'] for i in level['inputs']}
    all_parents=(*render,*collision,*seam)
    def capture(root_name,*,follower=None,item='asset'):
        return {'derived_items':{'root':'build/v2-derived/megapark/audit/'+root_name,'templates':[{'producer':'world.megapark.geometry.'+parent,'group':'geometry','unit_prefix':'world.megapark.export.'+parent,**({'follower':follower} if follower is not None else {}),'item':item} for parent in all_parents]}}
    letter_row=by_id['world.megapark.letters_data'];letter_item,letter_roots=park._product(letter_row,'megapark.letters_data');letter_path,letter_archive=next(iter(letter_roots.items()))
    audit_inputs=[park._item('level','unreal.megapark.level','asset'),park._item('build','world.megapark',library),park._item('letters',letter_row['id'],letter_item),{'role':'content','name':'map','source':{'kind':'file','path':source_map}}]
    audit_paths={'native-level':'inputs/level',park.BUILD+'/build.json':'inputs/build/'+roots[park.BUILD+'/build.json'],park.BUILD+'/letters.npz':'inputs/letters/'+letter_archive,source_map:'inputs/map'}
    import json
    source=json.loads((root/source_map).read_text())
    for index,path in enumerate(sorted({item['npz'] for kind in ('models','collision') for item in source[kind]})):
        slot='geometry'+str(index);relative=park.SOURCE+'/'+path;audit_inputs.append({'role':'content','name':slot,'source':{'kind':'file','path':relative}});audit_paths[relative]='inputs/'+slot
    audit_code=set(code)|{VERIFIER};audit_code.update(p.relative_to(root).as_posix() for p in scanner.local_imports(root/VERIFIER,(root/'platform/studio',root/park.GAME/'world',root/park.GAME/'world/regions')))
    outputs=[park.BUILD+'/import-report.json',park.BUILD+'/imported-geometry',park.BUILD+'/geometry-verification.json']
    audit={'id':'unreal.megapark.audit','op':{'kind':'recipe.python','version':'1'},'script':RECIPE,'code':sorted(audit_code),'inputs':audit_inputs,
        'params':{'recipe':{'version':1,'paths':audit_paths,'commands':[_call(root,'audit',(root/park.BUILD/'build.json',root/park.BUILD/'letters.npz',root/source_map,root/park.BUILD,
            capture('geometry',follower=1,item='geometry'),capture('reports',follower=1,item='report'),deepcopy(token),root/VERIFIER,root/'native-level'))],
            'outputs':[{'kind':'tree','path':path,'file':'outputs/'+str(i)+'.tree.tar','required':True} for i,path in enumerate(outputs)],'verify':None}},
        'outputs':[{'id':'output'+str(i),'logical_path':'/Internal/MegaPark/Audit/'+str(i),'class':'Data','destination':'store','files':[{'path':'outputs/'+str(i)+'.tree.tar','required':True}]} for i in range(len(outputs))]}
    fixed['units'].append(audit);fixed['staged_inputs'][audit['id']]={i['name']:'inputs/'+i['name'] for i in audit_inputs};fixed['content_slots'].update({i['name']:False for i in audit_inputs})
    fixed['audit_unit']=audit['id'];fixed['required_targets']=[audit['id'],'unreal.megapark.level']
    return fixed
