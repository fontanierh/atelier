"""The Hidamari Hippodrome's plan (docs/HIPPODROME.md): the racecourse on the slope north of the city.

Blender metres (x east, y north, z up). The oval lies east-west with its centre at ORIGIN; its turns are half circles
round (ORIGIN.x -+ HALF, ORIGIN.y). The track's centre line is RADIUS from the turn centres and the track is WIDTH wide.
The course is flat: one platform at PLATFORM_Z, just above the highest ground under it, with a skirt down to the
terraced slope. The race runs counter-clockwise seen from above: east along the home straight in front of the
grandstand (south), west along the back straight (north). Distances along the centre line, `s`, start at the finish
post and grow in the running direction.

Standard library and numpy only: build.py (no Blender) and the tests import it.
"""
import math

ORIGIN = (600., 525.)
HALF = 60.             # half the straights' length
RADIUS = 50.           # centre-line radius of the turns
WIDTH = 14.            # track width: the inner rail is RADIUS - WIDTH/2 from a turn centre, the outer RADIUS + WIDTH/2
LAP = 4 * HALF + 2 * math.pi * RADIUS
FINISH_X = ORIGIN[0]   # the finish post's line across the home straight
MARGIN = 7.            # flat ground outside the outer rail

# The platform rectangle (x0, y0, x1, y1): the oval and its margin, the grandstand apron to the south and the
# open grounds to the east.
PLATFORM = (ORIGIN[0] - HALF - RADIUS - WIDTH / 2 - MARGIN, ORIGIN[1] - 82.,
            ORIGIN[0] + HALF + RADIUS + WIDTH / 2 + 30., ORIGIN[1] + RADIUS + WIDTH / 2 + MARGIN)
PLATFORM_CLEARANCE = .18   # above the highest ground sample under the platform
SKIRT = 3.                 # the skirt's run outwards while it falls to the ground

# The lane from the city street (Hidamari's ROAD_X[1] = 560, which ends at y = 343) up to the platform.
LANE = ((560., 343.), (560., PLATFORM[1]))
LANE_WIDTH = 6.
LANE_START_Z = 36.0        # the street's height at its north end

# Structures: Tripo models (assets/hippodrome/props/<slug>/<slug>.glb). size = (along the model's front axis, across
# it, height) in metres; the model's front (its glTF +X) turns to face `yaw` (degrees, counter-clockwise from east).
STRUCTURES = {
    'grandstand':    dict(size=(16., 56., 15.), at=(ORIGIN[0], ORIGIN[1] - 72.), yaw=90.),
    'judges_tower':  dict(size=(5., 6.2, 8.), at=(ORIGIN[0] - 22., ORIGIN[1] - 25.), yaw=-90.),
    'finish_post':   dict(size=(1.2, 1.2, 5.5), at=(FINISH_X, ORIGIN[1] - RADIUS + WIDTH / 2 + 1.2), yaw=-90.),
    'tote_board':    dict(size=(3.7, 10., 8.1), at=(ORIGIN[0] + 25., ORIGIN[1] + 18.), yaw=-90.),
}

# Where people stand: the player's arrival spot by the grandstand.
RETURN = dict(at=(ORIGIN[0] - 36.5, ORIGIN[1] - 66.5), yaw=120.)   # facing the grandstand
# Gaps in the rails (centre x on the home straight, width) so people can walk into the infield.
RAIL_GAPS = [(ORIGIN[0] - 45., 5.)]
RAIL_HEIGHT = 1.15
RAIL_POST_STEP = 2.5


def centre(s, offset=0.):
    """The point `offset` metres outwards from the centre line at distance `s` (running direction), and the running
    heading (radians, counter-clockwise from east). The inside of the course is to the runner's left."""
    s %= LAP
    ox, oy = ORIGIN
    r = RADIUS + offset
    legs = (HALF, math.pi * RADIUS, 2 * HALF, math.pi * RADIUS, HALF)
    if s < legs[0]:                                    # home straight, east, from the finish
        return (FINISH_X + s, oy - r, 0.)
    s -= legs[0]
    if s < legs[1]:                                    # east turn, counter-clockwise
        a = -math.pi / 2 + s / RADIUS
        return (ox + HALF + r * math.cos(a), oy + r * math.sin(a), a + math.pi / 2)
    s -= legs[1]
    if s < legs[2]:                                    # back straight, west
        return (ox + HALF - s, oy + r, math.pi)
    s -= legs[2]
    if s < legs[3]:                                    # west turn
        a = math.pi / 2 + s / RADIUS
        return (ox - HALF + r * math.cos(a), oy + r * math.sin(a), a + math.pi / 2)
    s -= legs[3]
    return (ox - HALF + s, oy - r, 0.)                 # home straight again, up to the finish


def curvature_scale(s, offset):
    """How much further a runner `offset` metres outwards travels per metre of centre line at `s`: 1 on the straights,
    (R + offset) / R in the turns."""
    s %= LAP
    straight = s < HALF or HALF + math.pi * RADIUS <= s < 3 * HALF + math.pi * RADIUS or s >= LAP - HALF
    return 1. if straight else (RADIUS + offset) / RADIUS


def platform_height(height):
    """The platform's height over the ground function `height(xs, ys)` (numpy arrays): its highest sample plus the
    clearance, so no terrace pokes through."""
    import numpy as np
    x0, y0, x1, y1 = PLATFORM
    xs, ys = np.meshgrid(np.arange(x0 - 1, x1 + 1.01, 1.), np.arange(y0 - 1, y1 + 1.01, 1.))
    return round(float(height(xs, ys).max()) + PLATFORM_CLEARANCE, 2)


def clearance():
    """Polygons (Blender metres) where the island's trees, bushes, grass and rocks are removed: the platform with its
    skirt and a border, and the lane's corridor."""
    x0, y0, x1, y1 = PLATFORM
    pad = SKIRT + 4.
    lane = LANE_WIDTH / 2 + 4.
    (lx, ly0), (_, ly1) = LANE
    return [
        [[x0 - pad, y0 - pad], [x1 + pad, y0 - pad], [x1 + pad, y1 + pad], [x0 - pad, y1 + pad]],
        [[lx - lane, ly0 - 2.], [lx + lane, ly0 - 2.], [lx + lane, ly1 + 1.], [lx - lane, ly1 + 1.]],
    ]
