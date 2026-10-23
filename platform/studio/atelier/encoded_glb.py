"""Bounded encoded static-mesh data with lossless independently cached GLB publication."""
import hashlib
import json
import math
from pathlib import Path
import struct
import tempfile
from copy import deepcopy

from .export_manifest import TRIANGLE_LIMIT, name, real_directory, publish_receipt
from .gltf import glb_parts,glb_pack
from .gltf_partition import split
from .model_files import regular_files

MAGIC=b'ATELIER-STATIC-MESH-1\0'
MAX_BYTES=64*1024*1024
MAX_HEADER=1024*1024


def geometry(data,*,role='render'):
    """Validate the existing strict identity-node encoded mesh policy, without recoding attributes."""
    if not isinstance(data,bytes) or not 0<len(data)<=MAX_BYTES:
        raise ValueError('Encoded geometry exceeds its bounded data envelope')
    if role not in ('render','collision'):raise ValueError('Unknown encoded mesh role')
    doc,binary=glb_parts(data)
    counts=[doc['accessors'][primitive['indices']]['count'] for mesh in doc.get('meshes',[])
            for primitive in mesh.get('primitives',[])]
    if (not counts or any(type(count) is not int or count<=0 or count%3 for count in counts)
            or sum(counts)//3>TRIANGLE_LIMIT):
        raise ValueError('Encoded atomic mesh must already fit the triangle budget')
    # At most32768 faces guarantees split returns the exact original encoded
    # bytes. Its strict decoder validates every attribute and triangle reference.
    # This is validation, not spatial subdivision. The fixed finite envelope
    # covers every float32 position; the early count check forbids any split.
    extent=float.fromhex('0x1.fffffep+127')
    checked=data
    if role=='collision':
        if doc.get('materials') or any('material' in primitive for mesh in doc['meshes'] for primitive in mesh['primitives']):
            raise ValueError('Authored collision data must be material-free')
        # Reuse the exact static decoder on a validation-only material table.
        # The original material-free bytes remain the sole published payload.
        validation=deepcopy(doc);validation['materials']=[dict(name='CollisionValidation')]
        for mesh in validation['meshes']:
            for primitive in mesh['primitives']:primitive['material']=0
        checked=glb_pack(validation,binary)
    pieces=split(checked,(-extent,-extent,extent,extent),triangle_limit=TRIANGLE_LIMIT)
    if len(pieces)!=1 or pieces[0]['suffix'] or pieces[0]['data']!=checked:
        raise ValueError('Encoded atomic mesh must already fit the triangle budget')
    return dict(triangles=pieces[0]['triangles'],bounds=[list(point) for point in pieces[0]['bounds']],
                slots=[material['name'] for material in doc.get('materials',[])])


def encode(data,*,key,metadata=None,role='render'):
    """@cc [owner:fontanierh,label:correctness] lossless-bounded-encoded-mesh-data
    Planned encoded mesh data MUST contain one complete validated bounded static
    mesh. Preserve all encoded corner attributes, material identity and original
    bytes; do not decode/re-export through Blender or join sibling products.
    The explicit owner, digest, triangle count and bounds MUST match on read.
    """
    current=geometry(data,role=role)
    value=dict(schema=1,asset=name(key),role=role,sha256=hashlib.sha256(data).hexdigest(),
               **current,metadata=metadata or {})
    header=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if len(header)>MAX_HEADER:raise ValueError('Encoded mesh header exceeds bound')
    return MAGIC+struct.pack('<I',len(header))+header+data


def decode(packet,*,key=None):
    if (not isinstance(packet,bytes) or len(packet)>MAX_BYTES+MAX_HEADER+len(MAGIC)+4
            or not packet.startswith(MAGIC) or len(packet)<len(MAGIC)+4):
        raise ValueError('Invalid encoded mesh data')
    size=struct.unpack_from('<I',packet,len(MAGIC))[0]
    if not 0<size<=MAX_HEADER or len(packet)<=len(MAGIC)+4+size:raise ValueError('Invalid encoded mesh header')
    value=json.loads(packet[len(MAGIC)+4:len(MAGIC)+4+size])
    if (not isinstance(value,dict) or set(value)!={'schema','asset','role','sha256','triangles','bounds','slots','metadata'}
            or type(value['schema']) is not int or value['schema']!=1 or not isinstance(value['metadata'],dict)):
        raise ValueError('Invalid encoded mesh identity')
    name(value['asset'])
    if key is not None and value['asset']!=key:raise ValueError('Encoded mesh belongs to another owner')
    data=packet[len(MAGIC)+4+size:]
    actual=geometry(data,role=value['role'])
    if (hashlib.sha256(data).hexdigest()!=value['sha256'] or any(value[field]!=actual[field] for field in actual)
            or type(value['triangles']) is not int or not 0<value['triangles']<=TRIANGLE_LIMIT
            or any(not math.isfinite(v) for row in value['bounds'] for v in row)):
        raise ValueError('Encoded mesh data differs from its declaration')
    return value,data


def read(path,*,key=None):
    path=Path(path)
    real_directory(path.parent)
    if path.is_symlink() or not path.is_file() or path.stat().st_size>MAX_BYTES+MAX_HEADER+len(MAGIC)+4:
        raise ValueError('Encoded mesh data must be a bounded regular input')
    return decode(path.read_bytes(),key=key)


def export(source,destination):
    """Publish exactly one small GLB and its receipt, with unchanged encoded bytes."""
    source=Path(source)
    if source.suffix!='.mesh':raise ValueError('Encoded export requires its explicitly owned data packet')
    value,data=read(source,key=source.stem)
    destination=real_directory(destination)
    primary=value['asset']+'.glb'
    if destination.exists() and (regular_files(destination)-{primary,'export.json'}
                                 or any(path.is_dir() for path in destination.iterdir())):
        raise ValueError('Foreign encoded export members')
    destination.mkdir(parents=True,exist_ok=True)
    target=destination/primary
    if target.is_symlink() or (target.exists() and not target.is_file()):raise ValueError('Linked encoded primary')
    if not target.exists() or target.read_bytes()!=data:
        with tempfile.NamedTemporaryFile(prefix='.encoded-',dir=destination,delete=False) as stream:
            temporary=Path(stream.name);stream.write(data)
        try:temporary.replace(target)
        finally:temporary.unlink(missing_ok=True)
    return publish_receipt(destination,key=value['asset'],primary=primary,triangles=value['triangles'],
                           bounds=value['bounds'],metadata=value['metadata']|dict(role=value['role'],slots=value['slots'],geometry_sha256=value['sha256']))
