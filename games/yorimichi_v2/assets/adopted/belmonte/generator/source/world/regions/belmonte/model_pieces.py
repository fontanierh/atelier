"""Bound committed model imports while retaining authored pivots, slots and collision ownership."""
import hashlib
import math
import re

from atelier.gltf import glb_parts
from atelier.gltf_partition import split


LIMIT = 32768


def planned(entry, payload, *, triangle_limit=LIMIT):
    """@cc [owner:fontanierh,label:correctness] belmonte-bounded-model-policy
    Every committed model triangle MUST remain in exactly one bounded rendered piece.
    Pivots/transforms, source material-slot indices and parent cull/shadow policy MUST
    survive. An authored whole-model collision hull MUST belong to exactly one piece;
    other pieces MUST disable component collision. Models without a hull retain collision
    on every piece. Small models MUST retain their names and exact GLB bytes. Generated
    terrain/query surfaces are a separate producer and MUST NOT be silently renamed here.
    """
    if hashlib.sha256(payload).hexdigest() != entry['sha256']:
        raise ValueError('Prepared model differs from its declared source')
    doc, _ = glb_parts(payload)
    slots = [int(material['name'].split('_')[1]) for material in doc['materials']]
    counts = [doc['accessors'][primitive['indices']]['count']
              for mesh in doc['meshes'] for primitive in mesh['primitives']]
    if any(count % 3 for count in counts) or sum(counts)//3 != entry['triangles']:
        raise ValueError('Model triangle declaration differs from its GLB')
    if entry['triangles'] <= triangle_limit:
        return [(entry, slots, True, payload)]
    if entry['name'].startswith(('SM_BM_BT_Terrain_', 'SM_BM_North')):
        raise ValueError('Oversized query terrain requires its own published surface/piece boundary')
    if not re.fullmatch(r'SM_BM_[A-Za-z0-9_]+', entry['name']):
        raise ValueError('Invalid generated model owner name')
    low, high = entry['bounds_m']
    bounds = tuple(math.floor(low[i]/128)*128 for i in range(2))
    bounds += tuple(max(bounds[i]+128, math.ceil(high[i]/128)*128) for i in range(2))
    parts = split(payload, bounds, triangle_limit=triangle_limit)
    if sum(part['triangles'] for part in parts) != entry['triangles']:
        raise ValueError('Partitioned model differs from its declared triangle count')
    names = [entry['name']+'_Piece'+part['suffix'] for part in parts]
    result = []
    hull = isinstance(entry.get('collision'), dict)
    for index, (part, name) in enumerate(zip(parts, names)):
        current = dict(entry, name=name, path='glb/'+name+'.glb',
                       sha256=hashlib.sha256(part['data']).hexdigest(), triangles=part['triangles'],
                       bounds_m=[list(row) for row in part['bounds']], parent_bounds_m=entry['bounds_m'],
                       parent_material_slots=slots)
        if hull and index:
            del current['collision']
        result.append((current, [slots[i] for i in part['materials']], not hull or index == 0,part['data']))
    return result


def prepare(entry, path, *, triangle_limit=LIMIT):
    """Compatibility file adapter over the same byte-preserving source planner."""
    rows=planned(entry,path.read_bytes(),triangle_limit=triangle_limit)
    destinations=[path.with_name(row['name']+'.glb') for row,_,_,_ in rows]
    if any(candidate.is_symlink() for destination in destinations
           for candidate in (destination,*destination.parents)):
        raise ValueError('Linked generated model destination')
    for destination,(_,_,_,data) in zip(destinations,rows):
        if destination!=path:destination.write_bytes(data)
    return [(row,slots,collides) for row,slots,collides,_ in rows]
