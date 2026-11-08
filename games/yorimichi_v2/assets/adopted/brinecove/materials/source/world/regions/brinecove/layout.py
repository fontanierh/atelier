"""Plan for Brinecove. Plain Python so the layout can be tested and reviewed without Blender.

The frame is Blender metres: x east, y north, z up. Sea level is 0. This module holds the one source of truth for
the basin silhouette, terraces, building lots, piers, landmarks and scatter masks.
"""
import math
import random

X_MIN, X_MAX = -800.0, 800.0
Y_MIN, Y_MAX = -700.0, 500.0
# The review terrain reaches past the playable basin so its edge is water, not a cut shelf.
VIEW_X_MIN, VIEW_X_MAX = -1100.0, 1100.0
VIEW_Y_MIN, VIEW_Y_MAX = -900.0, 850.0
QUAY_Y = 60.0
QUAY_Z = 4.5
UPPER_Z = 30.0
WATCHTOWER = (-120.0, 470.0, 42.0)
LIGHTHOUSE = (-618.0, -38.0, 63.0)
STATUE = (-120.0, -220.0, 0.0)
WATERFALL = (448.0, 30.0, 55.0)

COLORS = {
    'stone': '#8a7d67', 'stone_light': '#a89a80', 'stone_dark': '#63594a',
    'plaster': '#dfc79c', 'cream': '#efdcb5', 'ochre': '#d39a55', 'coral': '#c96b4f',
    'teal_wall': '#4f8b83', 'sage_wall': '#98a474', 'rose_wall': '#d9968a', 'yellow_wall': '#e6c06e', 'peach_wall': '#e6ad86',
    'azure_wall': '#679fb4', 'lime_wall': '#bcc58b',
    'shutter_blue': '#3d6b83', 'shutter_teal': '#3f7570',
    'shutter_green': '#4a6b3f', 'shutter_red': '#9c4a3c',
    'blossom': '#d4626a', 'blossom_pale': '#e39a92',
    'wood': '#6b4d35', 'wood_dark': '#3f3128', 'wood_light': '#95704b',
    'roof_terra': '#a8563e', 'roof_terra_light': '#bf7655', 'roof_teal': '#4f7f79',
    'roof_slate': '#4a5158', 'roof_straw': '#ad8b58',
    'cobble': '#9a8f7c', 'cobble_dark': '#756b5c',
    'canvas': '#e3d5b4', 'canvas_red': '#b0483a', 'canvas_teal': '#3f8a83', 'canvas_gold': '#d9a640',
    'canvas_blue': '#4c76a6', 'canvas_green': '#6f8f45', 'clay': '#a9684b',
    'jungle_dark': '#2f4522', 'jungle': '#3f5a2c', 'jungle_light': '#58733a',
    'autumn_rust': '#9c4f2c', 'autumn_gold': '#b07a34', 'autumn_olive': '#6d7034',
    'palm': '#4a6a2e', 'palm_light': '#6c8a3f', 'sand': '#c7ad7d', 'earth': '#93785a',
    'planks': '#8a6a48', 'hull': '#4f3a2a', 'deck_planks': '#a08055',
    'leaf_mid': '#4f6b33', 'leaf_light': '#6c8a3f', 'leaf_deep': '#33471f',
    'leaf_warm': '#96703a', 'palm_frond': '#5b7a36',
    'waterfall': '#dff2ef', 'mist': '#eef6f3', 'spray': '#f0f6f4',
    'leaf_sun': '#8aa046', 'leaf_rust': '#b0622c', 'leaf_gold': '#ba923a', 'palm_trunk': '#7a6448',
    'rock': '#8c7c60', 'rock_light': '#ad9a74', 'rock_dark': '#584f42', 'rock_strata': '#8a7a5e', 'moss': '#5f8a34',
    'seabed': '#315f63', 'water': '#1f7f8c', 'water_deep': '#0f4257', 'sea': '#1f8fa0',
    'water_shallow': '#57c4c6', 'water_mid': '#1f9fae', 'foam': '#e8f0e7',
    'sail': '#e1d3b3', 'sail_dark': '#3d3a37', 'sail_stripe': '#a44d3d',
    'metal': '#3b3a36', 'gold': '#d5a64a',
    'lantern': '#f2c36b', 'glass': '#26424a', 'glass_warm': '#ffc46b', 'skin': '#b98a63',
    'flag_black': '#292424', 'flag_red': '#a23c32', 'rope': '#bda77c',
}


def clamp(value, lo=0.0, hi=1.0):
    return lo if value < lo else hi if value > hi else value


def smooth(value):
    value = clamp(value)
    return value * value * (3.0 - 2.0 * value)


def lerp(a, b, t):
    return a + (b - a) * t


def bay_half(y):
    """Half-width of the water at y. The cove narrows at the town and opens to the sea."""
    if y >= QUAY_Y:
        return 2000.0
    return min(620.0, 430.0 + 0.28 * (QUAY_Y - y))


def is_water(x, y):
    return y < QUAY_Y and abs(x) < bay_half(y)


def town_height(x, y):
    z = QUAY_Z
    z += (UPPER_Z - QUAY_Z) * smooth((y - 280.0) / 8.0)
    z += 30.0 * smooth((y - 452.0) / 72.0)
    z += 8.0 * smooth((y - 520.0) / 90.0)
    # Gentle rise at the sides keeps the quay from reading as a ruler.
    z += 3.0 * smooth((abs(x) - 300.0) / 120.0) * smooth((y - QUAY_Y) / 130.0)
    # A knoll for the watchtower, kept inside its own pad so no roof floats.
    z += 12.0 * math.exp(-((x - WATCHTOWER[0]) ** 2 + (y - WATCHTOWER[1]) ** 2) / (72.0 ** 2))
    return z


# Sea-cliff profile, as distance inland from the waterline: a rocky toe, a lower cliff, a ledge wide enough for the
# stilt cabins, an upper cliff and the plateau. The old single 74 m smoothstep was a 40-degree ramp; these steps
# reach 65-70 degrees, and the prism outcrops (rocks.py) turn them into stone walls.
TOE, LOW_TOP, LEDGE_IN, UP_TOP = 8.0, 22.0, 48.0, 64.0
LEDGE_D = 35.0
GORGE_Y = 30.0  # axis of the east river and its two-tier waterfall


def cliff_wobble(y, side):
    """How far the cliff line wanders in and out along the shore, in metres."""
    return 5.0 * math.sin(y * 0.031 + side) + 3.0 * math.sin(y * 0.083 + 2.0 * side)


def cliff_profile(d):
    z = 3.0 * smooth(d / TOE)
    z += 21.0 * smooth((d - TOE) / (LOW_TOP - TOE))
    z += 4.0 * smooth((d - LOW_TOP) / (LEDGE_IN - LOW_TOP))
    z += 28.0 * smooth((d - LEDGE_IN) / (UP_TOP - LEDGE_IN))
    return z


def fall_lips():
    """x of the lower and upper waterfall lips on the gorge axis."""
    wob = cliff_wobble(GORGE_Y, 1)
    return bay_half(GORGE_Y) + LOW_TOP - wob, bay_half(GORGE_Y) + UP_TOP - wob


def in_gorge(x, y, margin=0.0):
    lower, _ = fall_lips()
    return lower - 28.0 - margin <= x <= 700.0 + margin and abs(y - GORGE_Y) <= 16.0 + margin


_LEVELS = {}


def gorge_levels():
    """Water levels: the river at the upper lip (rising 2 cm per metre upstream) and the ledge pool."""
    if not _LEVELS:
        lower, upper = fall_lips()
        floor = min(raw_height(x, GORGE_Y) - 0.02 * (x - upper) for x in range(int(upper) + 2, 690, 4))
        _LEVELS.update(river=floor - 1.6, pool=raw_height((lower + upper) / 2 - 6.0, GORGE_Y) - 1.0,
                       lower=lower, upper=upper)
    return _LEVELS


def river_level(x):
    g = gorge_levels()
    return g['river'] + 0.02 * max(0.0, x - g['upper'])


def gorge_depth(x, y, raw=None):
    """How far the slot canyon, the ledge pool and the lower notch cut below the natural ground."""
    if x < 425.0 or x > 720.0 or abs(y - GORGE_Y) > 40.0:
        return 0.0
    raw = raw_height(x, y) if raw is None else raw
    g = gorge_levels()
    dy = abs(y - GORGE_Y)
    cut = 0.0
    # Slot canyon: a flat 10 m river bed with walls rising 40 m over the next 10 m.
    if g['upper'] - 14.0 <= x <= 700.0:
        fade = 1.0 - smooth((x - 680.0) / 20.0)
        bed = river_level(x) - 1.4 + 40.0 * smooth((dy - 5.0) / 10.0)
        cut = max(cut, (raw - bed) * fade)
    # Ledge pool between the two falls.
    if g['lower'] + 1.0 <= x <= g['upper'] - 6.0:
        edge = smooth((x - (g['lower'] + 1.0)) / 4.0)
        bed = g['pool'] - 1.4 + 20.0 * smooth((dy - 7.0) / 8.0) + 6.0 * (1.0 - edge)
        cut = max(cut, raw - bed)
    # The lower lip notch the pool spills through.
    if g['lower'] - 1.5 <= x <= g['lower'] + 3.0:
        bed = g['pool'] - 0.4 + 14.0 * smooth((dy - 5.0) / 7.0)
        cut = max(cut, raw - bed)
    # A sea-level plunge alcove under the lip: a sheer back wall, so the lower fall drops free into a grotto
    # instead of sliding down the 56-degree cliff.
    if g['lower'] - 28.0 <= x <= g['lower'] - 1.5:
        back = smooth((g['lower'] - 1.5 - x) / 1.4)
        bed = -3.0 + 45.0 * smooth((dy - 10.0 - 0.12 * (g['lower'] - x)) / 5.0)
        cut = max(cut, (raw - bed) * back)
    return max(0.0, cut)


def headland_height(x, y):
    d = abs(x) - bay_half(y)
    side = 1 if x > 0 else -1
    # A high stepped cliff right at the water, then lower, broken country inland.
    cliff = cliff_profile(d + cliff_wobble(y, side))
    back = 1.0 - 0.45 * smooth((d - 120.0) / 280.0)
    z = 2.0 + cliff * back
    z += 10.0 * smooth((y - 10.0) / 190.0)
    z += 3.0 * smooth((abs(x) - 600.0) / 150.0)
    z += 8.0 * math.sin(x * 0.017) * math.cos(y * 0.014) * smooth(d / 90.0)
    z += 4.0 * math.sin(x * 0.041 + y * 0.022) * smooth(d / 120.0)
    return z


def raw_height(x, y):
    if y >= QUAY_Y:
        z = town_height(x, y)
        # Fade the town plateau into the natural side hills, then raise the
        # east and west walls into the cliffs that frame the cove.
        side = smooth((abs(x) - 390.0) / 140.0)
        z = lerp(z, headland_height(x, y), side)
        cliff = 58.0 * smooth((abs(x) - 420.0) / 72.0)
        z = max(z, QUAY_Z + cliff + 7.0 * smooth((abs(x) - 390.0) / 100.0) * smooth((y - QUAY_Y) / 280.0))
        rolling = 7.0 * smooth((abs(x) - 420.0) / 180.0) + 7.0 * smooth((y - 460.0) / 150.0)
        z += rolling * (0.7 * math.sin(x * 0.014) * math.cos(y * 0.011)
                        + 0.35 * math.sin(x * 0.033 + y * 0.021))
        if y > 520.0:
            z += 20.0 * smooth((y - 520.0) / 260.0)
        return z
    if not is_water(x, y):
        z = headland_height(x, y)
        z += 6.0 * math.sin(x * 0.020) * math.cos(y * 0.017) * smooth((abs(x) - bay_half(y)) / 120.0)
        return z
    return -3.5 - 0.035 * (QUAY_Y - y) - 0.25 * smooth((120.0 - abs(x)) / 240.0)


def noise(x, y):
    return (1.15 * math.sin(x * 0.031 + 0.7) * math.sin(y * 0.027 - 0.4)
            + 0.55 * math.sin(x * 0.071 + y * 0.053)
            + 0.28 * math.cos(x * 0.13 - y * 0.09))


def height(x, y):
    raw = raw_height(x, y)
    z = raw - gorge_depth(x, y, raw)
    if y >= QUAY_Y - 2.0:
        town = smooth((y - QUAY_Y) / 30.0) * (1.0 - smooth((abs(x) - 380.0) / 130.0))
        z += noise(x, y) * (1.0 - 0.75 * town)
    # The headlands' outer shores: a wandering coast that tapers each headland to a rounded point, so neither the
    # map nor the sea view shows the old straight-sided fingers ending on a rectangle.
    edge = max(outer_shore(x, y), y - 680.0)
    if edge > 0.0:
        z = lerp(z, -9.0, smooth(edge / 120.0))
    return z


def outer_shore(x, y):
    """Signed distance past the headlands' outer sea coast (positive offshore), in metres."""
    side = 1.0 if x > 0 else -1.0
    wander = (30.0 * math.sin(y * 0.0071 + 1.3 * side) + 17.0 * math.sin(y * 0.0193 + 0.4 * side)
              + 8.0 * math.sin(y * 0.0467 + 2.1 * side) + 4.0 * math.sin(y * 0.103 + side))
    # Narrowing south of the lighthouse to a blunt point just outside the cove's own cliff line.
    taper = smooth((-120.0 - y) / 600.0)
    limit = lerp(840.0, bay_half(y) + 60.0, taper) + wander * (1.0 - 0.55 * taper)
    across = abs(x) - limit
    tip = -660.0 + 22.0 * math.sin(abs(x) * 0.019 + side) + 9.0 * math.sin(abs(x) * 0.061) - y
    # A soft maximum rounds the point instead of cutting a corner.
    k = 60.0
    top = max(across, tip)
    return top + k * math.log(math.exp((across - top) / k) + math.exp((tip - top) / k))


def slope(x, y, step=6.0):
    dx = (height(x + step, y) - height(x - step, y)) / (2 * step)
    dy = (height(x, y + step) - height(x, y - step)) / (2 * step)
    return math.hypot(dx, dy)


def yaw_point(x, y, cx, cy, yaw):
    a = math.radians(yaw)
    dx, dy = x - cx, y - cy
    return cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a)


def local_point(x, y, cx, cy, yaw):
    """The point's offset in a lot's own rotated frame."""
    a = math.radians(yaw)
    dx, dy = x - cx, y - cy
    return dx * math.cos(a) - dy * math.sin(a), dx * math.sin(a) + dy * math.cos(a)


# Lots are (key, x, y, z, width, depth, height, floors, style, yaw, roof). Fronts face south (-Y) unless yaw says
# otherwise. The market opening is x -90..90, so no lot sits inside it.
BUILDINGS = [
    ('rum-w1', -352, 122, QUAY_Z, 46, 27, 15.5, 3, 'tavern', 0, 'roof_terra'),
    ('rum-w2', -300, 122, QUAY_Z, 42, 25, 12.0, 2, 'shop', 0, 'roof_teal'),
    ('rum-w3', -253, 122, QUAY_Z, 38, 26, 16.5, 3, 'tavern', 0, 'roof_terra'),
    ('rum-w4', -205, 122, QUAY_Z, 40, 24, 11.0, 2, 'house', 0, 'roof_slate'),
    ('rum-w5', -158, 122, QUAY_Z, 38, 27, 14.0, 3, 'warehouse', 0, 'roof_terra'),
    ('rum-w6', -108, 122, QUAY_Z, 34, 25, 12.5, 2, 'shop', 0, 'roof_teal'),
    ('rum-e1', 110, 122, QUAY_Z, 34, 26, 13.0, 3, 'shop', 0, 'roof_terra'),
    ('rum-e2', 155, 122, QUAY_Z, 38, 25, 16.0, 3, 'tavern', 0, 'roof_slate'),
    ('rum-e3', 204, 122, QUAY_Z, 40, 27, 11.5, 2, 'warehouse', 0, 'roof_terra'),
    ('rum-e4', 254, 122, QUAY_Z, 38, 25, 14.5, 3, 'house', 0, 'roof_teal'),
    ('rum-e5', 303, 122, QUAY_Z, 40, 26, 12.5, 2, 'shop', 0, 'roof_terra'),
    ('rum-e6', 352, 122, QUAY_Z, 38, 24, 15.0, 3, 'tavern', 0, 'roof_slate'),
    ('back-w1', -340, 194, 5.1, 40, 26, 12.0, 2, 'house', 0, 'roof_terra'),
    ('back-w2', -294, 194, 5.2, 38, 24, 14.5, 3, 'house', 0, 'roof_teal'),
    ('back-w3', -246, 194, 5.3, 42, 27, 10.5, 2, 'warehouse', 0, 'roof_slate'),
    ('back-w4', -196, 194, 5.4, 36, 25, 13.5, 3, 'house', 0, 'roof_terra'),
    ('back-w5', -145, 194, 5.5, 40, 26, 11.0, 2, 'shop', 0, 'roof_teal'),
    ('back-e1', 132, 194, 5.2, 38, 25, 12.5, 2, 'house', 0, 'roof_terra'),
    ('back-e2', 180, 194, 5.3, 40, 26, 14.0, 3, 'tavern', 0, 'roof_slate'),
    ('back-e3', 230, 194, 5.4, 38, 24, 11.5, 2, 'house', 0, 'roof_teal'),
    ('back-e4', 280, 194, 5.5, 42, 27, 13.0, 3, 'warehouse', 0, 'roof_terra'),
    ('back-e5', 334, 194, 5.6, 38, 25, 12.0, 2, 'shop', 0, 'roof_slate'),
    ('terrace-w1', -270, 338, UPPER_Z, 44, 26, 13.0, 2, 'house', 0, 'roof_terra'),
    ('terrace-w2', -216, 338, UPPER_Z, 36, 24, 15.5, 3, 'tavern', 0, 'roof_teal'),
    ('terrace-w3', -164, 338, UPPER_Z, 38, 26, 11.5, 2, 'house', 0, 'roof_slate'),
    ('terrace-w4', -114, 338, UPPER_Z, 36, 25, 14.0, 3, 'house', 0, 'roof_terra'),
    ('terrace-w5', -64, 338, UPPER_Z, 34, 24, 10.5, 2, 'shop', 0, 'roof_teal'),
    ('terrace-e1', 58, 338, UPPER_Z, 36, 25, 12.5, 2, 'house', 0, 'roof_terra'),
    ('terrace-e2', 108, 338, UPPER_Z, 38, 26, 15.0, 3, 'tavern', 0, 'roof_slate'),
    ('terrace-e3', 158, 338, UPPER_Z, 36, 24, 11.0, 2, 'house', 0, 'roof_teal'),
    ('terrace-e4', 208, 338, UPPER_Z, 38, 25, 13.5, 3, 'house', 0, 'roof_terra'),
    ('terrace-e5', 258, 338, UPPER_Z, 36, 26, 12.0, 2, 'shop', 0, 'roof_slate'),
    ('terrace-e6', 308, 338, UPPER_Z, 38, 24, 14.5, 3, 'tavern', 0, 'roof_teal'),
    ('crest-w1', -250, 414, UPPER_Z + 0.5, 38, 24, 12.0, 2, 'house', 0, 'roof_terra'),
    ('crest-w2', -190, 414, UPPER_Z + 0.5, 36, 25, 14.0, 3, 'house', 0, 'roof_teal'),
    ('crest-e1', 70, 414, UPPER_Z + 0.5, 38, 24, 13.0, 2, 'tavern', 0, 'roof_slate'),
    ('crest-e2', 130, 414, UPPER_Z + 0.5, 36, 25, 11.0, 2, 'house', 0, 'roof_terra'),
    ('crest-e3', 190, 414, UPPER_Z + 0.5, 40, 26, 15.0, 3, 'house', 0, 'roof_teal'),
    ('crest-e4', 250, 414, UPPER_Z + 0.5, 36, 24, 12.0, 2, 'shop', 0, 'roof_slate'),
    ('cliff-w1', -398, 248, 12.0, 30, 22, 8.5, 2, 'shack', -8, 'roof_straw'),
    ('cliff-w2', -438, 292, 19.0, 26, 20, 7.5, 1, 'shack', -12, 'roof_terra'),
    ('cliff-e1', 405, 262, 14.0, 28, 20, 9.0, 2, 'shack', 8, 'roof_straw'),
    # A third row fills the shelf between Rum Row and the retaining wall.
    ('mid-w1', -330, 258, 5.0, 38, 25, 11.0, 2, 'house', 0, 'roof_terra'),
    ('mid-w2', -270, 258, 5.0, 36, 24, 12.0, 2, 'shop', 0, 'roof_teal'),
    ('mid-w3', -208, 258, 5.0, 38, 25, 10.5, 2, 'house', 0, 'roof_slate'),
    ('mid-w4', -70, 258, 5.0, 34, 24, 11.0, 2, 'house', 0, 'roof_terra'),
    ('mid-e1', 70, 258, 5.0, 34, 24, 11.0, 2, 'shop', 0, 'roof_slate'),
    ('mid-e2', 150, 258, 5.0, 38, 25, 11.5, 2, 'house', 0, 'roof_terra'),
    ('mid-e3', 212, 258, 5.0, 36, 24, 12.5, 2, 'tavern', 0, 'roof_teal'),
    # Its west house stood 0.8-3.3 m into the east terrace stair (x 248-256.7); it now starts 2.4 m clear of it.
    ('mid-e4', 276, 258, 5.0, 34, 25, 10.5, 2, 'shop', 0, 'roof_slate'),
]

# A narrow row right on the terrace lip. From the harbor it hides the bare
# retaining wall and gives the town the stacked, inhabited edge in the refs.
_edge_x = (-310, -264, -218, -172, -126, -80, 80, 126, 172, 218, 264, 310)
_edge_styles = ('house', 'shop', 'tavern', 'house', 'shop', 'house')
_edge_roofs = ('roof_terra', 'roof_teal', 'roof_terra', 'roof_slate', 'roof_terra_light')
BUILDINGS = BUILDINGS + [
    (f'edge-{i}', x, 302.0, UPPER_Z, 26.0, 16.0, 8.4 + (i % 4) * 0.9, 2,
     _edge_styles[i % len(_edge_styles)], 0.0, _edge_roofs[i % len(_edge_roofs)])
    for i, x in enumerate(_edge_x)
]

# Permanent two-storey market halls close the long sides of the square. The
# refs read as a dense bazaar street, not a paved parade ground.
_hall_y = (132.0, 166.0, 200.0)
_hall_h = (10.5, 12.0, 11.0)
BUILDINGS = BUILDINGS + [
    (f'hall-{side}-{i}', side * 78.0, y, QUAY_Z, 24.0, 18.0, _hall_h[i], 2,
     ('shop', 'tavern', 'shop')[i], 90.0 if side < 0 else -90.0,
     ('roof_terra', 'roof_teal', 'roof_terra_light')[i])
    for side in (-1, 1) for i, y in enumerate(_hall_y)
]

# Slight, deterministic yaw variation keeps the waterfront from reading as a
# spreadsheet without moving any lot outside its graded pad.
_organic = []
for _b in BUILDINGS:
    _key, _x, _y, _z, _w, _d, _h, _fl, _style, _yaw, _roof = _b
    if _style != 'warehouse':
        _yaw += ((sum(map(ord, _key)) * 7) % 11) - 5
    _organic.append((_key, _x, _y, _z, _w, _d, _h, _fl, _style, _yaw, _roof))
BUILDINGS = _organic

# The reference roofscape climbs. Lift the lower town and add a third storey
# where the extra height reads as another gallery row.
_taller = []
for _b in BUILDINGS:
    _key, _x, _y, _z, _w, _d, _h, _fl, _style, _yaw, _roof = _b
    if _y < 280 and _style != 'warehouse':
        _h += 2.0
        if _style in ('house', 'shop', 'tavern') and _h >= 14.0:
            _fl = max(_fl, 3)
    elif _y >= 280 and _style in ('house', 'shop', 'tavern'):
        _h += 1.2
    _taller.append((_key, _x, _y, _z, _w, _d, _h, _fl, _style, _yaw, _roof))
BUILDINGS = _taller
LOTS = {b[0]: b for b in BUILDINGS}

# A handful of stilt houses on the two headland shores make the town wrap
# around the cove instead of stopping at the quay.
_SHORE = [
    # key, y, width along the shore, depth, height, floors, roof
    ('shore-w1', -168, 24, 16, 8.5, 1, 'roof_straw'), ('shore-w2', -134, 22, 16, 9.5, 2, 'roof_terra'),
    ('shore-w3', -100, 20, 15, 7.5, 1, 'roof_straw'), ('shore-w4', -66, 22, 16, 8.0, 1, 'roof_terra'),
    ('shore-w5', -32, 20, 15, 9.0, 2, 'roof_straw'), ('shore-w6', 2, 18, 14, 7.0, 1, 'roof_terra'),
    ('shore-e1', -178, 24, 16, 8.0, 1, 'roof_straw'), ('shore-e2', -144, 22, 16, 9.0, 2, 'roof_terra'),
    ('shore-e3', -110, 20, 15, 7.5, 1, 'roof_straw'), ('shore-e4', -76, 22, 16, 8.0, 1, 'roof_terra'),
    ('shore-e5', -42, 20, 15, 9.0, 2, 'roof_straw'), ('shore-e6', -8, 18, 14, 7.0, 1, 'roof_terra'),
]
# The cabins sit on the cliff ledge, following its wobble, so none straddles a face.
SHORE_BUILDINGS = [
    (key, (1 if key[6] == 'e' else -1) * (bay_half(y) + LEDGE_D - cliff_wobble(y, 1 if key[6] == 'e' else -1)),
     y, 0, w, d, h, floors, 'shack', (90 if key[6] == 'e' else -90) + (k % 3 - 1) * 4, roof)
    for k, (key, y, w, d, h, floors, roof) in enumerate(_SHORE)
]

# A high, stilted hamlet above the upper terrace gives the town a skyline.
HILLSIDE_BUILDINGS = [
    ('hill-w1', -330, 505, 0, 28, 18, 8.5, 1, 'shack', -6, 'roof_straw'),
    ('hill-w2', -270, 518, 0, 26, 17, 9.0, 2, 'shack', -3, 'roof_terra'),
    ('hill-w3', -210, 505, 0, 24, 16, 8.0, 1, 'shack', -8, 'roof_straw'),
    ('hill-e1', 100, 508, 0, 26, 17, 8.5, 1, 'shack', 5, 'roof_straw'),
    ('hill-e2', 165, 518, 0, 26, 17, 9.0, 2, 'shack', -4, 'roof_terra'),
    ('hill-e3', 230, 505, 0, 24, 16, 8.0, 1, 'shack', 7, 'roof_straw'),
    ('hill-e4', 300, 522, 0, 26, 17, 9.0, 2, 'shack', -3, 'roof_terra'),
]

# The reference town does not stop at the central shelf: narrow houses climb
# both headland slopes and a broken ridge of roofs closes the skyline.  These
# lots are generated into the same table as the hand-placed rows so terrain
# pads, planting masks and the upper/lower module split stay consistent.
def _slope_lots():
    rng = random.Random(6621)
    out = []
    hand_cliff = [b for b in BUILDINGS if b[0].startswith('cliff-')]
    for side in (-1, 1):
        for row in range(3):
            base_x = side * (402.0 + row * 40.0)
            for j in range(6):
                y = 128.0 + j * 43.0 + row * 14.0 + rng.uniform(-5.0, 5.0)
                if y > 398.0:
                    continue
                x = base_x + side * rng.uniform(-7.0, 7.0)
                if side > 0 and abs(x - WATERFALL[0]) < 42.0 and 45.0 < y < 200.0:
                    continue
                if any(abs(x - c[1]) < 32.0 and abs(y - c[2]) < 32.0 for c in hand_cliff):
                    continue
                z = height(x, y) + 0.25
                if z < 7.0:
                    continue
                w = rng.uniform(22.0, 29.0)
                d = rng.uniform(17.0, 21.0)
                h = rng.uniform(8.5, 15.5)
                floors = max(1, min(3, round(h / 5.0)))
                style = rng.choice(('house', 'house', 'shop', 'tavern', 'shack'))
                roof = rng.choice(('roof_terra', 'roof_terra', 'roof_teal', 'roof_slate'))
                yaw = 90.0 if side < 0 else -90.0
                out.append((f'slope-{side}-{row}-{j}', x, y, z, w, d, h, floors, style,
                            yaw + rng.uniform(-4.0, 4.0), roof))
    return out


def _ridge_lots():
    rng = random.Random(3317)
    out = []
    for j in range(16):
        x = -368.0 + j * 49.0 + rng.uniform(-8.0, 8.0)
        y = 458.0 + rng.uniform(-8.0, 23.0)
        if abs(x - WATCHTOWER[0]) < 37.0 and abs(y - WATCHTOWER[1]) < 37.0:
            continue
        if abs(x) < 25.0:
            continue
        z = height(x, y) + 0.3
        w = rng.uniform(20.0, 27.0)
        d = rng.uniform(16.0, 20.0)
        h = rng.uniform(8.0, 14.0)
        style = rng.choice(('house', 'shop', 'tavern', 'shack'))
        out.append((f'ridge-{j}', x, y, z, w, d, h, max(1, min(3, round(h / 5.0))), style,
                    rng.uniform(-6.0, 6.0), rng.choice(('roof_terra', 'roof_teal', 'roof_straw'))))
    return out


def dense_lots():
    """Split every broad lot into narrow touching townhouses.

    The Sunburst views show a continuous, irregular wall of narrow facades.  Two
    to three houses per original lot keep the hand-placed street rhythm while
    removing the repeated-wide-box read of the blockout.
    """
    out = []
    for spec in BUILDINGS:
        key, x, y, z, w, d, h, floors, style, yaw, roof = spec
        n = 3 if w >= 38.0 else 2
        if style in ('warehouse', 'shack'):
            n = 2
        gap = 1.2
        nw = (w - gap * (n - 1)) / n
        for i in range(n):
            rng = random.Random(sum(map(ord, key)) * 97 + i * 41 + n * 13)
            lx = -w / 2 + w * (i + 0.5) / n
            nd = d * rng.uniform(0.86, 0.98)
            ly = -d / 2 + nd / 2 + rng.uniform(-0.7, 0.7)
            px, py = yaw_point(x + lx, y + ly, x, y, yaw)
            hh = h * rng.uniform(0.82, 1.18)
            if style == 'warehouse':
                hh = h * rng.uniform(0.92, 1.1)
                sub_style = 'warehouse'
                sub_floors = floors
            elif style == 'shack':
                sub_style = 'shack'
                sub_floors = max(1, min(2, floors))
            else:
                sub_style = rng.choices(('house', 'shop', 'tavern'), (5, 2, 2))[0]
                sub_floors = max(1, min(4, round(hh / 4.7)))
            sub_roof = roof if rng.random() < 0.58 else rng.choice(
                ('roof_terra', 'roof_terra_light', 'roof_teal', 'roof_slate', 'roof_straw'))
            out.append((f'{key}-{i}', px, py, z + rng.uniform(-0.08, 0.18),
                        nw - rng.uniform(0.2, 1.4), nd, hh, sub_floors, sub_style,
                        yaw + rng.uniform(-2.6, 2.6), sub_roof))
    return out

PIERS = [
    ('central', 0.0, 60.0, -184.0, 24.0),
    ('west', -238.0, 60.0, -112.0, 13.0),
    ('east', 238.0, 60.0, -138.0, 16.0),
]

SHIPS = [
    ('galleon-adventure', -44.0, -70.0, -16.0, 1.18, True),
    ('galleon-nightjar', 40.0, -132.0, 10.0, 1.10, False),
    ('sloop-east', 252.0, -72.0, 180.0, 0.45, True),
]

MARKET_STALLS = [
    (-42, 116, 12, 7, 'roof_red'), (-12, 110, 12, 7, 'roof_sail'),
    (24, 116, 12, 7, 'roof_red'), (60, 112, 12, 7, 'roof_sail'),
    (-38, 146, 10, 6, 'roof_sail'), (40, 146, 10, 6, 'roof_red'),
    (-16, 202, 10, 6, 'roof_sail'), (18, 202, 10, 6, 'roof_red'),
    (-55, 128, 10, 6, 'roof_sail'), (55, 128, 10, 6, 'roof_red'),
    (-22, 132, 10, 6, 'roof_red'), (22, 132, 10, 6, 'roof_sail'),
    (-24, 174, 10, 6, 'roof_sail'), (24, 174, 10, 6, 'roof_red'),
    (-60, 176, 10, 6, 'roof_red'), (60, 176, 10, 6, 'roof_sail'),
    (-36, 220, 11, 6, 'roof_sail'), (36, 220, 11, 6, 'roof_red'),
    (0, 222, 20, 7, 'roof_sail'),
]


def building_pads():
    global BUILDINGS, LOTS
    BUILDINGS = BUILDINGS + _slope_lots() + _ridge_lots()
    LOTS = {b[0]: b for b in BUILDINGS}
    return [(b[1], b[2], b[4] + 5.0, b[5] + 5.0, b[3], b[9]) for b in BUILDINGS]


PADS = building_pads() + [
    (0.0, 160.0, 200.0, 140.0, height(0.0, 160.0), 0.0),   # the market stays open and flat
    (WATCHTOWER[0], WATCHTOWER[1], 46.0, 46.0, height(WATCHTOWER[0], WATCHTOWER[1]), 0.0),
]

# Pre-split once: the lower and upper town modules both read this table.
DENSE_LOTS = dense_lots()


def pad_height(x, y):
    """The exact surface of a building or public pad at a point, or None outside every pad."""
    for cx, cy, w, d, z, yaw in PADS:
        lx, ly = local_point(x, y, cx, cy, -yaw)
        if abs(lx) <= w / 2 and abs(ly) <= d / 2:
            return z
    return None


def ground(x, y):
    z = height(x, y)
    # Last few metres around a lot settle onto its pad so no wall floats over a noisy sample.
    for cx, cy, w, d, pz, yaw in PADS:
        lx, ly = local_point(x, y, cx, cy, -yaw)
        edge = max(abs(lx) - w / 2, abs(ly) - d / 2)
        if edge <= 5.0:
            blend = smooth((5.0 - edge) / 3.0)
            z = lerp(z, pz, blend)
    return z


def in_lot(x, y, margin=2.0):
    for b in list(BUILDINGS) + list(SHORE_BUILDINGS) + list(HILLSIDE_BUILDINGS):
        lx, ly = local_point(x, y, b[1], b[2], -b[9])
        if abs(lx) <= b[4] / 2 + margin and abs(ly) <= b[5] / 2 + margin:
            return True
    return False


_LOT_GRID = {}
_LOT_CELL = 32.0


def _lot_grid():
    """Town buildings bucketed by 32 m cell, so per-ground-cell lookups stay cheap."""
    if not _LOT_GRID:
        for spec in list(BUILDINGS) + list(SHORE_BUILDINGS):
            r = math.hypot(spec[4], spec[5]) / 2 + 8.0
            for i in range(int((spec[1] - r) // _LOT_CELL), int((spec[1] + r) // _LOT_CELL) + 1):
                for j in range(int((spec[2] - r) // _LOT_CELL), int((spec[2] + r) // _LOT_CELL) + 1):
                    _LOT_GRID.setdefault((i, j), []).append(spec)
    return _LOT_GRID


def town_floor(x, y, margin=5.0):
    """True on the trodden ground around the town's lots, streets and market, where grass must not show."""
    if on_street(x, y, margin) or on_market(x, y, margin):
        return True
    for spec in _lot_grid().get((int(x // _LOT_CELL), int(y // _LOT_CELL)), ()):
        lx, ly = local_point(x, y, spec[1], spec[2], -spec[9])
        if abs(lx) <= spec[4] / 2 + margin and abs(ly) <= spec[5] / 2 + margin:
            return True
    return False


def on_market(x, y, margin=2.0):
    return -98 - margin <= x <= 98 + margin and 96 - margin <= y <= 228 + margin


def on_pier(x, y, margin=3.0):
    for _, px, y0, y1, width in PIERS:
        if abs(x - px) <= width / 2 + margin and y1 - margin <= y <= y0 + margin:
            return True
    return False


def on_street(x, y, margin=1.5):
    if -392 - margin <= x <= 392 + margin and (QUAY_Y - 4 - margin <= y <= 104 + margin or 143 - margin <= y <= 177 + margin):
        return True
    if -318 - margin <= x <= 338 + margin and 312 - margin <= y <= 378 + margin:
        return True
    if abs(x) <= 20 + margin and 225 - margin <= y <= 318 + margin:
        return True
    return False


def on_shore_walkway(x, y, margin=3.0):
    """The timber links between the stilt houses run along each headland shore."""
    for side in (-1, 1):
        specs = sorted([s for s in SHORE_BUILDINGS if s[1] * side > 0], key=lambda s: s[2])
        for a, c in zip(specs, specs[1:]):
            ax, ay = a[1], a[2]
            bx, by = c[1], c[2]
            vx, vy = bx - ax, by - ay
            denom = vx * vx + vy * vy
            t = 0.0 if denom == 0 else max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / denom))
            if math.hypot(x - (ax + vx * t), y - (ay + vy * t)) < margin:
                return True
    return False


def plantable(x, y):
    if y < Y_MIN - 30 or y > Y_MAX + 250:
        return False
    if abs(x) > 880:
        return False
    # South of the quay only the headland shelves are plantable; the bay and
    # the beach edge stay clear.
    if y < QUAY_Y + 2:
        if is_water(x, y) or abs(x) < bay_half(y) + 6.0:
            return False
    if in_lot(x, y, 3.0) or on_market(x, y, 4.0) or on_street(x, y, 3.0) or on_pier(x, y, 5.0):
        return False
    if on_shore_walkway(x, y, 3.5):
        return False
    if abs(x - WATCHTOWER[0]) < 28 and abs(y - WATCHTOWER[1]) < 28:
        return False
    if math.hypot(x - LIGHTHOUSE[0], y - LIGHTHOUSE[1]) < 34.0:
        return False
    if abs(x - WATERFALL[0]) < 30 and 0 <= y <= 180:
        return False
    if in_gorge(x, y, 5.0):
        return False
    if slope(x, y) > 1.8:
        return False
    return True


def headland_plantable(x, y):
    """Dense jungle cover for the cliffs and shelves that frame the cove."""
    if y < -250 or y > 520 or abs(x) < 420 or abs(x) > 815:
        return False
    if y < QUAY_Y and (is_water(x, y) or abs(x) < bay_half(y) + 5.0):
        return False
    if in_lot(x, y, 9.0) or on_shore_walkway(x, y, 4.5):  # keep the cliff cabins in view
        return False
    if math.hypot(x - LIGHTHOUSE[0], y - LIGHTHOUSE[1]) < 85.0:
        return False  # an open, rocky headland round the lighthouse, as painted
    if abs(x - WATERFALL[0]) < 36.0 and 45.0 <= y <= 205.0:
        return False
    if in_gorge(x, y, 4.0):
        return False
    if abs(x - WATCHTOWER[0]) < 34.0 and abs(y - WATCHTOWER[1]) < 34.0:
        return False
    if height(x, y) < 4.0 or slope(x, y) > 1.55:
        return False
    return True


def scatter(seed=7319):
    """Deterministic positions for palms, jungle trees and bushes."""
    rng = random.Random(seed)
    palms, trees, bushes = [], [], []
    # Palms favour the lower town, the quay ends and the sunny headland margins.
    for _ in range(18000):
        x = rng.uniform(X_MIN + 20, X_MAX - 20)
        y = rng.uniform(Y_MIN + 20, Y_MAX - 20)
        if not plantable(x, y) or is_water(x, y):
            continue
        z = ground(x, y)
        if z < 1.5:
            continue
        if len(palms) < 340 and (y < 320 or abs(x) > 390) and rng.random() < 0.55:
            palms.append((x, y, z, rng.uniform(0, 360), rng.uniform(0.75, 1.25)))
        elif len(trees) < 860 and (y > 300 or abs(x) > 390 or rng.random() < 0.35):
            trees.append((x, y, z, rng.uniform(0, 360), rng.uniform(0.75, 1.35)))
        elif len(bushes) < 760:
            bushes.append((x, y, z, rng.uniform(0, 360), rng.uniform(0.6, 1.2)))
        if len(palms) >= 340 and len(trees) >= 860 and len(bushes) >= 760:
            break
    # A dedicated headland pass keeps the framing cliffs lush rather than
    # relying on a few strays from the town scatter.
    for _ in range(26000):
        side = -1 if rng.random() < 0.5 else 1
        x = side * rng.uniform(425, 810)
        y = rng.uniform(-245, 515)
        if not headland_plantable(x, y):
            continue
        z = ground(x, y)
        sl = slope(x, y)
        if len(trees) < 1950 and sl < 1.15 and (y > 70 or rng.random() < 0.72):
            trees.append((x, y, z, rng.uniform(0, 360), rng.uniform(1.15, 1.85)))
        elif len(palms) < 540 and sl < 1.42 and (y < 170 or rng.random() < 0.5):
            palms.append((x, y, z, rng.uniform(0, 360), rng.uniform(0.85, 1.35)))
        elif len(bushes) < 1500:
            bushes.append((x, y, z, rng.uniform(0, 360), rng.uniform(0.7, 1.35)))
        if len(trees) >= 1950 and len(palms) >= 540 and len(bushes) >= 1500:
            break
    # Close the view behind the town with a forested ridge rather than a bare
    # sample surface. The ridge is outside the playable basin but very visible
    # from the harbor and the aerial camera.
    for _ in range(9000):
        x = rng.uniform(-770, 770)
        y = rng.uniform(505, 670)
        if not plantable(x, y):
            continue
        z = ground(x, y)
        if z < 6.0 or slope(x, y) > 1.6:
            continue
        if len(trees) < 2500:
            trees.append((x, y, z, rng.uniform(0, 360), rng.uniform(1.05, 1.8)))
        elif len(bushes) < 2000:
            bushes.append((x, y, z, rng.uniform(0, 360), rng.uniform(0.7, 1.3)))
        if len(trees) >= 2500 and len(bushes) >= 2000:
            break
    return dict(palms=palms, trees=trees, bushes=bushes)


SEA_STACKS = [(-332, -322, 0.0, 13.0), (368, -300, 0.0, 16.0), (160, -412, 0.0, 10.0),
              (-226, -382, 0.0, 7.0), (452, -238, 0.0, 9.0)]


def area():
    return dict(width=X_MAX - X_MIN, depth=Y_MAX - Y_MIN, land=sum(
        1 for x in range(-800, 801, 20) for y in range(-700, 501, 20) if not is_water(x, y)) * 400.0)
