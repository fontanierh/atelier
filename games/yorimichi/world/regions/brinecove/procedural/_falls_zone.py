"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove import layout as L
import functools


@functools.lru_cache(maxsize=1)
def _falls_zone():
    g = L.gorge_levels()
    return g['lower'] - 45.0, g['upper'] + 8.0, g['pool'] + 14.0
