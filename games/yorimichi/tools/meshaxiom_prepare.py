"""Prepare UVs and a Pixel Match camera in one guarded, sequential CPU job.

The outer atelier.safety.guarded caller owns admission, the Blender descendant and both
memory guards. This helper takes no additional lock and leaves painting to a later job,
after the calibration images have been inspected.
"""
import argparse
from pathlib import Path
import subprocess
import time


def main():
    from atelier.harness.safety.process import spawn
    from meshaxiom_pixel_match import calibrate, load_module
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mesh', type=Path, required=True, help='Completed native mesh.json')
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--blender', type=Path, default=Path('/Applications/Blender.app/Contents/MacOS/Blender'))
    args = parser.parse_args()
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
    if code:
        return code
    print('UV export complete; calibrating reference camera', flush=True)
    args.mesh = args.output/'clay-uv.glb'
    args.yaw = args.pitch = None
    args.module = Path(__file__).with_name('pixel_match')/'photo_paint.py'
    calibrate(args, load_module(args.module))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
