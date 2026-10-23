"""Narrow final source/query reads needed by the ropeway's owned ground."""
import hashlib
import json
import math
from pathlib import Path
from atelier.export_manifest import real_directory
import re

GROUND_BOUNDS = (340.,3550.,535.,4670.)
REPO = Path(__file__).resolve().parents[4]
CODE = {name:REPO / name for name in (
    'games/yorimichi/world/gondola/inputs.py','games/yorimichi/world/gondola/probe.py',
    'games/yorimichi/world/gondola/source_inputs.py','games/yorimichi/world/region_query.py',
    'games/yorimichi/world/gondola/query_frames.py','games/yorimichi/assets/vehicles/gondola/fbx-query-frame.json',
    'games/yorimichi/world/regions/belmonte/source.py','games/yorimichi/world/regions/belmonte/surface_data.py',
    'games/yorimichi/world/gondola/__init__.py','platform/studio/atelier/__init__.py',
    'platform/studio/atelier/paths.py','platform/studio/atelier/gltf.py','platform/studio/atelier/export_manifest.py',
    'platform/studio/atelier/model_files.py','platform/studio/atelier/atomic_files.py')}


def selected_ground(build):
    """@cc [owner:fontanierh,label:correctness] logical-final-ground-selection
    Selection MUST consume explicit final source/query products before render exports.
    Only complete declared valley/apron sources and the final North Trail may enter
    the query. No legacy whole FBX/GLB path or natural-stage fallback is permitted.
    """
    path=Path(build) / 'gondola/world/ground-sources.json'
    real_directory(path.parent)
    if path.is_symlink() or not path.is_file():raise ValueError('Missing final ground source projection')
    value=json.loads(path.read_text())
    if (set(value)!={'schema','owner','origin_cm','groups'} or value['schema']!=1
            or value['owner']!='GondolaGroundSources' or not isinstance(value['groups'],list)):
        raise ValueError('Incomplete final ground source projection')
    origin=value['origin_cm']
    if (not isinstance(origin,list) or len(origin)!=3 or
            any(type(v) not in (int,float) or not math.isfinite(v) for v in origin)):
        raise ValueError('Invalid final ground source frame')
    seen=set()
    for row in value['groups']:
        if (set(row)!={'name','path'} or not re.fullmatch(r'SM_BM_(?:BT_Terrain_[A-Za-z0-9_]+|NorthApron)',row['name'])
                or row['name'].casefold() in seen or row['path']!='belmonte-source-data/'+row['name']+'.surface'):
            raise ValueError('Invalid final ground source member')
        seen.add(row['name'].casefold())
    if len(seen)<2 or 'sm_bm_northapron' not in seen:raise ValueError('Incomplete valley/apron final source coverage')
    return dict(origin_cm=origin,groups=value['groups'])


def geometry_paths(build,ground):
    build=Path(build)
    return [build / 'terrain/HD_Terrain/final.npz',build / 'terrain/HD_NorthMountains/final.npz',
            build / 'hidamari/query-data/HD_NorthTrail.npz',*(build / row['path'] for row in ground['groups'])]


def paths(build):
    build=Path(build)
    return [build / 'gondola/world/ground-sources.json',*geometry_paths(build,selected_ground(build))]


def snapshot(build):
    build=Path(build);ground=selected_ground(build)
    for path in geometry_paths(build,ground):
        real_directory(path.parent)
        if path.is_symlink() or not path.is_file():raise ValueError('Final query input must be regular')
    return dict(code={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in CODE.items()},
                belmonte_ground=ground,files={str(path.relative_to(build)):hashlib.sha256(path.read_bytes()).hexdigest()
                                           for path in geometry_paths(build,ground)})
