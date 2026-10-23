"""Exercise actual bounded planning, IR reconstruction and independent deterministic export."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys

import bpy
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'games/yorimichi/world'))
import yori  # noqa: E402,F401
from atelier import export_assembly, export_tasks, mesh_ir
from atelier.blender.fbx import export_atomic_fbx, export_fbx
from mesh_pieces import capture, subset
from region_mesh_parts import plan
import export_region_piece
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'native'))
from fbx_corners import read as exported_corners


def corners(piece):
    """Complete ordered face rows, retaining UV/color names and material identity."""
    result = Counter()
    offset = 0
    for index, face in enumerate(piece['faces']):
        size = len(face)
        rows = []
        for local, vertex in enumerate(face):
            loop = offset + local
            rows.append((tuple(piece['positions'][vertex]), tuple(piece['normals'][loop]),
                         tuple((name, tuple(uv[loop])) for name, uv in piece['uvs']),
                         tuple((name, domain, kind, tuple(value[vertex if domain == 'POINT' else loop]))
                               for name, domain, kind, value in piece['colours'])))
        result[(piece['slots'][int(piece['materials'][index])], bool(piece['smooth'][index]), tuple(rows))] += 1
        offset += size
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    root = export_tasks.real_directory(args.output)
    if root.exists(): raise ValueError('Canary requires a fresh root')
    root.mkdir(parents=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    # One deliberately oversized, distributed parent with six UV channels, two material
    # slots and both supported color domains. No degenerate faces or all-miss controls.
    count = 32770
    positions, faces = [], []
    for index in range(count):
        x, y = index % 256, index // 256
        first = len(positions)
        positions.extend(((x, y, 0), (x + .25, y, .125), (x, y + .25, .25)))
        faces.append((first, first + 1, first + 2))
    data = bpy.data.meshes.new('AtomicProbe')
    data.from_pydata(positions, [], faces); data.update()
    for label in ('Stone', 'Timber'):
        data.materials.append(bpy.data.materials.new(label))
    data.polygons.foreach_set('material_index', np.arange(count, dtype=np.int32) % 2)
    for channel in range(6):
        uv = data.uv_layers.new(name='UV' + str(channel))
        values = np.arange(len(data.loops) * 2, dtype=np.float32).reshape(-1, 2) / 8192 + channel
        uv.data.foreach_set('uv', values.ravel())
    for domain in ('POINT', 'CORNER'):
        attribute = data.color_attributes.new(name=domain, type='FLOAT_COLOR', domain=domain)
        colours = np.tile(np.array([.125, .25, .5, 1.], np.float32), (len(attribute.data), 1))
        attribute.data.foreach_set('color', colours.ravel())
    for domain in ('POINT', 'CORNER'):
        attribute = data.color_attributes.new(name='BYTE_' + domain, type='BYTE_COLOR', domain=domain)
        colours = np.tile(np.array([.125, .25, .5, 1.], np.float32), (len(attribute.data), 1))
        attribute.data.foreach_set('color', colours.ravel())
    data.uv_layers.active_index = 4
    data.uv_layers[5].active_render = True
    data.color_attributes.active_color_index = 1
    data.color_attributes.render_color_index = 1
    obj = bpy.data.objects.new('AtomicProbe', data)
    bpy.context.collection.objects.link(obj); obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    original = capture(data)
    full = subset(original, tuple(range(count)))
    full['slots'] = [slot.name for slot in full['slots']]
    expected = corners(full)
    try:
        export_atomic_fbx(filepath=str(root / 'oversized.fbx'), use_selection=True, object_types={'MESH'})
    except ValueError:
        assert not (root / 'oversized.fbx').exists()
    else:
        raise AssertionError('Oversized native selection was accepted')
    # An explicit diagnostic whole control exercises the original exporter. It
    # never enters production membership or the atomic task admission path.
    control = root / 'whole-control.fbx'
    export_fbx(filepath=str(control), use_selection=True, object_types={'MESH'}, bake_anim=False)
    expected_exported = exported_corners(control)
    observed_exported = dict(render=Counter(), collision=Counter())
    inventory = plan(obj, root / 'plan')
    assert len(inventory['pieces']) > 1
    observed = Counter()
    items = []
    for row in inventory['pieces']:
        payload = root / 'plan' / row['payload']
        meta, piece = mesh_ir.decode(payload.read_bytes())
        assert piece['selection'] == original['selection']
        observed.update(corners(piece))
        assert 0 < row['triangles'] <= export_tasks.TRIANGLE_LIMIT
        output = root / 'exports' / row['name']
        print('ATOMIC CANARY EXPORT ' + row['name'], flush=True)
        export_region_piece.main(['--input', str(payload), '--output', str(output)])
        before = (output / (row['name'] + '.fbx')).read_bytes()
        emitted = exported_corners(output / (row['name'] + '.fbx'))
        for kind in observed_exported:
            observed_exported[kind].update(emitted[kind])
        export_region_piece.main(['--input', str(payload), '--output', str(output)])
        assert (output / (row['name'] + '.fbx')).read_bytes() == before
        assert export_tasks.validate(output, key=row['name'])['triangles'] == row['triangles']
        items.append(export_assembly.Item(row['name'], output))
    assert observed == expected, 'Planned pieces changed face/corner/material/UV/color multiplicity'
    assert observed_exported == expected_exported, 'Serialized FBX changed complete exported polygon corners'
    # GLB uses the same bounded input, with all six UV channels and both colors
    # requested explicitly. Inspect the actual serialized primitive attributes.
    import struct
    row = inventory['pieces'][0]
    payload = root / 'plan' / row['payload']
    glb_root = root / 'glb' / row['name']
    export_region_piece.main(['--input', str(payload), '--output', str(glb_root), '--format', '.glb'])
    blob = (glb_root / (row['name'] + '.glb')).read_bytes()
    length, kind = struct.unpack_from('<II', blob, 12)
    assert kind == 0x4E4F534A
    document = json.loads(blob[20:20 + length])
    primitives = [p for mesh in document['meshes'] for p in mesh['primitives']]
    assert primitives
    for primitive in primitives:
        attributes = primitive['attributes']
        assert all('TEXCOORD_' + str(i) in attributes for i in range(6)), attributes
        assert sum(key.startswith('COLOR_') for key in attributes) >= 4, attributes
    export_region_piece.main(['--input', str(payload), '--output', str(glb_root), '--format', '.glb'])
    assert (glb_root / (row['name'] + '.glb')).read_bytes() == blob

    assembled = export_assembly.assemble(items, root / 'assembled')
    assert len(assembled['exports']) == len(inventory['pieces'])
    (root / 'result.json').write_text(json.dumps(dict(complete=True, source_triangles=count,
        pieces=len(items), uv_channels=6, exact_corner_conservation=True,
        exported_fbx_corners_equal=True, colour_layers=4,
        repeated_exports_byte_identical=True, oversized_refused=True)))
    print('ATOMIC MESH EXPORT CANARY COMPLETE', flush=True)


if __name__ == '__main__': main()
