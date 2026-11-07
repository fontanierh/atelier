"""Visual parity compare: identical captures pass, shifts and noise move the metrics the right way, thresholds gate."""
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('v2_parity_compare', ROOT / 'tools/parity/compare.py')
compare = importlib.util.module_from_spec(spec)
sys.modules['v2_parity_compare'] = compare
spec.loader.exec_module(compare)


def scene(size=64):
    """A smooth gradient with a few hard-edged blocks: structure for SSIM to see."""
    y, x = np.mgrid[0:size, 0:size] / size
    img = np.stack([x, y, 0.5 * (x + y)], axis=2)
    for i in range(0, size, 16):
        img[i:i + 8, i:i + 8] = [1.0, 0.2, 0.1]
    return img.astype(np.float32)


def noisy(img, sigma, seed=0):
    return np.clip(img + np.random.default_rng(seed).normal(0, sigma, img.shape), 0, 1).astype(np.float32)


def save(folder, name, img):
    folder.mkdir(parents=True, exist_ok=True)
    Image.fromarray((np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)).save(folder / f'{name}.png')


def run(tmp_path, donor, v2, *extra):
    for name, img in donor.items():
        save(tmp_path / 'donor', name, img)
    for name, img in v2.items():
        save(tmp_path / 'v2', name, img)
    code = compare.main([str(tmp_path / 'donor'), str(tmp_path / 'v2'), '--out', str(tmp_path / 'out'), *extra])
    report = json.loads((tmp_path / 'out' / 'report.json').read_text())
    return code, {row['name']: row for row in report['poses']}, report


def test_identical_captures_pass(tmp_path):
    img = scene()
    code, rows, report = run(tmp_path, {'coast': img}, {'coast': img}, '--min-ssim', '0.99', '--max-mad', '0')
    assert code == 0 and report['passed']
    assert rows['coast']['mad'] == 0 and rows['coast']['ssim'] > 0.9999
    assert (tmp_path / 'out' / 'coast_side.png').is_file() and (tmp_path / 'out' / 'coast_diff.png').is_file()
    assert Image.open(tmp_path / 'out' / 'coast_side.png').width == 2 * 64 + 12


def test_noise_and_shift_lower_ssim_and_raise_mad():
    img = scene()
    light, heavy = noisy(img, 0.02), noisy(img, 0.15)
    assert compare.ssim(img, img) > compare.ssim(img, light) > compare.ssim(img, heavy)
    assert 0 == compare.mad(img, img) < compare.mad(img, light) < compare.mad(img, heavy)
    shifted = np.roll(img, 3, axis=1)
    assert compare.ssim(img, shifted) < compare.ssim(img, np.roll(img, 1, axis=1)) < compare.ssim(img, img)
    assert compare.mad(img, shifted) > compare.mad(img, np.roll(img, 1, axis=1)) > 0


def test_ssim_ignores_a_uniform_brightness_change_more_than_structure_loss():
    img = scene()
    brighter = np.clip(img + 0.03, 0, 1)
    assert compare.ssim(img, brighter) > compare.ssim(img, noisy(img, 0.15))


def test_threshold_sets_the_exit_code(tmp_path):
    img = scene()
    v2 = noisy(img, 0.1)
    score = compare.ssim(compare.load(_roundtrip(tmp_path, img)), compare.load(_roundtrip(tmp_path, v2, 'b')))
    code, rows, _ = run(tmp_path / 'low', {'pier': img}, {'pier': v2}, '--min-ssim', f'{score - 0.05:.3f}')
    assert code == 0 and rows['pier']['passed']
    code, rows, report = run(tmp_path / 'high', {'pier': img}, {'pier': v2}, '--min-ssim', f'{score + 0.05:.3f}')
    assert code == 1 and not report['passed'] and 'SSIM' in rows['pier']['reason']
    code, rows, _ = run(tmp_path / 'mad', {'pier': img}, {'pier': v2}, '--min-ssim', '0', '--max-mad', '0.001')
    assert code == 1 and 'MAD' in rows['pier']['reason']


def test_missing_or_resized_captures_fail(tmp_path):
    poses = tmp_path / 'poses.json'
    poses.write_text(json.dumps({'schema': 1, 'poses': [{'name': 'coast'}, {'name': 'pier'}, {'name': 'road'}]}))
    img = scene()
    code, rows, _ = run(tmp_path, {'coast': img, 'pier': img}, {'coast': img, 'pier': scene(80)},
                        '--min-ssim', '0.5', '--poses', str(poses))
    assert code == 1
    assert rows['coast']['passed']
    assert 'size differs' in rows['pier']['reason']
    assert rows['road']['reason'] == 'no capture in donor, v2'


def test_real_poses_file_is_well_formed():
    data = json.loads((ROOT / 'tools/parity/poses.json').read_text())
    assert data['schema'] == 1
    names = [p['name'] for p in data['poses']]
    assert len(names) == len(set(names)) >= 2
    for pose in data['poses']:
        assert len(pose['location']) == 3 and set(pose['rotation']) == {'pitch', 'yaw', 'roll'}
        assert 0 < pose['fov'] < 180 and (pose.get('source') or pose.get('todo'))


def _roundtrip(tmp_path, img, name='a'):
    save(tmp_path / 'roundtrip', name, img)
    return tmp_path / 'roundtrip' / f'{name}.png'
