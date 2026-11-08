"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove import layout as L
from brinecove.geom import Builder
from brinecove.kit import banana
from brinecove.kit import fern
from brinecove.kit import grass_tuft
from brinecove.kit import vine
from brinecove.procedural.random_state import RNG


def vegetation():
    # Trees, palms, shrubs and flowering mounds are instanced from flora.py by the build; this mesh carries the
    # one-off understory: vines, ferns, bananas and crest grass.
    b = Builder('09_vegetation')
    sc = L.scatter()
    # Vines on the wet east cliff and the west headland.
    for y in range(90, 230, 12):
        vine(b, 438 - RNG.uniform(0, 8), y, 48 - RNG.uniform(0, 8), RNG.uniform(12, 26), RNG)
    for y in range(-80, 150, 16):
        vine(b, -430 - RNG.uniform(0, 12), y, 42 - RNG.uniform(0, 12), RNG.uniform(8, 18), RNG)
    # Hanging green breaks up the bare cliff bands along both headland shores.
    for side in (-1, 1):
        for y in range(-220, 62, 11):
            x = side * (L.bay_half(y) + RNG.uniform(16.0, 58.0))
            z = L.height(x, y)
            if z > 8.0:
                vine(b, x, y, z + RNG.uniform(0.5, 3.0), RNG.uniform(10, 24), RNG)
    # Ferns and banana plants give the understory a second layer.
    for i, (x, y, z, _, scale) in enumerate(sc['bushes']):
        if i % 5 == 0:
            fern(b, x + RNG.uniform(-1, 1), y + RNG.uniform(-1, 1), z,
                 RNG.uniform(0, 360), RNG.uniform(0.75, 1.25), RNG)
        if i % 13 == 0:
            banana(b, x + RNG.uniform(-1.5, 1.5), y + RNG.uniform(-1.5, 1.5), z,
                   RNG.uniform(0, 360), RNG.uniform(0.8, 1.3), RNG)
    # Dry crest grass catches the late light on both headlands.
    for _ in range(900):
        side = -1 if RNG.random() < 0.5 else 1
        x = side * RNG.uniform(420, 790)
        y = RNG.uniform(-220, 500)
        z = L.height(x, y)
        if z < 44.0 or L.is_water(x, y):
            continue
        grass_tuft(b, x, y, z + 0.05, RNG.uniform(0, 360), RNG.uniform(0.7, 1.4), RNG)
    return b
