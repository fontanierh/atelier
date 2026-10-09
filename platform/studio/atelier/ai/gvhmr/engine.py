"""Run GVHMR on one video of one person and return SMPL-X body motion in world and camera frames.

Each stage matches upstream's demo, with three changes for Apple silicon. The video is decoded at half size once and
cropped once, and those crops feed ViTPose and HMR2; upstream decodes and crops for each stage. SimpleVO matches frame
pairs on several threads, alongside the GPU stages. The two ViT-H backbones can also run in float16 or with fused
attention, but both were slower on an M1 Max, so the defaults keep upstream's float32 batches of 16.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import chdir, contextmanager
import hashlib
import json
import os
from pathlib import Path
import time

from .install import BODY_MODEL, CHECKPOINTS, MIRROR, PYTORCH3D_REVISION, REVISION

PRECISIONS = ('fp32', 'fp16')


def _digest(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def fused_attention(module, x):
    """Upstream ViT attention (softmax(q·kᵀ·scale)·v, no dropout at inference) as one fused kernel."""
    import torch.nn.functional as F

    B, N, _ = x.shape
    q, k, v = module.qkv(x).reshape(B, N, 3, module.num_heads, -1).permute(2, 0, 3, 1, 4)
    x = F.scaled_dot_product_attention(q, k, v, scale=module.scale)
    return module.proj(x.transpose(1, 2).reshape(B, N, -1))


@contextmanager
def _fused_vit_attention(enabled):
    """Swap both upstream ViT attention classes to `fused_attention` for the duration."""
    if not enabled:
        yield
        return
    from hmr4d.network.hmr2 import vit as hmr2_vit
    from hmr4d.utils.preproc.vitpose_pytorch.src.vitpose_infer.builder.backbones import vit as pose_vit

    classes = (hmr2_vit.Attention, pose_vit.Attention)
    saved = [c.forward for c in classes]
    for c in classes:
        c.forward = fused_attention
    try:
        yield
    finally:
        for c, forward in zip(classes, saved):
            c.forward = forward


class Engine:
    """GVHMR inference from an `atelier.ai.gvhmr.install` root.

    `device` defaults to MPS when present. `precision` applies to the two ViT-H stages (ViTPose and HMR2 features),
    which take most of the time; the tracker and the GVHMR transformer keep upstream precision.
    """

    def __init__(self, root, device=None, precision='fp32', fused_attention=False, batch_size=16, vo_workers=6):
        import torch

        if precision not in PRECISIONS:
            raise ValueError(f'precision must be one of {PRECISIONS}')
        self.root = Path(root).resolve()
        self.upstream = self.root / 'upstream'
        self.device = torch.device(device or ('mps' if torch.backends.mps.is_available() else 'cpu'))
        os.environ['HMR4D_DEVICE'] = self.device.type
        # Upstream and ultralytics 8.2 load pickled checkpoints, which PyTorch 2.6+ refuses by default. Every
        # checkpoint here is checksum-verified by the installer.
        os.environ.setdefault('TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD', '1')
        self.precision, self.fused, self.batch_size, self.vo_workers = (
            precision, fused_attention, batch_size, vo_workers)
        self.torch = torch
        self.timings = {}

    def _stage(self, name, started):
        self._sync()
        self.timings[name] = round(time.perf_counter() - started, 3)

    def _sync(self):
        if self.device.type == 'mps':
            self.torch.mps.synchronize()

    def _release(self):
        import gc

        gc.collect()
        if self.device.type == 'mps':
            self.torch.mps.empty_cache()

    def _vit(self, model, backbone):
        """Put a ViT-H stage model on the device; at fp16 only its backbone is halved and returns float32, because
        the heads build float32 tensors of their own (MPS refuses mixed-precision adds)."""
        model.to(self.device).eval()
        if self.precision == 'fp16':
            backbone.half()
            backbone.register_forward_hook(lambda module, args, out: out.float())
        return model

    def track(self, video):
        """Upstream YOLOv8x person tracking (float16 YOLO measured no faster on M1 Max and moved boxes)."""
        from hmr4d.utils.geo.hmr_cam import get_bbx_xys_from_xyxy
        from hmr4d.utils.preproc import Tracker

        started = time.perf_counter()
        video = Path(video).resolve()
        with chdir(self.upstream):
            tracker = Tracker()
            bbx_xyxy = tracker.get_one_track(str(video)).float()
        del tracker
        self._release()
        self._stage('track', started)
        return bbx_xyxy, get_bbx_xys_from_xyxy(bbx_xyxy, base_enlarge=1.2).float()

    def crops(self, frames, bbx_xys):
        """Upstream `get_batch(video, bbx_xys, img_ds=0.5)` on frames already decoded at half size."""
        from hmr4d.utils.preproc.vitfeat_extractor import get_batch

        started = time.perf_counter()
        imgs, _ = get_batch(frames, bbx_xys * 0.5, img_ds=1.0, path_type='np')
        self._stage('crop', started)
        return imgs

    def keypoints(self, imgs, bbx_xys):
        """ViTPose-H COCO-17 keypoints with flip test, as upstream `VitPoseExtractor.extract`."""
        import numpy as np
        from hmr4d.utils.geo.flip_utils import flip_heatmap_coco17
        from hmr4d.utils.kpts.kp2d_utils import keypoints_from_heatmaps
        from hmr4d.utils.preproc.vitpose_pytorch import build_model

        torch = self.torch
        started = time.perf_counter()
        with chdir(self.upstream):
            pose = build_model('ViTPose_huge_coco_256x192', 'inputs/checkpoints/vitpose/vitpose-h-multi-coco.pth')
        pose = self._vit(pose, pose.backbone)
        dtype = next(pose.backbone.parameters()).dtype
        out = []
        with torch.no_grad(), _fused_vit_attention(self.fused):
            for j in range(0, len(imgs), self.batch_size):
                batch = imgs[j:j + self.batch_size, :, :, 32:224].to(self.device, dtype)
                heatmap, flipped = pose(torch.cat([batch, batch.flip(3)])).chunk(2)
                heatmap = ((heatmap + flip_heatmap_coco17(flipped)) * 0.5).cpu().numpy()
                box = bbx_xys[j:j + self.batch_size]
                scale = (torch.cat((box[:, [2]] * 24 / 32, box[:, [2]]), dim=1) / 200).numpy()
                preds, maxvals = keypoints_from_heatmaps(heatmaps=heatmap, center=box[:, :2].numpy(), scale=scale,
                                                         use_udp=True)
                out.append(torch.from_numpy(np.concatenate((preds, maxvals), axis=-1)))
        del pose
        self._release()
        self._stage('vitpose', started)
        return torch.cat(out).float()

    def features(self, imgs):
        """HMR2.0a image tokens, as upstream `Extractor.extract_video_features`."""
        from hmr4d.network.hmr2 import load_hmr2

        torch = self.torch
        started = time.perf_counter()
        with chdir(self.upstream):
            model = load_hmr2()
        model = self._vit(model, model.backbone)
        dtype = next(model.backbone.parameters()).dtype
        out = []
        with torch.no_grad(), _fused_vit_attention(self.fused):
            for j in range(0, len(imgs), self.batch_size):
                out.append(model({'img': imgs[j:j + self.batch_size].to(self.device, dtype)}).cpu())
        del model
        self._release()
        self._stage('hmr2', started)
        return torch.cat(out)

    def camera(self, frames, f_mm=None):
        """World-to-camera rotations from SimpleVO on the half-size frames, as upstream `SimpleVO.compute`."""
        import numpy as np
        from hmr4d.utils.preproc.relpose.matcher_wrapper import Matcher
        from hmr4d.utils.preproc.relpose.simple_vo import SimpleVO
        from hmr4d.utils.preproc.relpose.solver_two_view import (
            CameraParams, TwoPairSolver, interpolate_missing_frames)
        from hmr4d.utils.preproc.relpose.utils import focal_length_from_mm

        started = time.perf_counter()
        vo = SimpleVO(None, scale=0.5, step=8, method='sift', f_mm=f_mm, num_workers=self.vo_workers)
        sample = np.arange(0, len(frames), vo.step)
        if sample[-1] != len(frames) - 1:
            sample = np.concatenate([sample, [len(frames) - 1]])
        picked = frames[sample]
        _, H, W, _ = picked.shape
        solver = TwoPairSolver(CameraParams(W, H, focal_length=focal_length_from_mm(W, H, vo.f_mm)), solver='pycolmap')
        T_w2c = interpolate_missing_frames(vo.process_video_T_w2c_list_np(picked, Matcher(vo.method), solver), sample)
        self.timings['simple_vo'] = round(time.perf_counter() - started, 3)  # CPU only: no device sync
        return self.torch.from_numpy(np.asarray(T_w2c)[:, :3, :3])

    def predict(self, data, static_cam):
        import hydra
        from hydra import compose, initialize_config_module
        from hmr4d.utils.net_utils import detach_to_cpu

        if not (self.root / 'checkpoints' / BODY_MODEL).exists():
            raise FileNotFoundError(f'{BODY_MODEL} missing; install it with atelier.ai.gvhmr.install --smplx')
        started = time.perf_counter()
        with chdir(self.upstream):
            with initialize_config_module(version_base='1.3', config_module='hmr4d.configs'):
                # Register only the demo's model, network and encoder. Upstream's register_store_gvhmr also imports
                # every training dataset, which pulls in the pytorch3d mesh renderer this port does not build.
                import hmr4d.model.gvhmr.gvhmr_pl_demo  # noqa: F401
                import hmr4d.model.gvhmr.utils.endecoder  # noqa: F401
                import hmr4d.network.gvhmr.relative_transformer  # noqa: F401
                cfg = compose(config_name='demo', overrides=['video_name=atelier', f'static_cam={static_cam}'])
            model = hydra.utils.instantiate(cfg.model, _recursive_=False)
            model.load_pretrained_model(cfg.ckpt_path)
            model = model.eval().to(self.device)
            pred = detach_to_cpu(model.predict(data, static_cam=static_cam))
        del model
        self._release()
        self._stage('gvhmr', started)
        return pred

    def run(self, video, *, static_cam, f_mm=None):
        """Return (prediction, provenance) for the longest-tracked person in `video`.

        Frames are taken as consecutive 30 fps samples, as upstream does; supply 30 fps footage for true timing.
        `static_cam` skips visual odometry and must only be set for a locked-off camera. `f_mm` is the full-frame
        equivalent focal length; upstream estimates one when it is omitted.
        """
        from hmr4d.utils.geo.hmr_cam import create_camera_sensor, estimate_K
        from hmr4d.utils.geo_transform import compute_cam_angvel
        from hmr4d.utils.video_io_utils import read_video_np
        import av

        torch = self.torch
        video = Path(video).resolve()
        self.timings = {}
        began = time.perf_counter()
        with av.open(str(video)) as container:
            stream = container.streams.video[0]
            source_fps = float(stream.average_rate)
        bbx_xyxy, bbx_xys = self.track(video)
        started = time.perf_counter()
        frames = read_video_np(str(video), scale=0.5)
        self._stage('decode', started)
        length = len(frames)
        height, width = frames.shape[1] * 2, frames.shape[2] * 2
        if len(bbx_xys) != length:
            raise RuntimeError(f'tracker saw {len(bbx_xys)} frames, decoder {length}')
        # SimpleVO is CPU work (SIFT, pycolmap); it overlaps the two GPU ViT stages.
        with ThreadPoolExecutor(1) as pool:
            camera = None if static_cam else pool.submit(self.camera, frames, f_mm)
            imgs = self.crops(frames, bbx_xys)
            kp2d = self.keypoints(imgs, bbx_xys)
            f_imgseq = self.features(imgs)
            del imgs
            R_w2c = torch.eye(3).repeat(length, 1, 1) if static_cam else camera.result().float()
        del frames
        if f_mm is not None:
            K = create_camera_sensor(width, height, f_mm)[2].repeat(length, 1, 1)
        else:
            K = estimate_K(width, height).repeat(length, 1, 1)
        data = {'length': torch.tensor(length), 'bbx_xys': bbx_xys, 'kp2d': kp2d, 'K_fullimg': K,
                'cam_angvel': compute_cam_angvel(R_w2c), 'f_imgseq': f_imgseq}
        pred = self.predict(data, static_cam)
        pred.pop('net_outputs', None)
        pred.update(bbx_xyxy=bbx_xyxy, bbx_xys=bbx_xys, kp2d=kp2d, R_w2c=R_w2c)
        elapsed = time.perf_counter() - began
        provenance = {
            'model': 'GVHMR (SIGGRAPH Asia 2024)',
            'upstream_revision': REVISION,
            'pytorch3d_revision': PYTORCH3D_REVISION,
            'checkpoint_mirror': MIRROR,
            'checkpoint_sha256': CHECKPOINTS,
            'body_model_sha256': _digest(self.root / 'checkpoints' / BODY_MODEL),
            'video': video.name,
            'video_sha256': _digest(video),
            'frames': length,
            'size': [width, height],
            'source_fps': source_fps,
            'sample_fps': 30,
            'static_cam': static_cam,
            'f_mm': f_mm,
            'device': self.device.type,
            'precision': self.precision,
            'fused_attention': self.fused,
            'batch_size': self.batch_size,
            'vo_workers': None if static_cam else self.vo_workers,
            'torch': torch.__version__,
            'seconds': self.timings | {'total': round(elapsed, 3)},
            'frames_per_second': round(length / elapsed, 2),
        }
        return pred, provenance


def save(pred, provenance, out_dir):
    """Write `gvhmr.pt` (upstream prediction tensors) and `provenance.json` into `out_dir`."""
    import torch

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    torch.save(pred, out / 'gvhmr.pt')
    (out / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    return out
