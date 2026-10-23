"""Build v2 H4a source texture fixtures: 4x4 8-bit RGBA PNG, one-pixel variant and manifest."""
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


FIXTURE_DIR = Path(__file__).resolve().parents[3] / 'platform/build-v2/fixtures/textures'

EXPECTED_BASE_PIXELS = [
    [[240, 32, 48, 255], [32, 208, 64, 255], [48, 96, 240, 255], [255, 224, 32, 192]],
    [[16, 180, 200, 128], [200, 48, 192, 96], [32, 160, 224, 192], [224, 128, 24, 255]],
    [[128, 64, 216, 160], [64, 224, 160, 224], [248, 248, 240, 255], [24, 28, 36, 255]],
    [[0, 0, 0, 0], [180, 90, 45, 0], [96, 144, 72, 64], [212, 176, 140, 255]],
]

EXPECTED_VARIANT_PIXELS = [
    [[240, 32, 48, 255], [32, 208, 64, 255], [48, 96, 240, 255], [255, 224, 32, 192]],
    [[16, 180, 200, 128], [200, 48, 192, 96], [250, 20, 140, 64], [224, 128, 24, 255]],
    [[128, 64, 216, 160], [64, 224, 160, 224], [248, 248, 240, 255], [24, 28, 36, 255]],
    [[0, 0, 0, 0], [180, 90, 45, 0], [96, 144, 72, 64], [212, 176, 140, 255]],
]


def _decode_png(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        assert image.format == 'PNG'
        assert image.mode == 'RGBA'
        assert image.size == (4, 4)
        assert image.info.get('interlace', 0) == 0
        arr = np.asarray(image)
    assert arr.dtype == np.uint8
    assert arr.shape == (4, 4, 4)
    return arr


def test_texture_fixtures_decode_to_hand_written_rgba_arrays():
    base = _decode_png(FIXTURE_DIR / 'rgba_4x4.png')
    variant = _decode_png(FIXTURE_DIR / 'rgba_4x4_pixel_changed.png')

    assert base.tolist() == EXPECTED_BASE_PIXELS
    assert variant.tolist() == EXPECTED_VARIANT_PIXELS

    # All 16 pixels in the base fixture are distinct and exercise transparent, translucent and opaque alpha.
    flat = [tuple(px) for row in base.tolist() for px in row]
    assert len(set(flat)) == 16
    alphas = {px[3] for px in flat}
    assert 0 in alphas and 255 in alphas and len(alphas - {0, 255}) >= 4
    # Straight (unpremultiplied) RGB channels survive where alpha is zero.
    assert base[3, 1].tolist() == [180, 90, 45, 0]


def test_single_pixel_variant_differs_only_at_intended_pixel():
    base = _decode_png(FIXTURE_DIR / 'rgba_4x4.png')
    variant = _decode_png(FIXTURE_DIR / 'rgba_4x4_pixel_changed.png')

    changed_coords = [tuple(int(i) for i in rc) for rc in np.argwhere(np.any(base != variant, axis=-1))]
    assert changed_coords == [(1, 2)]
    assert base[1, 2].tolist() == [32, 160, 224, 192]
    assert variant[1, 2].tolist() == [250, 20, 140, 64]
    assert np.all(base[1, 2] != variant[1, 2])


def test_texture_fixture_manifest_matches_files_and_decoded_pixels():
    manifest = json.loads((FIXTURE_DIR / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest['schema_version'] == 1
    assert (manifest['width'], manifest['height'], manifest['bit_depth']) == (4, 4, 8)
    assert manifest['color_type'] == 'RGBA'
    assert manifest['channels'] == ['R', 'G', 'B', 'A']
    interp = manifest['channel_interpretation']
    assert interp == {
        'order': 'RGBA',
        'encoding': 'uint8',
        'value_range': [0, 255],
        'alpha': 'straight_unpremultiplied',
        'row_order': 'top_to_bottom',
        'column_order': 'left_to_right',
    }

    for key, expected in (('base', EXPECTED_BASE_PIXELS), ('single_pixel_variant', EXPECTED_VARIANT_PIXELS)):
        entry = manifest['fixtures'][key]
        png_path = FIXTURE_DIR / entry['file']
        raw = png_path.read_bytes()
        assert entry['byte_length'] == len(raw)
        assert entry['sha256'] == hashlib.sha256(raw).hexdigest()
        assert entry['pixels'] == expected
        assert _decode_png(png_path).tolist() == entry['pixels']

    diff = manifest['fixtures']['single_pixel_variant']['changed_pixel']
    assert diff == {
        'row': 1,
        'col': 2,
        'from': [32, 160, 224, 192],
        'to': [250, 20, 140, 64],
    }
