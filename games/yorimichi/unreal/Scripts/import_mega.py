"""Targeted mini-mega import; leaves existing village and character meshes intact."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json,runpy
from pathlib import Path
import unreal
HERE=Path(__file__).resolve().parent;ROOT=yori.OUT
helper=runpy.run_path(str(HERE/'import_village.py'))
E=unreal.EditorAssetLibrary
unreal.SystemLibrary.execute_console_command(None,'Interchange.FeatureFlags.Import.FBX 0')
mat=E.load_asset('/Game/Japan/Materials/M_Village');assert mat
report={}
for name in ['Mega_Ramp','Mega_Trim','Mega_Trail']:
 mesh=helper['import_mesh'](ROOT/'mega/assets'/f'{name}.fbx','/Game/Japan/Assets',name)
 mesh.set_material(0,mat)
 # Mega_Trim is look only (AMegaRamp gives it no collision), so it keeps no physics mesh.
 mesh.get_editor_property('body_setup').set_editor_property('collision_trace_flag',unreal.CollisionTraceFlag.CTF_USE_SIMPLE_AS_COMPLEX if name=='Mega_Trim' else unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
 E.save_loaded_asset(mesh)
 report[name]={'imported':True,'materials':len(mesh.static_materials)}
# The terrain belongs to unreal.world and unreal.southwest: a change to the ramp alone leaves it as it is.
(ROOT/'mega/import-report.json').write_text(json.dumps(report,indent=2)+'\n')
unreal.log('MEGA IMPORT COMPLETE')
