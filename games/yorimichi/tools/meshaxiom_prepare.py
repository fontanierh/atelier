"""Prepare UVs and a Pixel Match camera in one guarded, sequential CPU job.

Run this entry point directly with --report and a bounded --timeout. It owns one normal
admission/lock and explicitly enables the aggregate guard on unmanaged machines too.
Painting remains a later job, after the calibration images have been inspected.
"""
import argparse
from pathlib import Path
import subprocess
import sys
import time


def prepare(args):
    from atelier.harness.safety.process import spawn
    from meshaxiom_pixel_match import calibrate, load_module
    script = Path(__file__).with_name('meshaxiom_uv.py')
    command = [str(args.blender), '--background', '--threads', '3', '--python', str(script), '--',
               '--mesh', str(args.mesh), '--output', str(args.output), '--height', '.35']
    print('UV preparation: starting owned Blender child', flush=True)
    started = time.monotonic()
    child = spawn(command)
    while True:
        try:
            code = child.wait(timeout=20)
            break
        except subprocess.TimeoutExpired:
            print(f'UV preparation: Blender still running at {time.monotonic()-started:.0f}s; waiting for export', flush=True)
    print(f'UV preparation: Blender exited {code} after {time.monotonic()-started:.1f}s', flush=True)
    if code:
        return code
    print('UV export complete; calibrating reference camera', flush=True)
    args.mesh = args.output/'clay-uv.glb'
    args.yaw = args.pitch = None
    args.module = Path(__file__).with_name('pixel_match')/'photo_paint.py'
    calibrate(args, load_module(args.module))
    return 0


def main(argv=None):
    """@cc [owner:fontanierh,label:safety] meshaxiom-prepare-owns-tree-guard
    The public entry point MUST start native preparation only through one existing guarded
    run with aggregate_tree enabled, including without a capacity broker. Its worker MUST
    remain inside that admission, lock, deadline and owned descendant cleanup.
    """
    from atelier.harness.safety.guarded import run
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mesh', type=Path, required=True, help='Completed native mesh.json')
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--blender', type=Path, default=Path('/Applications/Blender.app/Contents/MacOS/Blender'))
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if not 1 <= args.timeout <= 3600:
        parser.error('Use a bounded preparation timeout of 1–3600 seconds')
    if args.worker:
        return prepare(args)
    if args.report.exists():
        parser.error('Use a new guard report directory')
    command = [sys.executable, '-u', str(Path(__file__).resolve()), '--worker', *argv]
    return run(command, args.report, timeout=args.timeout,
               purpose='MeshAxiom head UV and Pixel Match camera', aggregate_tree=True, progress=20)


if __name__ == '__main__':
    raise SystemExit(main())
