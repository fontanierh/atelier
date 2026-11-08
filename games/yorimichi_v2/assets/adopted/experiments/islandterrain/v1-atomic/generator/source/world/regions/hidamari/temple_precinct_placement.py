"""City placement parameters and data functions, independent from mesh construction."""
import math
import random


WALL_Y = 241.2


APPROACHES = [(690., 266.)]


PAGODA = (641., 304.)


GRAVES = (739., 271., 34., 16.)


BAMBOO = [(616., 318., 7), (588., 312., 6), (662., 322., 6), (722., 318., 7), (758., 322., 5), (816., 312., 4)]


MAPLES = [(652., 288.), (628., 286.), (716., 290.), (762., 292.), (735., 258.), (747., 287.), (660., 262.), (622., 262.)]


PADS = [dict(asset='HD_Pagoda', x=PAGODA[0], y=PAGODA[1], yaw=0, half_width=5., front=-5., back=5., fade_x=3., fade_y=3.,
             group='public'),
        dict(asset='HD_Graves', x=GRAVES[0], y=GRAVES[1], yaw=0, half_width=GRAVES[2]/2, front=-GRAVES[3]/2,
             back=GRAVES[3]/2, fade_x=3., fade_y=3., group='public')]


def place(put, inst, height, buildings):
    """Clear the lamp rows off the hill, then add the lantern-lined approaches, the pagoda, graves, bamboo and maples."""
    inst['HD_Lamp'] = [p for p in inst.get('HD_Lamp', []) if not (630 < p[0] < 810 and abs(p[1]-255) < 1.5)]
    for name in ('HD_Lamp', 'HD_Bench', 'HD_Planter'):
        inst[name] = [p for p in inst.get(name, []) if not (GRAVES[0]-GRAVES[2]/2-2 < p[0] < GRAVES[0]+GRAVES[2]/2+2 and
                                                           GRAVES[1]-GRAVES[3]/2-2 < p[1] < GRAVES[1]+GRAVES[3]/2+2)]
    x, y1 = APPROACHES[0]
    for y in range(int(WALL_Y)+4, int(y1)-1, 6):
        for side in (-1, 1):put('HD_P_stone_lantern', x+side*2.9, y)
    for name, (x, y), w, d in (('HD_Pagoda', PAGODA, 8.2, 8.2), ('HD_Graves', GRAVES[:2], GRAVES[2], GRAVES[3])):
        z = float(height(x, y)); put(name, x, y, z)
        buildings.append({'asset': name, 'position': [x, y, z], 'yaw': 0, 'width': w, 'depth': d, 'terrain_pad': True})
    for k, (bx, by, n) in enumerate(BAMBOO):
        r = random.Random(500+k)
        for i in range(n):
            a = r.uniform(0, math.tau); d = r.uniform(0, 4.5)
            put('HD_Bamboo', bx+math.cos(a)*d, by+math.sin(a)*d*.7, yaw=r.uniform(0, 360), scale=r.uniform(.85, 1.15))
    for k, (mx, my) in enumerate(MAPLES):
        r = random.Random(600+k)
        for i in range(3):
            put('Tree_Maple_A', mx+r.uniform(-3, 3), my+r.uniform(-2.5, 2.5), yaw=r.uniform(0, 360), scale=r.uniform(.9, 1.2))
