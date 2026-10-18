"""Rock groups and backshore groves, using the island's existing asset library."""
import numpy as np

import shorelines as coast
from skatepark.pier_site import ORIGIN, HALF_X, HALF_Y


def clear_footprint(x, y, radius):
    """@cc [owner:fontanierh,label:correctness] coastal-feature-clearance
    Coastal dressing MUST stay outside the protected occupied ground, railway
    cover, working harbor and Sunset Pier, including each feature's footprint.
    It MUST leave the separate temple islet and its crossing unchanged.
    """
    x, y, radius = np.broadcast_arrays(x, y, radius)
    safe = y-radius > -300.
    x0, y0, x1, y1 = coast.HARBOR_RECT
    safe &= (x+radius < x0) | (x-radius > x1) | (y+radius < y0) | (y-radius > y1)
    safe &= (abs(x-ORIGIN[0]) > HALF_X+radius+6.) | (abs(y-ORIGIN[1]) > HALF_Y+radius+6.)
    safe &= (x+radius < -550.) | (x-radius > 1650.) | (y+radius < -125.) | (y-radius > 500.)
    for box in coast._rail_headlands():
        safe &= coast._headland_distance(x, y, box) > radius+80.
    # A circumscribed square protects the whole footprint, including narrow
    # curved corners of the occupied-ground and railway exclusion fields.
    for dx in [-1., 0., 1.]:
        for dy in [-1., 0., 1.]:
            px, py = x+dx*radius, y+dy*radius
            perimeter = coast.perimeter_weight(px, py)
            safe &= (perimeter > .02) & (coast.weight(px, py) >= perimeter*(1.-1e-6))
    return safe


def placements(ground):
    """Deterministic coastal objects; ground is the final world-space sampler.

    Keep separate random streams from the established inland forest so a new
    cove cannot move an unrelated tree, house, path or gameplay placement.
    """
    rng = np.random.default_rng(83047)
    result = {}

    def put(name, x, y, z, scale):
        result.setdefault(str(name), []).append([round(float(x), 2), round(float(y), 2),
                                           round(float(z), 2), round(float(rng.uniform(0., 360.)), 1),
                                           round(float(scale), 3)])

    x, y = np.meshgrid(np.arange(-3130., 3131., 18.), np.arange(-230., 7001., 18.))
    x, y = x.ravel(), y.ravel()
    x += rng.uniform(-5., 5., len(x)); y += rng.uniform(-5., 5., len(y))
    d, rock = coast.field(x, y)
    scale = rng.uniform(4., 14., len(x))
    # Groups at rocky shoulders and on the first shelf. Sparse outlying slabs
    # run into the shallows; the broad sand bay centres remain open.
    groups = .5+.5*np.sin(y/73.+x/91.)
    keep = (d > -16.) & (d < 57.) & (rock > .43) & (rng.random(len(x)) < .22+.35*groups)
    keep &= clear_footprint(x, y, scale*1.8)
    x, y, scale = x[keep], y[keep], scale[keep]
    z = ground(x, y)
    names = ['SW_Boulder_A', 'SW_Boulder_B', 'SW_Boulder_C']
    for i, (xx, yy, zz, size) in enumerate(zip(x, y, z, scale)):
        if -9. < zz < 65.:
            put(names[i % len(names)], xx, yy, zz+size*.20, size)

    # Full-cell jitter and a two-dimensional clump field leave open meadows
    # between groves. The inland edge follows the rolling country transition,
    # not a constant-distance row parallel to the beach.
    x, y = np.meshgrid(np.arange(-3050., 3051., 17.), np.arange(-210., 6971., 17.))
    x, y = x.ravel(), y.ravel()
    x += rng.uniform(-8.5, 8.5, len(x)); y += rng.uniform(-8.5, 8.5, len(y))
    d, rock = coast.field(x, y)
    grove = (.52*np.sin(y/89.+x/97.)+.31*np.cos(y/63.-x/131.)
             +.17*np.sin(y/157.+x/57.))
    front = 88.-18.*rock+24.*np.sin(y/103.+x/67.)
    back = np.minimum(coast.reach(x, y)-45., 160.+.62*coast.reach(x, y)+75.*grove)
    keep = (d > front) & (d < back) & (grove > .30)
    keep &= rng.random(len(x)) < .35+.5*np.clip(grove, 0., 1.)
    keep &= clear_footprint(x, y, 13.)
    x, y = x[keep], y[keep]
    z = ground(x, y)
    slope = np.hypot((ground(x+2., y)-ground(x-2., y))/4.,
                     (ground(x, y+2.)-ground(x, y-2.))/4.)
    keep = (z > 3.) & (slope < .48)
    x, y, z = x[keep], y[keep], z[keep]
    species = ['Tree_Pine_B', 'Tree_Maple_A', 'Tree_Ginkgo', 'Tree_Cedar_B']
    for xx, yy, zz in zip(x, y, z):
        name = rng.choice(species, p=[.35, .34, .19, .12])
        put(name, xx, yy, zz-.45, rng.uniform(1.55, 2.3))
        if rng.random() < .45:
            put('Bush_Ochre_A', xx, yy, zz-.12, rng.uniform(1.2, 2.))
    return result


def integrate(world, heightmap):
    from hidamari import layout
    from belmonte import terrain
    from train import earthworks
    from train.corridor import clear_instances
    # The world generator has just written this final grid. Keep the public
    # sampler on that same grid while locating the new coastal features.
    layout.H = heightmap
    n = len(heightmap)

    def ground(x, y):
        x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
        # Match the source triangles used by the coastal mesh refinement,
        # rather than bilinearly smoothing the coarse backdrop's diagonal.
        out = layout.coastal_backdrop_height(x, y, terrain.old_height(x, np.minimum(y, 3200.)))
        north = y > 3200.
        out[north] = terrain.country_height(x[north], y[north], carved=False)
        out = earthworks.carve(x, y, out)
        fine = (abs(x) <= 300.) & (abs(y) <= 300.)
        fx = np.clip((x[fine]+300.)/600.*(n-1), 0., n-1.000001)
        fy = np.clip((y[fine]+300.)/600.*(n-1), 0., n-1.000001)
        i, j = fx.astype(int), fy.astype(int); u, v = fx-i, fy-j
        a, b = heightmap[j, i], heightmap[j, i+1]
        c, d = heightmap[j+1, i+1], heightmap[j+1, i]
        out[fine] = np.where(u >= v, a+u*(b-a)+v*(c-b), a+u*(c-d)+v*(d-a))
        city = (x > 300.) & (x <= 1420.) & (y >= -300.) & (y <= 500.)
        out[city] = layout.height(x[city], y[city])
        return out

    objects = placements(ground)
    clear_instances(objects)
    for name, rows in objects.items():
        world['instances'].setdefault(name, []).extend(rows)
    counts = {name: len(rows) for name, rows in objects.items()}
    world['coastal_dressing'] = counts
    print('COASTAL FEATURES', counts, flush=True)
