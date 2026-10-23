"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove import layout as L
from brinecove import rocks
from brinecove.kit import bush
from brinecove.kit import grass_tuft
from brinecove.procedural.foam_ring import foam_ring
from brinecove.procedural.random_state import RNG
from brinecove.procedural.rock_cluster import rock_cluster
from brinecove.procedural.shore_foam import shore_foam
from brinecove.procedural.shoreline_foam import shoreline_foam
import random


def terrain_dressing(b, hills=True):
    """Rock shelves, crags, the statue islet, foam and (for the review scene only) the distant domed hills."""
    # Angular coastal rock shelves break up the sampled heightfield edge.
    rock_points = []
    for y in range(-620, 61, 26):
        hw = L.bay_half(y)
        for side in (-1, 1):
            x = side * (hw + RNG.uniform(1, 12))
            rock_points.append((x, y + RNG.uniform(-8, 8), L.height(x, y), RNG.uniform(3.5, 8.5)))
    for x, y, z, r in rock_points:
        rock_cluster(b, x, y, z - 1.0, r, RNG.randint(2, 4))
    crag_rng = random.Random(3307)
    for x, y, _, r in L.SEA_STACKS:
        rocks.crag(b, x, y, -3.0, r * crag_rng.uniform(1.1, 1.8), r, crag_rng, 7)
        foam_ring(b, x, y, r * 1.05, 16)
    # Broken rock shelves on both headlands keep the cliff silhouette from
    # reading as one smooth sampled surface.
    for side in (-1, 1):
        for _ in range(120):
            x = side * RNG.uniform(420, 790)
            y = RNG.uniform(-220, 470)
            if L.is_water(x, y) or L.slope(x, y) < 0.45:
                continue
            z = L.height(x, y)
            if z < 4.0:
                continue
            rock_cluster(b, x, y, z - 1.2, RNG.uniform(2.0, 6.0), RNG.randint(1, 3))
        # Ferns and dry grass on the steep ground between the outcrops. Thin ledge beams and spikes used to stand
        # here; drawn across uneven slopes they floated and crossed each other (playtest note 2).
        for _ in range(500):
            x = side * RNG.uniform(420, 800)
            y = RNG.uniform(-260, 520)
            if L.is_water(x, y) or L.slope(x, y) < 0.55 or L.height(x, y) < 5.0:
                continue
            if RNG.random() < 0.5:
                bush(b, x, y, L.height(x, y) - 0.2, 0.0, RNG.uniform(0.35, 0.75), RNG)
            else:
                grass_tuft(b, x, y, L.height(x, y) - 0.05, RNG.uniform(0, 360), RNG.uniform(0.6, 1.2), RNG)
    # Tiered bedded outcrops dress every steep face (rocks.py).
    rocks.cliff_rocks(b, random.Random(6113))
    # The statue islet: a craggy spire whose core top is the statue's plinth.
    rock_cluster(b, L.STATUE[0], L.STATUE[1], -2.5, 16.0, 6, tall=False)
    rocks.crag(b, L.STATUE[0], L.STATUE[1], -3.0, 12.0, 15.0, random.Random(911), 11)
    b.cylinder((L.STATUE[0], L.STATUE[1], 10.5), (L.STATUE[0], L.STATUE[1], 12.2), 5.2, 'rock_light', 9,
               radius_b=4.6)
    for i in range(5):
        b.sphere((L.STATUE[0] + RNG.uniform(-7, 7), L.STATUE[1] + RNG.uniform(-7, 7),
                  RNG.uniform(1, 10)), RNG.uniform(1.0, 2.6), 'rock_light' if i % 2 else 'rock',
                 (1.2, 1.0, 0.8), subdiv=0)
    foam_ring(b, L.STATUE[0], L.STATUE[1], 17.5, 20)
    shoreline_foam(b)
    shore_foam(b)
    if not hills:
        return b
    # Distant forested hills, low and rounded so they frame rather than
    # dominate the cove. Several overlapping domes make each ridge. The game has its own far hills.
    hill_rng = random.Random(7741)
    for x, y, r, mat in [
        (-720, 640, 210, 'jungle_dark'), (-470, 700, 240, 'jungle_dark'),
        (-210, 740, 220, 'jungle'), (60, 720, 250, 'jungle_dark'),
        (330, 690, 230, 'jungle'), (590, 650, 205, 'jungle_dark'),
        (-880, 240, 210, 'rock'), (890, 260, 220, 'rock'),
        (-870, -30, 180, 'jungle_dark'), (880, -10, 190, 'jungle_dark'),
    ]:
        b.sphere((x, y, -5), r, mat, (1.35, 1.0, 0.27), subdiv=1)
        b.sphere((x + r * 0.55, y + r * 0.2, -5), r * 0.72, mat, (1.2, 1.0, 0.24), subdiv=1)
        if mat != 'rock':
            rocks.canopy_hill(b, x, y, r, 1.35, 0.27, hill_rng)
            rocks.canopy_hill(b, x + r * 0.55, y + r * 0.2, r * 0.72, 1.2, 0.24, hill_rng)
    return b
