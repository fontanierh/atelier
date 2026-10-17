"""Bind the procedural model, the shared kit and the design sheet to Suzu's exports."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parent / 'wanderer' / 'kit'

import sys  # noqa: E402

sys.path.insert(0, str(HERE.parents[2] / 'world'))
import yori  # noqa: E402

OUT = yori.OUT / 'bell-ringer'
SOURCES = ('build.py', 'pipeline.py', 'suzu_mesh.py', 'suzu_hair.py', 'suzu_foot.py', 'suzu_shapes.py',
           'suzu_rig.py', 'suzu_motion.py', 'references/sheet.jpg', 'references/sheet.prompt.txt')
KIT_SOURCES = ('mesh_tools.py', 'shoe.py', 'rig.py', 'animate.py', 'hair.py', 'head.py', 'motion.py',
               'motion_profiles.py')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_hashes():
    return {name: digest(HERE/name) for name in SOURCES} | {
        'wanderer/kit/'+name: digest(KIT/name) for name in KIT_SOURCES}


def mark(sources):
    assert sources == source_hashes(), 'Source changed during build'
    clips = json.loads((OUT/'animation_manifest.json').read_text())
    files = ['Suzu.blend', 'model_manifest.json', 'animation_manifest.json', 'animation_targets.json',
             'fbx/Suzu.fbx']+['fbx/'+name+'.fbx' for name in clips]
    data = {'sources': sources, 'artifacts': {name: digest(OUT/name) for name in files}}
    temp = OUT/'build.tmp.json'
    temp.write_text(json.dumps(data, indent=2)+'\n')
    temp.replace(OUT/'build.json')


def verify():
    data = json.loads((OUT/'build.json').read_text())
    assert data['sources'] == source_hashes(), 'Rebuild Suzu: sources changed'
    for name, sha in data['artifacts'].items():
        assert digest(OUT/name) == sha, 'Incomplete export: '+name
    return data
