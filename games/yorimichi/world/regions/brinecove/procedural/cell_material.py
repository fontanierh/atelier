"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove import layout as L
from brinecove import rocks
from brinecove.procedural.falls_cliff import falls_cliff
from brinecove.procedural.yard_material import yard_material


def cell_material(a, bb, c, d, gx, gy, sl, i, j):
    """Material for one ground cell from its corners, centre (local metres) and slope."""
    zavg = (a[2] + bb[2] + c[2] + d[2]) / 4
    # A cell that straddles the waterline at a cliff toe must not paint seabed above the sea.
    dry = max(a[2], bb[2], c[2], d[2]) > 0.8
    if zavg < 0.15 and not dry:
        return 'seabed'
    if zavg < 2.2:
        return 'terrain'
    if L.is_water(gx, gy):
        return 'terrain' if dry else 'seabed'
    if L.in_gorge(gx, gy, 3.0):
        if sl > 0.45:
            return 'rock' if falls_cliff(gx, gy, zavg) else 'terrain'
        return 'seabed'
    if sl < 0.4 and L.town_floor(gx, gy):
        return yard_material(gx, gy)
    if falls_cliff(gx, gy, zavg) and (sl > 0.3 or max(a[2], bb[2], c[2], d[2]) - min(a[2], bb[2], c[2], d[2]) > 1.6):
        return 'rock'
    return rocks.terrain_material(gx, gy, zavg, sl, i, j)
