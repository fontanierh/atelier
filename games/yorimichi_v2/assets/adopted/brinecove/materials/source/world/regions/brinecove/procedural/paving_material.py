"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove import rocks


def paving_material(x, y, seed=0):
    """Mostly cobble, with drifts of darker worn setts and patches of big flagstones, never a tile checkerboard."""
    n = rocks.fbm(x, y, 34.0, 3, 61 + seed)
    m = rocks.fbm(x, y, 13.0, 2, 83 + seed)
    if n < 0.3:
        return 'stone_light' if m > 0.45 else 'stone'
    if n > 0.7 or (n > 0.6 and m > 0.62):
        return 'cobble_dark'
    return 'cobble'
