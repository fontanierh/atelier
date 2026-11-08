"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove import layout as L
import math


def shoreline_foam(b):
    for y in range(-560, 56, 13):
        hw = L.bay_half(y)
        for side in (-1, 1):
            x = side * (hw + 1.5)
            wobble = 2.2 * math.sin(y * 0.18 + side)
            b.quad((x + side * 3.0, y - 4.2, 0.04),
                   (x + side * (11.0 + wobble), y - 3.4, 0.03),
                   (x + side * (10.0 + wobble), y + 3.4, 0.03),
                   (x + side * 3.0, y + 4.2, 0.04), 'water_shallow')
            # Two broad shallow shelves fade the deep blue into the shore.
            b.quad((x + side * 8.0, y - 6.0, 0.02),
                   (x + side * (42.0 + wobble), y - 5.0, 0.01),
                   (x + side * (38.0 + wobble), y + 5.0, 0.01),
                   (x + side * 8.0, y + 6.0, 0.02), 'water_shallow')
            b.quad((x + side * 38.0, y - 6.0, 0.005),
                   (x + side * (82.0 + wobble), y - 5.0, 0.0),
                   (x + side * (78.0 + wobble), y + 5.0, 0.0),
                   (x + side * 38.0, y + 6.0, 0.005), 'water_mid')
