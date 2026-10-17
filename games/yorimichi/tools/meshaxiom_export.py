"""Pack generated JSON into a metre-scaled GLB with simple matte preview materials.

This is lightweight format conversion: no model, renderer, remeshing or subdivision.
"""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import struct


def export(mesh_path, output, height, palette):
    """@cc [owner:fontanierh,label:correctness] meshaxiom-export-keeps-neural-triangles
    Export MUST retain every input triangle's indices and winding, with only a uniform
    scale, origin and Z-up to Y-up conversion of positions. Material grouping MAY reorder
    whole triangles but MUST NOT add, remove, subdivide or repair geometry.
    """
    if not math.isfinite(height) or not .1 <= height <= 20:
        raise ValueError('Height must be finite, 0.1–20 metres')
    raw = mesh_path.read_bytes()
    if mesh_path.suffix == '.gz':
        raw = gzip.decompress(raw)
    data = json.loads(raw)
    vertices, faces = data['vertices'], data['faces']
    if (not vertices or not faces or any(len(v) != 3 or not all(math.isfinite(x) for x in v) for v in vertices)
            or any(len(f) != 3 or any(type(i) is not int or not 0 <= i < len(vertices) for i in f) for f in faces)):
        raise ValueError('Invalid positions or triangle indices')
    lo = [min(v[i] for v in vertices) for i in range(3)]
    hi = [max(v[i] for v in vertices) for i in range(3)]
    if hi[2] <= lo[2]:
        raise ValueError('Mesh has no height')
    scale = height/(hi[2]-lo[2])
    cx, cy = (lo[0]+hi[0])/2, (lo[1]+hi[1])/2
    positions = [((v[0]-cx)*scale, (v[2]-lo[2])*scale, -(v[1]-cy)*scale) for v in vertices]
    positions = [struct.unpack('<3f', struct.pack('<3f', *v)) for v in positions]
    shades = {'cart': [0x977344, 0x354f6f], 'bin': [0x354f6f, 0xc4953f], 'clay': [0xb5aca0]}[palette]
    groups = [[] for _ in shades]
    threshold = .68 if palette == 'cart' else .78
    for f in faces:
        upper = sum((vertices[i][2]-lo[2])/(hi[2]-lo[2]) for i in f)/3 > threshold
        groups[int(upper) if len(groups) == 2 else 0].extend(f)
    binary = bytearray()
    views, accessors = [], []
    def add(payload, accessor):
        binary.extend(b'\0'*(-len(binary)%4))
        views.append(dict(buffer=0, byteOffset=len(binary), byteLength=len(payload)))
        binary.extend(payload)
        accessors.append(dict(bufferView=len(views)-1, **accessor))
        return len(accessors)-1
    position = add(b''.join(struct.pack('<3f', *v) for v in positions),
                   dict(componentType=5126, count=len(positions), type='VEC3',
                        min=[min(v[i] for v in positions) for i in range(3)],
                        max=[max(v[i] for v in positions) for i in range(3)]))
    primitives = []
    for material, indices in enumerate(groups):
        if not indices:
            continue
        accessor = add(b''.join(struct.pack('<I', i) for i in indices),
                       dict(componentType=5125, count=len(indices), type='SCALAR'))
        primitives.append(dict(attributes=dict(POSITION=position), indices=accessor, material=material, mode=4))
    def linear(value):
        value /= 255
        return value/12.92 if value <= .04045 else ((value+.055)/1.055)**2.4
    materials = [dict(name=f'{palette}-{i}', doubleSided=True, pbrMetallicRoughness=dict(
        baseColorFactor=[*(linear((c >> shift) & 255) for shift in (16, 8, 0)), 1],
        metallicFactor=0, roughnessFactor=.86)) for i, c in enumerate(shades)]
    doc = dict(asset=dict(version='2.0', generator='Atelier MeshAxiom uniform-scale export'),
               scene=0, scenes=[dict(nodes=[0])], nodes=[dict(mesh=0, name='MeshAxiom')],
               meshes=[dict(primitives=primitives)], materials=materials, accessors=accessors,
               bufferViews=views, buffers=[dict(byteLength=len(binary))])
    encoded = json.dumps(doc, separators=(',', ':')).encode()
    encoded += b' '*(-len(encoded)%4)
    binary.extend(b'\0'*(-len(binary)%4))
    payload = (struct.pack('<III', 0x46546c67, 2, 28+len(encoded)+len(binary))
               + struct.pack('<II', len(encoded), 0x4e4f534a)+encoded
               + struct.pack('<II', len(binary), 0x004e4942)+binary)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    report = dict(source_sha256=hashlib.sha256(raw).hexdigest(), output_sha256=hashlib.sha256(payload).hexdigest(),
                  vertices=len(vertices), triangles=len(faces), height_metres=height, scale=scale,
                  source_center_xy=[cx, cy], source_ground_z=lo[2], up_axis='y', palette=palette,
                  changes='Uniform scale/origin, Z-up to Y-up, matte face materials; no geometry repair')
    output.with_suffix('.export.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mesh', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--height', type=float, required=True)
    parser.add_argument('--palette', choices=['bin', 'cart', 'clay'], default='clay')
    args = parser.parse_args()
    export(args.mesh, args.output, args.height, args.palette)
