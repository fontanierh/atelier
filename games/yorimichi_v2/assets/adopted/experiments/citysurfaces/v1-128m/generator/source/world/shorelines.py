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
    near = d < _profile_reach(p[:, 0], p[:, 1])+60.
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


def _profile_reach(x, y):
    """Country-only rolling backshore; the arrival coast keeps its established band."""
    x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
    country = smooth((y-3500.)/700.)*(1.-smooth((y-6200.)/500.))
    return REACH+(COUNTRY_REACH-REACH)*country


def _profile_perimeter_weight(x, y):
    d, _ = field(x, y)
    band = _profile_reach(x, y)
    inland = smooth((d-100.)/(band-100.))
    country = (band-REACH)/(COUNTRY_REACH-REACH)
    # Keep the foreground on the authored low shelf. The old 225 m plateau
    # must not dominate halfway through that shelf merely because it is high.
    return 1.-inland*(1.-country+country*inland)


def _profile_weight(x, y, *, exposed_west=False):
    x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
    w = _profile_perimeter_weight(x, y)
    # Preserve the occupied mainland above the coastal strip. The quay's drop
    # is hidden inside its existing retaining wall, not stretched under boats.
    south = smooth((-125.-y)/28.)
    quay = (x >= 420.) & (x <= 900.)
    south = np.where(quay & (y <= -125.), 1., south)
    occupied = smooth((x+550.)/150.)*smooth((1650.-x)/230.)
    occupied *= 1.-smooth((y-400.)/100.)
    # Exported backdrop west of the actual fine footprint is not occupied
    # ground. Keep the default scenery mask/RNG eligibility unchanged.
    if exposed_west:occupied=np.where(x < -300.,0.,occupied)
    w *= 1.-occupied*(1.-south)
    for box in _rail_headlands():
        w *= smooth(_headland_distance(x, y, box)/80.)
    return w


COUNTRY_RIDGES=[
 {'y':3660.,'lean':-.18,'width':130.,'height':42.},
 {'y':4310.,'lean':.28,'width':110.,'height':52.},
 {'y':5080.,'lean':-.24,'width':145.,'height':64.},
 {'y':5530.,'lean':.16,'width':125.,'height':38.},
 {'y':6200.,'lean':-.15,'width':150.,'height':55.}]
HEADLAND_MASSES=[
 {'x':2900.,'y':220.,'rx':155.,'ry':95.,'angle':25.,'height':48.},
 {'x':2950.,'y':410.,'rx':110.,'ry':105.,'angle':-30.,'height':62.},
 {'x':2840.,'y':790.,'rx':175.,'ry':110.,'angle':35.,'height':42.},
 {'x':2880.,'y':975.,'rx':145.,'ry':100.,'angle':-25.,'height':57.},
 {'x':2980.,'y':310.,'rx':85.,'ry':70.,'angle':-15.,'height':28.},
 {'x':2950.,'y':875.,'rx':90.,'ry':65.,'angle':20.,'height':31.}]
# Each broad headland is a connected cluster with three different crowns, not one tabletop.
HEADLAND_MASSES=[dict(x=c['x']+dx*c['rx'],y=c['y']+dy*c['ry'],rx=c['rx']*sx,ry=c['ry']*sy,angle=c['angle']+turn,height=c['height']*h)
 for c in HEADLAND_MASSES for dx,dy,sx,sy,turn,h in [(-.32,.15,.66,.73,-18.,1.),(.34,-.18,.61,.62,22.,.78),(.05,.43,.48,.55,-32.,.58)]]

def landform_regions(x, y):
    """Localized editable scenery; occupied Belmonte ground ends west of x=1575."""
    from belmonte import layout as town
    x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
    country = smooth((x-1575.)/300.)*smooth((3250.-x)/100.)
    # The south collar rim belongs to the existing northern surface. Keep
    # local deformation zero there; the coast farther east keeps its reach.
    east_join = town.BOUNDS[2]+town.APRON
    south = 3150.+(town.SOUTH_JOIN-3150.)*(1.-smooth((x-east_join)/200.))
    country *= smooth((y-south)/300.)*smooth((6600.-y)/300.)
    headland = smooth((x-2200.)/250.)*smooth((3350.-x)/100.)
    headland *= smooth((y+20.)/120.)*smooth((1430.-y)/160.)
    return country, headland


def reach(x, y):
    """Refine every affected local landform while retaining the original coast elsewhere."""
    country, headland = landform_regions(x, y)
    band = _profile_reach(x, y)
    return np.maximum(band, np.maximum(np.where(country > 0., 1650., 0.),
                                      np.where(headland > 0., 850., 0.)))


@lru_cache(maxsize=1)
def rail_cover_boxes():
    """Overlapping groups cover every committed segment, including newly reached inland track."""
    p = np.array([[r['x'], r['y']] for r in json.loads(RAIL_LINE.read_text())['samples']])
    return tuple((float(q[:,0].min()-30.), float(q[:,1].min()-30.),
                  float(q[:,0].max()+30.), float(q[:,1].max()+30.))
                 for i in range(0, len(p)-1, 10) for q in [p[i:i+11]])


def rail_cover_distance(x, y, *, maximum=np.inf):
    x, y = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float))
    distance = np.full_like(x, maximum)
    if not x.size:
        return distance
    bounds = (x.min()-maximum, y.min()-maximum, x.max()+maximum, y.max()+maximum)
    for box in rail_cover_boxes():
        if box[2] < bounds[0] or box[3] < bounds[1] or box[0] > bounds[2] or box[1] > bounds[3]:
            continue
        distance = np.minimum(distance, _headland_distance(x, y, box))
    return distance


def protected_weight(x, y):
    return smooth(rail_cover_distance(x, y, maximum=350.)/350.)


def landform_envelope(x, y):
    country, headland = landform_regions(x, y)
    d, rock = field(x, y)
    country *= smooth((d-3.)/10.)*smooth((1650.-d)/100.)
    front = np.maximum(smooth(d/4.)*smooth((rock-.02)/.20), smooth((d-60.)/12.))
    headland *= front*smooth((850.-d)/180.)
    return np.maximum(country, headland)


def perimeter_weight(x, y):
    return np.maximum(_profile_perimeter_weight(x, y), landform_envelope(x, y))


def weight(x, y):
    return np.maximum(_profile_weight(x, y), landform_envelope(x, y)*protected_weight(x, y))


def wedge(x,y,c):
    """Joined rock shoulder with unequal peaks, a recessed face and a broad toe."""
    a=np.deg2rad(c['angle']);dx=x-c['x'];dy=y-c['y']
    u=(dx*np.cos(a)+dy*np.sin(a))/c['rx'];v=(-dx*np.sin(a)+dy*np.cos(a))/c['ry']
    edge=np.minimum.reduce([1.-u,1.+u,1.-v,1.+v,1.-.8*u-.6*v,1.+.5*u-.9*v])
    peak=np.maximum(0.,1.-np.abs(u-.12)/.85-np.abs(v+.18)/.90)
    secondary=.62*np.maximum(0.,1.-np.abs(u+.44)/.62-np.abs(v-.34)/.70)
    roof=.25+.82*np.maximum(peak,secondary)
    body=roof*smooth(edge/.32)
    gully=np.exp(-((u+.32*v+.07)/.13)**4)*smooth((v+.65)/.4)
    body*=1.-.50*gully
    toe=.22*smooth((edge+.12)/.48)
    return c['height']*np.maximum(body,toe)


def _landform_height(x,y,z):
    x,y,z=np.broadcast_arrays(np.asarray(x,float),np.asarray(y,float),np.asarray(z,float))
    d,rock=field(x,y)
    terrace=np.interp(d,[0.,60.,300.,600.,850.,1100.,1450.,1650.],[0.,3.6,10.,20.,36.,70.,190.,225.])
    ridge=np.zeros_like(z)
    for i,c in enumerate(COUNTRY_RIDGES):
        axis=c['y']+c['lean']*(x-2400.)
        along=np.exp(-((x-(2410.+100.*(i%2)))/420.)**4)
        ridge=np.maximum(ridge,c['height']*np.exp(-((y-axis)/c['width'])**2)*along)
    target=terrace+ridge*smooth((d-55.)/110.)
    for cy,lean,width in [(4670.,.13,170.),(5800.,-.12,150.)]:
        valley=np.exp(-((y-(cy+lean*(x-2400.)))/width)**4)*smooth((1350.-d)/300.)
        floor=6.+.025*np.maximum(d-80.,0.)
        target=target*(1.-.9*valley)+floor*.9*valley
    country_region,headland_region=landform_regions(x,y)
    w=country_region*smooth((d-60.)/60.)*smooth((1650.-d)/100.)
    w*=protected_weight(x,y)
    out=z*(1.-w)+target*w
    country_rock=np.zeros_like(z)
    for cy,cx,h,angle in [(4270.,2845.,36.,20.),(4390.,2900.,29.,-15.),(5180.,2920.,42.,-25.),(5340.,2910.,27.,25.),(6150.,2810.,38.,15.)]:
        country_rock=np.maximum(country_rock,wedge(x,y,dict(x=cx,y=cy,rx=180.,ry=95.,angle=angle,height=h)))
    cw=smooth((x-2400.)/180.)*smooth((3300.-x)/100.)*smooth((y-3500.)/200.)*smooth((6500.-y)/200.)
    cw*=smooth((d-3.)/10.)*smooth((280.-d)/100.)*smooth((rock-.25)/.45)*protected_weight(x,y)
    out=out*(1.-cw)+(5.+.035*np.maximum(d,0.)+country_rock)*cw
    masses=np.zeros_like(z)
    for c in HEADLAND_MASSES:
        masses=np.maximum(masses,wedge(x,y,c))
    # Two explicit recessed gullies divide crowns while leaving a connected rock base.
    for cy,lean,depth in [(330.,.35,27.),(825.,-.45,25.)]:
        cut=depth*np.exp(-((y-(cy+lean*(x-2900.)))/20.)**4)
        masses=np.maximum(0.,masses-cut)
    back=np.interp(d,[0.,60.,180.,400.,650.,850.],[0.,5.,9.,18.,48.,110.])
    # Keep the established low toe before the joined mass rises inland.
    target=back+masses*smooth(d/12.)*smooth((d-20.)/40.)
    front=np.maximum(smooth(d/4.)*smooth((rock-.02)/.20),smooth((d-60.)/12.))
    w=headland_region*front*smooth((850.-d)/180.)
    w*=protected_weight(x,y)
    return out*(1.-w)+target*w


def landforms(x, y, z):
    """Apply the named scenery only inside its two explicit regions."""
    x, y, z = np.broadcast_arrays(np.asarray(x, float), np.asarray(y, float), np.asarray(z, float))
    country, headland = landform_regions(x, y)
    active = (country > 0.) | (headland > 0.)
    if not np.any(active):
        return z
    out = z.copy()
    out[active] = _landform_height(x[active], y[active], z[active])
    return out


def height(x, y, base, *, exposed_west=False):
    """@cc [owner:fontanierh,label:correctness] coast-ground-ownership
    Ground beyond reach(x, y) inside the coast MUST remain unchanged. The wider
    Belmonte terrace/valley and eastern wedge landforms MUST remain inside their
    explicit local regions; occupied town terrain and the complete railway
    clearance envelope MUST retain their natural ground. The collar MUST join
    the same shaped country height at its outer edge.
    Country bays MUST retain broad dry sand followed by a rolling backshore,
    without compressing the high country into the southern 260 metre band.
    Country foreground relief MUST vary in two dimensions and taper out before
    protected or unchanged ground, rather than becoming one smooth ramp.
    Exterior ground MUST pass through sea level into a submerged toe; it MUST
    NOT retain broad zero-height quads. The occupied southern road/quay ground
    above y=-125 MUST remain unchanged. The committed railway and its natural
    tunnel cover MUST remain unchanged within 20 metres of the centre line.
    exposed_west MAY restore the coastal profile over the unoccupied legacy
    backdrop west of x=-300; it MUST NOT change the fine terrain or the default
    vegetation eligibility mask.
    """
    return landforms(x, y, profile_height(x, y, base,exposed_west=exposed_west))


def profile_height(x, y, base, *, exposed_west=False):
    """Established beach/cliff profile before the localized country landforms.

    The connecting collar interpolates this baseline first, then applies the
    bounded deformation at its own vertices so rail protection holds there too.
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
    w = _profile_weight(x, y,exposed_west=exposed_west)
    ground = base*(1.-w)+target*w
    perimeter = _profile_perimeter_weight(x, y)
    protection = np.divide(w, perimeter, out=np.zeros_like(w), where=perimeter > 1e-8)
    band = _profile_reach(x, y)
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


def meadow_caps(x, y, z, normal_z):
    """@cc [owner:fontanierh,label:correctness] coastal-meadow-cap-ownership
    Only gentle upper shoulders of the editable eastern landforms may gain
    meadow cover. Steep rock, pocket sand, occupied ground and rail cover MUST
    retain their existing palette. This mask MUST NOT change ground geometry.
    """
    x,y,z,normal_z=np.broadcast_arrays(x,y,z,normal_z)
    _,headland=landform_regions(x,y)
    d,rock=field(x,y)
    country=smooth((y-3500.)/400.)*smooth((6500.-y)/400.)*smooth((x-2200.)/250.)
    region=np.maximum(headland,country)
    high=smooth((z-(20.-14.*country))/18.)
    return (region*protected_weight(x,y)*smooth((weight(x,y)-.1)/.2)
            *smooth((d-28.)/35.)*smooth((500.-d)/100.)
            *smooth((rock-.25)/.35)*smooth((normal_z-.58)/.28)*high)


def meadow_cap_colour(x, y):
    patch=np.clip(.5+.3*np.sin(np.asarray(x)/37.+np.asarray(y)/53.)
                  +.2*np.cos(np.asarray(y)/29.),0.,1.)
    return np.array([.17,.235,.065])*(1.-patch[...,None])+np.array([.32,.285,.11])*patch[...,None]


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
    cap=meadow_caps(x,y,z,normal_z)
    shore=shore*(1.-cap[...,None])+meadow_cap_colour(x,y)*cap[...,None]
    coverage=np.maximum(coverage,cap)
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


def sample_grid_mesh(xs, ys, z, x, y, *, step=STEP, shape=height, parents=None, parent_refinement=None, edge_knots=None):
    """@cc [owner:fontanierh,label:correctness] coastal-planting-triangle-support
    Sample the same refined polygons and fan diagonals as grid_mesh and the
    terrain exporter. Do not evaluate the nonlinear shape at the query itself.
    Queries outside this grid or without a supporting face MUST fail.
    """
    xs,ys,z=np.asarray(xs),np.asarray(ys),np.asarray(z)
    x,y=np.broadcast_arrays(np.asarray(x,float),np.asarray(y,float));size=x.shape
    x,y=x.ravel(),y.ravel();out=np.empty_like(x)
    if np.any((x<xs[0])|(x>xs[-1])|(y<ys[0])|(y>ys[-1])):
        raise ValueError('Coastal ground query outside the exported grid')
    ix=np.clip(np.searchsorted(xs,x)-1,0,len(xs)-2)
    iy=np.clip(np.searchsorted(ys,y)-1,0,len(ys)-2)
    keys=iy*(len(xs)-1)+ix
    for key in np.unique(keys):
        mask=keys==key;j,i=divmod(int(key),len(xs)-1)
        vertices,faces=grid_mesh(xs[i:i+2],ys[j:j+2],z[j:j+2,i:i+2],step=step,shape=shape,parents=parents,parent_refinement=parent_refinement,edge_knots=edge_knots)
        triangles=np.asarray(vertices)[np.asarray([(p[0],p[k],p[k+1]) for p in faces for k in range(1,len(p)-1)])]
        a,b,c=np.moveaxis(triangles,1,0)
        den=(b[:,1]-c[:,1])*(a[:,0]-c[:,0])+(c[:,0]-b[:,0])*(a[:,1]-c[:,1])
        u=((b[:,1]-c[:,1])[:,None]*(x[mask]-c[:,0,None])+(c[:,0]-b[:,0])[:,None]*(y[mask]-c[:,1,None]))/den[:,None]
        v=((c[:,1]-a[:,1])[:,None]*(x[mask]-c[:,0,None])+(a[:,0]-c[:,0])[:,None]*(y[mask]-c[:,1,None]))/den[:,None]
        on=(u>=-1e-9)&(v>=-1e-9)&(u+v<=1.+1e-9)
        if not on.any(axis=0).all():raise ValueError('Coastal ground query has no exported support')
        values=u*a[:,2,None]+v*b[:,2,None]+(1.-u-v)*c[:,2,None]
        out[mask]=np.max(np.where(on,values,-np.inf),axis=0)
    return out.reshape(size)


def grid_mesh(xs, ys, z, *, hidden=None, step=STEP, shape=height, parents=None, parent_refinement=None, edge_knots=None):
    """@cc [owner:fontanierh,label:correctness] coastal-parent-triangle-topology
    Refined faces MUST preserve the original parent a-c breakline, including
    initial inserted knots and asymmetric x/y subdivision counts. With parents,
    its axes MUST partition every input cell and its heights are authoritative.
    Unchanged source heights MUST remain the same
    piecewise affine surface inside faces, not only at their vertices.
    Explicit edge_knots MUST be inserted into adjacent retained faces at the
    same shaped heights, without changing other edges or parent breaklines.

    Shared cell edges retain their original knots. Returns vertices and upward
    triangle/quad faces in world metres, without Blender.
    """
    xs, ys, z = np.asarray(xs), np.asarray(ys), np.asarray(z)
    if parents is not None:
        source_x,source_y,source_z=map(np.asarray,parents)
    if (parent_refinement or edge_knots) and parents is None:
        raise ValueError('Shared-edge refinement requires original parents')
    for (axis,value),knots in (edge_knots or {}).items():
        knots=np.asarray(knots)
        if axis not in (0,1) or not np.isfinite(value) or knots.ndim!=1 or not np.isfinite(knots).all():
            raise ValueError('Shared-edge knots require a finite axis and one-dimensional coordinates')
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
            px0,px1,py0,py1=ax,bx,ay,by
            a,b,c,d = z[j,i],z[j,i+1],z[j+1,i+1],z[j+1,i]
            if parents is not None:
                pi=int(np.clip(np.searchsorted(source_x,(ax+bx)/2.)-1,0,len(source_x)-2))
                pj=int(np.clip(np.searchsorted(source_y,(ay+by)/2.)-1,0,len(source_y)-2))
                px0,px1=source_x[pi:pi+2];py0,py1=source_y[pj:pj+2]
                if ax<px0-1e-9 or bx>px1+1e-9 or ay<py0-1e-9 or by>py1+1e-9:
                    raise ValueError('Inserted grid cell crosses an original parent boundary')
                a,b,c,d=source_z[pj,pi],source_z[pj,pi+1],source_z[pj+1,pi+1],source_z[pj+1,pi]
            lattice=(parent_refinement or {}).get((pi,pj),0) if parents is not None else 0
            if lattice:
                # Keep the original railway planner's parent sampling lattice,
                # independently of the number of newly refined coastal faces.
                q=np.linspace(0.,1.,lattice+1)
                xx=px0+(px1-px0)*q;yy=py0+(py1-py0)*q
                xx=np.unique(np.r_[ax,xx[(xx>ax+1e-9)&(xx<bx-1e-9)],bx])
                yy=np.unique(np.r_[ay,yy[(yy>ay+1e-9)&(yy<by-1e-9)],by])
                nx,ny=len(xx)-1,len(yy)-1
                x,y=np.meshgrid(xx,yy);u,v=(x-ax)/(bx-ax),(y-ay)/(by-ay)
            aligned=(ax==px0 and bx==px1 and ay==py0 and by==py1)
            pu,pv=(u,v) if aligned else ((x-px0)/(px1-px0),(y-py0)/(py1-py0))
            base = np.where(pu>=pv,a+pu*(b-a)+pv*(c-b),a+pu*(c-d)+pv*(d-a))
            h = shape(x, y, base)
            first = len(vertices)
            vertices.extend(np.stack((x, y, h), -1).reshape(-1, 3).tolist())
            face_start=len(faces)
            def finish_edges():
                if not parent_refinement and not edge_knots:return
                _join_parent_lattice_edges(vertices,faces,face_start,(ax,bx,ay,by),
                    (px0,px1,py0,py1,a,b,c,d),parents,parent_refinement or {},step,shape,edge_knots=edge_knots)
            signs=pu-pv
            if (nx == ny and aligned) or signs.min()>=-1e-12 or signs.max()<=1e-12:
                # Every diagonal-crossing child already uses the parent a-c.
                faces.extend((first+k*(nx+1)+l, first+k*(nx+1)+l+1,
                              first+(k+1)*(nx+1)+l+1, first+(k+1)*(nx+1)+l)
                             for k in range(ny) for l in range(nx))
                finish_edges()
                continue
            # Clip at ORIGINAL parent U=V, also when an inserted boundary
            # cuts that diagonal before the local refinement begins.
            diagonal = {}
            knots = np.unique(np.r_[pu[0,:],pv[:,0]])
            lo=max((ax-px0)/(px1-px0),(ay-py0)/(py1-py0))
            hi=min((bx-px0)/(px1-px0),(by-py0)/(py1-py0))
            knots=knots[(knots>=lo-1e-12)&(knots<=hi+1e-12)]
            dz = shape(px0+(px1-px0)*knots,py0+(py1-py0)*knots,a+(c-a)*knots)
            uv = {first+k*(nx+1)+l: (float(pu[k,l]),float(pv[k,l])) for k in range(ny+1) for l in range(nx+1)}
            for t, zz in zip(knots, dz):
                qx,qy=px0+(px1-px0)*t,py0+(py1-py0)*t
                lu,lv=(qx-ax)/(bx-ax),(qy-ay)/(by-ay)
                l,k=(int(np.argmin(abs(x[0]-qx))),int(np.argmin(abs(y[:,0]-qy)))) if lattice else (round(lu*nx),round(lv*ny))
                matches=(abs(x[0,l]-qx)<1e-9 and abs(y[k,0]-qy)<1e-9) if lattice else (abs(l/nx-lu)<1e-12 and abs(k/ny-lv)<1e-12)
                if matches:
                    index = first+k*(nx+1)+l
                else:
                    index = len(vertices)
                    vertices.append((qx,qy,float(zz)))
                    uv[index] = (t, t)
                diagonal[round(float(t), 12)] = index

            def clip(poly, sign):
                result = []
                for p, q in zip(poly[-1:]+poly[:-1], poly):
                    pu, pv = uv[p]; qu, qv = uv[q]
                    sp, sq = sign*(pu-pv), sign*(qu-qv)
                    if (sp < -1e-12 and sq > 1e-12) or (sp > 1e-12 and sq < -1e-12):
                        t = pu+(qu-pu)*sp/(sp-sq)
                        result.append(diagonal[round(t, 12)])
                    if sq >= -1e-12:
                        result.append(q)
                return result

            for k in range(ny):
                for l in range(nx):
                    quad = [first+k*(nx+1)+l, first+k*(nx+1)+l+1,
                            first+(k+1)*(nx+1)+l+1, first+(k+1)*(nx+1)+l]
                    signs = [uv[p][0]-uv[p][1] for p in quad]
                    if min(signs) >= -1e-12 or max(signs) <= 1e-12:
                        faces.append(tuple(quad))
                        continue
                    for sign in [-1., 1.]:
                        polygon = clip(quad, sign)
                        if len(polygon) == 4:
                            faces.append(tuple(polygon))
                        else:
                            faces.extend((polygon[0], polygon[q], polygon[q+1]) for q in range(1, len(polygon)-1))
            finish_edges()
    return vertices, faces


def _join_parent_lattice_edges(vertices,faces,start,bounds,parent,parents,refinement,step,shape,*,edge_knots=None):
    """Conform shared cell edges without propagating a rail grid across the island."""
    ax,bx,ay,by=bounds;px0,px1,py0,py1,a,b,c,d=parent
    sx,sy,_=parents
    def density(x,y):
        if x<sx[0] or x>sx[-1] or y<sy[0] or y>sy[-1]:return 0
        i=int(np.clip(np.searchsorted(sx,x)-1,0,len(sx)-2));j=int(np.clip(np.searchsorted(sy,y)-1,0,len(sy)-2))
        return refinement.get((i,j),0)
    own=density((ax+bx)/2.,(ay+by)/2.);edges={}
    for axis,value,lo,hi,outer,pa,pb in [
        (0,ax,ay,by,(ax-1e-6,(ay+by)/2.),py0,py1),
        (0,bx,ay,by,(bx+1e-6,(ay+by)/2.),py0,py1),
        (1,ay,ax,bx,((ax+bx)/2.,ay-1e-6),px0,px1),
        (1,by,ax,bx,((ax+bx)/2.,by+1e-6),px0,px1)]:
        n=max(own,density(*outer))
        knots=np.empty(0)
        if n:
            knots=pa+(pb-pa)*np.linspace(0.,1.,n+1)
            knots=np.r_[knots,np.linspace(lo,hi,math.ceil((hi-lo)/step)+1)]
        knots=np.unique(np.r_[knots,(edge_knots or {}).get((axis,value),[])])
        selected=knots[(knots>lo+1e-9)&(knots<hi-1e-9)]
        if len(selected):edges[axis,value]=selected
    if not edges:return
    lookup={tuple(np.round(vertices[i][:2],10)):i for f in faces[start:] for i in f}
    def point(x,y):
        key=tuple(np.round([x,y],10))
        if key not in lookup:
            u,v=(x-px0)/(px1-px0),(y-py0)/(py1-py0)
            z=a+u*(b-a)+v*(c-b) if u>=v else a+u*(c-d)+v*(d-a)
            lookup[key]=len(vertices);vertices.append((float(x),float(y),float(shape(x,y,z))))
        return lookup[key]
    result=[]
    for face in faces[start:]:
        polygon=[]
        for p,q in zip(face,face[1:]+face[:1]):
            polygon.append(p);vp,vq=vertices[p],vertices[q]
            for (axis,value),knots in edges.items():
                if abs(vp[axis]-value)>1e-9 or abs(vq[axis]-value)>1e-9:continue
                lo,hi=sorted([vp[1-axis],vq[1-axis]]);selected=knots[(knots>lo+1e-9)&(knots<hi-1e-9)]
                for t in selected[::1 if vq[1-axis]>vp[1-axis] else -1]:
                    polygon.append(point(value,t) if axis==0 else point(t,value))
        if len(polygon)==len(face):result.append(face);continue
        x,y=np.asarray([vertices[i][:2] for i in face]).mean(0);centre=point(x,y)
        result.extend((centre,p,q) for p,q in zip(polygon,polygon[1:]+polygon[:1]))
    faces[start:]=result
