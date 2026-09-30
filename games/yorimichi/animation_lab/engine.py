"""UniMate inference on an owned, previously unseen body skeleton.

Uses upstream topology/collation/rotation decoding, the released EMA weights,
and Flan-T5. No training dataset or third-party character assets are required.
"""
import hashlib
import json
import sys
import time
from pathlib import Path

TEXT_REVISION = '7bcac572ce56db69c1ea7c8af255c5d7c9672fc2'

class Engine:
    def __init__(self, root, device='mps'):
        self.root = Path(root).resolve()
        sys.path.insert(0, str(self.root / 'upstream'))
        import numpy as np
        import torch
        from scipy.sparse.csgraph import shortest_path
        from transformers import T5EncoderModel, T5Tokenizer
        from unimate.configs.schema import MainConfig
        from unimate.models.factory import create_model
        from data_process.utils.motion_features import build_topology_cond
        from data_process.joint_annotation.names_clean_rule import clean_joint_name, post_process
        from unimate.dataset.transforms import apply_normalization, build_parent_features
        self.np, self.torch = np, torch
        torch.set_num_threads(4)
        if device == 'mps' and not torch.backends.mps.is_available():
            device = 'cpu'
        self.device = device
        self.config = c = MainConfig.from_json(self.root / 'model/config.json')
        self.rig = rig = json.loads((self.root / 'assets/rig.json').read_text())
        # Joint-name embeddings are learned on the anatomical training vocabulary,
        # including capitalization. Reuse upstream cleaning rather than guessing
        # from CamelCase: Mixamo Leg means Shin, Arm means Upper Arm, and all
        # numbered spine segments are named Spine.
        rig['clean_names'] = [post_process(clean_joint_name(name, 'mixamo')) for name in rig['names']]
        parents = np.array(rig['parents'])
        points = np.array(rig['positions'], dtype=np.float32)
        n = len(parents)
        if n > c.dataset.max_joints:
            raise ValueError('Conditioning skeleton exceeds checkpoint joint limit')
        # Training canonicalization uses the longest leaf-to-leaf tree distance.
        dist = np.full((n, n), np.inf)
        np.fill_diagonal(dist, 0)
        for j, p in enumerate(parents):
            if p >= 0:
                dist[j, p] = dist[p, j] = np.linalg.norm(points[j] - points[p])
        self.scale = 2.0 / shortest_path(dist, directed=False).max()
        points *= self.scale
        points[:, 1] -= points[:, 1].min()
        self.floor_offset = min(p[1] for p in rig['positions'])
        offsets = points.copy()
        for j, p in enumerate(parents):
            if p >= 0:
                offsets[j] -= points[p]
        identity = np.tile([1., 0, 0, 0], (n, 1))
        topology = build_topology_cond('FoxHunter', parents, offsets, rig['names'], rig['clean_names'],
            points, identity, identity, max_freqs=c.model.max_freqs, scale_factor=self.scale)
        stats = np.load(self.root / 'model/dataset_stats.npy', allow_pickle=True).item()['mixamo']
        mean = np.tile(stats['mean_local'], (n, 1)).astype(np.float32)
        std = np.tile(stats['std_local'], (n, 1)).astype(np.float32)
        mean[0], std[0] = stats['mean_root'], stats['std_root']
        tpose = np.zeros((n, 12), dtype=np.float32)
        tpose[:, :3] = points
        # Motion's continuous rotation encoding flattens the first two columns.
        from Quaternions import Quaternions
        tpose[:, 3:9] = Quaternions.id(n).rotation_matrix(cont6d=True)
        tpose = apply_normalization(tpose, mean, std).astype(np.float32)
        self.base = {'motion': np.zeros((60, n, 12), dtype=np.float32),
            'max_joints': n, 'motion_length': 60, 'start_idx': 0, 'parents': parents,
            'tpos_first_frame': tpose, 'mean': mean, 'std': std,
            'joint_graph_dist': topology['joint_graph_dists'],
            **{k: np.asarray(topology[k]).astype(np.int64 if k in ('joint_depths', 'joint_relations', 'edge_indexs') else np.float32)
               for k in ('joint_depths', 'joint_relations', 'edge_indexs', 'spectral_feats', 'offsets')},
            **build_parent_features(tpose, parents)}
        self.tokenizer = T5Tokenizer.from_pretrained(c.model.text_encoder_version, revision=TEXT_REVISION)
        self.encoder = T5EncoderModel.from_pretrained(c.model.text_encoder_version, revision=TEXT_REVISION).to(device).eval()
        with torch.inference_mode():
            self.base['joint_names_emb'] = self.encode(rig['clean_names'])
        self.model = create_model(c.dataset, c.model)
        state = torch.load(self.root / 'model/checkpoint.pt', map_location='cpu', weights_only=False)
        self.model.load_state_dict(state['model_state_dict'])
        # Spectral attention has no learned joint-index table. Its padding mask
        # can use the actual rig size without changing checkpoint parameters.
        self.model.input_layer.max_joints = n
        self.model.final_layer.joint = n
        if 'ema_state_dict' in state:
            for parameter, shadow in zip(self.model.parameters(), state['ema_state_dict']['shadow_params'], strict=True):
                parameter.data.copy_(shadow)
        del state
        self.model.to(device).eval()
        with (self.root / 'model/checkpoint.pt').open('rb') as checkpoint:
            self.checkpoint_sha = hashlib.file_digest(checkpoint, 'sha256').hexdigest()
        import subprocess
        self.revision = subprocess.check_output(['git', '-C', str(self.root / 'upstream'), 'rev-parse', 'HEAD'], text=True).strip()

    def encode(self, texts):
        torch = self.torch
        tokens = self.tokenizer(texts, return_tensors='pt', padding=True, truncation=True, max_length=128).to(self.device)
        with torch.inference_mode():
            hidden = self.encoder(**tokens).last_hidden_state
            mask = tokens.attention_mask.unsqueeze(-1)
            return ((hidden * mask).sum(1) / mask.sum(1).clamp(min=1)).cpu().numpy().astype('float32')

    def generate(self, prompt, seed, guidance=3.0, steps=32, progress=None, guided_sprint=False):
        from unimate.dataset.mixture.collate import mixture_batch_collate
        from unimate.utils.motion_utils import recover_unimate_anim_from_rot
        np, torch = self.np, self.torch
        start = time.monotonic()
        row = {**self.base, 'caption_emb': self.encode([prompt])[0]}
        _, cond = mixture_batch_collate([row])
        cond = {k: v.to(self.device) if torch.is_tensor(v) else v for k, v in cond.items()}
        # CPU generator makes identical initial noise available on MPS and CPU.
        noise = torch.Generator(device='cpu').manual_seed(seed)
        x = torch.randn((1, len(self.rig['names']), 12, 60), generator=noise).to(self.device)
        reference = None
        start_t = 0.
        if guided_sprint:
            from guided import reference_features
            reference = json.loads((self.root / 'assets/run-reference.json').read_text())
            if reference['source_sha256'] != self.rig['source_sha256'] or reference['names'] != self.rig['names']:
                raise ValueError('Run reference does not match the exported fox rig; rerun setup')
            known, keep, reference_error = reference_features(reference, self.rig, self.scale, self.floor_offset)
            known = torch.from_numpy((known - self.base['mean']) / self.base['std']).permute(1, 2, 0)[None].to(self.device)
            mask = torch.from_numpy(keep)[None, :, None, None].to(self.device)
            eps = x.clone()
            start_t = .55
            x = (1 - start_t) * eps + start_t * known
            def replace(state, t):
                return torch.where(mask, (1 - t) * eps + t * known, state)
        else:
            def replace(state, t):
                return state
        # Fixed midpoint flow ODE: bounded latency; record solver and step count.
        def velocity(state, t):
            ts = torch.full((1,), t, device=self.device)
            a = self.model(state, ts, cond)
            b = self.model(state, ts, cond, force_mask=True)
            return b + guidance * (a - b)
        with torch.inference_mode():
            for i in range(steps):
                dt = (1 - start_t) / steps
                t = start_t + i * dt
                x = replace(x, t)
                v = velocity(x, t)
                middle = replace(x + v * dt / 2, t + dt / 2)
                x = replace(x + velocity(middle, t + dt / 2) * dt, t + dt)
                if progress:
                    progress(i + 1, steps)
        features = x[0].permute(2, 0, 1).cpu().numpy()
        features = features * self.base['std'][None] + self.base['mean'][None]
        if not np.isfinite(features).all():
            raise ValueError('UniMate returned non-finite motion')
        anim = recover_unimate_anim_from_rot(features, self.rig['parents'], self.base['offsets'])
        q = anim.rotations.qs
        root = anim.positions[:, 0] / self.scale
        root[:, 1] += self.floor_offset
        if not np.isfinite(q).all() or not np.isfinite(root).all():
            raise ValueError('UniMate rotation decoding returned non-finite transforms')
        # JSON quaternions are xyzw for the browser; original features stay in .npy.
        motion = {'names': self.rig['names'], 'parents': self.rig['parents'], 'fps': 30,
                  'rotations': q[:, :, [1, 2, 3, 0]].round(7).tolist(),
                  'root_positions': root.round(7).tolist(),
                  'rest_root': self.rig['positions'][0], 'frames': len(q),
                  'conditioning_version': 'canonical-names-v2',
                  'canonical_to_gltf': [0, 2**-0.5, 0, 2**-0.5]}
        from Animation import positions_global
        pos = positions_global(anim) / self.scale
        foot_ids = [self.rig['names'].index('mixamorig:' + s + 'ToeBase') for s in ('Left', 'Right')]
        floor = pos[:, foot_ids, 1].min(axis=1)
        diagnostics = {'root_travel_m': float(np.linalg.norm(root[-1, [0, 2]] - root[0, [0, 2]])),
                       'foot_height_range_m': [float(floor.min()), float(floor.max())],
                       'finite': True, 'review': 'experimental; inspect feet, contacts and recovery before game use'}
        if reference:
            from guided import make_sprint_loop
            motion = make_sprint_loop(motion, reference)
            diagnostics.update(root_travel_m=0., reference_fk_error_m=reference_error,
                review='hybrid sprint: authored gait and contacts; bounded UniMate arm variation')
        return features, motion, {'prompt': prompt, 'seed': seed, 'guidance': guidance, 'steps': steps,
            'solver': 'fixed midpoint flow ODE', 'model': 'UniMate uniml3d f60 v2 EMA step 100000',
            'start_time': start_t,
            'checkpoint_sha256': self.checkpoint_sha, 'upstream_revision': self.revision,
            'source_sha256': self.rig['source_sha256'], 'device': self.device,
            'conditioning_version': 'canonical-names-v2', 'joint_names': self.rig['clean_names'],
            'guided': motion.get('guided'), 'reference_clip': motion.get('reference_clip'),
            'text_encoder_revision': TEXT_REVISION,
            'seconds': round(time.monotonic() - start, 2), 'diagnostics': diagnostics}


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--device', default='mps')
    ap.add_argument('--prompt', default='A human runs forward at a steady pace.')
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--steps', type=int, default=24)
    args = ap.parse_args()
    engine = Engine(args.root, args.device)
    features, motion, provenance = engine.generate(args.prompt, args.seed, steps=args.steps,
        progress=lambda i,n: print(f'{i}/{n}', flush=True))
    target = args.root / 'probe'
    target.mkdir(exist_ok=True)
    engine.np.save(target / 'features.npy', features)
    (target / 'motion.json').write_text(json.dumps(motion))
    (target / 'provenance.json').write_text(json.dumps(provenance, indent=2))
    print(json.dumps(provenance, indent=2))
