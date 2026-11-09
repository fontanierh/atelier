"""Visual parity: compare donor and V2 captures of the same named poses (initially plan P3.6).

    uv run python games/yorimichi_v2/tools/parity/compare.py DONOR_DIR V2_DIR --out OUT --min-ssim 0.8 \
        [--max-mad 0.05] [--poses games/yorimichi_v2/tools/parity/poses.json] [--only 'w07_*']

Each folder holds one `<pose>.png` per pose and the capture receipt `capture.json` (unreal/Scripts/capture_poses.py
writes both). The expected poses always come from --poses (default: poses.json next to this script). For every pose
it measures the mean absolute difference of the RGB values (MAD, 0..1) and the structural similarity of their luma
(SSIM, 11-tap Gaussian window, sigma 1.5), and writes OUT/report.json (with both receipts), OUT/<pose>_side.png
(donor left, V2 right) and OUT/<pose>_diff.png (the absolute difference, amplified by --gain).

It fails closed: a pose missing from a folder or captured at another size, a PNG that is not an expected pose, a
missing or unreadable receipt, a receipt lacking a required field (schema, source, revision, map, size, warmup,
poses_sha256, poses, captured_utc, engine_version, render) or holding one of the wrong type, a receipt made from another
poses file, a capture whose real size is not its receipt's, receipts of different capture sizes or render settings
(renderer and quality), and a source other than "donor-runtime" for the donor or "v2" for V2 all fail. Exit 0 only when none of these happen and every pose has
SSIM >= --min-ssim and, when given, MAD <= --max-mad.

The donor baseline must come from a real initialized donor scene (the running game). The donor island's scenery is
spawned at runtime, so capture_poses.py opening the donor's editor map does NOT show it and is no donor baseline.
That donor-runtime capture route is pending: no script for it exists yet.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from poseset import load_poses, select  # noqa: E402

SIGMA, RADIUS = 1.5, 5
C1, C2 = 0.01 ** 2, 0.03 ** 2   # SSIM's stabilisers for a dynamic range of 1
LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float32)
PANEL_WIDTH = 1280               # side-by-side panels are scaled down to this width at most
DEFAULT_POSES = Path(__file__).resolve().parent / 'poses.json'
RECEIPT = 'capture.json'


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


def pose_names(poses, only=None):
    return [p['name'] for p in select(load_poses(poses), only)]


def read_receipt(folder):
    try:
        receipt = json.loads((folder / RECEIPT).read_text())
    except (OSError, ValueError):
        return None
    return receipt if isinstance(receipt, dict) else None


SOURCES = {'donor': 'donor-runtime', 'v2': 'v2'}   # the only capture source each side accepts


def receipt_errors(side, r, names, poses_sha, folder):
    """The receipt's required fields with their types, its source, its poses and the real size of each capture."""
    def bad(field, want):
        return f'{side}: receipt {field} must be {want}, not {r.get(field)!r}'
    errors = []
    rev = r.get('revision')
    size = r.get('size')
    render = r.get('render')
    for ok, field, want in (
            (r.get('schema') == 1, 'schema', '1'),
            (r.get('source') == SOURCES[side], 'source', repr(SOURCES[side])),
            (isinstance(rev, dict) and isinstance(rev.get('commit'), str) and len(rev['commit']) >= 7
             and isinstance(rev.get('dirty'), bool) and rev.get('launch') in ('session', 'process'), 'revision',
             '{"commit": <sha>, "dirty": <bool>, "launch": "session" or "process"} (the proven launch revision)'),
            (isinstance(r.get('map'), str) and r['map'].startswith('/'), 'map', 'a package path'),
            (isinstance(size, list) and len(size) == 2 and all(type(v) is int and v > 0 for v in size),
             'size', '[width, height] in pixels'),
            (type(r.get('warmup')) is int and r['warmup'] >= 0, 'warmup', 'a count of renders'),
            (r.get('poses_sha256') == poses_sha, 'poses_sha256', "the compared poses file's sha256"),
            (r.get('poses') == names, 'poses', 'the poses file\'s names in order'),
            (isinstance(r.get('captured_utc'), str) and r['captured_utc'].endswith('Z'), 'captured_utc', 'a UTC time'),
            (isinstance(r.get('engine_version'), str) and r['engine_version'], 'engine_version', 'the engine version'),
            (isinstance(render, dict) and isinstance(render.get('renderer'), str)
             and isinstance(render.get('quality'), dict) and render['quality'], 'render',
             '{"renderer": ..., "quality": {setting: value}}')):
        if not ok:
            errors.append(bad(field, want))
    if not errors:
        for name in names:
            path = folder / f'{name}.png'
            if path.is_file():
                with Image.open(path) as image:
                    if list(image.size) != size:
                        errors.append(f'{side}: {name}.png is {image.size[0]}x{image.size[1]}, '
                                      f'the receipt says {size[0]}x{size[1]}')
    return errors


def check(dirs, receipts, names, poses_sha):
    """What fails the run whatever the metrics: stray captures, missing, incomplete or mismatched receipts."""
    errors = [f'{side}: unexpected capture {p.name} (not a pose in the poses file)'
              for side, d in dirs.items() for p in sorted(d.glob('*.png')) if p.stem not in names]
    for side, r in receipts.items():
        if r is None:
            errors.append(f'{side}: no readable {RECEIPT} in {dirs[side]}')
        else:
            errors += receipt_errors(side, r, names, poses_sha, dirs[side])
    donor, v2 = receipts['donor'], receipts['v2']
    if donor is not None and v2 is not None:
        for field in ('size', 'render'):
            if donor.get(field) != v2.get(field):
                errors.append(f'capture {field} differs: donor receipt {donor.get(field)}, V2 receipt {v2.get(field)}')
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('donor', type=Path, help='folder of the donor captures (<pose>.png)')
    parser.add_argument('v2', type=Path, help='folder of the V2 captures (<pose>.png)')
    parser.add_argument('--out', type=Path, required=True, help='folder for report.json and the review images')
    parser.add_argument('--min-ssim', type=float, required=True, help='lowest SSIM a pose may have (0..1)')
    parser.add_argument('--max-mad', type=float, help='highest mean absolute difference a pose may have (0..1)')
    parser.add_argument('--poses', type=Path, default=DEFAULT_POSES,
                        help='poses.json: the poses that must be present (default: the one next to this script)')
    parser.add_argument('--gain', type=float, default=4., help='amplification of the difference image')
    parser.add_argument('--only', action='append', help='compare only the poses named by this glob (e.g. w07_*), '
                        'comma separated or repeated; the captures must then hold exactly those poses')
    args = parser.parse_args(argv)
    try:
        names = pose_names(args.poses, args.only)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    if not names:
        print(f'no poses in {args.poses}', file=sys.stderr)
        return 2
    dirs = {'donor': args.donor, 'v2': args.v2}
    receipts = {side: read_receipt(d) for side, d in dirs.items()}
    errors = check(dirs, receipts, names, hashlib.sha256(args.poses.read_bytes()).hexdigest())
    args.out.mkdir(parents=True, exist_ok=True)
    rows = [compare_pose(n, args.donor, args.v2, args.out, args.min_ssim, args.max_mad, args.gain) for n in names]
    passed = not errors and all(r['passed'] for r in rows)
    report = {'schema': 1, 'donor': str(args.donor), 'v2': str(args.v2), 'poses_file': str(args.poses),
              'passed': passed, 'errors': errors, 'receipts': receipts,
              'thresholds': {'min_ssim': args.min_ssim, 'max_mad': args.max_mad}, 'poses': rows}
    (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    for r in rows:
        metrics = f'SSIM {r["ssim"]:.4f}, MAD {r["mad"]:.4f}' if 'ssim' in r else ''
        print(f'  {"pass" if r["passed"] else "FAIL"} {r["name"]}: {metrics}{"  " if metrics and not r["passed"] else ""}'
              f'{r.get("reason", "")}')
    for e in errors:
        print(f'  FAIL {e}')
    print(f'{sum(r["passed"] for r in rows)}/{len(rows)} poses pass, {len(errors)} other failures; '
          f'report {args.out / "report.json"}')
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
