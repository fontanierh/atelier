"""Eight fixed-label base-color views of an existing native GLB; no mesh writes."""
from functools import partial
from pathlib import Path
import argparse
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image, ImageDraw
from meshaxiom_pixel_match import digest, fitted_view, load_module, matte, stage
from meshaxiom_quality import render, write, VENDOR

p = argparse.ArgumentParser()
p.add_argument('--root', type=Path, required=True)
p.add_argument('--model', type=Path, required=True)
p.add_argument('--image', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--yaw-offset', type=float, default=0,
               help='Documented camera-frame rotation only; model bytes remain untouched')
args = p.parse_args()
if not -360 <= args.yaw_offset <= 360:
    p.error('Camera offset must be within one turn')
args.output.mkdir(parents=True, exist_ok=True)
pm = load_module(VENDOR)
pm.rasterize = partial(pm.rasterize, chunk=256)
before = digest(args.model)
doc, _ = pm._split_glb(args.model.read_bytes())
if 'COLOR_0' in doc['meshes'][0]['primitives'][0]['attributes']:
    from vertex_bake import render_existing
    render_existing(args)
    raise SystemExit(0)
positions, uvs, faces, texture = pm.read_glb(args.model)
reference = matte(Image.open(args.image))
contact = Image.new('RGB', (1536, 816))
draw = ImageDraw.Draw(contact)
cameras = []
for index, (yaw, pitch) in enumerate([(0, -5), (60, -5), (120, -5), (180, -5),
                                     (240, -5), (300, -5), (60, 55), (240, -40)]):
    name = f'yaw{yaw}-pitch{pitch}'
    view = fitted_view(pm, positions, reference, yaw+args.yaw_offset, pitch)
    with stage(f'Comparison render {index+1}/8: {name}'):
        pixels, _ = render(pm, positions, faces, view, texture, uvs)
    Image.fromarray(pixels).save(args.output/(name+'.png'))
    contact.paste(Image.fromarray(pixels).convert('RGB').resize((384, 384)),
                  (index%4*384, index//4*408))
    draw.text((index%4*384+8, index//4*408+386), name, fill='white')
    cameras.append(dict(name=name, yaw=yaw+args.yaw_offset, pitch=pitch,
                        transform_matrix=view.cam_to_world.tolist(), camera_angle_x=view.fov_x))
if digest(args.model) != before:
    raise ValueError('Comparison changed the source GLB')
contact.save(args.output/'contact.png')
write(args.output/'comparison.json', dict(model_sha256=before, reference_sha256=digest(args.image),
    camera_yaw_offset=args.yaw_offset, source_unchanged=True, mode='Base color, no relighting', views=cameras))
