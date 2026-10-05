"""The planting of the back-lane houses' front plots (kit/house.py), placed as foliage instances by layout.generate():
clipped shrubs (garden_shrubs.py) behind the boundary and spilling over it, a clipped hedge on variant 1's planter, a
garden maple, an azalea and a ball by the porch, a potted-plant stand at the door and, on variant 2's parking pad, a
kei truck or a scooter, after the concepts in assets/hidamari/houses/*/concept.jpg.
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
    if variant == 1:                 # a clipped hedge on the planter behind the low wall
        x = -4.35
        while x < 4.6:
            if not PATH[0]-.6 < x < PATH[1]+.6:
                out.append(('Bush_HD_Hedge', x, BOUNDARY+.45, r.choice((0, 180)), .8*r.uniform(.95, 1.05)))
            x += 1.2
    else:                            # shrubs behind the wall, crowns showing over it
        for x in (-4.4, -3.1, .1, 1.4, 2.7, 4.1):
            if clear_x(x) and r.random() < .85:shrub(x, BOUNDARY+.55, 1.)
    # by the porch and the house front
    for x, y in ((-.15, FRONT-.55), (-2.75, FRONT-.6), (3.9, FRONT-.55)):
        if clear_x(x) and not (variant in (0, 2) and x < -2.5):shrub(x, y, .8, ['Bush_HD_Azalea', 'Bush_HD_Ball'], (.6, .4))
    # a garden maple in a front corner, about 4 m tall: smaller ones switch to the coarse foliage LODs within a few
    # houses' distance
    mx, my = {0: (3.7, -3.6), 1: (3.2, -3.4), 2: (-4.25, -3.8), 3: (3.75, -3.6)}[variant]
    out.append(('Tree_Maple_A', mx, my, r.uniform(0, 360), r.uniform(.56, .64)))
    # a stand of pots beside the door
    out.append(('HD_P_potted_plants', .55, FRONT-.55, 0, r.uniform(.9, 1.)))
    # variant 2's gravel pad (x 1.3 to 4.7): mostly a kei truck parked along it, otherwise a scooter
    if variant == 2:
        out.append(('HD_P_kei_truck', 3.0, -2.9, 90, .96) if r.random() < .65 else ('HD_P_scooter', 2.2, -2.6, 70, 1.))
    return out


def place(put, sites):
    """Plant every house site: sites as layout.house_sites() (name, x, y, yaw)."""
    for k, (name, x, y, yaw) in enumerate(sites):
        a = math.radians(yaw); c, s = math.cos(a), math.sin(a)
        for item, lx, ly, iyaw, scale in plants(int(name[-2:]), 7300+k):
            px, py = x+lx*c-ly*s, y+lx*s+ly*c
            put(item, px, py, yaw=(yaw+iyaw) % 360, scale=scale)
