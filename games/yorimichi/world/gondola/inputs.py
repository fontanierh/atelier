"""Narrow final world reads needed by the ropeway's owned ground queries."""
import hashlib
import json
import sys
from pathlib import Path


sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import export_digest

GROUND_BOUNDS = (390., 3550., 535., 4670.)
REPO = Path(__file__).resolve().parents[4]
MANIFEST = Path(__file__).resolve().parents[2] / 'assets/belmonte/source.json'
CODE = {name: REPO / name for name in (
    'games/yorimichi/world/gondola/inputs.py',
    'games/yorimichi/world/gondola/probe.py',
    'games/yorimichi/world/regions/belmonte/source.py',
    'games/yorimichi/export_digest.py',
    'platform/studio/atelier/gltf.py',
)}


def selected_ground(build):
    runtime=json.loads((build/'belmonte/runtime.json').read_text())
    manifest={row['name']:row for row in json.loads(MANIFEST.read_text())['meshes']}
    origin=[v/f for v,f in zip(runtime['origin_cm'],(100.,-100.,100.))]
    groups=[]
    for group in runtime['groups']:
        name=group['asset'].rsplit('/',1)[-1].split('.')[0]
        if name.startswith('SM_BM_BT_Terrain_') or name=='SM_BM_NorthApron':
            identity={'translation_cm':[0.,0.,0.], 'rotation_xyzw':[0.,0.,0.,1.], 'scale':[1.,1.,1.]}
            if group['transforms'] != [identity]:
                raise ValueError('Gondola terrain read requires the declared identity Belmonte placement')
            if name != 'SM_BM_NorthApron':
                bounds=manifest[name]['bounds_m']
                low=[bounds[0][i]+origin[i] for i in (0,1)]
                high=[bounds[1][i]+origin[i] for i in (0,1)]
                x0,y0,x1,y1=GROUND_BOUNDS
                if high[0]<x0 or low[0]>x1 or high[1]<y0 or low[1]>y1:
                    continue
            groups.append({key:group[key] for key in ('asset','transforms')})
    if not groups or not any(g['asset'].rsplit('/',1)[-1].split('.')[0]=='SM_BM_NorthApron' for g in groups):
        raise ValueError('Belmonte final terrain or apron is missing')
    return {'origin_cm':runtime['origin_cm'],'groups':groups}


def paths(build):
    build=Path(build)
    groups=selected_ground(build)['groups']
    return [build/'terrain/HD_Terrain/final.npz',build/'terrain/HD_NorthMountains/final.npz',
            build/'hidamari/assets/HD_NorthTrail.fbx',
            *(build/'belmonte/glb'/f"{g['asset'].rsplit('/',1)[-1].split('.')[0]}.glb" for g in groups)]


def snapshot(build):
    build=Path(build)
    return {'code':{name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in CODE.items()},
            'belmonte_ground':selected_ground(build),
            'files':{str(path.relative_to(build)):(export_digest.fbx(path.read_bytes()) if path.suffix=='.fbx' else hashlib.sha256(path.read_bytes()).hexdigest())
                     for path in paths(build)}}
