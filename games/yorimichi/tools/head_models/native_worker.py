"""Real Pixal3D texture inference on MPS, retaining the supplied GLB geometry/UVs."""
from pathlib import Path
from functools import partial
import argparse
import gc
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time

p=argparse.ArgumentParser()
p.add_argument('--root',type=Path,required=True)
p.add_argument('--dataset',type=Path,required=True)
p.add_argument('--mesh',type=Path,required=True)
p.add_argument('--image',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--naf-size',type=int,choices=[512,1024],default=1024)
p.add_argument('--steps',type=int,default=12)
p.add_argument('--mps-gib',type=int,choices=[8,10,12],default=8)
p.add_argument('--condition-size',type=int,choices=[512,1024],default=1024)
args=p.parse_args()
root=args.root.resolve()
os.environ['PATH']=str(Path(sys.executable).parent)+os.pathsep+os.environ['PATH']
repo=root/'pixal3d-mac'
sys.path.insert(0,str(Path(__file__).resolve().parent))
from support import verify_source
verify_source(root,'native')
models_root=root/'models'
args.output.mkdir(parents=True,exist_ok=True)
if (args.output/'native-report.json').exists():raise ValueError('Completed output exists')
os.environ['PYTORCH_ENABLE_MPS_FALLBACK']='1'
os.environ['ATTN_BACKEND']='sdpa'
os.environ['SPARSE_ATTN_BACKEND']='naive'
os.environ['SPARSE_CONV_BACKEND']='flex_gemm'
os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'
os.environ['FLEX_GEMM_AUTOTUNE_CACHE_PATH']=str(args.output.resolve()/'autotune.json')
(args.output/'autotune.json').write_text('{}\n')
checkout=Path.cwd()
sys.path[:0]=[str(repo),str(Path(__file__).resolve().parents[1])]
import numpy as np
from PIL import Image,ImageDraw
import torch
from safetensors.torch import load_file
from safetensors import safe_open
from meshaxiom_pixel_match import load_module, digest, matte, stage
from meshaxiom_quality import verify_geometry,render,write,VENDOR,camera_set

torch.set_num_threads(2)
torch.set_num_interop_threads(2)
if not 1<=args.steps<=40:raise ValueError('Native texture sampling must use1–40 steps')
if not torch.backends.mps.is_available():raise RuntimeError('MPS unavailable')
torch.mps.set_per_process_memory_fraction(min(1.,args.mps_gib*2**30/torch.mps.recommended_max_memory()))
torch.set_grad_enabled(False)
device=torch.device('mps')
import torch.nn.functional as F
original_sdpa=F.scaled_dot_product_attention
def tiled_sdpa(q,k,v,attn_mask=None,dropout_p=0.,is_causal=False,*,scale=None,enable_gqa=False):
    if q.device.type!='mps' or q.shape[-2]<=256:
        return original_sdpa(q,k,v,attn_mask,dropout_p,is_causal,scale=scale,enable_gqa=enable_gqa)
    if is_causal or dropout_p:
        raise ValueError('Bounded head inference requires noncausal attention without dropout')
    output=torch.empty((*q.shape[:-1],v.shape[-1]),dtype=q.dtype,device=q.device)
    for first in range(0,q.shape[-2],256):
        last=min(first+256,q.shape[-2])
        mask=attn_mask
        if mask is not None and mask.ndim>=2 and mask.shape[-2]>1:mask=mask[...,first:last,:]
        output[...,first:last,:]=original_sdpa(q[...,first:last,:],k,v,mask,0.,False,scale=scale,enable_gqa=enable_gqa)
    return output
F.scaled_dot_product_attention=tiled_sdpa
started=time.monotonic()
bindings=json.loads(Path(__file__).with_name('native-weights.json').read_text())
for item in bindings:
    file=models_root/item['repo']/item['file']
    h=hashlib.sha256()
    with file.open('rb') as f:
        for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
    if file.stat().st_size!=item['size_bytes'] or h.hexdigest()!=item['sha256']:
        raise ValueError('Pinned weight changed: '+item['file'])
print('All native texture weight bytes verified',flush=True)

import generate_mps
generate_mps.load_runtime_deps()  # installs the vendored Metal NAF dispatch, no models loaded
from pixal3d import models
from pixal3d.modules.sparse import SparseTensor
from pixal3d.pipelines import samplers
from pixal3d.pipelines.pixal3d_image_to_3d import Pixal3DImageTo3DPipeline
from pixal3d.trainers.flow_matching.mixins.image_conditioned_proj import DinoV3ProjFeatureExtractor
from pixal3d.trainers.flow_matching.mixins.image_conditioned_proj import ProjGrid

# Prove that selecting queried grid points before projection preserves their values.
probe=ProjGrid(grid_resolution=4,image_resolution=32)
features=torch.linspace(-1,1,8*8*6).reshape(1,8,8,6)
selected=torch.tensor([0,7,9,24,39,51,63])
probe_args=[torch.tensor([.4]),torch.tensor([3.]),torch.tensor([1.])]
full=probe(features,*probe_args)
probe.grid_points=probe.grid_points[selected]
subset=probe(features,*probe_args)
if not torch.equal(full[:,selected],subset):
    raise ValueError('Sparse projected conditioning differs from full-grid values')
print('Projected-grid subset equivalence passed exactly on CPU control',flush=True)
del probe,features,full,subset

# The upstream helper imports the CUDA rasterizer even for its independent encode/decode
# methods. Bind that import to the real Metal package; its CUDA-only bake is never called.
file=repo/'pixal3d/pipelines/trellis2_texturing.py'
source=file.read_text()
old='import nvdiffrast.torch as dr'
if source.count(old)!=1:raise ValueError('Texturing helper import anchor changed')
source=source.replace(old,'import mtldiffrast.torch as dr')
old_faces='faces = torch.from_numpy(mesh.faces).long()'
if source.count(old_faces)!=1:raise ValueError('CPU voxelizer index adapter anchor changed')
source=source.replace(old_faces,'faces = torch.from_numpy(mesh.faces).int()')
spec=importlib.util.spec_from_loader('pixal3d.pipelines.atelier_texturing',loader=None)
module=importlib.util.module_from_spec(spec)
exec(compile(source,str(file),'exec'),module.__dict__)
Texture=module.Trellis2TexturingPipeline
extension=root/'voxelizer-build/atelier_mesh_voxelizer.so'
spec=importlib.util.spec_from_file_location('atelier_mesh_voxelizer',extension)
voxelizer=importlib.util.module_from_spec(spec)
spec.loader.exec_module(voxelizer)
import importlib
cpu_conversion=importlib.import_module('o_voxel.convert.flexible_dual_grid')
cpu_conversion._C=voxelizer
cpu_conversion._HAS_C=True
model_checks={}

def release():
    gc.collect();torch.mps.synchronize();torch.mps.empty_cache()
    print(f'Released stage models; MPS active {torch.mps.current_allocated_memory()/2**30:.2f} GiB, driver {torch.mps.driver_allocated_memory()/2**30:.2f} GiB',flush=True)

def load(prefix):
    config=json.loads(prefix.with_suffix('.json').read_text())
    print('Loading pinned',prefix.name,flush=True)
    with torch.device('meta'):
        model=getattr(models,config['name'])(**config['args'])
    expected=model.state_dict()
    state=load_file(str(prefix.with_suffix('.safetensors')),device='cpu')
    if set(state)!=set(expected) or any(state[k].shape!=expected[k].shape for k in state):
        raise ValueError('Incomplete or mismatched native model state')
    state={k:v.to(dtype=expected[k].dtype) for k,v in state.items()}
    model.load_state_dict(state,strict=True,assign=True)
    # These deterministic frequency tensors are deliberately outside state_dict.
    # Recreate precisely the constructor formula after allocation on meta.
    for sub in model.modules():
        for key,value in list(vars(sub).items()):
            if isinstance(value,torch.Tensor) and value.is_meta:
                if key!='freqs' or not hasattr(sub,'freq_dim'):
                    raise ValueError(f'Unmaterialized non-checkpoint tensor: {type(sub).__name__}.{key}')
                frequencies=torch.arange(sub.freq_dim,dtype=torch.float32,device='cpu')/sub.freq_dim
                if hasattr(sub,'rope_freq'):
                    sub.freqs=sub.rope_freq[0]/(sub.rope_freq[1]**frequencies)
                elif type(sub).__name__=='AbsolutePositionEmbedder':
                    sub.freqs=1./(10000**frequencies)
                else:raise ValueError('Unknown deterministic position frequency formula')
    model.eval().requires_grad_(False)
    model_checks[prefix.name]=dict(keys=len(state),strict_complete_state=True)
    del state,expected
    return model.to(device)

pm=load_module(VENDOR)
pm.rasterize=partial(pm.rasterize,chunk=256)
model_path,cameras=camera_set(args.dataset,args.image)
if digest(model_path)!=cameras['mesh_sha256']:raise ValueError('Prepared mesh changed')
verify_geometry(args.mesh,model_path,pm)
positions,uvs,faces,base=pm.read_glb(model_path)
camera=next(c for c in cameras['views'] if c['name']=='yaw60-pitch-5')
matrix=np.asarray(camera['transform_matrix'])
rotated=positions@matrix[:3,:3]
center=(rotated.min(0)+rotated.max(0))/2
scale=.9/np.ptp(rotated,axis=0).max()
cam=(matrix[:3,3]@matrix[:3,:3]-center)*scale
aligned=(rotated-center)*scale-np.array([cam[0],cam[1],0])
if abs(aligned).max()>=.5 or cam[2]<=.5:raise ValueError('Conditioning alignment exceeds voxel bounds')
write(args.output/'alignment.json',dict(source_camera=camera,uniform_scale=float(scale),
    rotated_center=center.tolist(),camera_normalized=cam.tolist(),temporary_only=True,
    note='Rigid camera alignment for neural support only; exported buffers remain exact source bytes'))
pipeline=json.loads((models_root/'TencentARC/Pixal3D/pipeline.json').read_text())['args']
s= pipeline['tex_slat_sampler']
pipe=Pixal3DImageTo3DPipeline({},tex_slat_sampler=getattr(samplers,s['name'])(**s['args']),
    tex_slat_sampler_params={**s['params'],'steps':args.steps},low_vram=True,
    shape_slat_normalization=pipeline['shape_slat_normalization'],
    tex_slat_normalization=pipeline['tex_slat_normalization'])
pipe.to(device)
import trimesh
mesh=trimesh.Trimesh(vertices=aligned,faces=faces,process=False)
encoder=load(models_root/'microsoft/TRELLIS.2-4B/ckpts/shape_enc_next_dc_f16c32_fp16')
pipe.models={'shape_slat_encoder':encoder}
with stage('Native supplied-shape encoder 1024'):
    shape=Texture.encode_shape_slat(pipe,mesh,1024)
print(f'Encoded fixed head: {len(shape.coords)} latent tokens',flush=True)
pipe.models={};del encoder;release()

with stage(f'Native DINOv3 + NAF projected conditioning ({args.naf_size})'):
    condition_model=DinoV3ProjFeatureExtractor(str(models_root/'camenduru/dinov3-vitl16-pretrain-lvd1689m'),
        image_size=args.condition_size,grid_resolution=64,use_naf_upsample=True,naf_target_size=args.naf_size).eval()
    naf=torch.hub.load(str(root/'naf'),'naf',source='local',pretrained=False,device='cpu')
    naf.load_state_dict(torch.load(models_root/'valeoai/NAF/naf_release.pth',map_location='cpu',weights_only=True),strict=True)
    condition_model.naf_model=naf.eval().requires_grad_(False)
    image=Image.fromarray(matte(Image.open(args.image))).convert('RGB')
    # Upstream computes 64^3 projected vectors, then selects the occupied tokens.
    # Select those same deterministic grid points before image sampling instead.
    coords=shape.coords[:,1:].long()
    if not bool(((coords>=0)&(coords<64)).all()):raise ValueError('Shape token outside projected grid')
    point_ids=(coords[:,0]*64*64+coords[:,1]*64+coords[:,2]).cpu()
    condition_model.proj_grid.grid_points=condition_model.proj_grid.grid_points[point_ids]
    condition_model.to(device)
    global_features,projected_features=condition_model([image],
        camera_angle_x=torch.tensor([camera['camera_angle_x']],device=device),
        distance=torch.tensor([float(cam[2])],device=device),mesh_scale=torch.tensor([1.],device=device))
    features=projected_features[0]
    condition={'cond':{'global':global_features,'proj':SparseTensor(feats=features,coords=shape.coords)},
               'neg_cond':{'global':torch.zeros_like(global_features),'proj':SparseTensor(feats=torch.zeros_like(features),coords=shape.coords)}}
    del projected_features,global_features,features
del condition_model,naf;release()
flow=load(models_root/'TencentARC/Pixal3D/ckpts/slat_flow_imgshape2tex_dit_1_3B_1024_bf16')
torch.manual_seed(42)
with stage('Native texture-only flow sampling'):
    texture=pipe.sample_tex_slat(condition,flow,shape)
del condition,flow;release()
texture._spatial_cache=shape._spatial_cache
texture._scale=shape._scale
decoder=load(models_root/'microsoft/TRELLIS.2-4B/ckpts/tex_dec_next_dc_f16c32_fp16')
pipe.models={'tex_slat_decoder':decoder}
with stage('Native PBR decoder on supplied shape support'):
    pbr=Texture.decode_tex_slat(pipe,texture)
pipe.models={};del decoder,texture;release()
if not bool(torch.isfinite(pbr.feats).all()):raise ValueError('Native PBR decoder produced nonfinite attributes')
np.savez_compressed(args.output/'native-pbr.npz',coords=pbr.coords.cpu().numpy(),attributes=pbr.feats.cpu().numpy())

with stage('Bake native PBR onto existing UVs; no mesh changes'):
    import flex_gemm
    h,w=base.shape[:2]
    face,bary=pm.rasterize((uvs*np.array([w,h]))[faces],np.zeros((len(faces),3)),(h,w))
    mask=face>=0
    points=(aligned[faces[face[mask]]]*bary[mask,:,None]).sum(1)
    result=np.zeros((len(points),6),dtype='float32')
    for start in range(0,len(points),65536):
        grid=torch.tensor((points[start:start+65536]+.5)*1024,dtype=torch.float32,device=device).reshape(1,-1,3)
        values=flex_gemm.ops.grid_sample.grid_sample_3d(pbr.feats,pbr.coords,
            shape=torch.Size([*pbr.shape,*pbr.spatial_shape]),grid=grid,mode='trilinear')
        result[start:start+len(grid[0])]=values.reshape(-1,6).float().cpu().numpy()
    if not np.isfinite(result).all():raise ValueError('Native PBR sampling produced nonfinite attributes')
    attrs=np.zeros((h,w,6),dtype='float32');attrs[mask]=result
    import cv2
    color=np.clip(attrs[...,:3]*255,0,255).astype('uint8')
    color=cv2.inpaint(color,(~mask).astype('uint8'),3,cv2.INPAINT_TELEA)
    rgba=np.concatenate([color,np.full((h,w,1),255,dtype='uint8')],axis=-1)
    mr=np.stack([np.zeros((h,w)),attrs[...,4],attrs[...,3]],axis=-1)
    mr=cv2.inpaint(np.clip(mr*255,0,255).astype('uint8'),(~mask).astype('uint8'),1,cv2.INPAINT_TELEA)
    Image.fromarray(rgba).save(args.output/'base-color.png')
    Image.fromarray(mr).save(args.output/'metallic-roughness.png')
    data=pm.replace_base_colour(model_path.read_bytes(),pm.encode_png(rgba))
    doc,binary=pm._split_glb(data)
    png=pm.encode_png(mr);binary+=b'\0'*(-len(binary)%4)
    view_id=len(doc['bufferViews']);doc['bufferViews'].append(dict(buffer=0,byteOffset=len(binary),byteLength=len(png)))
    binary+=png;doc['buffers'][0]['byteLength']=len(binary)
    image_id=len(doc['images']);doc['images'].append(dict(bufferView=view_id,mimeType='image/png'))
    texture_id=len(doc['textures']);doc['textures'].append(dict(source=image_id))
    material=doc['materials'][0]['pbrMetallicRoughness']
    material.update(metallicRoughnessTexture=dict(index=texture_id),metallicFactor=1.,roughnessFactor=1.)
    output=args.output/'head-native.glb';output.write_bytes(pm._join_glb(doc,binary))
    before_doc,before_binary=pm._split_glb(model_path.read_bytes())
    image_view=before_doc['images'][pm.base_colour_image_index(before_doc)]['bufferView']
    for index,a in enumerate(before_doc['bufferViews']):
        if index==image_view:continue
        b=doc['bufferViews'][index]
        if before_binary[a.get('byteOffset',0):a.get('byteOffset',0)+a['byteLength']]!=binary[b.get('byteOffset',0):b.get('byteOffset',0)+b['byteLength']]:
            raise AssertionError('Native texture bake changed a mesh buffer')
    geometry=verify_geometry(args.mesh,output,pm)
    write(args.output/'geometry-verification.json',geometry)
del pbr,shape;release()
report=dict(worker_sha256=digest(Path(__file__)),method='MeshAxiom documented Pixal3D texture flow + TRELLIS.2 supplied-shape encoder/PBR decoder; MPS adapter',
    output_sha256=digest(output),native_triangles=len(faces),geometry_changed=False,non_image_buffers_identical=True,
    naf_target_size=args.naf_size,image_conditioning_size=args.condition_size,
    texture_resolution=[w,h],shape_resolution=1024,steps=args.steps,seed=42,
    weight_bindings=bindings,model_key_checks=model_checks,seconds=round(time.monotonic()-started,3),
    source_commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip(),
    encoder_decoder_import_adapter_sha256=hashlib.sha256(source.encode()).hexdigest(),
    reference_sha256=digest(args.image),camera_manifest_sha256=digest(args.dataset/'guides/cameras.json'))
write(args.output/'native-report.json',report)
contact=Image.new('RGB',(1536,816));draw=ImageDraw.Draw(contact)
for index,camera in enumerate(cameras['views']):
    view=pm.View(np.zeros((1024,1024,4),dtype='uint8'),np.array(camera['transform_matrix']),camera['camera_angle_x'],camera['name'])
    pixels,_=render(pm,positions,faces,view,rgba,uvs)
    Image.fromarray(pixels).save(args.output/(camera['name']+'.png'))
    contact.paste(Image.fromarray(pixels).convert('RGB').resize((384,384)),(index%4*384,index//4*408))
    draw.text((index%4*384+8,index//4*408+386),camera['name'],fill='white')
    print(f'Native texture diagnostic {index+1}/8 complete',flush=True)
contact.save(args.output/'contact.png')
print(json.dumps(report),flush=True)
