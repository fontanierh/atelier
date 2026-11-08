"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove import rocks


def yard_material(x, y):
    """Beaten earth and old setts between the houses and the paved streets, never a lawn."""
    n = rocks.fbm(x, y, 18.0, 3, 41)
    return 'cobble_dark' if n > 0.58 else 'earth'
