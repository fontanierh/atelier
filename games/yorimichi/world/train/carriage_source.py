"""Bounded service-node source data before GLB serialization.

The original Blender exporter still gathers the original complete scene and material
state. Its final file writer is intercepted only within this selected source action:
body/door node subsets are published as JSON plus their exact consumed buffer bytes.
No combined carriage GLB is serialized by this source path.
"""
import ast
from contextlib import contextmanager
import hashlib
import inspect
import json
from pathlib import Path
import struct
import sys

from atelier.atomic_files import atomic_json
from atelier.export_manifest import TRIANGLE_LIMIT, name, real_directory
from atelier.model_files import regular_files, retain_files

TOOLS = Path(__file__).resolve().parents[2] / 'tools'
sys.path.insert(0, str(TOOLS))
import gltf_subset as G  # noqa: E402

MAGIC = b'ATELIER-CARRIAGE-SOURCE-1\0'
MAX_BYTES = 128 * 1024 * 1024


def triangles(doc):
    # Count every placed mesh instance, including linked bogie/wheelset data.
    return sum(sum(doc['accessors'][p['indices']]['count'] // 3 for p in doc['meshes'][node['mesh']]['primitives'])
               for node in doc['nodes'] if 'mesh' in node)


def encode(key, doc, binary):
    key = name(key)
    from train.carriage_mesh import geometry
    count = geometry(doc, binary)['triangles']
    if not 0 < count <= TRIANGLE_LIMIT: raise ValueError('Service source exceeds the atomic triangle budget')
    header = json.dumps(dict(schema=1, asset=key, triangles=count, document=doc,
        binary_sha256=hashlib.sha256(binary).hexdigest()), separators=(',', ':'), allow_nan=False).encode()
    result = MAGIC + struct.pack('<I', len(header)) + header + binary
    if len(result) > MAX_BYTES: raise ValueError('Carriage source exceeds its data envelope')
    return result


def decode(data, *, key=None):
    if not isinstance(data, bytes) or len(data) > MAX_BYTES or not data.startswith(MAGIC):
        raise ValueError('Foreign carriage source packet')
    if len(data) < len(MAGIC) + 4: raise ValueError('Truncated carriage source packet')
    size = struct.unpack_from('<I', data, len(MAGIC))[0]; start = len(MAGIC) + 4
    if not 0 < size < len(data) - start: raise ValueError('Incomplete carriage source packet')
    value = json.loads(data[start:start + size]); binary = data[start + size:]
    if (set(value) != {'schema', 'asset', 'triangles', 'document', 'binary_sha256'} or value['schema'] != 1
            or (key is not None and value['asset'] != key)
            or hashlib.sha256(binary).hexdigest() != value['binary_sha256']
            or triangles(value['document']) != value['triangles'] or not 0 < value['triangles'] <= TRIANGLE_LIMIT):
        raise ValueError('Incomplete or changed carriage source data')
    name(value['asset'])
    from train.carriage_mesh import geometry
    geometry(value['document'], binary)
    return value, binary


def read(path, *, key=None):
    path = Path(path); real_directory(path.parent)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError('Carriage source must be a bounded regular file')
    return decode(path.read_bytes(), key=key)


def write(root, key, doc, binary):
    root = real_directory(root, create=True); target = root / (name(key) + '.source')
    data = encode(key, doc, binary)
    if not target.exists() or target.read_bytes() != data: target.write_bytes(data)
    return dict(name=key, source=target.name, sha256=hashlib.sha256(data).hexdigest(), triangles=triangles(doc))


def subsets(doc, binary, *, mesh, level, leaves):
    """The exact existing runtime G.keep operations, before the original GLB writer."""
    if level not in (0, 1, 2): raise ValueError('Unknown authored carriage LOD')
    if level == 2: return [(f'{mesh}_LOD2', doc, binary)]
    index = G.names(doc)
    missing = set(leaves) - set(index)
    if missing: raise ValueError('Missing authored moving door nodes: ' + ', '.join(sorted(missing)))
    body, body_binary = G.keep(doc, binary, drop={index[leaf] for leaf in leaves})
    result = [(f'{mesh}_LOD{level}', body, body_binary)]
    if level == 0:
        for node, key in leaves.items():
            part, part_binary = G.keep(doc, binary, only={index[node]})
            result.append((key, part, part_binary))
    return result


@contextmanager
def capture_writer(consume, *, expected):
    """@cc [owner:fontanierh,label:correctness] original-carriage-pre-file-boundary
    Source capture MUST retain the original exporter gathering, attributes, node frames,
    materials, images and extras before its final file write. Oversized combined GLBs MUST
    never be serialized. The installed writer MUST be restored on every exit. Nonfactory
    user extensions or a changed unsupported writer protocol MUST refuse.
    """
    from io_scene_gltf2.blender.exp import export as exporter
    from io_scene_gltf2.io.exp import export as writer
    from io_scene_gltf2.blender.com.json_util import BlenderJSONEncoder
    original = exporter.__write_file
    if tuple(inspect.signature(original).parameters) != ('json', 'buffer', 'export_settings'):
        raise ValueError('Unsupported installed Blender GLB writer signature')
    files = dict(exporter=Path(exporter.__file__), writer=Path(writer.__file__))
    def verify():
        actual = {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in files.items()}
        if actual != expected: raise ValueError('Installed Blender GLB addon changed from prepared identity')
    verify()
    # Use the current installed writer's actual top-level ordering. G.read of an
    # original GLB observes this order; the old runtime G.keep preserves it.
    tree = ast.parse(inspect.getsource(writer.save_gltf))
    orders = [ast.literal_eval(node.value) for node in ast.walk(tree) if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == 'sort_order' for target in node.targets)]
    if len(orders) != 1: raise ValueError('Unsupported installed Blender GLB writer ordering')
    order, = orders
    def capture(document, binary, settings):
        if settings['gltf_format'] != 'GLB' or settings.get('gltf_user_extensions'):
            raise ValueError('Carriage source requires the original factory GLB exporter')
        # This is JSON source data, not a GLB. The same encoder converts any
        # Blender/numpy scalar exactly as the original writer before G.read.
        ordered = dict(sorted(document.items(), key=lambda item: order.index(item[0])))
        source = json.loads(json.dumps(ordered, separators=(',', ':'), cls=BlenderJSONEncoder, allow_nan=False))
        consume(source, bytes(binary), Path(settings['gltf_filepath']))
    exporter.__write_file = capture
    try: yield
    finally:
        exporter.__write_file = original
        verify()


def source_sink(builder, root, *, addon):
    """Return the selected-vehicle constructor's source publisher, never a leaf exporter."""
    def publish(coach, *, mesh, lod_sets, placements, info):
        root_path = real_directory(root, create=True)
        before = regular_files(root_path)
        allowed = {'inventory.json', 'placements.json', 'info.json'}
        if any(not member.endswith('.source') and member not in allowed for member in before):
            raise ValueError('Foreign carriage source member')
        leaves = {leaf['name']: 'SM_BTD_' + mesh.removeprefix('SM_BT_') + '_' +
                  ''.join(c if c.isalnum() else '_' for c in leaf['name'].removeprefix('Door_'))
                  for door in placements['doors'] for leaf in door['leaves']}
        if len({key.casefold() for key in leaves.values()}) != len(leaves): raise ValueError('Aliased carriage door keys')
        records = []
        def consume(doc, binary, path):
            if path.stem not in {f'{mesh}_LOD{k}' for k in (0, 1, 2)}:
                raise ValueError('Foreign source-only carriage export')
            level = int(path.stem[-1])
            for key, part, blob in subsets(doc, binary, mesh=mesh, level=level, leaves=leaves):
                records.append(write(root_path, key, part, blob))
        with capture_writer(consume, expected=addon):
            for level in (0, 1, 2): builder.export_glb(root_path / f'{mesh}_LOD{level}.glb', lod_sets[level])
        expected = {f'{mesh}_LOD{k}' for k in (0, 1, 2)} | set(leaves.values())
        if {row['name'] for row in records} != expected or len(records) != len(expected):
            raise ValueError('Incomplete carriage body/door source census')
        atomic_json(root_path / 'placements.json', placements)
        atomic_json(root_path / 'info.json', info)
        policies = dict(version=1,
            about='Belmonte train coach shells, generated by games/yorimichi/world/train/build.py from train/layout.py',
            units='metres in the .blend and placements; GLBs are standard glTF (Y-up) exported by Blender',
            frame=placements['frame'], envelope=builder.L.envelope(), coupling=builder.L.coupling(),
            human_gauges=dict(cairo=builder.L.CAIRO, adult=builder.L.HUMAN),
            budgets=dict(LOD0_triangles=60000, LOD1_triangles=20000, LOD2_triangles=1500,
                         textures='7 maps, 512-1024 px, shared by both coaches'))
        atomic_json(root_path / 'inventory.json', dict(schema=1, coach=coach.name, mesh=mesh, complete=True,
            pieces=records, doors=leaves, original_triangles=info['triangles'], policies=policies))
        retain_files(root_path, [*allowed, *(row['source'] for row in records)])
        return info
    return publish
