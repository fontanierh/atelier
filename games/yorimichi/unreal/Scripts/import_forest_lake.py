"""Targeted woodland lake import. Creates an independent lightweight animated lake water material."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json,runpy
from pathlib import Path
import unreal
HERE=Path(__file__).resolve().parent;ROOT=yori.OUT
helper=runpy.run_path(str(HERE/'import_village.py'))
E=unreal.EditorAssetLibrary
unreal.SystemLibrary.execute_console_command(None,'Interchange.FeatureFlags.Import.FBX 0')
mat=E.load_asset('/Game/Japan/Materials/M_Village');assert mat
water=runpy.run_path(str(HERE/"forest_lake_material.py"))["create"]()
report={}
for name in ['Lake_Cabin','Lake_Shore','Lake_Trail','Lake_Water','Lake_Plants']:
 mesh=helper['import_mesh'](ROOT/'forest_lake/assets'/f'{name}.fbx','/Game/Japan/Assets',name)
 mesh.set_material(0,water if name=='Lake_Water' else mat)
 mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
 E.save_loaded_asset(mesh)
 report[name]={'imported':True,'materials':len(mesh.static_materials)}
mesh=helper['import_mesh'](ROOT/'terrain.fbx','/Game/Japan','Terrain')
for i,slot in enumerate(mesh.static_materials):
 key=str(slot.get_editor_property('imported_material_slot_name')).split('.')[0]
 material=E.load_asset('/Game/Japan/Materials/MI_'+key);assert material,key
 mesh.set_material(i,material)
mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
E.save_loaded_asset(mesh)
(ROOT/'forest_lake/import-report.json').write_text(json.dumps(report,indent=2)+'\n')
unreal.log('LAKE IMPORT COMPLETE')
