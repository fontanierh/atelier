"""Video to SMPL-X motion: `python -m atelier.ai.gvhmr --root build/gvhmr VIDEO --out DIR (--static-cam | --moving-cam)`.

Run it with the installed environment's Python, inside `atelier.safety.guarded`. Writes `gvhmr.pt`, `provenance.json`
and `motion.json` (world frame, see motion.py) into DIR. `gvhmr.pt` always holds GVHMR's raw predictions; `--root-height
camera` (experimental, `--static-cam` only) changes just the height of the root in `motion.json`.
"""
import argparse
import json
from pathlib import Path

from . import Engine, save
from .engine import PRECISIONS
from .install import BODY_MODEL
from .motion import body_motion, camera_anchored_transl, load_body_model


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('video', type=Path)
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    camera = ap.add_mutually_exclusive_group(required=True)
    camera.add_argument('--static-cam', action='store_true', help='locked-off camera: skip visual odometry')
    camera.add_argument('--moving-cam', action='store_true', help='estimate camera rotation with SimpleVO')
    ap.add_argument('--f-mm', type=float, help='full-frame equivalent focal length')
    ap.add_argument('--precision', choices=PRECISIONS, default='fp32')
    ap.add_argument('--root-height', choices=('global', 'camera'), default='global',
                    help="root height in motion.json: GVHMR's world output (default) or, experimental and for a "
                         'locked-off camera only, the in-camera body anchored to the frame-0 camera')
    args = ap.parse_args()
    if args.root_height == 'camera' and not args.static_cam:
        ap.error('--root-height camera needs --static-cam: the anchor assumes the camera never moves')
    engine = Engine(args.root, precision=args.precision)
    pred, provenance = engine.run(args.video, static_cam=args.static_cam, f_mm=args.f_mm)
    body_model = load_body_model(Path(args.root) / 'checkpoints' / BODY_MODEL)
    params = {k: v.numpy() for k, v in pred['smpl_params_global'].items()}
    provenance['export'] = {'root_height': 'global'}
    if args.root_height == 'camera':
        incam = {k: v.numpy() for k, v in pred['smpl_params_incam'].items()}
        params['transl'], provenance['export'] = camera_anchored_transl(params, incam, body_model)
    out = save(pred, provenance, args.out)
    motion = body_motion(params, body_model)
    (out / 'motion.json').write_text(json.dumps(motion) + '\n')
    print(json.dumps(provenance['seconds'] | {'frames_per_second': provenance['frames_per_second']}))


if __name__ == '__main__':
    main()
