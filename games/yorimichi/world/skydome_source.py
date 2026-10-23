"""Public exact original SkyDome authority, avoiding allocator-dependent BMesh normals."""
import ast
import hashlib
import inspect
import json
from pathlib import Path

from atelier import mesh_ir
from atelier.export_manifest import real_directory

ROOT=Path(__file__).resolve().parents[1]/'assets/props/skydome'
PROVENANCE=ROOT/'provenance.json'
PACKET=ROOT/'mesh.source.npz'


def sha(data):return hashlib.sha256(data).hexdigest()


def read():
    real_directory(ROOT)
    for path in (PROVENANCE,PACKET):
        if path.is_symlink() or not path.is_file():raise ValueError('Missing regular public SkyDome source')
    raw=PACKET.read_bytes();provenance=json.loads(PROVENANCE.read_text());record=provenance['packet']
    if (provenance.get('schema')!=1 or provenance.get('asset')!='SkyDome'
            or record.get('path')!='mesh.source.npz' or record.get('sha256')!=sha(raw) or record.get('bytes')!=len(raw)):
        raise ValueError('Public SkyDome packet identity differs from its provenance')
    meta,piece=mesh_ir.decode(raw)
    if (meta['schema']!=2 or meta['asset']!='SkyDome' or meta['options'] or meta['collisions']
            or meta['slots']!=['Sky'] or piece['triangles']!=record.get('triangles')
            or len(piece['faces'])!=record.get('polygons') or not 0<piece['triangles']<=32768):
        raise ValueError('Incomplete original SkyDome source packet')
    return provenance,meta,piece


def reference(function):
    """@cc [owner:fontanierh,label:correctness;performance] authoritative-skydome-source
    SkyDome MUST consume the exact public immutable-original source packet, retaining every
    normal/corner/channel/frame rather than rerunning its allocator-dependent BMesh sphere.
    The selected original constructor AST MUST match provenance; changes MUST refuse until
    a new explicit source capture and original FBX equivalence proof replaces the authority.
    No sibling construction, normal recomputation/rounding or private geometry fallback is allowed.
    """
    provenance,_,_=read()
    # Python 3.13 omits empty AST fields by default; the original 3.12 authority
    # includes them. Bind the same complete AST on the host and Blender runtimes.
    options={'show_empty':True} if 'show_empty' in inspect.signature(ast.dump).parameters else {}
    if provenance['constructor']['ast_sha256']!=sha(ast.dump(function,include_attributes=False,**options).encode()):
        raise ValueError('SkyDome constructor changed; capture and prove a new public source authority')
    return dict(path='props/skydome/mesh.source.npz',sha256=provenance['packet']['sha256'],
                provenance_sha256=sha(PROVENANCE.read_bytes()))


def construct(reference,materials):
    from mathutils import Matrix
    import bpy
    from mesh_pieces import create_mesh
    provenance,meta,piece=read()
    expected=dict(path='props/skydome/mesh.source.npz',sha256=provenance['packet']['sha256'],
                  provenance_sha256=sha(PROVENANCE.read_bytes()))
    if reference!=expected:raise ValueError('Selected SkyDome source differs from its public authority')
    piece['slots']=[materials[label] for label in meta['slots']]
    obj=bpy.data.objects.new('SkyDome',create_mesh('SkyDome',piece))
    bpy.context.collection.objects.link(obj);obj.matrix_world=Matrix(meta['matrix'])
    return obj
