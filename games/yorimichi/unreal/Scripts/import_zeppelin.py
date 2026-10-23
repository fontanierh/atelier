"""Targeted zeppelin import: new meshes plus the two changed terrain surfaces."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json,runpy,os
from pathlib import Path
import unreal
from atelier.unreal_mesh_reuse import AssetGroup,set_if_changed
from atelier.native_protocol import native_context
from atelier import native_membership
HERE=Path(__file__).resolve().parent;ROOT=yori.OUT
_sys.path.insert(0,str(HERE));E=unreal.EditorAssetLibrary
unreal.SystemLibrary.execute_console_command(None,'Interchange.FeatureFlags.Import.FBX 0')
mat=E.load_asset('/Game/Japan/Materials/M_Village');assert mat
def fabric_material():
    path='/Game/Japan/Materials/M_ZeppelinFabric';M=unreal.MaterialEditingLibrary
    m=E.load_asset(path) if E.does_asset_exist(path) else unreal.AssetToolsHelpers.get_asset_tools().create_asset('M_ZeppelinFabric','/Game/Japan/Materials',unreal.Material,unreal.MaterialFactoryNew())
    M.delete_all_material_expressions(m);m.set_editor_property('shading_model',unreal.MaterialShadingModel.MSM_UNLIT)
    color=M.create_material_expression(m,unreal.MaterialExpressionVertexColor,-500,0)
    normal=M.create_material_expression(m,unreal.MaterialExpressionPixelNormalWS,-500,200)
    depth=M.create_material_expression(m,unreal.MaterialExpressionPixelDepth,-500,600)
    sun=M.create_material_expression(m,unreal.MaterialExpressionVectorParameter,-500,400);sun.set_editor_property('parameter_name','SunDirection');sun.set_editor_property('default_value',unreal.LinearColor(-.646,-.173,.743,0))
    shade=M.create_material_expression(m,unreal.MaterialExpressionCustom,-150,0)
    shade.set_editor_property('code','float3 Base=lerp(C/12.92,pow((C+.055)/1.055,2.4),step(.04045,C)); float light=.72+.58*smoothstep(-1.,1.,dot(normalize(N),normalize(D))); return lerp(Base*light,float3(.64,.68,.76),saturate((Z-7000.)/220000.)*.5);')
    shade.set_editor_property('output_type',unreal.CustomMaterialOutputType.CMOT_FLOAT3)
    inputs=[]
    for name in ('C','N','D','Z'):
        p=unreal.CustomInput();p.set_editor_property('input_name',name);inputs.append(p)
    shade.set_editor_property('inputs',inputs)
    for source,name in [(color,'C'),(normal,'N'),(sun,'D'),(depth,'Z')]:M.connect_material_expressions(source,'',shade,name)
    M.connect_material_property(shade,'',unreal.MaterialProperty.MP_EMISSIVE_COLOR);M.recompile_material(m);E.save_loaded_asset(m)
    return m
fabric_group=AssetGroup(native_context(yori.GAME.name),'unreal.zeppelin',__file__,('fabric_material',),parameters={})
if not fabric_group.matches(['/Game/Japan/Materials/M_ZeppelinFabric']):
 fabric_material();fabric_group.validated(['/Game/Japan/Materials/M_ZeppelinFabric'])
fabric=E.load_asset('/Game/Japan/Materials/M_ZeppelinFabric');assert fabric
manifest=json.loads((ROOT/'zeppelin/manifest.json').read_text());report={}
logical=json.loads((ROOT/'zeppelin/logical-pieces.json').read_text())
parents={child:parent for parent,children in logical['parents'].items() for child in children}
if set(parents)!=set(manifest):raise ValueError('Incomplete Zeppelin native membership')
previous=native_membership.inventory(E,'/Game/Japan/Assets','ZP_')


def current(mesh,expected,parent):
 if not mesh or mesh.get_num_triangles(0)!=expected['triangles']:return False
 slots=list(mesh.get_editor_property('static_materials'))
 if len(slots)!=expected['materials']:return False
 for index,slot in enumerate(slots):
  want=fabric if parent=='ZP_Airship' and 'ZeppelinFabric' in str(slot.get_editor_property('imported_material_slot_name')) else mat
  if mesh.get_material(index)!=want:return False
 body=mesh.get_editor_property('body_setup')
 if not body or body.get_editor_property('collision_trace_flag')!=unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE:return False
 box=mesh.get_bounding_box();lo,hi=expected['min'],expected['max']
 actual=[box.min.x,box.min.y,box.min.z,box.max.x,box.max.y,box.max.z]
 wanted=[lo[0]*100,-hi[1]*100,lo[2]*100,hi[0]*100,-lo[1]*100,hi[2]*100]
 return max(abs(a-b) for a,b in zip(actual,wanted))<1.


from mesh_import import import_mesh
for name,expected in manifest.items():
 parent=parents[name];path=ROOT/'zeppelin/assets'/f'{name}.fbx'
 from atelier.mesh_reuse import digest
 if digest(path)!=expected['sha256']:raise ValueError('Changed Zeppelin export: '+name)
 mesh=import_mesh(path,'/Game/Japan/Assets',name,reuse_validator=lambda mesh:current(mesh,expected,parent))
 slots=list(mesh.get_editor_property('static_materials'))
 assert len(slots)==expected['materials'],name
 for i,slot in enumerate(slots):
  want=fabric if parent=='ZP_Airship' and 'ZeppelinFabric' in str(slot.get_editor_property('imported_material_slot_name')) else mat
  if mesh.get_material(i)!=want:mesh.set_material(i,want)
 set_if_changed(mesh.get_editor_property('body_setup'),'collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
 assert E.save_loaded_asset(mesh,only_if_is_dirty=True),name
 assert current(mesh,expected,parent),name
 report[name]=True
native_membership.retire(E,previous,list(manifest),'/Game/Japan/Assets','ZP_')
(ROOT/'zeppelin/import-report.json').write_text(json.dumps(report,indent=2)+'\n');unreal.log('ZEPPELIN IMPORT COMPLETE')
