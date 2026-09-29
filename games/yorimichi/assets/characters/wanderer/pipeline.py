"""Bind the redesigned model, shared solvers and references to its exports."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent
import yori  # build.py puts games/yorimichi/world on sys.path first
OUT=yori.OUT/'wanderer'
SOURCES=('build.py','pipeline.py','wanderer_mesh.py','wanderer_hair.py','wanderer_rig.py','wanderer_motion.py','accessories.py',
         'kit/mesh_tools.py','kit/shoe.py','kit/rig.py','kit/animate.py','kit/hair.py','kit/head.py',
         'kit/motion.py','kit/motion_profiles.py',
         'references/design-sheet.png','references/motion-sheet.png','references/skate-sheet.png')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def source_hashes():return {name:digest(HERE/name) for name in SOURCES}
def mark(sources):
    assert sources==source_hashes(),'Source changed during build'
    clips=json.loads((OUT/'animation_manifest.json').read_text())
    files=['Wanderer.blend','model_manifest.json','animation_manifest.json','animation_targets.json','fbx/Wanderer.fbx']
    files+=['fbx/'+name+'.fbx' for name in clips]
    data={'sources':sources,'artifacts':{name:digest(OUT/name) for name in files}}
    temp=OUT/'build.tmp.json';temp.write_text(json.dumps(data,indent=2)+'\n');temp.replace(OUT/'build.json')
def verify():
    data=json.loads((OUT/'build.json').read_text())
    assert data['sources']==source_hashes(),'Rebuild Wanderer: sources changed'
    for name,sha in data['artifacts'].items():assert digest(OUT/name)==sha,'Incomplete export: '+name
    return data
