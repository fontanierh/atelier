"""The planting of the back-lane houses' front plots (kit/house.py), placed as foliage instances by layout.generate():
clipped shrubs (garden_shrubs.py) behind the boundary and spilling over it, a clipped hedge on variant 1's planter, a
garden maple and on some a cloud-pruned pine, an azalea and a ball by the porch, a potted-plant stand at the door, on
variants 1 and 3 a bicycle against the front and, on variant 2's parking pad, a kei truck, a kei car or a scooter,
after the concepts in assets/hidamari/houses/*/concept.jpg. In the side gaps an air-conditioner unit, propane tanks or
a laundry stand, on some front yards a bonsai shelf; along the lanes a roadside shrine in a garden gap and a curve
mirror where a lane meets the street (the Tripo props, tools/hidamari_props.py).
Positions are in the house's frame (front faces -Y, the plot 10 x 9 m about the origin); kept clear of the stepping
stones to the porch (x -1.4), the porch and its posts, the bicycle and variant 2's parking pad. No Blender here.
"""
import math, random

FRONT, BOUNDARY = -2.15, -4.3       # kit/house.py: the house's front wall and the front boundary line
PATH = (-2.1, -.7)                  # the stepping stones and porch, along x
SHRUBS = ['Bush_HD_Mound', 'Bush_HD_Ball', 'Bush_HD_Azalea', 'Bush_HD_Amber']


def plants(variant, seed):
    """[(name, x, y, yaw, scale)] in the house's frame for one plot."""
    r = random.Random(seed); out = []
    def shrub(x, y, s=1., names=SHRUBS, weights=(.38, .27, .2, .15)):
        out.append((r.choices(names, weights)[0], x+r.uniform(-.15, .15), y+r.uniform(-.1, .1), r.uniform(0, 360),
                    s*r.uniform(.8, 1.05)))
    clear_x = (lambda x: x < 1.0) if variant == 2 else (lambda x: True)     # the parking pad east of x 1.2
    pine = variant in (1, 3) and r.random() < .6          # a cloud-pruned pine in the west front corner
    if variant == 1:                 # a clipped hedge on the planter behind the low wall
        x = -4.35
        while x < 4.6:
            if not PATH[0]-.6 < x < PATH[1]+.6:
                out.append(('Bush_HD_Hedge', x, BOUNDARY+.45, r.choice((0, 180)), .8*r.uniform(.95, 1.05)))
            x += 1.2
    else:                            # shrubs behind the wall, crowns showing well over it
        for x in (-4.4, -3.1, .1, 1.4, 2.7, 4.1):
            if clear_x(x) and not (pine and x < -2.5) and r.random() < .85:shrub(x, BOUNDARY+.6, 1.3)
    if pine:out.append(('Bush_HD_Niwaki', -3.9, -3.1, r.uniform(0, 360), r.uniform(.9, 1.1)))
    # by the porch and the house front
    for x, y in ((-.15, FRONT-.55), (-2.75, FRONT-.6), (3.9, FRONT-.55)):
        if clear_x(x) and not (variant in (0, 2) and x < -2.5):shrub(x, y, .8, ['Bush_HD_Azalea', 'Bush_HD_Ball'], (.6, .4))
    # a garden maple in a front corner, about 4 m tall: smaller ones switch to the coarse foliage LODs within a few
    # houses' distance
    mx, my = {0: (3.7, -3.6), 1: (3.2, -3.4), 2: (-4.25, -3.8), 3: (3.75, -3.6)}[variant]
    out.append(('Tree_Maple_A', mx, my, r.uniform(0, 360), r.uniform(.56, .64)))
    # the side gaps (the house body is 8.2 m wide in its 10 m plot): an air conditioner against the east wall, propane
    # tanks or a laundry stand by the west one
    if r.random() < .7:out.append(('HD_P_ac_unit', 4.42, -1.0+r.uniform(-.3, .6), 90, r.uniform(.95, 1.05)))
    west = r.random()
    if west < .45:out.append(('HD_P_propane_tanks', -4.45, -1.3, -90, 1.))
    elif west < .75:out.append(('HD_P_laundry_stand', -4.5, 1.2, 90, 1.))
    # variant 0's bonsai shelf east of the door, between the pots (kit/house.py's clay pot at x 3.3 and its bicycle west)
    if variant == 0 and r.random() < .5:out.append(('HD_P_bonsai_shelf', 2.3, FRONT-.6, 0, r.uniform(.9, 1.)))
    # a stand of pots beside the door
    out.append(('HD_P_potted_plants', .55, FRONT-.55, 0, r.uniform(.9, 1.)))
    # a town bicycle against the house front east of the door, where kit/house.py has put none (variants 0 and 2 have
    # one west of the path)
    if variant in (1, 3) and r.random() < .4:out.append(('HD_P_bicycle', 2.1, FRONT-.45, 90, 1.))
    # variant 2's gravel pad (x 1.3 to 4.7): mostly a kei truck or a kei car parked along it, otherwise a scooter
    if variant == 2:
        car = r.random()
        out.append(('HD_P_kei_truck', 3.0, -2.9, 90, .96) if car < .4 else ('HD_P_kei_car', 3.0, -2.9, 90, .96) if car < .75
                   else ('HD_P_scooter', 2.2, -2.6, 70, 1.))
    return out


def lanes(sites):
    """{site index: [(name, x, y, yaw, scale)] in that house's frame}: a roadside shrine in about half the garden gaps (a
    skipped plot) and a curve mirror at both ends of each run of the rows facing south, where the inner lane meets a
    street, turned a little towards the crossing."""
    rows = {}
    for k, (_, x, y, yaw) in enumerate(sites):rows.setdefault((y, yaw), []).append((x, k))
    out = {}
    for (y, yaw), row in rows.items():
        row.sort(); runs = [[row[0]]]
        for (x0, k0), (x1, k1) in zip(row, row[1:]):
            gap = x1-x0
            if gap > 29:runs.append([])            # a street between: a new run
            # a plot left as a garden: a shrine in it on one side of the lane or the other (the row facing it has the
            # same gap), never both
            elif gap > 20 and (random.Random(round(x0+x1)).random() < .5) == (yaw == 0):
                out.setdefault(k0, []).append(('HD_P_hokora', gap/2*(1 if yaw == 0 else -1), -3.4, 0, 1.))
            runs[-1].append((x1, k1))
        if yaw != 0:continue
        for run in runs:
            out.setdefault(run[0][1], []).append(('HD_P_curve_mirror', -4.7, -4.7, -35, 1.))
            out.setdefault(run[-1][1], []).append(('HD_P_curve_mirror', 4.7, -4.7, 35, 1.))
    return out


def place(put, sites):
    """Plant every house site: sites as layout.house_sites() (name, x, y, yaw)."""
    extra = lanes(sites)
    for k, (name, x, y, yaw) in enumerate(sites):
        a = math.radians(yaw); c, s = math.cos(a), math.sin(a)
        for item, lx, ly, iyaw, scale in plants(int(name[-2:]), 7300+k)+extra.get(k, []):
            px, py = x+lx*c-ly*s, y+lx*s+ly*c
            put(item, px, py, yaw=(yaw+iyaw) % 360, scale=scale)
