"""Targeted zeppelin import: new meshes plus the two changed terrain surfaces."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json,runpy,os
from pathlib import Path
import unreal
HERE=Path(__file__).resolve().parent;ROOT=yori.OUT
helper=runpy.run_path(str(HERE/'import_village.py'));E=unreal.EditorAssetLibrary
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
fabric=fabric_material()
manifest=json.loads((ROOT/'zeppelin/manifest.json').read_text());report={}
for name in manifest:
 mesh=helper['import_mesh'](ROOT/'zeppelin/assets'/f'{name}.fbx','/Game/Japan/Assets',name);mesh.set_material(0,mat)
 if name=='ZP_Airship':
  assert len(mesh.static_materials)==2
  for i,slot in enumerate(mesh.static_materials):mesh.set_material(i,fabric if 'ZeppelinFabric' in str(slot.get_editor_property('imported_material_slot_name')) else mat)
 mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
 E.save_loaded_asset(mesh);report[name]=True
if not (globals().get('ASSETS_ONLY') or os.environ.get('ZEPPELIN_ASSETS_ONLY')):
 mesh=helper['import_mesh'](ROOT/'hidamari/assets/HD_Terrain.fbx','/Game/Japan/Assets','HD_Terrain');mesh.set_material(0,mat)
 mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE);E.save_loaded_asset(mesh)
 mesh=helper['import_mesh'](ROOT/'terrain.fbx','/Game/Japan','Terrain')
 for i,slot in enumerate(mesh.static_materials):
  key=str(slot.get_editor_property('imported_material_slot_name')).split('.')[0];material=E.load_asset('/Game/Japan/Materials/MI_'+key);assert material,key;mesh.set_material(i,material)
 mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE);E.save_loaded_asset(mesh)
(ROOT/'zeppelin/import-report.json').write_text(json.dumps(report,indent=2)+'\n');unreal.log('ZEPPELIN IMPORT COMPLETE')
