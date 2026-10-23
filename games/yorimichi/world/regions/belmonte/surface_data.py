"""Canonical final query data before any bounded render export."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile

from atelier.export_manifest import name,real_directory
from atelier.gltf import glb_parts
from atelier.gltf_partition import split
from belmonte.ground_pieces import is_ground

MAGIC=b'ATELIER-FINAL-SURFACE-1\0'
MAX_BYTES=256*1024*1024
MAX_HEADER=1024*1024
MAX_TRIANGLES=2_000_000


def validate(entry,data):
    key=name(entry['name'])
    if not is_ground(key) or entry.get('collision'):raise ValueError('Final query data requires its explicit ground owner')
    if not isinstance(data,bytes) or not 0<len(data)<=MAX_BYTES:raise ValueError('Final query source exceeds bounded envelope')
    if hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('Final surface differs from its source identity')
    doc,_=glb_parts(data)
    counts=[doc['accessors'][p['indices']]['count'] for mesh in doc.get('meshes',[]) for p in mesh.get('primitives',[])]
    if (not counts or any(type(n) is not int or n<=0 or n%3 for n in counts)
            or not 0<sum(counts)//3<=MAX_TRIANGLES or type(entry['triangles']) is not int
            or entry['triangles']!=sum(counts)//3):raise ValueError('Incomplete final surface triangle inventory')
    # This is source validation, never a render export. The exact complete source
    # may exceed the render budget; its children have the separate strict32768 gate.
    extent=float.fromhex('0x1.fffffep+127')
    rows=split(data,(-extent,-extent,extent,extent),triangle_limit=entry['triangles'])
    if len(rows)!=1 or rows[0]['data']!=data:raise ValueError('Final query source must remain whole and unchanged')
    return entry


def encode(entry,data):
    """@cc [owner:fontanierh,label:correctness] final-query-before-render-exports
    Canonical query data MUST retain the complete final source and its exact
    encoded triangle/corner bytes, owner and current hash before render export.
    Reading a final query MUST NOT require sibling exported meshes or substitute
    natural terrain. The render triangle budget MUST remain enforced separately
    by every atomic primary exporter.
    """
    validate(entry,data)
    header=json.dumps(dict(schema=1,entry=entry),sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    if not 0<len(header)<=MAX_HEADER:raise ValueError('Final query header exceeds bounded envelope')
    return MAGIC+struct.pack('<I',len(header))+header+data


def decode(packet,*,owner):
    if (not isinstance(packet,bytes) or not packet.startswith(MAGIC)
            or not len(MAGIC)+4<len(packet)<=MAX_BYTES+MAX_HEADER+len(MAGIC)+4):raise ValueError('Invalid final query data')
    size=struct.unpack_from('<I',packet,len(MAGIC))[0]
    if not 0<size<=MAX_HEADER or len(packet)<=len(MAGIC)+4+size:raise ValueError('Invalid final query header')
    value=json.loads(packet[len(MAGIC)+4:len(MAGIC)+4+size]);data=packet[len(MAGIC)+4+size:]
    if (set(value)!={'schema','entry'} or type(value['schema']) is not int or value['schema']!=1
            or value['entry']['name']!=name(owner)):raise ValueError('Foreign final query owner')
    return validate(value['entry'],data),data


def write(path,entry,data):
    path=Path(path);real_directory(path.parent)
    if path.name!=name(entry['name'])+'.surface':raise ValueError('Final query path belongs to another source')
    packet=encode(entry,data)
    if path.is_symlink() or path.exists() and not path.is_file():raise ValueError('Final query must be regular')
    if path.exists() and path.read_bytes()==packet:return
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix='.surface-',dir=path.parent,delete=False) as stream:
        temporary=Path(stream.name);stream.write(packet)
    try:temporary.replace(path)
    finally:temporary.unlink(missing_ok=True)


def read(path,*,owner):
    path=Path(path);real_directory(path.parent)
    if (path.name!=name(owner)+'.surface' or path.is_symlink() or not path.is_file()
            or path.stat().st_size>MAX_BYTES+MAX_HEADER+len(MAGIC)+4):raise ValueError('Invalid final query input')
    return decode(path.read_bytes(),owner=owner)
