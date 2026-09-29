"""Export a browser-preview glTF from a review .blend: JSON .gltf whose single buffer has no uri, plus a
<name>.buffer.js file that sets window.GLTF_BUFFER_B64 to the base64 geometry, plus textures as external
JPEGs downscaled to --texture-size. For hosting on pages that serve only standard web media types
(JSON, scripts, images) and whose security policy may block data: fetches; the page rebuilds a GLB in
memory (JSON chunk + BIN chunk) and hands it to GLTFLoader.parse.

blender -b review.blend --python platform/studio/atelier/export_preview_gltf.py -- --output preview --name Asset --texture-size 2048
"""
import argparse, base64, json, sys
from pathlib import Path
import bpy

ap = argparse.ArgumentParser()
ap.add_argument('--output', type=Path, required=True)
ap.add_argument('--name', required=True)
ap.add_argument('--texture-size', type=int, default=2048)
a = ap.parse_args(sys.argv[sys.argv.index('--') + 1:])
out = a.output.resolve(); out.mkdir(parents=True, exist_ok=True)
for im in bpy.data.images:
    if im.size[0] > a.texture_size:
        im.scale(a.texture_size, a.texture_size)
# export only mesh objects (no review cameras/lights)
for o in bpy.data.objects:
    o.select_set(o.type == 'MESH')
gltf = out / f'{a.name}.gltf'
bpy.ops.export_scene.gltf(filepath=str(gltf), export_format='GLTF_SEPARATE', use_selection=True,
                          export_image_format='JPEG', export_jpeg_quality=85, export_texture_dir='tex',
                          export_apply=True, export_yup=True, export_animations=False, export_skins=False)
doc = json.loads(gltf.read_text())
assert len(doc.get('buffers', [])) == 1, 'expected one buffer'
b = doc['buffers'][0]
blob = (gltf.parent / b['uri']).read_bytes()
(gltf.parent / b['uri']).unlink()
del b['uri']
b['byteLength'] = len(blob)
gltf.write_text(json.dumps(doc))
(out / f'{a.name}.buffer.js').write_text('window.GLTF_BUFFER_B64="' + base64.b64encode(blob).decode() + '";\n')
print('preview gltf:', gltf, gltf.stat().st_size, 'bytes; images:', [str(p.name) for p in (out / 'tex').glob('*')])
