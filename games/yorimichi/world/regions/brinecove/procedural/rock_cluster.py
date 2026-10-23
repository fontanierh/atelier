"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove import rocks
from brinecove.procedural.random_state import RNG
from brinecove.procedural.random_state import TAU
import math


def rock_cluster(b, x, y, z, radius, count, tall=False):
    for i in range(count):
        ang = RNG.uniform(0, TAU)
        rr = RNG.uniform(0, radius * 0.75)
        px, py = x + math.cos(ang) * rr, y + math.sin(ang) * rr
        sx = RNG.uniform(0.55, 1.15) * radius
        sy = RNG.uniform(0.55, 1.15) * radius
        sz = RNG.uniform(0.55, 1.3) * radius * (1.8 if tall else 1.0)
        # Bedded, noise-eroded boulders half buried in the ground (rocks.boulder), never cut prisms.
        rocks.boulder(b, px, py, z + 1.0, (sx * 1.2, sy, sz), RNG, ('rock', 'rock_dark', 'rock_light')[i % 3])
