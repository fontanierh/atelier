"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove.kit import local


def split_lot(spec, rng):
    """Break a wide waterfront block into narrow houses with their own rooflines.

    The painted references read as many 8-14 m facades, while the generated
    lots are 34-46 m blocks.  Splitting them keeps the same footprint but gives
    the town the varied height, colour and roof rhythm the cove needs.
    """
    key, x, y, z, w, d, h, floors, style, yaw, roof = spec
    if style == 'warehouse' or w < 20.0:
        return [spec]
    n = 2 if w < 34.0 else 3
    weights = ([0.46, 0.54] if n == 2 else [0.30, 0.38, 0.32])
    jitter = [rng.uniform(-0.045, 0.045) for _ in range(n)]
    scale = sum(weights)
    weights = [max(0.2, weight / scale + jitter[i]) for i, weight in enumerate(weights)]
    scale = sum(weights)
    weights = [weight / scale for weight in weights]
    roofs = ('roof_terra', 'roof_teal', 'roof_terra_light', 'roof_slate', 'roof_terra')
    out = []
    cursor = -w / 2
    for i, weight in enumerate(weights):
        sw = w * weight
        cx = cursor + sw / 2
        px, py = local(x, y, yaw, cx, 0.0)
        out.append((f'{key}-{i}', px, py, z, max(6.0, sw - 0.35), d,
                    h + rng.uniform(-1.1, 1.3), max(1, floors + (1 if rng.random() < 0.22 else 0)),
                    style, yaw, roofs[(i + sum(map(ord, key))) % len(roofs)]))
        cursor += sw
    return out
