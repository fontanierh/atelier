"""Lossless pre-export geometry for cuts and queries, independent of mesh exports.

Ordered bounded packets retain original vertex IDs, including unused vertices.
This is a construction input, deliberately rejected by the final export planner.
"""
import json

import numpy as np

from atelier import mesh_ir
from atelier.export_manifest import TRIANGLE_LIMIT, name, real_directory, sha
from mesh_pieces import subset
import region_plan_files


def groups(counts):
    """Consecutive complete faces preserve the source topology and ordering."""
    first, total = 0, 0
    for index, count in enumerate(counts):
        triangles = int(count) - 2
        if not 0 < triangles <= TRIANGLE_LIMIT:
            raise ValueError('Source polygon cannot fit a complete bounded packet')
        if total + triangles > TRIANGLE_LIMIT:
            yield tuple(range(first, index))
            first, total = index, 0
        total += triangles
    if total:
        yield tuple(range(first, len(counts)))


def write(root, source, *, owner, slots, matrix, collisions=()):
    """@cc [owner:fontanierh,label:correctness] lossless-pre-export-source-data
    Source data MUST preserve original vertex/face order, connectivity, every corner
    channel, material/selection roles and authored transform/collision. It MUST NOT
    read a generated FBX/GLB or masquerade as a final atomic export plan. Packet
    limits remain the unchanged atomic format limits. Complete current membership
    MUST validate before retiring this owner's superseded data packets.
    """
    owner, root = name(owner), real_directory(root)
    members = list(groups(source['counts']))
    if not members:
        raise ValueError('Source geometry must contain complete faces')
    starts = np.concatenate(([0], np.cumsum(source['counts'], dtype=np.int64)[:-1]))
    if not np.array_equal(starts, source['starts']):
        raise ValueError('Source face corners must be contiguous and ordered')
    used = np.unique(source['vertex_indices'])
    if np.any(used < 0) or np.any(used >= len(source['positions'])):
        raise ValueError('Source geometry has invalid vertex references')
    unused = np.setdiff1d(np.arange(len(source['positions'])), used)
    # Validate every packet in memory before the first destination mutation.
    packets = []
    for index, faces in enumerate(members):
        piece = subset(source, faces)
        ids = piece['used']
        if index == 0 and len(unused):
            piece['positions'] = np.concatenate((piece['positions'], source['positions'][unused]))
            piece['colours'] = [(label, domain, kind,
                np.concatenate((values, original[unused])) if domain == 'POINT' else values)
                for (label, domain, kind, values), (_, _, _, original)
                in zip(piece['colours'], source['colours'])]
            ids = np.concatenate((ids, unused))
        key = f'{owner}_Source{index:04d}'
        payload = mesh_ir.encode(piece, key=key, slots=slots, matrix=matrix, options={},
                                 collisions=collisions if index == 0 else ())
        packets.append((key, ids, payload, len(faces)))
    region_plan_files.begin(root, owner, [key + '.npz' for key, _, _, _ in packets])
    rows = []
    for key, ids, payload, polygons in packets:
        path = root / (key + '.npz')
        mesh_ir.write(path, payload)
        rows.append(dict(payload=path.name, vertices=ids.tolist(), polygons=polygons, sha256=sha(path)))
    value = dict(schema=1, kind='source_geometry', complete=True, parent=owner,
                 vertex_count=len(source['positions']), polygon_count=len(source['counts']),
                 pieces=rows)
    read(root, value=value)
    region_plan_files.finish(root, value)
    return value


def read(root, *, owner=None, value=None):
    """Reconstitute source topology; verify full membership and shared vertex bytes."""
    root = real_directory(root)
    if value is None:
        value = json.loads((root / region_plan_files.PLAN).read_text())
        if region_plan_files.files(root) != {region_plan_files.PLAN, *(r['payload'] for r in value['pieces'])}:
            raise ValueError('Incomplete or foreign source geometry membership')
    if (set(value) != {'schema', 'kind', 'complete', 'parent', 'vertex_count', 'polygon_count', 'pieces'}
            or value['schema'] != 1 or value['kind'] != 'source_geometry' or value['complete'] is not True
            or type(value['vertex_count']) is not int or not 0 < value['vertex_count'] <= 16_000_000
            or type(value['polygon_count']) is not int or not 0 < value['polygon_count'] <= 16_000_000
            or not isinstance(value['pieces'], list) or not value['pieces'] or len(value['pieces']) > 4096):
        raise ValueError('Invalid source geometry inventory')
    parent = name(value['parent'])
    if owner is not None and parent != name(owner):
        raise ValueError('Source geometry belongs to another owner')
    count = value['vertex_count']
    positions, seen = np.empty((count, 3), dtype='<f4'), np.zeros(count, dtype=np.bool_)
    shared, result, point_colours = None, None, {}
    normals, materials, smooth, uvs, corner_colours = [], [], [], [], []
    faces = []
    for index, row in enumerate(value['pieces']):
        key = f'{parent}_Source{index:04d}'
        if (set(row) != {'payload', 'vertices', 'polygons', 'sha256'} or row['payload'] != key + '.npz'
                or not isinstance(row['vertices'], list) or not row['vertices']
                or any(type(i) is not int or not 0 <= i < count for i in row['vertices'])
                or len(set(row['vertices'])) != len(row['vertices'])):
            raise ValueError('Invalid source geometry vertex ownership')
        path = root / row['payload']
        if path.is_symlink() or not path.is_file() or sha(path) != row['sha256']:
            raise ValueError('Source geometry packet is missing or changed')
        meta, piece = mesh_ir.decode(path.read_bytes())
        signature = {k: v for k, v in meta.items() if k not in ('asset', 'collisions')}
        if (meta['asset'] != key or meta['options'] != {} or (index and meta['collisions'])
                or type(row['polygons']) is not int or row['polygons'] != len(piece['faces'])
                or len(row['vertices']) != len(piece['positions'])
                or (shared is not None and signature != shared)):
            raise ValueError('Source geometry packet identity or channels differ')
        ids = np.asarray(row['vertices'], dtype=np.int64)
        overlap = seen[ids]
        if positions[ids[overlap]].tobytes() != piece['positions'][overlap].tobytes():
            raise ValueError('Shared source vertex positions differ')
        if result is None:
            shared = signature
            result = dict(matrix=meta['matrix'], slots=meta['slots'], selection=meta['selection'],
                          collisions=meta['collisions'])
            uvs = [(label, []) for label, _ in piece['uvs']]
            corner_colours = [(label, domain, kind, []) for label, domain, kind, _ in piece['colours']
                              if domain == 'CORNER']
            point_colours = {label: (kind, np.empty((count, 4), dtype='<f4'))
                             for label, domain, kind, _ in piece['colours'] if domain == 'POINT'}
        for label, domain, _, values in piece['colours']:
            if domain == 'POINT':
                target = point_colours[label][1]
                if target[ids[overlap]].tobytes() != values[overlap].tobytes():
                    raise ValueError('Shared source vertex colours differ')
                target[ids] = values
        positions[ids] = piece['positions']; seen[ids] = True
        faces.extend(ids[np.asarray(face)].tolist() for face in piece['faces'])
        normals.append(piece['normals']); materials.append(piece['materials']); smooth.append(piece['smooth'])
        for (_, chunks), (_, values) in zip(uvs, piece['uvs']):
            chunks.append(values)
        for (_, _, _, chunks), (_, _, _, values) in zip(corner_colours,
                [entry for entry in piece['colours'] if entry[1] == 'CORNER']):
            chunks.append(values)
    if not seen.all() or len(faces) != value['polygon_count']:
        raise ValueError('Source geometry topology is incomplete')
    colours = {label: (label, 'POINT', kind, values) for label, (kind, values) in point_colours.items()}
    colours.update({label: (label, domain, kind, np.concatenate(chunks))
                    for label, domain, kind, chunks in corner_colours})
    result.update(positions=positions, faces=faces, normals=np.concatenate(normals),
                  materials=np.concatenate(materials), smooth=np.concatenate(smooth),
                  uvs=[(label, np.concatenate(chunks)) for label, chunks in uvs],
                  colours=[colours[label] for label, _, _, _ in shared['colours']],
                  triangles=sum(len(face) - 2 for face in faces))
    return result
