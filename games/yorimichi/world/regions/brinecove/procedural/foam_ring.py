"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove import falls
import random


def foam_ring(b, x, y, radius, segments=14):
    """A broken collar of animated foam around a rock or islet: v runs 0 at the rock to 1 offshore."""
    falls.foam_ring(b, x, y, 0.07, radius * 0.72, radius * 1.18, random.Random(int(x * 7 + y * 13)), segments)
