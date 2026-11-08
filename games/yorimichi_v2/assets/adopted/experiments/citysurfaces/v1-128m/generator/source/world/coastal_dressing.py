"""Rock groups and backshore groves, using the island's existing asset library."""
import numpy as np

import shorelines as coast
import coastal_surface
from skatepark.pier_site import ORIGIN, HALF_X, HALF_Y
from belmonte.terrain import OUTER as TOWN_JOIN_BOUNDS


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
    # The new local reach approaches the town collar and previously inland rail.
    # The Belmonte producer already plants the actual collar triangles. Leave
    # that region to its owner instead of sampling it as unconstrained country.
    tx0, ty0, tx1, ty1 = TOWN_JOIN_BOUNDS
    safe &= (x+radius < tx0) | (x-radius > tx1) | (y+radius < ty0) | (y-radius > ty1)
    safe &= coast.rail_cover_distance(x, y, maximum=100.+float(np.max(radius, initial=0.))) > radius+80.
    # A circumscribed square also keeps every edge inside an authored scenery region.
    for dx in [-1., 0., 1.]:
        for dy in [-1., 0., 1.]:
            px, py = x+dx*radius, y+dy*radius
            perimeter = coast._profile_perimeter_weight(px, py)
            old = (perimeter > .02) & (coast._profile_weight(px, py) >= perimeter*(1.-1e-6))
            safe &= old | (coast.landform_envelope(px, py) > .02)
    return safe


def landform_groves(x, y):
    """Groves follow the named ridges and rail foothill, leaving explicit valley mouths open."""
    country, headland = coast.landform_regions(x, y)
    clump = .5+.3*np.sin(x/71.+y/93.)+.2*np.sin(y/49.-x/63.)
    ridge = np.zeros_like(x)
    for c in coast.COUNTRY_RIDGES:
        axis = c['y']+c['lean']*(x-2400.)
        ridge = np.maximum(ridge, np.exp(-((y-axis)/210.)**4))
    distance = coast.rail_cover_distance(x, y, maximum=460.)
    rail_foot = coast.smooth((distance-80.)/80.)*(1.-coast.smooth((distance-260.)/200.))
    return np.maximum(country*np.maximum(ridge, rail_foot), headland)*np.clip((clump-.25)/.65, 0., 1.)


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
    local_grove = landform_groves(x, y)
    keep |= (d > front) & (d < coast.reach(x, y)-45.) & (local_grove > .25)
    chance = np.maximum(.35+.5*np.clip(grove, 0., 1.), .35+.5*local_grove)
    keep &= rng.random(len(x)) < chance
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
    shape_crowns(result)
    # Finish the established random stream before discarding these faulty
    # mainland props, so removing them cannot reshuffle the coastal woodland.
    return {name:rows for name,rows in result.items() if not name.startswith('SW_Boulder_')}


def shape_crowns(objects):
    """@cc [owner:fontanierh,label:correctness] coastal-crown-producer-isolation
    Only this producer's headland crown trees may be reduced. Preserve all
    outside transforms and all random draws, and never filter another owner's trees.
    """
    for name,rows in objects.items():
        if not rows or not name.startswith('Tree_'):continue
        p=np.asarray(rows,float)
        on=coastal_surface.crown_zone(p[:,0],p[:,1],p[:,2])
        # Finish the original RNG stream first. This spatial postfilter cannot
        # reshuffle later trees, shrubs, or objects outside the crown masses.
        gaps=.5+.5*np.sin(p[:,0]/41.+p[:,1]/29.)
        keep=~on | (gaps > .3)
        objects[name]=[[*row[:4],round(row[4]*.55,3)] if selected else row
                       for row,selected,k in zip(rows,on,keep) if k]


def integrate(world, heightmap):
    from hidamari import layout
    from belmonte import terrain
    from train import earthworks
    from train.corridor import clear_instances
    # The world generator has just written this final grid. Keep the public
    # sampler on that same grid while locating the new coastal features.
    layout.H = heightmap
    # The city's street profile starts where this world's road ends. world.json is written only after this
    # step, so a fresh build has none to read yet, and an incremental one would read the previous road.
    layout.street_height.start = max(world['road'], key=lambda q: q[0])[:2]
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


def repair_west_forest(world, heightmap, owned_rows):
    """@cc [owner:fontanierh,label:correctness] repaired-west-rim-forest-support
    Re-seat only surviving original far-forest rows whose triangle support
    changes in the west repair, including adjacent parent-cell interiors.
    Preserve XY/yaw/scale, unchanged-support rows and every RNG draw. Compare
    the original coast/southern stitch without new knots to the repaired mesh;
    no private baseline is a build dependency. Changed support MUST remain
    outside railway carving. Do not move another producer.
    """
    from hidamari import layout
    from farhills_grid import mesh_grid, source_grid
    from train import earthworks
    owned={(name,*row[:2]) for name,rows in owned_rows.items() for row in rows}
    selected=[row for name,rows in world['instances'].items() for row in rows
              if (name,*row[:2]) in owned]
    if not selected:return
    p=np.asarray(selected,float)
    # Match the float32 heightmap consumed by the later geometry producer.
    layout.H=np.asarray(heightmap,dtype=np.float32)
    xs,ys,z=mesh_grid(len(heightmap))
    parents=source_grid()
    def previous(x,y,base):return layout.coastal_backdrop_height(x,y,base,repair_west=False)
    def shape(x,y,base):
        x,y,base=np.broadcast_arrays(np.asarray(x,float),np.asarray(y,float),np.asarray(base,float))
        ground=layout.coastal_backdrop_height(x,y,base)
        changed=ground!=previous(x,y,base)
        if np.any(changed) and not np.array_equal(ground[changed],earthworks.carve(x[changed],y[changed],ground[changed])):
            raise ValueError('West-rim forest repair overlaps railway earthworks')
        return ground
    before=coast.sample_grid_mesh(xs,ys,z,p[:,0],p[:,1],shape=previous,parents=parents)
    ground=coast.sample_grid_mesh(xs,ys,z,p[:,0],p[:,1],shape=shape,
        parents=parents,edge_knots={(0,-300.):np.linspace(-300.,300.,len(heightmap))})
    changed=before!=ground
    if np.any(changed) and not np.array_equal(ground[changed],earthworks.carve(p[changed,0],p[changed,1],ground[changed])):
        raise ValueError('West-rim forest repair overlaps railway earthworks')
    for i in np.flatnonzero(changed):selected[i][2]=round(float(ground[i]-.3),2)
    world['west_rim_forest_support']={'producer':'far_forest','count':int(changed.sum()),'embedding_m':.3}
