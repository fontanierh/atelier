"""Final Belmonte structure geometry, kept separate from terrain ownership.

Selection and freshness checks use only the standard library so the importer
can refuse stale evidence before loading Unreal or geometry libraries.
"""
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import re
import struct

from atelier.gltf import glb_parts
from atelier.export_manifest import real_directory

# Includes both L2 station loops, complete station/access footprints and the
# intervening corridor. Queries outside this footprint must refuse.
BOUNDS = (340., 2700., 560., 4680.)
REPO = Path(__file__).resolve().parents[4]
CODE = ('games/yorimichi/world/gondola/structures.py',
        'games/yorimichi/world/gondola/structure_probe.py','games/yorimichi/world/gondola/source_inputs.py',
        'games/yorimichi/world/regions/belmonte/source.py','games/yorimichi/world/regions/belmonte/runtime_groups.py',
        'games/yorimichi/world/gondola/__init__.py','platform/studio/atelier/gltf.py',
        'platform/studio/atelier/encoded_glb.py','platform/studio/atelier/gltf_partition.py','platform/studio/atelier/mesh_partition.py',
        'platform/studio/atelier/__init__.py','platform/studio/atelier/paths.py',
        'platform/studio/atelier/export_manifest.py','platform/studio/atelier/model_files.py','platform/studio/atelier/atomic_files.py')


def affine(transform, origin):
    """Native instance transform converted to world Z-up metres."""
    translation = transform['translation_cm']
    scale = transform['scale']
    quaternion = transform['rotation_xyzw']
    if (len(translation) != 3 or len(scale) != 3 or len(quaternion) != 4 or len(origin) != 3 or
            not all(math.isfinite(v) for v in [*translation, *scale, *quaternion, *origin]) or
            any(abs(v) < 1e-12 for v in scale) or
            abs(sum(v*v for v in quaternion)-1.) > 1e-6):
        raise ValueError('Unsupported Belmonte structure instance transform')
    x,y,z,w = quaternion
    rotation = [[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]]
    reflection = (1., -1., 1.)
    matrix = [[reflection[i]*rotation[i][j]*scale[j]*reflection[j] for j in range(3)] for i in range(3)]
    offset = [(origin[i]+translation[i])*reflection[i]/100. for i in range(3)]
    return matrix, offset


def mesh_bounds(path):
    """Read actual POSITION bytes, including collision hulls with no bounds metadata."""
    return mesh_bounds_data(path.read_bytes())


def mesh_bounds_data(data):
    doc,binary = glb_parts(data)
    low,high = [math.inf]*3, [-math.inf]*3
    count = 0
    for node in doc['nodes']:
        if any(key in node for key in ('matrix','translation','rotation','scale')):
            raise ValueError('Belmonte source decoder requires baked node transforms')
        if 'mesh' not in node:
            continue
        for primitive in doc['meshes'][node['mesh']]['primitives']:
            accessor = doc['accessors'][primitive['attributes']['POSITION']]
            if accessor['componentType'] != 5126 or accessor['type'] != 'VEC3' or 'sparse' in accessor:
                raise ValueError('Unsupported Belmonte structure positions')
            view = doc['bufferViews'][accessor['bufferView']]
            start = view.get('byteOffset',0)+accessor.get('byteOffset',0)
            stride = view.get('byteStride',12)
            if stride < 12:
                raise ValueError('Invalid Belmonte structure position stride')
            for index in range(accessor['count']):
                a,b,c = struct.unpack_from('<3f',binary,start+index*stride)
                point = (a,-c,b)  # regions.belmonte.source.FRAME
                if not all(math.isfinite(v) for v in point):
                    raise ValueError('Nonfinite Belmonte structure vertex')
                for i,value in enumerate(point):
                    low[i],high[i] = min(low[i],value),max(high[i],value)
                count += 1
    if not count:
        raise ValueError('Empty Belmonte structure geometry')
    return low,high


BOUNDS_CACHE = '.state/gondola-mesh-bounds.json'
BOUNDS_SCHEMA = 1  # Bump when mesh_bounds or the FRAME mapping changes.
_bounds_memo = {}


def cached_bounds(build, relative):
    """mesh_bounds, remembered per file identity (size, mtime, inode) across runs.

    Planning decodes every structure GLB to choose the deferred inputs; an unchanged file keeps
    its observed bounds. The selected files are still hashed in full as the step's inputs.
    """
    build = Path(build)
    path = build/relative
    info = path.stat()
    identity = [info.st_size, info.st_mtime_ns, info.st_ino]
    store = _bounds_memo.get(str(build))
    if store is None:
        try:
            saved = json.loads((build/BOUNDS_CACHE).read_text())
            store = saved['entries'] if saved.get('schema') == BOUNDS_SCHEMA else {}
        except (OSError, ValueError, KeyError, TypeError):
            store = {}
        _bounds_memo[str(build)] = store
    hit = store.get(relative)
    if hit and hit[0] == identity:
        return hit[1], hit[2]
    low, high = mesh_bounds(path)
    store[relative] = [identity, low, high]
    target = build/BOUNDS_CACHE
    if target.parent.is_dir():  # Never create output folders; a missing cache only costs time.
        try:
            temporary = target.with_name(target.name + '.%d.tmp' % os.getpid())
            temporary.write_text(json.dumps({'schema': BOUNDS_SCHEMA, 'entries': store}, sort_keys=True))
            temporary.replace(target)
        except OSError:
            pass
    return low, high


def placed_bounds(bounds, matrix, offset):
    points = [[sum(matrix[i][j]*p[j] for j in range(3))+offset[i] for i in range(3)]
              for p in itertools.product(*zip(*bounds))]
    return [[min(p[i] for p in points) for i in range(3)],
            [max(p[i] for p in points) for i in range(3)]]


def selected(build):
    """@cc [owner:fontanierh,label:correctness] complete-structure-piece-geometry
    Query membership MUST preserve the original per-child bounds selection, order
    and whole-hull ownership using committed source packets before render exports.
    Every selected visual and collision face MUST occur once per selected instance.
    Explicit plant/collision booleans, paths and transforms MUST refuse inconsistent
    ownership; selecting a child MUST NOT broaden its query to sibling geometry.
    """
    path=Path(build)/'gondola/world/structures-sources.json'
    real_directory(path.parent)
    if path.is_symlink() or not path.is_file():raise ValueError('Missing pre-export structure source projection')
    value=json.loads(path.read_text())
    if (set(value)!={'schema','owner','bounds_m','origin_cm','groups','sources'} or value['schema']!=1
            or value['owner']!='GondolaStructureSources' or value['bounds_m']!=list(BOUNDS)
            or not isinstance(value['groups'],list)):
        raise ValueError('Incomplete pre-export structure source selection')
    origin=value['origin_cm']
    if (not isinstance(origin,list) or len(origin)!=3 or
            any(type(v) not in (int,float) or not math.isfinite(v) for v in origin)):
        raise ValueError('Invalid source structure origin')
    for row in value['groups']:
        if (set(row)!={'asset','geometry','transforms','plant','collision','parent_collision'}
                or row['plant'] is not False or type(row['collision']) is not bool or row['parent_collision'] is not True
                or not isinstance(row['transforms'],list) or not row['transforms']
                or set(row['geometry'])!=({'visual','collision'} if row['collision'] else {'visual'})):
            raise ValueError('Incomplete logical source parent collision ownership')
        key=row['asset'].rsplit('/',1)[-1].split('.')[0]
        if not re.fullmatch(r'SM_BM_[A-Za-z0-9_]+',key):raise ValueError('Foreign source structure owner')
        parents=set()
        for role,relative in row['geometry'].items():
            parts=Path(relative).parts
            if (len(parts)!=4 or parts[:2]!=('planned_exports','belmonte_models') or
                    not re.fullmatch(r'SM_BM_[A-Za-z0-9_]+',parts[2]) or
                    parts[3]!=(key+'.mesh') and not (role=='collision' and parts[3]==parts[2]+'_Collision.mesh') or
                    not (key==parts[2] or key.startswith(parts[2]+'_'))):
                raise ValueError('Foreign pre-export source structure path')
            parents.add(parts[2])
        if len(parents)!=1:raise ValueError('Mismatched logical whole collision owner')
        for transform in row['transforms']:affine(transform,origin)
    expected={name for row in value['groups'] for name in row['geometry'].values()}
    if (not isinstance(value['sources'],dict) or set(value['sources'])!=expected or
            any(not isinstance(digest,str) or not re.fullmatch('[0-9a-f]{64}',digest) for digest in value['sources'].values())):
        raise ValueError('Incomplete committed structure source identities')
    return dict(bounds_m=value['bounds_m'],origin_cm=origin,groups=value['groups'],sources=value['sources'])


def paths(build):
    return [Path(build)/'gondola/world/structures-sources.json',
            *(Path(build)/name for name in sorted({name for group in selected(build)['groups'] for name in group['geometry'].values()}))]


def inputs(build):
    roster=selected(build)
    files=sorted({name for group in roster['groups'] for name in group['geometry'].values()})
    for name in files:
        path=Path(build)/name;real_directory(path.parent)
        if path.is_symlink() or not path.is_file():raise ValueError('Committed structure query source must be regular')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=roster['sources'][name]:raise ValueError('Committed structure source differs from its definition')
    return dict(selection=roster,code={name:hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in CODE},
                files={name:hashlib.sha256((Path(build)/name).read_bytes()).hexdigest() for name in files})


def validate(build):
    folder = Path(build)/'gondola/world'
    report = json.loads((folder/'structures.json').read_text())
    if (report.get('inputs') != inputs(build) or
            report.get('output_sha256') != hashlib.sha256((folder/'structures.npz').read_bytes()).hexdigest()):
        raise ValueError('Gondola final structure geometry is stale')
    return report


