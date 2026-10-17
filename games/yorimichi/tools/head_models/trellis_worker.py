"""Bounded raw-geometry TRELLIS.2 MLX head experiment; no cleanup/simplification."""
from pathlib import Path
from functools import partial
import argparse
import ast
from types import SimpleNamespace
import gc
import hashlib
import json
import subprocess
import sys
import time

p=argparse.ArgumentParser()
p.add_argument('--root',type=Path,required=True)
p.add_argument('--image',type=Path,nargs='+',required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--resolution',type=int,choices=[512,768,1024],default=512)
p.add_argument('--steps',type=int,choices=[8,12,20],default=12)
p.add_argument('--quantize',type=int,choices=[0,4,8],default=0)
p.add_argument('--vertex-colors',action='store_true',help='Bake learned colors at raw vertices without UV construction')
p.add_argument('--mlx-gib',type=int,choices=[8,10,12],default=8)
p.add_argument('--max-tokens',type=int,choices=[8192,12288,16384],default=16384)
p.add_argument('--texture-size',type=int,choices=[1024,2048,4096],default=2048)
args=p.parse_args()
root=args.root.resolve()
repo=root/'trellis2mlx'
sys.path.insert(0,str(Path(__file__).resolve().parent))
from support import verify_source
from geometry import same_triangles
verify_source(root,'trellis')
model_root=root/'models'
args.output.mkdir(parents=True,exist_ok=True)
if (args.output/'head.glb').exists():raise ValueError('Completed GLB exists; use a separate trial')
expected='c0e66f782ac86f86212e049cf029478602b0e8d2'
actual=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip()
if actual!=expected:raise ValueError('Unreviewed MLX source revision')
sys.path[:0]=[str(repo),str(Path(__file__).resolve().parents[1])]
import mlx.core as mx
import mlx.utils
import numpy as np
from PIL import Image
from safetensors import safe_open
from meshaxiom_pixel_match import digest,matte,stage
from meshaxiom_quality import write,load_module,VENDOR

mx.set_memory_limit(args.mlx_gib*2**30)
mx.set_cache_limit(256*2**20)
print(f'MLX allocator limit{args.mlx_gib}GiB, cache256MiB; independent aggregate guard remains active',flush=True)
receipts=json.loads(Path(__file__).with_name('trellis-weights.json').read_text())
receipts+= [r for r in json.loads(Path(__file__).with_name('native-weights.json').read_text())
             if r['file']=='model.safetensors' or r['file'].startswith('ckpts/tex_dec_')]
for record in receipts:
    file=model_root/record['repo']/record['file']
    h=hashlib.sha256()
    with file.open('rb') as f:
        for chunk in iter(lambda:f.read(4*1024*1024),b''):h.update(chunk)
    if h.hexdigest()!=record['sha256'] or file.stat().st_size!=record['size_bytes']:
        raise ValueError('Pinned generation weight changed: '+record['file'])

from trellmlx.models import dinov3
dinov3.extract_features=partial(dinov3.extract_features,
    weights_path=str(model_root/'camenduru/dinov3-vitl16-pretrain-lvd1689m'))
from trellmlx import weight_loader
original_load=weight_loader.load_weights
key_checks=[]
def strict_load(model,file,verbose=True):
    expected=dict(mlx.utils.tree_flatten(model.parameters()))
    with safe_open(file,framework='numpy') as stored:
        keys={weight_loader._remap_key(k):k for k in stored.keys()}
        if set(keys)!=set(expected):
            raise ValueError(f'Incomplete MLX checkpoint: missing {set(expected)-set(keys)}, unexpected {set(keys)-set(expected)}')
        for key,source in keys.items():
            shape=tuple(stored.get_slice(source).get_shape())
            if weight_loader._should_permute_conv(key,shape):shape=(shape[0],shape[2],shape[3],shape[4],shape[1])
            if shape!=expected[key].shape:raise ValueError('MLX checkpoint shape mismatch '+key)
    skipped=original_load(model,file,verbose=verbose)
    if skipped:raise ValueError('MLX loader skipped checkpoint tensors')
    key_checks.append(dict(file=Path(file).name,keys=len(keys),strict_complete_state=True))
weight_loader.load_weights=strict_load

from trellmlx.preprocess import preprocess_image_with_provenance
prepared=[];image_provenance=[]
for i,file in enumerate(args.image):
    rgba=args.output/f'reference-{i}-alpha.png'
    Image.fromarray(matte(Image.open(file))).save(rgba)
    result=preprocess_image_with_provenance(rgba)
    target=args.output/f'reference-{i}-prepared.png';result.image.save(target)
    prepared.append(target)
    image_provenance.append(dict(source_sha256=digest(file),alpha_sha256=digest(rgba),
        prepared_sha256=digest(target),foreground_crop=result.provenance,
        alpha_method='Only border-connected near-black background; same identity pixels retained'))
source_path=repo/'generate.py'
source=source_path.read_text()
patches=[]
def replace(old,new):
    global source
    if source.count(old)!=1:raise ValueError('Pinned generation source anchor changed: '+old[:70])
    source=source.replace(old,new)
    patches.append(dict(old_sha256=hashlib.sha256(old.encode()).hexdigest(),new_sha256=hashlib.sha256(new.encode()).hexdigest()))
for repo_id,revision in [('TRELLIS.2-4B','af44b45f2e35a493886929c6d786e563ec68364d'),
                         ('TRELLIS-image-large','25e0d31ffbebe4b5a97464dd851910efc3002d96')]:
    old=f'"~/.cache/huggingface/hub/models--microsoft--{repo_id}/"\n        "snapshots/{revision}/ckpts/"'
    replace(old,repr(str((model_root/'microsoft'/repo_id/'ckpts').resolve())+'/'))
# Deleting function parameters inside cleanup_model does not drop caller references.
replace('    cleanup_model(ss_flow, ss_dec)','    del ss_flow, ss_dec\n    cleanup()')

# Fail closed rather than silently trying an unpinned PyTorch fallback or random input.
feature_node=next(node for node in ast.parse(source).body if isinstance(node,ast.FunctionDef) and node.name=='_extract_image_features')
replace(ast.get_source_segment(source,feature_node),'''def _extract_image_features(image_path, resolution=512):
    from trellmlx.models.dinov3 import extract_features
    features = extract_features(image_path, image_size=resolution)
    print(f"  Features: {features.shape} (pinned MLX)", flush=True)
    return features''')
if args.resolution>512:
    # Match the official cascade's stage-specific high-resolution image conditioning.
    replace('        hr_slat_flow = SLatFlowModel.for_shape()','''        high_features = [_extract_image_features(image, resolution=1024) for image in image_paths]
        cond = mx.concatenate(high_features, axis=1)
        neg_cond = mx.zeros_like(cond)
        del high_features
        hr_slat_flow = SLatFlowModel.for_shape()''')
    replace('"slat_flow_imgshape2tex_dit_1_3B_512_bf16.safetensors"','"slat_flow_imgshape2tex_dit_1_3B_1024_bf16.safetensors"')
    replace('            if num_tokens < args.max_tokens or hr_resolution == 1024:',
            '            if num_tokens <= args.max_tokens:')
    replace('            hr_resolution -= 128','''            if hr_resolution <= 512:
                raise ValueError("Cascade support exceeds the selected token limit even at512")
            hr_resolution -= 128''')
if args.vertex_colors:
    replace('    # === Stage 6: Texture Baking ===',
            '    return  # Complete native shape/PBR checkpoints; caller performs vertex-color bake.\n    # === Stage 6: Texture Baking ===')

argv=[str(source_path),'--image',*map(str,prepared),'--output',str(args.output/'head.glb'),
      '--resolution',str(args.resolution),'--steps',str(args.steps),'--seed','42',
      '--quantize',str(args.quantize),'--max-tokens',str(args.max_tokens),'--target-faces','0','--no-cleanup',
      '--no-hole-fill','--no-rembg','--texture-size',str(args.texture_size),'--uv-method','xatlas',
      '--save-checkpoints',str(args.output/'checkpoints')]
if args.resolution==512:argv+=['--no-cascade']
write(args.output/'requested-recipe.json',dict(backend='Microsoft TRELLIS.2 via pinned MLX port',
    source_commit=actual,source_sha256=digest(source_path),executed_source_sha256=hashlib.sha256(source.encode()).hexdigest(),
    source_patches=patches,configuration=dict(resolution=args.resolution,steps=args.steps,seed=42,
        quantize=args.quantize,max_tokens=args.max_tokens,mlx_limit_gib=args.mlx_gib,vertex_colors=args.vertex_colors,target_faces=0,cleanup=False,hole_fill=False,texture_size=args.texture_size,high_stage_image_size=1024 if args.resolution>512 else 512,
        texture_model_resolution=1024 if args.resolution>512 else 512),
    image_provenance=image_provenance,weights=receipts,
    multiview='Concatenated DINO feature sequences without camera labels; experimental inference heuristic, not a multiview-trained checkpoint' if len(prepared)>1 else 'single reference image'))
sys.argv=argv
start=time.monotonic()
namespace={'__name__':'__main__','__file__':str(source_path)}
with stage('TRELLIS.2 MLX native generation and raw-geometry texture bake'):
    exec(compile(source,str(source_path),'exec'),namespace)
gc.collect();mx.synchronize();mx.clear_cache()

if args.vertex_colors:
    from vertex_bake import worker as bake_vertices
    bake_vertices(SimpleNamespace(checkpoint=args.output/'checkpoints',output=args.output,
        image=args.image[0],render=True,yaw_offset=0))
    proof=json.loads((args.output/'vertex-bake.json').read_text())
    report=dict(worker_sha256=digest(Path(__file__)),backend='Microsoft TRELLIS.2 MLX, native vertex colors',
        native_vertices=proof['vertices'],native_triangles=proof['triangles'],
        output_sha256=proof['output_sha256'],native_checkpoint_sha256=proof['native_checkpoint_sha256'],
        all_native_positions_and_indices_exact=True,seconds=round(time.monotonic()-start,3),
        strict_model_key_checks=key_checks,mlx_peak_bytes=int(mx.get_peak_memory()),
        quantize=args.quantize,resolution_requested=args.resolution,
        actual_mesh_grid_size=json.loads((args.output/'checkpoints/mesh_raw.json').read_text())['mesh_grid_size'])
    write(args.output/'generation-report.json',report)
    print(json.dumps(report),flush=True)
    raise SystemExit(0)
raw=np.load(args.output/'checkpoints/mesh_raw.npz',allow_pickle=False)
vertices=raw['vertices'].astype('float32');faces=raw['faces'].astype('int64')
transformed=vertices.copy();transformed[:,1]=vertices[:,2];transformed[:,2]=-vertices[:,1]
pm=load_module(VENDOR)
exported,uvs,indices,texture=pm.read_glb(args.output/'head.glb')
if not same_triangles(transformed[faces],exported[indices]):
    raise ValueError('TRELLIS export changed a native triangle or winding')
# A raw JSON source in export coordinates permits independent viewer edge audits.
write(args.output/'mesh.json',dict(vertices=transformed.tolist(),faces=faces.tolist()))
report=dict(worker_sha256=digest(Path(__file__)),backend='Microsoft TRELLIS.2 MLX',native_vertices=len(vertices),native_triangles=len(faces),
    output_sha256=digest(args.output/'head.glb'),native_checkpoint_sha256=digest(args.output/'checkpoints/mesh_raw.npz'),
    mesh_sha256=digest(args.output/'mesh.json'),all_native_triangles_and_winding_preserved=True,
    transform='Only fixed Z-up to Y-up axis rotation performed by the pinned export',
    seconds=round(time.monotonic()-start,3),strict_model_key_checks=key_checks,
    mlx_peak_bytes=int(mx.get_peak_memory()),quantize=args.quantize,resolution_requested=args.resolution,
    actual_mesh_grid_size=json.loads((args.output/'checkpoints/mesh_raw.json').read_text())['mesh_grid_size'])
write(args.output/'generation-report.json',report)
print(json.dumps(report),flush=True)
