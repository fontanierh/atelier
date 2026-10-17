"""The island's coastal profile, shared by terrain, planting and the map.

Metres in the Blender frame. Inland terrain remains owned by its existing region;
only a narrow perimeter band is reshaped. Beaches and cliffs are actual ground,
not almost-coplanar ribbons over the sea or the original terrain.
"""
import math

import numpy as np
from coast_water import HARBOR_RECT

REACH = 260.
FLOOR = -32.
STEP = 6.
SAND = np.array([.38, .305, .185])
WET_SAND = np.array([.145, .119, .080])
ROCK = np.array([.105, .111, .104])


def smooth(t):
    t = np.clip(t, 0., 1.)
    return t*t*(3.-2.*t)


def _smin(a, b, radius=150.):
    h = np.clip(.5+.5*(b-a)/radius, 0., 1.)
    return b+(a-b)*h-radius*h*(1.-h)


def field(x, y):
    """Signed inland distance and rock share; the rounded outline stays inside the old envelope."""
    x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
    east = 2970.+90.*np.sin(y/690.)+38.*np.sin(y/177.+.7)
    west = -2970.+85.*np.sin(y/740.+1.2)+42.*np.sin(y/193.)
    north = 6835.-100.*(x/3000.)**2+65.*np.sin(x/530.)
    # The existing quay owns the central frontage: its water stays open under
    # the piers. Sand bays sit outside its ends, below the protected city streets.
    # The spawn inlet also clears Sunset Pier's fixed 1.8 m deck and access path.
    south = np.interp(x, [-3200., -1800., -600., -300., -150., 300., 380., 420.,
                         900., 1000., 1420., 1800., 2800., 3200.],
                        [-25., -45., -60., -175., -185., -185., -190., -124.,
                         -124., -195., -185., -60., -45., -25.])
    wild = smooth((np.abs(x)-600.)/500.)
    south += wild*(14.*np.sin(x/175.)+7.*np.sin(x/62.))
    de, dw, dn, ds = east-x, x-west, north-y, y-south
    side = _smin(_smin(de, dw), dn)
    d = _smin(side, ds)
    phase = np.where(de < dw, .4, 2.1)
    bays = (.5+.5*np.sin(y/420.+phase))**4
    flank = .88+.12*np.sin(y/280.+phase)
    country = .08+.87*bays
    side_rock = flank*(1.-smooth((y-3400.)/500.))+country*smooth((y-3400.)/500.)
    cap = .85*smooth((np.abs(x)-1450.)/1100.)
    side_rock = side_rock*(1.-smooth((np.minimum(de, dw)-dn)/180.))+cap*smooth((np.minimum(de, dw)-dn)/180.)
    shoulders = .8*np.exp(-((x+340.)/70.)**2)+.75*np.exp(-((x-260.)/65.)**2)
    south_rock = np.clip(shoulders+wild*(.5+.45*np.sin(x/250.)**2), 0., 1.)
    side_share = smooth((ds-side+80.)/160.)
    return d, side_rock*side_share+south_rock*(1.-side_share)


def weight(x, y):
    x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
    d, _ = field(x, y)
    w = 1.-smooth((d-100.)/(REACH-100.))
    # Preserve the occupied mainland above the coastal strip. The quay's drop
    # is hidden inside its existing retaining wall, not stretched under boats.
    south = smooth((-125.-y)/28.)
    quay = (x >= 420.) & (x <= 900.)
    south = np.where(quay & (y <= -125.), 1., south)
    occupied = smooth((x+550.)/150.)*smooth((1650.-x)/230.)
    occupied *= 1.-smooth((y-400.)/100.)
    return w*(1.-occupied*(1.-south))


def height(x, y, base):
    """@cc [owner:fontanierh,label:correctness] coast-ground-ownership
    Ground at least REACH metres inside the coast MUST remain unchanged.
    Exterior ground MUST pass through sea level into a submerged toe; it MUST
    NOT retain broad zero-height quads. The occupied southern road/quay ground
    above y=-125 MUST remain unchanged.
    """
    x, y, base = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float), np.asarray(base, float))
    d, rock = field(x, y)
    inland = np.maximum(d, 0.)
    beach = .075*inland+.0005*inland**2
    crown = np.minimum(68.+12.*np.sin(y/320.+x/430.), np.maximum(8., base+10.))
    cliff = crown*smooth(inland/24.)+.05*np.maximum(inland-24., 0.)
    target = beach*(1.-rock)+cliff*rock
    target = np.where(d < 0., np.maximum(FLOOR, d*(.18+.42*rock)), target)
    w = weight(x, y)
    return base*(1.-w)+target*w


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
    facet = .91+.09*np.sin(x/9.+y/13.)+.04*np.sin(z/3.3+y/37.)
    stone = ROCK*facet[..., None]*(.70+.30*normal_z[..., None])
    stone *= (1.-.35*wet[..., None])
    exposure = np.maximum(rock*(1.-smooth((z-45.)/35.)), smooth((.85-normal_z)/.22))
    shore = sand*(1.-exposure[..., None])+stone*exposure[..., None]
    # Beach sand fades into meadow on the backshore; cliff faces stay rock.
    coverage = np.maximum(1.-smooth((z-3.)/5.), exposure)
    w = weight(x, y)*coverage
    return shore, w


def colours(x, y, z, normal_z, base):
    shore, w = paint(x,y,z,normal_z)
    return np.asarray(base)*(1.-w[..., None])+shore*w[..., None]


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
            refine = d.min() < REACH+100. and d.max() > -220.
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
