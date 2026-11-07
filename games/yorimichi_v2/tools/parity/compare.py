"""Visual parity of the slice (plan P3.6): compare donor and V2 captures of the same named poses.

    uv run python games/yorimichi_v2/tools/parity/compare.py DONOR_DIR V2_DIR --out OUT --min-ssim 0.8 \
        [--max-mad 0.05] [--poses games/yorimichi_v2/tools/parity/poses.json]

Each folder holds one `<pose>.png` per pose (unreal/Scripts/capture_poses.py writes them). For every pose it measures
the mean absolute difference of the RGB values (MAD, 0..1) and the structural similarity of their luma (SSIM, 11-tap
Gaussian window, sigma 1.5), and writes OUT/report.json, OUT/<pose>_side.png (donor left, V2 right) and
OUT/<pose>_diff.png (the absolute difference, amplified by --gain). --poses names the expected poses; otherwise every
PNG in either folder is one. A pose missing from a folder, or captured at another size, fails. Exit 0 only when every
pose has SSIM >= --min-ssim and, when given, MAD <= --max-mad.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

SIGMA, RADIUS = 1.5, 5
C1, C2 = 0.01 ** 2, 0.03 ** 2   # SSIM's stabilisers for a dynamic range of 1
LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float32)
PANEL_WIDTH = 1280               # side-by-side panels are scaled down to this width at most


def load(path):
    """RGB in 0..1; alpha is dropped (a scene capture's alpha is not part of the picture)."""
    return np.asarray(Image.open(path).convert('RGB'), dtype=np.float32) / 255.


def blur(x):
    """Separable Gaussian filter, valid region only: the result is 2 * RADIUS smaller on each axis."""
    taps = np.exp(-0.5 * (np.arange(-RADIUS, RADIUS + 1) / SIGMA) ** 2).astype(np.float32)
    taps /= taps.sum()
    n = 2 * RADIUS
    h, w = x.shape
    x = sum(t * x[:, i:w - n + i] for i, t in enumerate(taps))
    return sum(t * x[i:h - n + i, :] for i, t in enumerate(taps))


def ssim(a, b):
    """Mean SSIM of two RGB images over their luma (Wang et al. 2004)."""
    if min(a.shape[:2]) <= 2 * RADIUS:
        raise ValueError(f'images must be larger than {2 * RADIUS} px on each side')
    x, y = a @ LUMA, b @ LUMA
    mx, my = blur(x), blur(y)
    vx, vy, cov = blur(x * x) - mx * mx, blur(y * y) - my * my, blur(x * y) - mx * my
    score = (2 * mx * my + C1) * (2 * cov + C2) / ((mx * mx + my * my + C1) * (vx + vy + C2))
    return float(score.mean())


def mad(a, b):
    return float(np.abs(a - b).mean())


def to_image(x):
    return Image.fromarray(np.clip(x * 255. + 0.5, 0, 255).astype(np.uint8))


def side_by_side(left, right, a, b):
    scale = min(1., PANEL_WIDTH / left.width)
    size = (max(1, round(left.width * scale)), max(1, round(left.height * scale)))
    left, right = left.resize(size, Image.LANCZOS), right.resize(size, Image.LANCZOS)
    out = Image.new('RGB', (2 * size[0] + 12, size[1] + 28), (255, 255, 255))
    out.paste(left, (0, 28)); out.paste(right, (size[0] + 12, 28))
    d = ImageDraw.Draw(out); d.text((8, 8), a, fill=(40, 40, 40)); d.text((size[0] + 20, 8), b, fill=(40, 40, 40))
    return out


def compare_pose(name, donor_dir, v2_dir, out, min_ssim, max_mad, gain):
    row = {'name': name}
    paths = {'donor': donor_dir / f'{name}.png', 'v2': v2_dir / f'{name}.png'}
    missing = [side for side, path in paths.items() if not path.is_file()]
    if missing:
        return {**row, 'passed': False, 'reason': f'no capture in {", ".join(missing)}'}
    a, b = load(paths['donor']), load(paths['v2'])
    if a.shape != b.shape:
        return {**row, 'passed': False,
                'reason': f'size differs: donor {a.shape[1]}x{a.shape[0]}, V2 {b.shape[1]}x{b.shape[0]}'}
    row.update(size=[a.shape[1], a.shape[0]], mad=round(mad(a, b), 6), ssim=round(ssim(a, b), 6))
    side_by_side(to_image(a), to_image(b), f'donor: {name}', f'V2: {name}').save(out / f'{name}_side.png')
    to_image(np.abs(a - b).mean(axis=2) * gain).save(out / f'{name}_diff.png')
    row.update(side=f'{name}_side.png', diff=f'{name}_diff.png')
    failed = ([f'SSIM {row["ssim"]} < {min_ssim}'] if row['ssim'] < min_ssim else []) + \
             ([f'MAD {row["mad"]} > {max_mad}'] if max_mad is not None and row['mad'] > max_mad else [])
    row['passed'] = not failed
    if failed:
        row['reason'] = '; '.join(failed)
    return row


def pose_names(donor_dir, v2_dir, poses):
    if poses:
        return [p['name'] for p in json.loads(poses.read_text())['poses']]
    return sorted({p.stem for d in (donor_dir, v2_dir) for p in d.glob('*.png')})


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('donor', type=Path, help='folder of the donor captures (<pose>.png)')
    parser.add_argument('v2', type=Path, help='folder of the V2 captures (<pose>.png)')
    parser.add_argument('--out', type=Path, required=True, help='folder for report.json and the review images')
    parser.add_argument('--min-ssim', type=float, required=True, help='lowest SSIM a pose may have (0..1)')
    parser.add_argument('--max-mad', type=float, help='highest mean absolute difference a pose may have (0..1)')
    parser.add_argument('--poses', type=Path, help='poses.json: the poses that must be present')
    parser.add_argument('--gain', type=float, default=4., help='amplification of the difference image')
    args = parser.parse_args(argv)
    names = pose_names(args.donor, args.v2, args.poses)
    if not names:
        print(f'no captures in {args.donor} or {args.v2}', file=sys.stderr)
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    rows = [compare_pose(n, args.donor, args.v2, args.out, args.min_ssim, args.max_mad, args.gain) for n in names]
    passed = all(r['passed'] for r in rows)
    report = {'schema': 1, 'donor': str(args.donor), 'v2': str(args.v2), 'passed': passed,
              'thresholds': {'min_ssim': args.min_ssim, 'max_mad': args.max_mad}, 'poses': rows}
    (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    for r in rows:
        metrics = f'SSIM {r["ssim"]:.4f}, MAD {r["mad"]:.4f}' if 'ssim' in r else ''
        print(f'  {"pass" if r["passed"] else "FAIL"} {r["name"]}: {metrics}{"  " if metrics and not r["passed"] else ""}'
              f'{r.get("reason", "")}')
    print(f'{sum(r["passed"] for r in rows)}/{len(rows)} poses pass; report {args.out / "report.json"}')
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
