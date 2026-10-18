"""The island's coastal profile, shared by terrain, planting and the map.

Metres in the Blender frame. Inland terrain remains owned by its existing region;
only the coastal transition is reshaped. Beaches and cliffs are actual ground,
not almost-coplanar ribbons over the sea or the original terrain.
"""
import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np
from coast_water import HARBOR_RECT

REACH = 260.
COUNTRY_REACH = 1050.
FLOOR = -32.
STEP = 6.
RAIL_LINE = Path(__file__).resolve().parents[1]/'assets/vehicles/belmonte-train/line.json'
SAND = np.array([.38, .305, .185])
WET_SAND = np.array([.145, .119, .080])
ROCK = np.array([.185, .180, .155])
LIGHT_ROCK = np.array([.43, .40, .33])
MEADOW = np.array([.26, .25, .105])


def smooth(t):
    t = np.clip(t, 0., 1.)
    return t*t*(3.-2.*t)


def _smin(a, b, radius=150.):
    h = np.clip(.5+.5*(b-a)/radius, 0., 1.)
    return b+(a-b)*h-radius*h*(1.-h)


def _base_field(x, y):
    """@cc [owner:fontanierh,label:correctness] harbor-west-beach-transition
    The southern outline between x=300 and x=420 MUST turn inland monotonically
    toward the quay. A seaward cusp there MUST NOT extrude a straight submerged
    ridge across the harbor approach. The quay outline from x=420 through x=900
    MUST retain its existing datum.

    Signed inland distance and rock share; the rounded outline stays inside the old envelope.
    """
    x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
    east = 2970.+90.*np.sin(y/690.)+38.*np.sin(y/177.+.7)
    # Belmonte's reference has two deep sand bays between compact rock points.
    # Broad inlets change the silhouette; small noise alone only frays a straight bank.
    country = smooth((y-3500.)/350.)
    east -= country*(235.*np.exp(-((y-4680.)/290.)**2)
                     +205.*np.exp(-((y-5810.)/280.)**2))
    pockets = [(560., 75., 130.), (1050., 110., 170.), (3000., 110., 145.)]
    pocket = np.zeros_like(y)
    for centre, width, depth in pockets:
        inlet = np.exp(-((y-centre)/width)**4)
        east -= depth*inlet
        pocket = np.maximum(pocket, inlet)
    east += 19.*np.sin(y/61.)+9.*np.sin(y/29.+.5)
    west = -2970.+85.*np.sin(y/740.+1.2)+42.*np.sin(y/193.)
    north = 6835.-100.*(x/3000.)**2+65.*np.sin(x/530.)
    # The existing quay owns the central frontage: its water stays open under
    # the piers. Sand bays sit outside its ends, below the protected city streets.
    # The spawn inlet also clears Sunset Pier's fixed 1.8 m deck and access path.
    # Retract the former x=380, y=-190 beach tip into a direct quay transition.
    # Its extruded underwater cusp occluded the deeper basin, making real
    # scene-depth-driven shallows jump across a straight diagonal in the water.
    south = np.interp(x, [-3200., -1800., -600., -300., -150., 300., 420.,
                         900., 1000., 1420., 1800., 2800., 3200.],
                        [-25., -45., -60., -175., -185., -185., -124.,
                         -124., -195., -185., -60., -45., -25.])
    wild = smooth((np.abs(x)-600.)/500.)
    south += wild*(14.*np.sin(x/175.)+7.*np.sin(x/62.))
    de, dw, dn, ds = east-x, x-west, north-y, y-south
    side = _smin(_smin(de, dw), dn)
    d = _smin(side, ds)
    phase = np.where(de < dw, .4, 2.1)
    bays = (.5+.5*np.sin(y/420.+phase))**4
    flank = .88+.12*np.sin(y/280.+phase)
    country_rock = smooth((bays-.30)/.50)
    east_bays = np.maximum(np.exp(-((y-4680.)/380.)**4),
                           np.exp(-((y-5810.)/370.)**4))
    country_rock = np.where(de < dw, 1.-smooth((east_bays-.25)/.55), country_rock)
    side_rock = flank*(1.-smooth((y-3400.)/500.))+country_rock*smooth((y-3400.)/500.)
    # Real sand inlets interrupt the eastern shelf, instead of painting a
    # different colour onto a continuous cliff wall.
    side_rock *= np.where(de < dw, 1.-pocket, 1.)
    cap = .85*smooth((np.abs(x)-1450.)/1100.)
    side_rock = side_rock*(1.-smooth((np.minimum(de, dw)-dn)/180.))+cap*smooth((np.minimum(de, dw)-dn)/180.)
    shoulders = .8*np.exp(-((x+340.)/70.)**2)+.75*np.exp(-((x-260.)/65.)**2)
    south_rock = np.clip(shoulders+wild*(.5+.45*np.sin(x/250.)**2), 0., 1.)
    side_share = smooth((ds-side+80.)/160.)
    return d, side_rock*side_share+south_rock*(1.-side_share)


@lru_cache(maxsize=1)
def _rail_headlands():
    """Natural cover around coastal parts of the committed line, including its spiral tunnel."""
    rows = json.loads(RAIL_LINE.read_text())['samples']
    p = np.array([[r['x'], r['y']] for r in rows])
    d, _ = _base_field(p[:, 0], p[:, 1])
    near = d < reach(p[:, 0], p[:, 1])+60.
    edges = np.flatnonzero(np.diff(np.r_[False, near, False]))
    return tuple((float(q[:, 0].min()-30.), float(q[:, 1].min()-30.),
                  float(q[:, 0].max()+30.), float(q[:, 1].max()+30.))
                 for a, b in zip(edges[::2], edges[1::2]) for q in [p[a:b]])


def _headland_distance(x, y, box):
    x0, y0, x1, y1 = box
    return np.hypot(np.maximum(np.maximum(x0-x, x-x1), 0.),
                    np.maximum(np.maximum(y0-y, y-y1), 0.))


def field(x, y):
    """Signed inland distance and rock share, with connected headlands over coastal railway cover."""
    x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
    d, rock = _base_field(x, y)
    for box in _rail_headlands():
        cape = 100.-_headland_distance(x, y, box)
        rock = np.where(cape > d, np.maximum(rock, .95), rock)
        d = np.maximum(d, cape)
    return d, rock


def reach(x, y):
    """Country-only rolling backshore; the arrival coast keeps its established band."""
    x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
    country = smooth((y-3500.)/700.)*(1.-smooth((y-6200.)/500.))
    return REACH+(COUNTRY_REACH-REACH)*country


def perimeter_weight(x, y):
    d, _ = field(x, y)
    band = reach(x, y)
    inland = smooth((d-100.)/(band-100.))
    country = (band-REACH)/(COUNTRY_REACH-REACH)
    # Keep the foreground on the authored low shelf. The old 225 m plateau
    # must not dominate halfway through that shelf merely because it is high.
    return 1.-inland*(1.-country+country*inland)


def weight(x, y):
    x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
    w = perimeter_weight(x, y)
    # Preserve the occupied mainland above the coastal strip. The quay's drop
    # is hidden inside its existing retaining wall, not stretched under boats.
    south = smooth((-125.-y)/28.)
    quay = (x >= 420.) & (x <= 900.)
    south = np.where(quay & (y <= -125.), 1., south)
    occupied = smooth((x+550.)/150.)*smooth((1650.-x)/230.)
    occupied *= 1.-smooth((y-400.)/100.)
    w *= 1.-occupied*(1.-south)
    for box in _rail_headlands():
        w *= smooth(_headland_distance(x, y, box)/80.)
    return w


def height(x, y, base):
    """@cc [owner:fontanierh,label:correctness] coast-ground-ownership
    Ground beyond reach(x, y) inside the coast MUST remain unchanged.
    Country bays MUST retain broad dry sand followed by a rolling backshore,
    without compressing the high country into the southern 260 metre band.
    Country foreground relief MUST vary in two dimensions and taper out before
    protected or unchanged ground, rather than becoming one smooth ramp.
    Exterior ground MUST pass through sea level into a submerged toe; it MUST
    NOT retain broad zero-height quads. The occupied southern road/quay ground
    above y=-125 MUST remain unchanged. The committed railway and its natural
    tunnel cover MUST remain unchanged within 20 metres of the centre line.
    """
    x, y, base = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float), np.asarray(base, float))
    d, rock = field(x, y)
    inland = np.maximum(d, 0.)
    country = smooth((y-3400.)/500.)
    # Country bays have sixty metres of usable sand. The southern arrival
    # coves keep their thirty-metre raised shore bench, which also supports
    # Sunset Pier's existing grade-limited approach to its fixed deck.
    beach = (.075*inland+.0005*inland**2)*(1.-country)
    # Keep the dry strip, then ease into meadow rather than extending the
    # quadratic sand ramp. A broad transition meets the old high country.
    bench = .025*inland+.0003*inland**2
    meadow = 3.6+.070*np.maximum(inland-75., 0.)
    rolling = (8.*np.sin(x/145.+y/213.)+4.*np.sin(y/97.-x/191.))
    meadow = np.maximum(3.6, meadow+rolling*smooth((inland-90.)/160.))
    bench = bench*(1.-smooth((inland-75.)/55.))+meadow*smooth((inland-75.)/55.)
    beach += bench*country
    dunes = (.65+.35*np.sin(x/23.+y/31.))*smooth((inland-55.)/30.)*country
    beach += dunes
    crown = np.minimum(68.+12.*np.sin(y/320.+x/430.), np.maximum(8., base+10.))
    crown = crown*(1.-country)+(28.+10.*np.sin(y/190.+x/300.))*country
    crown *= .78+.16*np.sin(y/77.+x/211.)+.06*np.sin(y/29.)
    # Two risers separated by a physical rock shelf; their widths vary along
    # the coast so the face reads as joined rock masses from a distant lookout.
    rib = 7.*np.sin(y/47.+x/91.)+3.*np.sin(y/19.-x/53.)
    # Broad gullies divide connected masses; their shoulders have different
    # shelf widths instead of repeating the same vertical wall everywhere.
    gully = np.exp(-(np.sin(y/83.+x/401.)/.22)**2)
    crown *= 1.-.36*gully
    ledge = inland+rib*smooth(inland/18.)
    shelf = 1.+.28*np.sin(y/59.+x/173.)
    cliff = 1.2*smooth(inland/8.)
    cliff += (crown-1.2)*(.48*smooth((ledge-5.)/(16.*shelf))+.16*smooth((ledge-29.*shelf)/12.)
                         +.36*smooth((ledge-49.*shelf)/20.))
    cliff += .05*np.maximum(inland-46., 0.)
    target = beach*(1.-rock)+cliff*rock
    target = np.where(d < 0., np.maximum(FLOOR, d*(.18+.42*rock)), target)
    w = weight(x, y)
    ground = base*(1.-w)+target*w
    perimeter = perimeter_weight(x, y)
    protection = np.divide(w, perimeter, out=np.zeros_like(w), where=perimeter > 1e-8)
    band = reach(x, y)
    country_band = (band-REACH)/(COUNTRY_REACH-REACH)
    relief = (11.*np.sin(x/140.+y/93.)+7.*np.sin(y/71.-x/113.)
              +3.*np.sin(x/57.+y/149.))
    relief *= smooth((d-100.)/150.)*smooth((band-d)/180.)
    relief *= country_band*protection*np.minimum(1., np.maximum(ground-4., 0.)/28.)
    return ground+relief


def vegetation(x, y):
    """Dry backshore for trees and undergrowth; never a canopy across a sand bay."""
    d, rock = field(x, y)
    return (weight(x,y)==0.) | (d > 72.-40.*rock)


def clear_vegetation(instances):
    """Keep town planting and the separate islet, clearing mainland sand and water."""
    removed=0
    for name,rows in instances.items():
        if not rows or not (name.startswith(('Tree','Bush','Grass')) or name=='Litter'):
            continue
        p=np.asarray(rows,float)
        keep=(p[:,1]<-300.) | vegetation(p[:,0],p[:,1])
        removed+=int(np.count_nonzero(~keep))
        instances[name]=[r for r,k in zip(rows,keep) if k]
    return removed


def paint(x, y, z, normal_z):
    x, y, z, normal_z = np.broadcast_arrays(x, y, z, normal_z)
    _, rock = field(x, y)
    wet = 1.-smooth((z-.05)/1.8)
    sand = SAND*(1.-wet[..., None])+WET_SAND*wet[..., None]
    facet = .86+.16*np.sin(x/12.+y/19.)+.08*np.sin(z/6.+y/37.)
    # Pale continental rock at the city headland and country bays, retaining
    # the dark volcanic flanks between them.
    pale = np.clip(smooth((1200.-y)/300.)+smooth((y-3400.)/400.), 0., 1.)
    geology = ROCK*(1.-pale[..., None])+LIGHT_ROCK*pale[..., None]
    stone = geology*facet[..., None]*(.70+.30*normal_z[..., None])
    stone *= (1.-.35*wet[..., None])
    exposure = np.maximum(rock*(1.-smooth((z-45.)/35.)), smooth((.85-normal_z)/.22))
    shore = sand*(1.-exposure[..., None])+stone*exposure[..., None]
    # Beach sand fades into meadow on the backshore; cliff faces stay rock.
    coverage = np.maximum(1.-smooth((z-3.)/5.), exposure)
    w = weight(x, y)*coverage
    return shore, w


def colours(x, y, z, normal_z, base):
    shore, w = paint(x,y,z,normal_z)
    d, _ = field(x, y)
    country = smooth((np.asarray(y)-3500.)/500.)
    patches = .62+.20*np.sin(np.asarray(x)/91.+np.asarray(y)/167.)
    meadow = weight(x,y)*country*smooth((d-65.)/100.)*smooth((np.asarray(normal_z)-.82)/.14)
    base = np.asarray(base)*(1.-(meadow*patches)[..., None])+MEADOW*(meadow*patches)[..., None]
    return base*(1.-w[..., None])+shore*w[..., None]


def sea_mesh(radius=24000.):
    """@cc [owner:fontanierh,label:correctness] ocean-surface-ownership
    Open-ocean faces MUST exclude HARBOR_RECT and share its z=0 datum.
    The four rectangles and harbor MUST partition the sea without overlap.
    """
    x0,y0,x1,y1=HARBOR_RECT
    rectangles=[(-radius,-radius,x0,radius),(x1,-radius,radius,radius),
                (x0,-radius,x1,y0),(x0,y1,x1,radius)]
    vertices,faces=[],[]
    for ax,ay,bx,by in rectangles:
        i=len(vertices)
        vertices.extend([(ax,ay,0.),(bx,ay,0.),(bx,by,0.),(ax,by,0.)])
        faces.append((i,i+1,i+2,i+3))
    return vertices,faces


def grid_mesh(xs, ys, z, *, hidden=None, step=STEP, shape=height):
    """Refine only coastal cells of an existing grid, retaining every original grid edge.

    The source cell uses the exported a-c triangle diagonal for each refinement. Shared cell
    edges use identical knots and heights; at the inland transition the shape
    weight is zero, so hanging edge vertices remain on the coarse neighbour.
    Returns vertices and upward quads in world metres, without Blender.
    """
    xs, ys, z = np.asarray(xs), np.asarray(ys), np.asarray(z)
    vertices, faces = [], []
    for j, (ay, by) in enumerate(zip(ys[:-1], ys[1:])):
        for i, (ax, bx) in enumerate(zip(xs[:-1], xs[1:])):
            if hidden is not None and hidden((ax+bx)/2., (ay+by)/2.):
                continue
            corners_x = np.array([ax, bx, bx, ax]); corners_y = np.array([ay, ay, by, by])
            d, _ = field(corners_x, corners_y)
            refine = np.any(d < reach(corners_x, corners_y)+100.) and d.max() > -220.
            nx = max(1, math.ceil((bx-ax)/step)) if refine else 1
            ny = max(1, math.ceil((by-ay)/step)) if refine else 1
            u, v = np.meshgrid(np.linspace(0., 1., nx+1), np.linspace(0., 1., ny+1))
            x, y = ax+(bx-ax)*u, ay+(by-ay)*v
            a,b,c,d = z[j,i],z[j,i+1],z[j+1,i+1],z[j+1,i]
            base = np.where(u>=v,a+u*(b-a)+v*(c-b),a+u*(c-d)+v*(d-a))
            h = shape(x, y, base)
            first = len(vertices)
            vertices.extend(np.stack((x, y, h), -1).reshape(-1, 3).tolist())
            faces.extend((first+k*(nx+1)+l, first+k*(nx+1)+l+1,
                          first+(k+1)*(nx+1)+l+1, first+(k+1)*(nx+1)+l)
                         for k in range(ny) for l in range(nx))
    return vertices, faces
