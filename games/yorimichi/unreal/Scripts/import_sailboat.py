"""Import only sailboat meshes, leaving all city assets and materials untouched."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2] / 'world')); import yori  # noqa: E402  (build/yorimichi = yori.OUT)
import json,sys
from pathlib import Path
import unreal
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from import_village import import_mesh
from sailboat_material import material
ROOT=yori.OUT;OUT=ROOT/'sailboat'
unreal.SystemLibrary.execute_console_command(None,'Interchange.FeatureFlags.Import.FBX 0')
mat=unreal.EditorAssetLibrary.load_asset('/Game/Japan/Materials/M_Village');assert mat
from import_southwest import sea_material
water=sea_material()
sea=unreal.EditorAssetLibrary.load_asset('/Game/Japan/Assets/Sea')
if sea:sea.set_material(0,water);unreal.EditorAssetLibrary.save_loaded_asset(sea)
cloth=material();foam=material(wake=True)
report={}
for name,entry in json.loads((OUT/'manifest.json').read_text()).items():
 m=import_mesh(OUT/'assets'/(name+'.fbx'),'/Game/Japan/Assets',name);m.set_material(0,cloth if name=='SB_Sail' else foam if name=='SB_Wake' else mat)
 b=m.get_bounding_box();assert abs(b.max.x-entry['max'][0]*100)<.3,(name,'axis/scale',b.max)
 unreal.EditorAssetLibrary.save_loaded_asset(m)
 report[name]={'min':[b.min.x,b.min.y,b.min.z],'max':[b.max.x,b.max.y,b.max.z],'triangles':entry['triangles']}
(OUT/'import-report.json').write_text(json.dumps(report,indent=2)+'\n')
unreal.log('SAILBOAT IMPORT COMPLETE')
