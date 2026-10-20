"""Shared, deterministic vegetation classification and canopy representation builder.

Unreal exports the built source vertices and their sampled linear material colours.
This kernel has no editor dependency: build and CI use exactly the same geometry.
Coordinates are Unreal centimetres. Sources and collision are never rewritten.
"""
from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path

VERSION = 1
ROOT = '/Game/FoliageSystem'
# Keep the authoring role codec independent of the geometry algorithm so changing
# canopy budgets does not invalidate every procedural world export.
import importlib.util
_roles_spec = importlib.util.spec_from_file_location('yorimichi_foliage_roles', Path(__file__).parent/'world/foliage_roles.py')
roles = importlib.util.module_from_spec(_roles_spec)
_roles_spec.loader.exec_module(roles)
WORDS, vegetation, material_vegetation, category = roles.WORDS, roles.vegetation, roles.material_vegetation, roles.category
SCREENS = (1., .24, .07, .018)
# Maximum leaf triangles retained per spatial crown, in addition to its closed core.
EDGE_BUDGETS = (160, 32, 0, 0)
CORE_GROUPS = (8, 4, 2, 1)
CELL_CM = 6400.


def asset_id(path: str) -> str:
    # A namespace is part of identity: two regions may legitimately use the same name.
    stem = re.sub('[^A-Za-z0-9_]', '_', path.rsplit('/', 1)[-1].split('.')[0])
    return stem + '_' + hashlib.sha256(path.encode()).hexdigest()[:16]


def package_inventory(content):
    root=Path(content)/'FoliageSystem'
    return {p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob('*')) if p.is_file() and p.suffix in ('.uasset','.uexp','.ubulk')}


def cache_records(previous, published, algorithm, packages):
    """A cached mesh is usable only with its complete certified material closure."""
    if (not packages or previous!=published or previous.get('algorithm')!=algorithm
            or previous.get('packages')!=packages):
        return {}
    return {row['source']:row for row in previous.get('assets',[])}


def sub(a, b):
    return tuple(x-y for x, y in zip(a, b))


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def normal(v):
    length = math.sqrt(dot(v, v))
    return tuple(x/length for x in v) if length > 1e-12 else (0., 0., 1.)


def bounds(points):
    return tuple(min(p[i] for p in points) for i in range(3)), tuple(max(p[i] for p in points) for i in range(3))


def groups(items, count, centre):
    """Stable spatial median cuts, never global RNG or source traversal-dependent clustering."""
    result = [list(items)]
    while len(result) < count:
        choices = [(max(hi[i]-lo[i] for i in range(3)), -n, n, lo, hi)
                   for n, group in enumerate(result) if len(group) > 1
                   for lo, hi in [bounds([centre(x) for x in group])]]
        if not choices:
            break
        _, _, n, lo, hi = max(choices)
        axis = max(range(3), key=lambda i: (hi[i]-lo[i], -i))
        ordered = sorted(result.pop(n), key=lambda x: (centre(x)[axis], centre(x)))
        half = len(ordered)//2
        result[n:n] = [ordered[:half], ordered[half:]]
    return result


def centroid(face, vertices):
    return tuple(sum(vertices[i]['p'][axis] for i in face['v'])/3 for axis in range(3))


def core(points, colour, slot):
    """Closed, outward-wound canopy lobe: 32 triangles, no alpha holes.

    The axis support bounds are kept exact. More lobes at close range preserve gaps
    between branches; the leaf fringe preserves fine silhouette detail.
    """
    lo, hi = bounds(points)
    c = tuple((a+b)/2 for a, b in zip(lo, hi))
    radii = tuple(max((b-a)/2, .25) for a, b in zip(lo, hi))
    # A subdivided octahedron has vertices on every axis and no coplanar double sides.
    directions = [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]
    triangles = [(0,2,4),(2,1,4),(1,3,4),(3,0,4),(2,0,5),(1,2,5),(3,1,5),(0,3,5)]
    edges = {}
    refined = []
    for a, b, c0 in triangles:
        mids = []
        for x, y in ((a,b),(b,c0),(c0,a)):
            edge = tuple(sorted((x,y)))
            if edge not in edges:
                edges[edge] = len(directions)
                directions.append(normal(tuple(directions[x][i]+directions[y][i] for i in range(3))))
            mids.append(edges[edge])
        ab, bc, ca = mids
        refined.extend(((a,ab,ca),(ab,b,bc),(ca,bc,c0),(ab,bc,ca)))
    triangles = refined
    vertices = []
    for d in directions:
        shade = .78+.22*max(d[2], 0)
        vertices.append(dict(p=[c[i]+d[i]*radii[i] for i in range(3)], n=list(normal(tuple(d[i]/radii[i] for i in range(3)))),
                             uv=[0.,0.], c=[min(1.,max(0.,v*shade)) for v in colour[:3]]+[colour[3]]))
    # MeshDescription's UE normal is cross(P2-P0,P1-P0), the reverse of
    # the usual right-handed mesh formula (StaticMeshOperations.cpp). Source
    # faces already use UE order; only our newly generated cores need reversal.
    return vertices, [dict(v=[t[0],t[2],t[1]], s=slot) for t in triangles]


def append_mesh(target, vertices, faces):
    offset = len(target['vertices'])
    target['vertices'].extend(vertices)
    target['faces'].extend(dict(v=[offset+i for i in face['v']], s=face['s']) for face in faces)


def validate_source(source):
    vertices, faces = source['vertices'], source['faces']
    if not vertices or not faces or not source['materials']:
        raise ValueError('Empty foliage source')
    for vertex in vertices:
        for key, size in (('p',3),('n',3),('uv',2),('c',4)):
            if len(vertex[key]) != size or not all(math.isfinite(v) for v in vertex[key]):
                raise ValueError('Invalid foliage vertex '+key)
        for key,size in (('sample',4),):
            if key in vertex and (len(vertex[key]) != size or not all(math.isfinite(v) for v in vertex[key])):
                raise ValueError('Invalid foliage vertex '+key)
        if 'uvs' in vertex and any(len(uv)!=2 or not all(math.isfinite(v) for v in uv) for uv in vertex['uvs']):
            raise ValueError('Invalid foliage UV channels')
    for face in faces:
        if (len(face['v']) != 3 or any(type(i) is not int or i < 0 or i >= len(vertices) for i in face['v'])
                or type(face['s']) is not int or not 0 <= face['s'] < len(source['materials'])):
            raise ValueError('Invalid foliage triangle')


def classified_faces(source):
    """One policy for imported material slots and the legacy vertex-palette adapter."""
    slots={i for i,m in enumerate(source['materials']) if m['foliage']}
    mode=source.get('classification','material')
    if mode not in ('material','palette','height','roles'):
        raise ValueError('Unknown foliage classification: '+mode)
    lo,hi=bounds([v['p'] for v in source['vertices']])
    canopy,rigid=[],[]
    for face in source['faces']:
        leaf=face.get('foliage',face['s'] in slots)
        if mode=='roles':
            values=[]
            for index in face['v']:
                channels=source['vertices'][index].get('uvs',[])
                if len(channels)<=roles.CHANNEL:
                    raise ValueError('Missing foliage face role channel')
                values.append(roles.face_role(channels[roles.CHANNEL]))
            if len(set(values))!=1:
                raise ValueError('Inconsistent foliage face roles')
            leaf=values[0]>0
            face=dict(face,thin=values[0]==2)
        elif mode=='palette':
            encoded=[sum(source['vertices'][i]['c'][c] for i in face['v'])/3 for c in range(3)]
            # The FBX palette and M_Arcade both use encoded sRGB attributes.
            r,g,b=[v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in encoded]
            leaf=r>.4 and g>.08 and b<.07 and r>g*1.2
        elif mode=='height':
            leaf=centroid(face,source['vertices'])[2]>lo[2]+(hi[2]-lo[2])*.4
        (canopy if leaf else rigid).append(face)
    return canopy,rigid


def build(source):
    """Make bounded canopy cores/fringes; retain non-vegetation sections byte-for-value.

    Mixed meshes retain all rigid triangles at every level. Open fronds and small
    groundcover retain sampled original surfaces instead of being inflated into blobs.
    The disabled renderer uses the separately retained source mesh, never these LODs.
    """
    validate_source(source)
    vertices, faces = source['vertices'], source['faces']
    if source.get('classification')=='authored':
        originals=[source,*source.get('rigid_lods',[])]
        for lod in originals:
            validate_source(lod)
            if len(lod['faces'])>roles.AUTHORED_BUDGET:
                raise ValueError('Authored foliage prop exceeds triangle budget: '+source['path'])
            for vertex in lod['vertices']:
                channels=vertex.get('uvs',[])
                if len(channels)<=roles.CHANNEL or channels[roles.CHANNEL] not in ([3.,roles.MARKER],[3.,1-roles.MARKER]):
                    raise ValueError('Missing authored foliage role')
        levels=[{key:originals[min(i,len(originals)-1)][key] for key in ('vertices','faces')} for i in range(4)]
        points=[v['p'] for v in vertices]
        pv,pf=core(points,[1.,1.,1.,0.],len(source['materials'])+1)
        return dict(version=VERSION,source=source['path'],kind=source['kind'],screens=list(SCREENS),
                    rigid_triangles=0,source_triangles=len(faces),levels=levels,shadow=levels[-1],
                    patch=dict(vertices=pv,faces=pf),canopy_bounds=bounds(points))
    canopy,rigid=classified_faces(source)
    if not canopy:
        raise ValueError('Vegetation source has no classified foliage surfaces: '+source['path'])
    # Spatial buckets keep separated trees in a merged regional mesh separated.
    crowns = {}
    solid_count = 0
    for f in canopy:
        material = source['materials'][f['s']]
        thin = (f.get('thin',False) or source['kind'] == 'groundcover' or category(material['path']) == 'groundcover'
                or any(word in material['path'].lower() for word in ('frond', 'palm_')))
        solid_count += not thin
        p = centroid(f, vertices)
        # Palette slots do not multiply the crown budget. Thin surfaces retain
        # their own materials; volume colours are sampled per spatial lobe.
        key = (thin, f['s'] if thin else -1, *(math.floor(x/800.) for x in p))
        crowns.setdefault(key, []).append(f)
    source_kind = source['kind']
    levels = []
    for level, (count, fringe) in enumerate(zip(CORE_GROUPS, EDGE_BUDGETS)):
        result = dict(vertices=[], faces=[])
        if level and source.get('rigid_lods'):
            lod = source['rigid_lods'][level-1]
            validate_source(lod)
            _,body=classified_faces(lod)
            append_mesh(result,lod['vertices'],body)
            selected = []
        else:
            selected = list(rigid)
        # Copy only referenced original vertices; indices are rebuilt without changing attributes.
        for key, crown in sorted(crowns.items()):
            is_thin = key[0]
            crown_count = count if is_thin else max(1, round(count*len(crown)/max(1,solid_count)))
            crown_fringe = round(fringe*len(crown)/max(1,solid_count))
            # A source's slots and spatial pieces share one budget. Already
            # cheap groups keep their exact surfaces rather than inflated blobs.
            if not is_thin and len(crown) <= crown_count*32 + crown_fringe:
                selected.extend(crown)
                continue
            pieces = groups(crown, crown_count, lambda f: centroid(f, vertices))
            for piece in pieces:
                points = [vertices[i]['p'] for f in piece for i in f['v']]
                lo, hi = bounds(points)
                if is_thin:
                    budget = max(1, (48, 16, 6, 2)[level])
                    # Even spatial distribution preserves long palm fronds and groundcover patches.
                    ordered = sorted(piece, key=lambda f: centroid(f, vertices))
                    keep = min(len(ordered), budget)
                    selected.extend(ordered[round(i*(len(ordered)-1)/max(1,keep-1))]
                                    for i in range(keep))
                    continue
                colour = [sum(vertices[i].get('sample',vertices[i]['c'])[c]
                              for f in piece for i in f['v'])/(len(piece)*3) for c in range(4)]
                # Solid cores get their own material; source leaf masks/lighting remain on the fringe.
                core_slot = len(source['materials']) + (0 if level == 0 else 1)
                cv, cf = core(points, colour, core_slot)
                append_mesh(result, cv, cf)
                if fringe:
                    centre = tuple((a+b)/2 for a,b in zip(lo,hi))
                    radius = tuple(max((b-a)/2, .25) for a,b in zip(lo,hi))
                    def score(f):
                        p = centroid(f,vertices)
                        return sum(((p[i]-centre[i])/radius[i])**2 for i in range(3))
                    # Rank the outside, not random interior leaves; stable tie breaks preserve determinism.
                    selected.extend(sorted(piece,key=lambda f:(-score(f),tuple(f['v'])))[:crown_fringe//max(1,len(pieces))])
        remap = {}
        for f in selected:
            indices = []
            for i in f['v']:
                if i not in remap:
                    remap[i] = len(result['vertices'])
                    result['vertices'].append(vertices[i])
                indices.append(remap[i])
            result['faces'].append(dict(v=indices,s=f['s']))
        levels.append(result)
    result = dict(version=VERSION, source=source['path'], kind=source_kind, screens=list(SCREENS),
                  rigid_triangles=len(rigid), source_triangles=len(faces), levels=levels)
    result['shadow'] = levels[-1]
    if len(canopy) <= 64:
        # Tiny authored flowers/leaves already fit the close budget. Registration
        # still certifies them; never inflate a two-triangle leaf into a solid.
        cheap = [source, *source.get('rigid_lods', [])]
        for i in range(len(result['levels'])):
            original = cheap[min(i,len(cheap)-1)]
            result['levels'][i] = {key:original[key] for key in ('vertices','faces')}
        result['shadow'] = result['levels'][-1]
    if source.get('far_proxy'):
        validate_source(source['far_proxy'])
        result['levels'][-1] = {key:source['far_proxy'][key] for key in ('vertices','faces')}
    points = [vertices[i]['p'] for f in canopy for i in f['v']]
    colour = [sum(vertices[i].get('sample',vertices[i]['c'])[c] for f in canopy for i in f['v'])/(len(canopy)*3)
              for c in range(4)]
    pv, pf = core(points, colour, len(source['materials'])+1)
    result['patch'] = dict(vertices=pv, faces=pf)
    result['canopy_bounds'] = bounds(points)
    return result
