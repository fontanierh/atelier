"""Apple GPU adaptations; model tensors and diffusion/geometry definitions stay upstream."""
import gc
import time
from pathlib import Path


def progress(message):
    import torch
    torch.mps.synchronize()
    print(f'{message}; MPS active={torch.mps.current_allocated_memory()/2**30:.2f} GiB '
          f'driver={torch.mps.driver_allocated_memory()/2**30:.2f} GiB', flush=True)


def install_operations(query_chunk=256):
    """@cc [owner:fontanierh,label:safety] bounded-apple-attention
    Attention MUST preserve every key/value token while bounding each query tile to query_chunk.
    FP64 position work MUST run on CPU; neither adaptation may truncate the geometry sequence.
    """
    import torch
    from meshaxiom_core.models import layers
    original_rope = layers.RoPE3D.cos_sin
    def cpu_rope(self, pos):
        # Upstream deliberately accumulates these small tables in FP64. Preserve that arithmetic.
        cpu = pos.detach().cpu()
        key = (tuple(cpu.shape), pos.device)
        cached = getattr(self, '_apple_rope', None)
        if cached is not None and cached[0] == key and torch.equal(cpu, cached[1]):
            return cached[2]
        # The upstream method only reads inv_i; keep CPU copies separate from the live module buffers.
        angles = []
        for i in range(3):
            inv = getattr(self, f'inv_{i}').detach().cpu().double()
            a = cpu[..., i:i+1].double()*inv.reshape(*([1]*(cpu.dim()-1)), -1)
            angles.append(torch.repeat_interleave(a, 2, dim=-1))
        angle = torch.cat(angles, dim=-1)
        result = (angle.cos().float().to(pos.device), angle.sin().float().to(pos.device))
        self._apple_rope = (key, cpu, result)
        return result
    layers.RoPE3D.cos_sin = cpu_rope
    def attention(q, k, v, mask=None):
        pieces = []
        for begin in range(0, q.shape[-2], query_chunk):
            tile = mask
            if mask is not None and mask.shape[-2] != 1:
                tile = mask[..., begin:begin+query_chunk, :]
            pieces.append(torch.nn.functional.scaled_dot_product_attention(
                q[..., begin:begin+query_chunk, :], k, v, attn_mask=tile))
        return torch.cat(pieces, dim=-2)
    layers._sdpa = attention
    return original_rope, attention


def restore_buffers(model):
    """Recreate nonpersistent position tables omitted from checkpoint state on meta construction."""
    import torch
    for module in model.modules():
        missing = [k for k,v in module._buffers.items() if v is not None and v.is_meta]
        if not missing:
            continue
        if type(module).__name__ == 'RoPE3D':
            fresh = type(module)(module.head_dim)
        elif type(module).__name__ == 'DINOv3ViTRopePositionEmbedding':
            fresh = type(module)(module.config)
        else:
            fresh = None
        for name in missing:
            if fresh is not None:
                module._buffers[name] = fresh._buffers[name]
            elif name in ('edge_thresh', 'face_thresh'):
                module._buffers[name] = torch.zeros(())
            else:
                raise RuntimeError(f'Unknown nonpersistent meta buffer: {type(module).__name__}.{name}')


def move_model(model, *, device='mps'):
    """Move one parameter at a time, using BF16 for Linear layers and FP32 elsewhere."""
    import torch
    restore_buffers(model)
    model.eval().requires_grad_(False)
    started, spoken = time.monotonic(), time.monotonic()
    count = sum(p.numel() for p in model.parameters())
    completed = 0
    for module in model.modules():
        for name, parameter in module._parameters.items():
            if parameter is not None:
                dtype = torch.bfloat16 if isinstance(module, torch.nn.Linear) else parameter.dtype
                parameter.data = parameter.detach().to(device=device, dtype=dtype)
                completed += parameter.numel()
        for name, value in module._buffers.items():
            if value is not None:
                module._buffers[name] = value.to(device=device)
        if time.monotonic()-spoken > 20:
            progress(f'Model load {completed/count:.0%}, elapsed {time.monotonic()-started:.0f}s')
            spoken = time.monotonic()
    gc.collect()
    progress(f'Loaded {count/1e9:.3f}B parameters in {time.monotonic()-started:.1f}s')
    return model


def load_model(root, stage):
    """Build on meta, assign mmap tensors strictly, then move only the image inference paths."""
    import torch
    from meshaxiom.vendor.recipe.runtime import activate_namespace
    activate_namespace('vertex' if stage=='vertex' else 'topology')
    from meshaxiom_core.config import Cfg
    from meshaxiom.workers.offline_encoder import offline_encoder
    from transformers import AutoImageProcessor
    # Resolve the lazy Transformers module before entering the meta default-device context.
    from transformers.models.dinov3_vit.modeling_dinov3_vit import DINOv3ViTModel  # noqa: F401
    root = Path(root)
    from .install import verify_one, verify_source
    verify_source(root)
    verify_one(root, stage)
    ck = torch.load(root/f'models/weights/{stage}-ema.pt', mmap=True, map_location='cpu', weights_only=True)
    cfg = Cfg(ck['cfg'])
    cfg.set_path('condition.model_id', str(root/'models/external/dinov3'))
    install_operations()
    with torch.device('meta'), offline_encoder(str(root/'models/external/dinov3')):
        if stage=='vertex':
            from meshaxiom_core.models.octree_dit import VertexModel
            model = VertexModel(cfg)
        else:
            from meshaxiom_core.models.topo_dit import TopologyModel
            from meshaxiom.vendor.recipe import model118rich
            if ck.get('v113', {}).get('version') != 'meshaxiom-topology-richknn-v118':
                raise ValueError('Unsupported topology architecture')
            model = model118rich.upgrade(TopologyModel(cfg), knn=True)
    model.load_state_dict(ck['ema'], strict=True, assign=True)
    if stage=='topology':
        model.dit.set_latent_stats(ck['latent_stats']['mean'], ck['latent_stats']['std'])
    if stage=='vertex':
        model.cond.encoder = None  # Point-cloud branch is unreachable for image-only inference.
    del ck
    model = move_model(model)
    processor = AutoImageProcessor.from_pretrained(root/'models/external/dinov3', local_files_only=True)
    return model, cfg, processor


def cache_geometry(model, coords):
    """Cache static CPU nearest-neighbour/PCA features and feed the original trained topology layers."""
    import torch
    import types
    from meshaxiom.vendor.recipe import model118rich
    print(f'Computing CPU kNN/PCA once for {coords.shape[1]} vertices', flush=True)
    features = model118rich.knn_features(coords.cpu(), None, chunk=512).to(coords.device)
    def forward(self, x, t, coords, lengths=None, ctx=None, sc=None, **unused):
        sc = torch.zeros_like(x) if sc is None else sc.to(x.dtype)
        extended = torch.cat([x, sc, features.to(x.dtype)], dim=-1)
        return self.dit.net(extended, t, coords.float()+0.5, ctx=ctx, lengths=lengths)
    model.forward = types.MethodType(forward, model)


def sample(flow, model_fn, x, *, steps=20, cfg=1., uncond_fn=None, label='diffusion'):
    """Upstream DPM++2M schedule with explicit stage progress and CPU scalar bookkeeping."""
    import torch
    from meshaxiom_core.diffusion.flow import LAMBDA_EPS
    # Avoid an implicit MPS scalar synchronization for every sampler expression.
    ts = torch.linspace(0., 1., steps+1, dtype=torch.float32)
    lam = torch.logit(ts.clamp(LAMBDA_EPS, 1.-LAMBDA_EPS))
    d_prev, h_prev = None, None
    started = time.monotonic()
    for i in range(steps):
        tc, tn = ts[i], ts[i+1]
        tb = torch.full((x.shape[0],), float(tc), device=x.device)
        with torch.autocast('mps', dtype=torch.bfloat16):
            v = model_fn(x, tb)
            if cfg != 1. and uncond_fn is not None:
                vu = uncond_fn(x, tb)
                v = vu + cfg*(v-vu)
        d = x + float(1.-tc)*v.float()
        h = lam[i+1]-lam[i]
        if d_prev is None or i==steps-1:
            d_use = d
        else:
            r = h_prev/h
            d_use = float(1+1/(2*r))*d-float(1/(2*r))*d_prev
        emh = float(tc*(1.-tn)/((1.-tc)*tn))
        x = float((1.-tn)/(1.-tc))*x+float(tn)*(1.-emh)*d_use
        d_prev, h_prev = d, h
        torch.mps.synchronize()
        if not bool(x.isfinite().all()):
            raise RuntimeError(f'Nonfinite {label} state at step {i+1}')
        print(f'{label}: step {i+1}/{steps}, tokens={x.shape[1]}, elapsed={time.monotonic()-started:.1f}s', flush=True)
    return x
