"""One isolated Apple Silicon geometry stage, intended to run inside Atelier's memory guard."""
import argparse
import gc
import hashlib
import json
from pathlib import Path
import time


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n')


def validate_vertex_input(args):
    """@cc [owner:fontanierh,label:correctness] meshaxiom-stage-input-identity
    A resumed topology stage MUST reject vertices from another image, recipe, revision or byte identity
    before loading a model. A coarse probe MUST NOT be accepted as complete vertex generation.
    """
    from . import SOURCE_REVISION, MODEL_REVISION
    report=json.loads((args.output/'vertex-report.json').read_text())
    expected=dict(status='complete',stage='vertex',source_revision=SOURCE_REVISION,
                  model_revision=MODEL_REVISION,face_budget=args.face_budget,steps=args.steps,seed=args.seed,
                  input_sha256=hashlib.sha256(args.image.read_bytes()).hexdigest())
    if any(report.get(k)!=v for k,v in expected.items()) or 'probe_completed_level' in report:
        raise ValueError('Vertex result does not match this image, recipe and pinned revisions')
    path=args.output/'vertices.npz'
    if not report.get('vertices_sha256') or hashlib.sha256(path.read_bytes()).hexdigest()!=report['vertices_sha256']:
        raise ValueError('Vertex byte identity does not match its completed report')


def vertex(args, model, cfg, ctx):
    import numpy as np
    import torch
    from meshaxiom_core.sample import flow_from, vertex_level_stream_seeds
    from meshaxiom_core.models.octree_dit import node_positions
    from meshaxiom_core.data.mesh_ops import expand_children, sort_by_key
    from .apple import sample, progress
    flow = flow_from(cfg)
    uc = model.cond.null_ctx(1).to(ctx.dtype)
    generators = [[torch.Generator(device='cpu').manual_seed(s) for s in vertex_level_stream_seeds(args.seed+k,9)] for k in range(8)]
    candidates = [[np.zeros((1,3), dtype=np.int64)] for _ in range(8)]
    chosen = None
    for d in range(1, args.stop_level+1):
        batches = candidates if d<=3 else [candidates[chosen]]
        parents = [c[-1] for c in batches]
        lengths = torch.tensor([len(p) for p in parents],device='mps')
        n = max(map(len,parents)); batch = len(parents)
        if n>args.max_nodes:
            raise RuntimeError(f'Level {d} has {n} parents beyond safe configured limit {args.max_nodes}')
        pc = torch.zeros(batch,n,3,dtype=torch.long,device='mps')
        noise = torch.zeros(batch,n,8)
        for k,p in enumerate(parents):
            pc[k,:len(p)] = torch.from_numpy(p).to('mps')
            generator = generators[k if d<=3 else chosen][d-1]
            noise[k,:len(p)] = torch.randn(len(p),8,generator=generator)
        pos = node_positions(pc,9,d-1)
        level = torch.full((batch,),d,dtype=torch.long,device='mps')
        cond, uncond = ctx.expand(batch,-1,-1),uc.expand(batch,-1,-1)
        mf = lambda x,t: model.dit(x,t,pos,ctx=cond,lengths=lengths if batch>1 else None,level=level)
        uf = lambda x,t: model.dit(x,t,pos,ctx=uncond,lengths=lengths if batch>1 else None,level=level)
        progress(f'Vertex level {d}/9, batch={batch}, max parents={n}')
        occ = sample(flow,mf,noise.to('mps'),steps=args.steps,cfg=3. if d<=4 else 5.,uncond_fn=uf,label=f'vertex level {d}').cpu().numpy()
        for k,p in enumerate(parents):
            child = expand_children(p,occ[k,:len(p)],0.4)
            if len(child)==0:
                # Same empty fallback as the released sampler: strongest child per parent.
                onehot=np.zeros_like(occ[k,:len(p)]);onehot[np.arange(len(p)),occ[k,:len(p)].argmax(1)]=1
                child=expand_children(p,onehot,0.5)
            if len(child)>args.max_nodes:
                raise RuntimeError(f'Level {d} expanded to {len(child)} nodes; refusing truncation above {args.max_nodes}')
            batches[k].append(child)
        if d==3:
            sets=[{tuple(x) for x in c[-1].tolist()} for c in candidates]
            consensus=[float(np.mean([len(sets[i]&sets[j])/max(len(sets[i]|sets[j]),1) for j in range(8) if j!=i])) for i in range(8)]
            chosen=int(np.argmax(consensus))
            print(f'MBR8 chose candidate {chosen}, consensus={consensus}',flush=True)
        write_json(args.output/f'level-{d}.json',{'level':d,'candidate_nodes':[len(c[-1]) for c in batches],'chosen':chosen})
        torch.mps.empty_cache()
    if args.stop_level==9:
        coords=sort_by_key(candidates[chosen][-1])
        if not 0<len(coords)<=26000:
            raise RuntimeError('Vertex result exceeds released topology contract')
        np.savez_compressed(args.output/'vertices.npz',coords=coords.astype(np.int16))
        return {'vertices':len(coords),'levels':[len(x) for x in candidates[chosen]],'chosen':chosen,
                'vertices_sha256':hashlib.sha256((args.output/'vertices.npz').read_bytes()).hexdigest()}
    return {'probe_completed_level':args.stop_level}


def topology(args, bundle):
    model, cfg, ctx = (bundle.pop(k) for k in ('model', 'cfg', 'ctx'))
    import numpy as np
    import torch
    from meshaxiom_core.sample import flow_from
    from .apple import cache_geometry, sample, progress, move_model
    from meshaxiom.vendor.recipe import decode_policy90 as decoder
    from meshaxiom_core.models.topo_vae import build_vae
    from meshaxiom_core.config import Cfg
    coords=np.load(args.output/'vertices.npz')['coords'].astype(np.int64)
    c=torch.from_numpy(coords)[None].to('mps')
    cache_geometry(model,c)
    # Preserve the released policy, including mean/sample self-conditioning and its bounded repairs.
    pol=decoder.policy();pol['steps']=args.steps
    def sampler(model_fn,x_init,steps=20,sampler='dpmpp2m',cfg_scale=1.,uncond_fn=None):
        if sampler!='dpmpp2m':raise ValueError('Only the pinned DPM++2M recipe is supported')
        return sample(None,model_fn,x_init,steps=steps,cfg=cfg_scale,uncond_fn=uncond_fn,label='topology')
    flow=flow_from(cfg);flow.sample=sampler
    generator=torch.Generator(device='mps').manual_seed(1574365204)
    progress(f'Topology sampling {len(coords)} vertices')
    with torch.autocast('mps',dtype=torch.bfloat16):
        latent=decoder.sample_latents(model,ctx,c,flow,generator,pol)
    if isinstance(latent,dict):
        latent={k:(v.cpu() if torch.is_tensor(v) else v) for k,v in latent.items()}
    elif torch.is_tensor(latent):latent=latent.cpu()
    else:raise RuntimeError('Unexpected latent recipe')
    # The expensive transformer exits residency before the small VAE decoder is allocated.
    del model,ctx,c,flow
    gc.collect();torch.mps.empty_cache()
    progress('Topology latents complete; loading VAE')
    from .install import verify_one
    verify_one(args.root,'vae')
    ck=torch.load(args.root/'models/weights/vae-ema.pt',map_location='cpu',mmap=True,weights_only=True)
    with torch.device('meta'):vae=build_vae(Cfg(ck['cfg']))
    vae.load_state_dict(ck['ema'],strict=True,assign=True)
    for name in ('in_proj','type_embed','graph','graph_norm','enc_attn','enc_norm','to_latent'):
        setattr(vae,name,None)
    del ck
    vae=move_model(vae)
    pos=torch.from_numpy((coords.astype(np.float32)+.5)/512*2-1)[None].to('mps')
    vlen=torch.tensor([len(coords)],device='mps')
    with torch.autocast('mps',dtype=torch.bfloat16):
        if isinstance(latent,dict):
            edge,face=vae.decode(latent['mean'].to('mps').float(),pos,vlen)
            e2,f2=vae.decode(latent['draw'].to('mps').float(),pos,vlen)
            embeddings=[x.float().cpu() for x in (edge,face,e2,f2)]
        else:
            embeddings=[x.float().cpu() for x in vae.decode(latent.to('mps').float(),pos,vlen)]
    metric=vae.metric;et=float(vae.edge_thresh);ft=float(vae.face_thresh)
    del vae,pos,vlen,latent
    gc.collect();torch.mps.empty_cache()
    # All geometry extraction is CPU; bound pair tiles and preserve the published threshold/merge policy.
    from meshaxiom_core.topology.spacetime import extract_mesh_topology
    print('CPU topology extraction and published edge-capacity repair',flush=True)
    lod=2*len(coords);max_edges=int(float(pol.get('edge_cap',0))*1.5*lod) or 4_000_000
    def extract(ze,zf):
        e,f,info=extract_mesh_topology(ze[0],zf[0],metric,et,ft,max_edges=max_edges,return_info=True)
        if pol.get('prune')=='edge_capacity2':f=decoder.prune_edge_capacity(zf[0],f,metric,2)
        return e,f,info
    e,f,info=extract(*embeddings[:2])
    if len(embeddings)==4:
        e2,f2,_=extract(*embeddings[2:])
        f=decoder.merge_faces_by_capacity(embeddings[1][0],f2,f,metric,2,attached=True)
        e=torch.unique(torch.cat([e,e2]),dim=0)
    faces=f.numpy().astype(np.int64);edges=e.numpy().astype(np.int64)
    from meshaxiom.vendor.recipe import mesh_utils90 as mesh
    from meshaxiom.workers.topology import write_mesh_exports
    world=(coords.astype(np.float64)+.5)/512*2-1
    exported,orientation=mesh.export_faces(world,faces)
    if 'module' in orientation:
        orientation['module']='meshaxiom/vendor/recipe/orient_faces.py'
    if not len(exported):raise RuntimeError('Generated mesh has no faces')
    write_mesh_exports(args.output,world,exported,'MeshAxiom Apple Silicon BF16 reference port')
    np.savez_compressed(args.output/'topology.npz',coords=coords.astype(np.int16),faces=faces.astype(np.int32),export_faces=exported.astype(np.int32),edges=edges.astype(np.int32))
    return {'vertices':len(coords),'faces':len(faces),'policy':pol,'extraction':info,'orientation':orientation}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--image',type=Path,required=True);p.add_argument('--stage',choices=['vertex','topology'],required=True)
    p.add_argument('--face-budget',type=int,default=2000);p.add_argument('--steps',type=int,default=20)
    p.add_argument('--seed',type=int,default=2026082301);p.add_argument('--stop-level',type=int,default=9)
    p.add_argument('--max-nodes',type=int,default=8192);p.add_argument('--load-only',action='store_true')
    args=p.parse_args()
    if not (1<=args.face_budget<=16000 and 1<=args.steps<=40 and 1<=args.max_nodes<=26000 and 1<=args.stop_level<=9):
        p.error('face budget 1–16000, steps 1–40, max nodes 1–26000 and stop level 1–9 are required')
    args.root=args.root.resolve();args.output.mkdir(parents=True,exist_ok=True)
    if args.stage=='topology':
        validate_vertex_input(args)
    import torch
    torch.set_num_threads(2)
    if not torch.backends.mps.is_available():raise RuntimeError('Apple MPS is required')
    from .apple import load_model,progress
    from PIL import Image
    start=time.monotonic()
    model,cfg,processor=load_model(args.root,args.stage)
    pixels=processor(images=Image.open(args.image).convert('RGB').resize((512,512)),do_resize=True,size={'height':512,'width':512},return_tensors='pt')['pixel_values'].to('mps')
    with torch.inference_mode(),torch.autocast('mps',dtype=torch.bfloat16):
        ctx=model.cond(image=pixels,lod=torch.tensor([float(args.face_budget)],device='mps')).float()
    progress(f'Image encoded: {tuple(ctx.shape)}')
    if not bool(ctx.isfinite().all()):raise RuntimeError('Nonfinite image conditioning')
    if args.load_only:
        result={'conditioning_shape':list(ctx.shape)}
    else:
        with torch.inference_mode():
            if args.stage=='vertex':
                result=vertex(args,model,cfg,ctx)
            else:
                bundle=dict(model=model,cfg=cfg,ctx=ctx)
                del model,cfg,ctx
                result=topology(args,bundle)
    from . import SOURCE_REVISION,MODEL_REVISION
    result.update(stage=args.stage,seconds=round(time.monotonic()-start,2),torch=torch.__version__,device='mps',linear_dtype='bfloat16',source_revision=SOURCE_REVISION,model_revision=MODEL_REVISION,face_budget=args.face_budget,steps=args.steps,seed=args.seed,input_sha256=hashlib.sha256(args.image.read_bytes()).hexdigest(),status='complete')
    write_json(args.output/f'{args.stage}-report.json',result)
    print(json.dumps(result),flush=True)

if __name__=='__main__':main()
