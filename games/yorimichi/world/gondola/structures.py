"""Final Belmonte structure geometry, kept separate from terrain ownership.

Selection and freshness checks use only the standard library so the importer
can refuse stale evidence before loading Unreal or geometry libraries.
"""
import hashlib
import itertools
import json
import math
from pathlib import Path
import re
import struct

from atelier.gltf import glb_parts

# Includes both L2 station loops, complete station/access footprints and the
# intervening corridor. Queries outside this footprint must refuse.
BOUNDS = (340., 2700., 560., 4680.)
REPO = Path(__file__).resolve().parents[4]
CODE = ('games/yorimichi/world/gondola/structures.py',
        'games/yorimichi/world/gondola/structure_probe.py',
        'games/yorimichi/world/regions/belmonte/source.py',
        'games/yorimichi/unreal/Scripts/import_belmonte.py',
        'games/yorimichi/world/gondola/__init__.py',
        'platform/studio/atelier/gltf.py','platform/studio/atelier/__init__.py',
        'platform/studio/atelier/paths.py')


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
    doc,binary = glb_parts(path.read_bytes())
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


def placed_bounds(bounds, matrix, offset):
    points = [[sum(matrix[i][j]*p[j] for j in range(3))+offset[i] for i in range(3)]
              for p in itertools.product(*zip(*bounds))]
    return [[min(p[i] for p in points) for i in range(3)],
            [max(p[i] for p in points) for i in range(3)]]


def selected(build):
    """@cc [owner:fontanierh,label:correctness] complete-structure-piece-geometry
    Every rendered child of a collidable logical structure MUST remain in visual clearance
    geometry even when a different child owns its whole authored collision hull. Collision
    geometry MUST enter only through actual collision-enabled components; it MUST NOT be
    duplicated once per visual child. Legacy groups without parent metadata keep their
    existing collision ownership. Inconsistent or nonboolean ownership MUST refuse.
    """
    build = Path(build)
    runtime = json.loads((build/'belmonte/runtime.json').read_text())
    report = json.loads((build/'belmonte/build-report.json').read_text())
    entries = {row['name']:row for row in report['meshes']}
    bounds_cache = {}
    groups = []
    for group in runtime['groups']:
        if type(group.get('plant')) is not bool or type(group.get('collision')) is not bool:
            raise ValueError('Belmonte structure roster lacks explicit collision/plant ownership')
        parent_collision = group.get('parent_collision', group['collision'])
        if type(parent_collision) is not bool or (group['collision'] and not parent_collision):
            raise ValueError('Belmonte structure parent collision ownership is inconsistent')
        # Vegetation has its own declared runtime clearing contract. Terrain
        # remains in the separately owned ground products.
        if group['plant'] or not parent_collision:
            continue
        name = group['asset'].rsplit('/',1)[-1].split('.')[0]
        if name.startswith('SM_BM_BT_Terrain_') or re.fullmatch(r'SM_BM_NorthApron(?:_Piece[0-3]+)?', name):
            continue
        if name not in entries:
            raise ValueError('Missing final Belmonte structure metadata: '+name)
        entry = entries[name]
        geometry = {'visual':'belmonte/glb/'+Path(entry['path']).name}
        if group['collision']:
            geometry['collision'] = ('belmonte/glb/'+Path(entry['collision']['path']).name
                                     if entry.get('collision') else geometry['visual'])
        for relative in set(geometry.values()):
            if relative not in bounds_cache:
                bounds_cache[relative] = mesh_bounds(build/relative)
        transforms = []
        if not group['transforms']:
            raise ValueError('Empty Belmonte structure instance roster')
        for transform in group['transforms']:
            matrix,offset = affine(transform,runtime['origin_cm'])
            boxes = [placed_bounds(bounds_cache[path],matrix,offset) for path in set(geometry.values())]
            if any(hi[0] >= BOUNDS[0] and lo[0] <= BOUNDS[2] and
                   hi[1] >= BOUNDS[1] and lo[1] <= BOUNDS[3] for lo,hi in boxes):
                transforms.append(transform)
        if transforms:
            groups.append({'asset':group['asset'],'geometry':geometry,'transforms':transforms})
    groups.sort(key=lambda row:json.dumps(row,sort_keys=True))
    return {'bounds_m':list(BOUNDS),'origin_cm':runtime['origin_cm'],'groups':groups}


def paths(build):
    return [Path(build)/name for name in sorted({name for group in selected(build)['groups']
                                               for name in group['geometry'].values()})]


def inputs(build):
    roster = selected(build)
    files = sorted({name for group in roster['groups'] for name in group['geometry'].values()})
    return {'selection':roster,
            'code':{name:hashlib.sha256((REPO/name).read_bytes()).hexdigest() for name in CODE},
            'files':{name:hashlib.sha256((Path(build)/name).read_bytes()).hexdigest() for name in files}}


def validate(build):
    folder = Path(build)/'gondola/world'
    report = json.loads((folder/'structures.json').read_text())
    if (report.get('inputs') != inputs(build) or
            report.get('output_sha256') != hashlib.sha256((folder/'structures.npz').read_bytes()).hexdigest()):
        raise ValueError('Gondola final structure geometry is stale')
    return report


