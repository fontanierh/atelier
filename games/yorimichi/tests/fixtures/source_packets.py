"""Pure original-source packet observation; importing it never loads region constructors."""
import hashlib
import numpy as np
from atelier import mesh_ir
from atelier.export_manifest import sha
from mesh_pieces import capture, subset


def captured(obj):
    data = capture(obj.data)
    data['slots'] = [material.name for material in data['slots']]
    return data


def signature(data):
    def arr(value):
        return (str(value.dtype), value.shape, hashlib.sha256(value.tobytes()).hexdigest())
    value = {key: arr(item) for key, item in data.items() if isinstance(item, np.ndarray)}
    value.update(slots=data['slots'], selection=data['selection'],
                 uvs=[(name, arr(values)) for name, values in data['uvs']],
                 colours=[(name, domain, kind, arr(values)) for name, domain, kind, values in data['colours']])
    return value


def baseline_packets(data, directory, key, matrix, *, options=None, collisions=()):
    """Persist EVERY immutable-original polygon in contiguous bounded source packets.

    Baseline membership does not use the new spatial partitioner. The independent
    cross-region harness reconstructs its complete corner Counter itself.
    """
    directory.mkdir(parents=True)
    groups = []; members = []; triangles = 0
    for face, count in enumerate(data['counts']):
        size = int(count) - 2
        if size > 32768: raise ValueError('Unbounded original source polygon')
        if members and triangles + size > 32768:
            groups.append(members); members = []; triangles = 0
        members.append(face); triangles += size
    if members: groups.append(members)
    rows = []
    for index, members in enumerate(groups):
        name = key + '_Source' + str(index).zfill(4)
        path = directory / (name + '.npz')
        piece = subset(data, members)
        mesh_ir.write(path, mesh_ir.encode(piece, key=name, slots=data['slots'], matrix=matrix,
                                           options={} if options is None else options,
                                           collisions=collisions if index == 0 else ()))
        rows.append(dict(path=path.name, sha256=sha(path), triangles=piece['triangles']))
    assert sum(row['triangles'] for row in rows) == int(sum(data['counts'] - 2))
    return rows
