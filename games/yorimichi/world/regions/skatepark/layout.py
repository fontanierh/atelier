"""Sunset Pier: shared geometry/gameplay dimensions, park-local metres (east, north, up)."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori
import json
import math
import numpy as np
try:
    from . import modules as M   # imported as skatepark.layout (gen_world, other regions)
except ImportError:
    import modules as M
JAPAN = yori.REGIONS
ORIGIN = (-110., -234., 1.8)
HALF_X, HALF_Y = 85., 66.
RAIL_INSET, RAILING_H, SLAB = .15, 1.1, .5
ENTRANCE_X, PATH_HALF = 6., 2.
COPING_R = .025  # flush rounded steel shoulder; no undercut for wheels to catch
STEEL_BAND, DECAL_Z, JOINT_W = .05, .025, .025
JOINTS_X = list(np.arange(-80., 81., 8.))
JOINTS_Y = list(np.arange(-64., 65., 8.))
LAMPS = [(x,y) for x in (-81.,-40.,0.,40.,81.) for y in (-62.,62.)]
# Existing detailed island trees sit in perimeter gardens; roots clear every riding line.
TREES = {
    'Tree_Maple_B': [[-72.,62.,.48,30.,.82],[-25.,62.,.48,140.,.9],[62.,62.,.48,75.,.85]],
    'Tree_Pine_B': [[-49.,62.,.48,60.,.53],[30.,62.,.48,160.,.5],[-68.,-62.,.48,25.,.5],
                    [40.,-62.,.48,70.,.53],[-80.,-38.,.48,110.,.5],[79.,-17.,.48,180.,.5]],
    'Tree_Maple_A': [[2.,-62.,.48,100.,.72]],
}
FLOOR_SUN = dict(x=-28., y=-10., r=3.2)
FLOOR_WAVES = [(-21.,-11.,-9.),(-20.5,-10.5,-11.),(-20.,-10.,-13.)]
# Every return transition reaches vertical; the flat decks sit beyond its coping.
QUARTERS = [dict(id='mini_west', lip=-36., sign=-1, y0=-23., y1=-13., radius=2.5, vert=.15, deck=3.),
            dict(id='mini_east', lip=-10., sign=1, y0=-23., y1=-13., radius=2.5, vert=.15, deck=2.5),
            dict(id='east_return', lip=70., sign=1, y0=18., y1=34., radius=2., vert=.15, deck=3.),
            dict(id='mellow_return', lip=68., sign=1, y0=-54., y1=-34., radius=1.5, vert=.1, deck=3.)]
BOWL = dict(x=29., y=-10., core_x=7., core_y=5., floor_radius=3., radius=3., vert=.2, deck=1.5, skirt=7.)
# Each terrace's stairs and handrails are extracted modules (modules.py): the kit's eight-stair (two sets side by side,
# 0.1875 m risers on 0.375 m treads) with its sloped rails on the big terrace, the park's two-step 0.75 m set with its
# handrails on the other two, sunk 40 cm into the ground: 55 cm over the top nosing like the kit's, 22 cm over the last.
# A set's top tread continues the deck: its risers stand at x1 + tread * (k + 1).
TERRACES = [dict(id='seven', x0=-70., x1=-48., y0=21., y1=36., height=1.5, steps=8, tread=.375, stair0=24., stair1=30., bank_sign=1, bank_run=8.,
                 stairs='kit_stairs', stairs_width=3., handrail='kit_handrail'),
            dict(id='four', x0=-70., x1=-48., y0=6., y1=17., height=.75, steps=2, tread=3., stair0=9., stair1=15., bank_sign=-1, bank_run=7.,
                 stairs='stairs_sml', stairs_width=6., handrail='handrail_sml', handrail_z=-.4),
            dict(id='market', x0=-76., x1=-56., y0=-28., y1=-10., height=.75, steps=2, tread=3., stair0=-24., stair1=-18., bank_sign=-1, bank_run=7.,
                 stairs='stairs_sml', stairs_width=6., handrail='handrail_sml', handrail_z=-.4)]
PADS = [dict(id='manny_low',x0=-40.,x1=-26.,y0=53.,y1=56.,height=.22),
        dict(id='manny_high',x0=-17.,x1=-3.,y0=53.,y1=56.,height=.30),
        dict(id='long_ledge',x0=-28.,x1=-8.,y0=25.,y1=28.,height=.32),
        dict(id='granite_ledge',x0=12.,x1=32.,y0=26.,y1=28.,height=.42),
        dict(id='harbour_bench',x0=42.,x1=56.,y0=22.,y1=23.2,height=.40),
        dict(id='low_curb',x0=-73.,x1=-52.,y0=-52.,y1=-50.8,height=.16),
        dict(id='sunset_manny',x0=-24.,x1=-10.,y0=-56.,y1=-52.,height=.24)]
BAR_R=.025


# Extracted obstacles (modules.py): a part, its centre (x, y, deck height) and yaw (its local +y turned anticlockwise
# from north: -90 lays a bar east-west), its paint, and how it is ground: along its measured top line (a bar, a
# handrail) or along its two top edges (a ledge, a bench). Bars in a row share one grind line (GRIND_LINES).
def _row(prefix, name, xs, y, colour):
    return [dict(id=f'{prefix}_{i}', part=name, at=(x, y, 0.), yaw=-90., colour=colour, finish='painted') for i, x in enumerate(xs)]


MODULES = (_row('flatbar_red', 'park_flatbar', (-25., -19., -13.), 43., 'red')
           # Sunk into the deck to ollie height: the hi-lo kink from 0.96 m down to 0.2 m, then a 0.5 m round rail after a run-out.
           + [dict(id='kink_rail', part='kink_rail', at=(9., 43., -.5), yaw=-90., colour='sage', finish='painted'),
              dict(id='round_rail', part='round_rail', at=(24., 43., -.2), yaw=-90., colour='sage', finish='painted'),
              dict(id='rainbow_medium', part='rainbow_medium', at=(46., 43., 0.), yaw=-90., colour='dusty_blue', finish='painted'),
              dict(id='rainbow_low', part='rainbow_low', at=(55., 43., 0.), yaw=-90., colour='dusty_blue', finish='painted')]
           + _row('sunset_bar', 'kit_flatrail', (5.5, 8.5, 11.5, 14.5), -46., 'mustard')
           # The street plaza north of the rainbows: a ledge, a manual pad, two benches, a curb rail, barriers and a table.
           + [dict(id='plaza_ledge', part='park_ledge', at=(45., 51., 0.), yaw=-90., colour='concrete_light', finish='concrete', grind='edges'),
              dict(id='plaza_pad', part='manual_pad', at=(54., 51., 0.), yaw=-90., colour='concrete_light', finish='concrete', grind='edges'),
              dict(id='plaza_bench_0', part='bench', at=(40., 56., 0.), yaw=0., colour='concrete_light', finish='concrete', grind='edges'),
              dict(id='plaza_bench_1', part='bench', at=(43.5, 56., 0.), yaw=0., colour='concrete_light', finish='concrete', grind='edges'),
              dict(id='plaza_curb_rail', part='curb_rail', at=(61., 51., 0.), yaw=0., colour='steel', finish='steel', grind='line', radius=None),
              dict(id='plaza_barrier_0', part='jersey', at=(51.3, 56.5, 0.), yaw=-90., colour='concrete', finish='concrete'),
              dict(id='plaza_barrier_1', part='jersey', at=(53.9, 56.5, 0.), yaw=-90., colour='concrete', finish='concrete'),
              dict(id='plaza_table', part='picnic_table', at=(60.5, 56., 0.), yaw=0., colour='timber', finish='wood')])
GRIND_LINES = [dict(id='flatbar_red', pieces=('flatbar_red_0', 'flatbar_red_1', 'flatbar_red_2'), radius=None),
               dict(id='kink_rail', pieces=('kink_rail',), radius=.065),
               dict(id='round_rail', pieces=('round_rail',), radius=.065),
               dict(id='rainbow_medium', pieces=('rainbow_medium',), radius=.042),
               dict(id='rainbow_low', pieces=('rainbow_low',), radius=.042),
               dict(id='sunset_bar', pieces=tuple(f'sunset_bar_{i}' for i in range(4)), radius=None)]
MODULE = {m['id']: m for m in MODULES}


def terrace_modules(t):
    """A terrace's stair sets and its two handrails, as module placements (yaw 90: the uphill side faces west)."""
    x1 = t['x1']; run = t['steps']*t['tread']; w = t['stairs_width']
    out = [dict(id=f"{t['id']}_stairs_{i}", part=t['stairs'], at=(x1+run/2, t['stair0']+w*(i+.5), 0.), yaw=90.,
                colour='concrete_light', finish='stairs') for i in range(int(round((t['stair1']-t['stair0'])/w)))]
    for i, y in enumerate((t['stair0']+1.5, t['stair1']-1.5)):
        part = M.part(t['handrail']); half = (part['bounds'][1][1]-part['bounds'][0][1])/2
        out.append(dict(id=f"{t['id']}_handrail_{i}", part=t['handrail'], at=(x1+half, y, t.get('handrail_z', 0.)), yaw=90., colour='red',
                        finish='painted'))
    return out


def joints(item_id):
    """Where a grind line's pieces meet, as (point, unit direction along the line): their facing end caps are buried
    in the bar and the board's sweep catches on them, so features.py leaves them out."""
    out = []
    for g in GRIND_LINES:
        if item_id not in g['pieces']: continue
        for a, b in zip(g['pieces'], g['pieces'][1:]):
            if item_id not in (a, b): continue
            end, start = M.line(MODULE[a])[-1], M.line(MODULE[b])[0]
            d = np.subtract(M.line(MODULE[a])[-1], M.line(MODULE[a])[0])[:2]
            out.append(((np.add(end, start)/2)[:2], d/np.linalg.norm(d)))
    return out


def grind_line(pieces):
    """One line through several modules' measured top lines, end to end."""
    pts = []
    for piece in pieces:
        for p in M.line(MODULE[piece]):
            if not pts or math.dist(p, pts[-1]) > .01: pts.append(p)
    return pts
FUNBOX=dict(x0=-26.,x1=0.,top0=-16.,top1=-10.,y0=-5.,y1=13.,height=.65)
HIPS=[dict(id='sunset_hip',x0=6.,x1=38.,top0=18.,top1=24.,y0=-57.,y1=-49.,height=.75)]
CURVE_LEDGE=dict(id='wave_ledge',x=-1.,y=29.,radius=11.,width=.8,height=.34,a0=-150.,a1=-30.)
CURVE_BAR=dict(id='crescent_rail',x=-57.,y=-44.5,radius=9.,height=.36,a0=20.,a1=160.)
# Approach banks end on the decks, with 2m fillets at both ends.
BANKS=[dict(id='mini_access',axis='y',top=-13.,sign=1,run=11.,w0=-39.,w1=-36.,height=2.65),
       dict(id='return_access',axis='y',top=18.,sign=-1,run=9.,w0=70.,w1=73.,height=2.15),
       dict(id='mellow_access',axis='y',top=-34.,sign=1,run=8.,w0=68.,w1=71.,height=1.6),
       dict(id='bump_to_bar',axis='x',top=-5.,sign=-1,run=5.,w0=-46.9,w1=-45.1,height=.45),
       dict(id='bump_return',axis='x',top=-5.,sign=1,run=5.,w0=-46.9,w1=-45.1,height=.45),
       dict(id='plaza_kicker',axis='x',top=8.,sign=-1,run=5.,w0=30.,w1=35.,height=.65),
       dict(id='plaza_landing',axis='x',top=8.,sign=1,run=5.,w0=30.,w1=35.,height=.65)]
for t in TERRACES:
    if t['id']=='seven':
        BANKS.append(dict(id='seven_access',axis='x',top=t['x1'],sign=1,run=8.,w0=30.7,w1=36.,height=t['height']))
        continue
    BANKS.append(dict(id=t['id']+'_access',axis='y',top=t['y1'] if t['bank_sign']>0 else t['y0'],sign=t['bank_sign'],run=t['bank_run'],w0=t['x0'],w1=t['x1'],height=t['height']))

# Back banks connect both street decks to a shared west circulation lane.
for t in TERRACES:
    BANKS.append(dict(id=t['id']+'_back',axis='x',top=t['x0'],sign=-1,run=5.,w0=t['y0'],w1=t['y1'],height=t['height']))
    BANKS.append(dict(id=t['id']+'_left',axis='x',top=t['x1'],sign=1,run=8.,w0=t['y0'],w1=t['stair0']-.7,height=t['height']))
    if t['id']!='seven':
        BANKS.append(dict(id=t['id']+'_right',axis='x',top=t['x1'],sign=1,run=8.,w0=t['stair1']+.7,w1=t['y1'],height=t['height']))


def world(p):
    return [ORIGIN[0]+p[0],ORIGIN[1]+p[1],ORIGIN[2]+(p[2] if len(p)>2 else 0)]

def quarter_profile(q, step_deg=2.):
    r=q['radius']; n=math.ceil(90/step_deg); toe=q['lip']-q['sign']*r
    pts=[(toe+q['sign']*r*math.sin(i*math.pi/2/n),r*(1-math.cos(i*math.pi/2/n))) for i in range(n+1)]
    h=r+q['vert']; cr=COPING_R
    return pts+[(q['lip'],h-cr)]+[(q['lip']+q['sign']*cr*(1-math.cos(a)),h-cr+cr*math.sin(a)) for a in np.linspace(math.pi/36,math.pi/2,18)]

def fillet_polyline(corners, radii, step_deg=2.5):
    """2D polyline (u, z) with circular fillets at interior corners; exact tangent points."""
    c = [np.array(p, float) for p in corners]
    out = [c[0]]
    for i in range(1, len(c) - 1):
        a, b, d = c[i - 1], c[i], c[i + 1]
        u = (b - a) / np.linalg.norm(b - a); v = (d - b) / np.linalg.norm(d - b)
        ang = math.acos(float(np.clip(u @ v, -1, 1)))
        r = radii[i - 1]
        if ang < 1e-6 or r <= 0:
            out.append(b); continue
        t = r * math.tan(ang / 2)
        p1 = b - u * t; p2 = b + v * t
        cross = u[0] * v[1] - u[1] * v[0]
        n = np.array([-u[1], u[0]]) * (1 if cross > 0 else -1)
        centre = p1 + n * r
        a1 = math.atan2(*(p1 - centre)[::-1]); a2 = math.atan2(*(p2 - centre)[::-1])
        d_ang = a2 - a1
        while d_ang > math.pi: d_ang -= 2 * math.pi
        while d_ang < -math.pi: d_ang += 2 * math.pi
        m = max(1, int(math.ceil(abs(math.degrees(d_ang)) / step_deg)))
        for k in range(m + 1):
            t_ = a1 + d_ang * k / m
            out.append(centre + r * np.array([math.cos(t_), math.sin(t_)]))
    out.append(c[-1])
    clean = [out[0]]
    for p in out[1:]:
        if np.linalg.norm(p - clean[-1]) > 1e-6: clean.append(p)
    return [tuple(map(float, p)) for p in clean]



def bank_profile(b):
    # Shift corner positions to put the final tangent exactly at the deck join.
    h=b['height']; a=math.atan2(h,b['run']); t=2*math.tan(a/2); sign=b['sign']; top=b['top']
    pts=fillet_polyline([(-1.,0),(0.,0),(b['run'],h),(b['run']+1,h)],[2.,2.])[1:-1]
    return [(round(top+sign*(b['run']+t-u),6),round(z,6)) for u,z in pts]

def funbox_profile(f=None):
    f=f or FUNBOX; h=f['height']
    pts=fillet_polyline([(f['x0']-1,0),(f['x0'],0),(f['top0'],h),(f['top1'],h),(f['x1'],0),(f['x1']+1,0)],[2.,2.,2.,2.])[1:-1]
    pts=[(round(x,6),round(z,6)) for x,z in pts]
    return pts,(pts[len(pts)//2-1][0],pts[len(pts)//2][0])


def arc_points(feature, radius=None, z=None):
    r=feature['radius'] if radius is None else radius
    height=feature['height'] if z is None else z
    return [(feature['x']+r*math.cos(a),feature['y']+r*math.sin(a),height)
            for a in np.linspace(math.radians(feature['a0']),math.radians(feature['a1']),121)]

def bowl_ring(radius,z):
    """Consistent CCW rings: quarter-circle corners and subdivided straight sections."""
    b=BOWL; out=[]
    corners=[(b['core_x'],b['core_y'],0),(-b['core_x'],b['core_y'],90),(-b['core_x'],-b['core_y'],180),(b['core_x'],-b['core_y'],270)]
    for i,(cx,cy,angle) in enumerate(corners):
        for k in range(37):
            a=math.radians(angle+90*k/36); out.append((b['x']+cx+radius*math.cos(a),b['y']+cy+radius*math.sin(a),z))
        nx,ny,na=corners[(i+1)%4]; a=math.radians(angle+90)
        end=np.array([b['x']+nx+radius*math.cos(a),b['y']+ny+radius*math.sin(a),z]); start=np.array(out[-1]); n=math.ceil(np.linalg.norm(end-start)/.75)
        fractions=set(k/n for k in range(1,n))
        if i==1: fractions.update((.1,.9))  # exact west bank entrance boundaries
        out.extend([tuple(start+(end-start)*f) for f in sorted(fractions)])
    return out

def terrace_rails(t):
    """The handrail modules' top lines, as (y, [(x, z), ...]) down the stairs."""
    return [(m['at'][1], [(p[0], p[2]) for p in M.line(m)]) for m in terrace_modules(t) if m['finish'] == 'painted']

def hubba_profile(t):
    x=t['x1']+t['tread']; end=t['x1']+t['steps']*t['tread']
    return [(t['x1']-3.,t['height']+.32),(x,t['height']+.32),(end+2.,.32)]

def footprints():
    out={}
    for q in QUARTERS:
        p=quarter_profile(q); back=q['lip']+q['sign']*q['deck']
        out[q['id']]=(min(p[0][0],back),max(p[0][0],back),q['y0'],q['y1'])
    for b in BANKS:
        p=bank_profile(b); ends=sorted([p[0][0],p[-1][0]])
        out[b['id']]=(*ends,b['w0'],b['w1']) if b['axis']=='x' else (b['w0'],b['w1'],*ends)
    for t in TERRACES:
        out[t['id']+'_terrace']=(t['x0'],t['x1'],t['y0'],t['y1'])
        out[t['id']+'_stairs']=(t['x1'],t['x1']+t['steps']*t['tread'],t['stair0'],t['stair1'])
        for side in (-1,1):
            y=t['stair0']-.7 if side<0 else t['stair1']
            out[t['id']+'_hubba_'+str(side)]=(t['x1'],hubba_profile(t)[-1][0],y,y+.7)
    back=bank_profile(next(b for b in BANKS if b['id']=='seven_back'))
    front=bank_profile(next(b for b in BANKS if b['id']=='seven_left'))
    out['street_link']=(back[0][0],front[0][0],17.,21.)
    for p in PADS: out[p['id']]=(p['x0'],p['x1'],p['y0'],p['y1'])
    p,_=funbox_profile(); out['flow_table']=(p[0][0],p[-1][0],FUNBOX['y0'],FUNBOX['y1'])
    for f in HIPS:
        p,_=funbox_profile(f);out[f['id']]=(p[0][0],p[-1][0],f['y0'],f['y1'])
    return out

def grid_lines(spacing=1.25):
    hx={-HALF_X,HALF_X}; hy={-HALF_Y,HALF_Y}
    for x0,x1,y0,y1 in footprints().values(): hx|={round(x0,6),round(x1,6)};hy|={round(y0,6),round(y1,6)}
    hx|={round(ENTRANCE_X+o,6) for o in PATH_OFFSETS}
    hy|={FUNBOX['y0']+.05,FUNBOX['y1']-.05}
    for j in JOINTS_X: hx|={round(j-JOINT_W/2,6),round(j+JOINT_W/2,6)}
    for j in JOINTS_Y: hy|={round(j-JOINT_W/2,6),round(j+JOINT_W/2,6)}
    def fill(hard,half):
        h=np.array(sorted(hard)); uni=np.linspace(-half,half,math.ceil(2*half/spacing)+1)
        return np.array(sorted(hard|{round(float(u),6) for u in uni if np.min(np.abs(h-u))>.12}))
    return fill(hx,HALF_X),fill(hy,HALF_Y)

def lines_between(lines,a,b):
    return [float(v) for v in lines if a-1e-6<=v<=b+1e-6]

# ----------------------------------------------------------------------------- path
PATH_OFFSETS = [-2.0, -1.85, -0.95, 0.0, 0.95, 1.85, 2.0]
PATH_GRADE = 0.090             # centreline limit on straights (edges checked <= 10%)
PATH_EDGE_GRADE = 0.097        # inner-edge limit on curves
PATH_CLEAR = 0.05              # surface above the upper terrain envelope


def _fillet_route(pts, radii, spacing=0.5):
    pts = [np.array(p, float) for p in pts]
    segs = []; cur = pts[0]
    for k in range(1, len(pts) - 1):
        a, b, c = pts[k - 1], pts[k], pts[k + 1]
        u = (b - a) / np.linalg.norm(b - a); v = (c - b) / np.linalg.norm(c - b)
        ang = math.acos(float(np.clip(u @ v, -1, 1))); r = radii[k - 1]
        t = r * math.tan(ang / 2)
        assert t < np.linalg.norm(b - cur) + 1e-6 and t < np.linalg.norm(c - b), ('fillet too large', k)
        p1 = b - u * t; p2 = b + v * t
        segs.append(('L', cur, p1, math.inf))
        cross = u[0] * v[1] - u[1] * v[0]
        n = np.array([-u[1], u[0]]) * (1 if cross > 0 else -1)
        segs.append(('A', p1 + n * r, r, p1, p2, cross > 0))
        cur = p2
    segs.append(('L', cur, pts[-1], math.inf))
    P = []; R = []
    for sg in segs:
        if sg[0] == 'L':
            a, b = sg[1], sg[2]; L = np.linalg.norm(b - a)
            if L < 1e-6: continue
            n = max(1, int(math.ceil(L / spacing)))
            for i in range(n): P.append(a + (b - a) * i / n); R.append(math.inf)
        else:
            _, c, r, p1, p2, ccw = sg
            a1 = math.atan2(*(p1 - c)[::-1]); a2 = math.atan2(*(p2 - c)[::-1]); d = a2 - a1
            if ccw and d < 0: d += 2 * math.pi
            if not ccw and d > 0: d -= 2 * math.pi
            n = max(1, int(math.ceil(abs(d) * r / spacing)))
            for i in range(n):
                t = a1 + d * i / n; P.append(c + r * np.array([math.cos(t), math.sin(t)])); R.append(r)
    P.append(pts[-1]); R.append(math.inf)
    return np.array(P), np.array(R)


def _lipschitz(z, s, g):
    z = z.copy()
    for i in range(1, len(z)): z[i] = max(z[i], z[i - 1] - g[i] * (s[i] - s[i - 1]))
    for i in range(len(z) - 2, -1, -1): z[i] = max(z[i], z[i + 1] - g[i] * (s[i + 1] - s[i]))
    return z


def _gauss(z, s, sigma):
    ds = float(np.mean(np.diff(s))); k = int(3 * sigma / ds)
    x = np.arange(-k, k + 1) * ds; w = np.exp(-.5 * (x / sigma) ** 2); w /= w.sum()
    zp = np.r_[np.full(k, z[0]), z, np.full(k, z[-1])]
    return np.convolve(zp, w, mode='valid')


def load_world():
    return json.loads((yori.OUT / 'world.json').read_text()), np.load(yori.OUT / 'heightmap.npy')


def path_layout(world, h):
    """Centreline, frames and a smooth grade-limited profile that never dips under the terrain."""
    import sys
    sys.path.insert(0, str(JAPAN))
    from village.layout import upper_surface
    road = np.array(world['road'])
    i = int(np.argmin(np.abs(road[:, 0] + 155.3)))
    tan = road[i + 1, :2] - road[i - 1, :2]; tan /= np.linalg.norm(tan)
    south = np.array([tan[1], -tan[0]])
    start = road[i, :2] + south * world['road_width'] / 2
    end = np.array([ORIGIN[0] + ENTRANCE_X, ORIGIN[1] + HALF_Y])
    route = [start, start + south * 5.0, (-154.6, -101.5), (-121.0, -106.5), (end[0], -146.0), (end[0], end[1] + 8.0), end]
    radii = [20.0, 10.0, 20.0, 25.0]
    P, R = _fillet_route(route[:-1], radii)
    # straight run-in to the deck edge
    tail = np.array([P[-1] + (end - P[-1]) * k / 16 for k in range(1, 17)])
    P = np.vstack([P, tail]); R = np.r_[R, np.full(len(tail), math.inf)]
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(P, axis=0), axis=1))]
    t = np.gradient(P, s, axis=0); t /= np.linalg.norm(t, axis=1)[:, None]
    t[0] = south; t[-8:] = (0, -1)
    n = np.column_stack([-t[:, 1], t[:, 0]])
    # terrain envelope over the whole footprint (dense across and along)
    offs = np.linspace(-PATH_HALF - .15, PATH_HALF + .15, 44)
    fine = np.linspace(0, s[-1], int(s[-1] / .1) + 1)
    Px = np.interp(fine, s, P[:, 0]); Py = np.interp(fine, s, P[:, 1])
    nx = np.interp(fine, s, n[:, 0]); ny = np.interp(fine, s, n[:, 1])
    Tf = np.max([upper_surface(h, Px + nx * o, Py + ny * o) for o in offs], axis=0) + PATH_CLEAR
    T = np.array([Tf[max(0, int((a - .3) / .1)):int((a + .3) / .1) + 1].max() for a in s])
    z0 = float(road[i, 2] + 0.06); z1 = ORIGIN[2]
    g = np.where(np.isfinite(R), PATH_EDGE_GRADE * (1 - (PATH_HALF + .05) / np.maximum(R, 3)), PATH_GRADE)
    g = np.minimum(g, PATH_GRADE)
    # the smoothing below mixes grades over about +-6 m: hold the curve limit that far out
    g = np.array([g[(s > a - 6.5) & (s < a + 6.5)].min() for a in s])
    lo = T.copy()
    lo[s < 1.0] = np.maximum(lo[s < 1.0], z0)                 # level run-off the road
    lo[s > s[-1] - 4.0] = np.maximum(lo[s > s[-1] - 4.0], z1)  # level run-in to the deck
    E = _lipschitz(lo, s, g)
    assert E[0] <= z0 + 1e-6 and E[-1] <= z1 + 1e-6, ('path infeasible', E[0], z0, E[-1], z1)
    fixed = (s < 1.0) | (s > s[-1] - 4.0)
    target = np.where(s < 1.0, z0, np.where(s > s[-1] - 4.0, z1, E))
    z = target.copy()
    for _ in range(6):
        z = np.maximum(_gauss(z, s, 2.0), E)
        z[fixed] = target[fixed]
    z = np.maximum(z, E)
    return dict(P=P, s=s, t=t, n=n, z=z, R=R, T=T - PATH_CLEAR, E=E, z0=z0, start=start, road_index=i,
                road_tangent=tan, end=end, road=road, route=[list(map(float, p)) for p in route], radii=radii)


def path_ring(pl, k):
    """World-space ring of the path surface at sample k (x, y, z for each PATH_OFFSET)."""
    return [(pl['P'][k, 0] + pl['n'][k, 0] * o, pl['P'][k, 1] + pl['n'][k, 1] * o, pl['z'][k]) for o in PATH_OFFSETS]


def offset_polyline(top, r):
    """Axis of a round rail whose top contact line is `top` [(x, z)...] (perpendicular offset)."""
    top = [np.array(p, float) for p in top]
    lines = []
    for a, b in zip(top[:-1], top[1:]):
        d = (b - a) / np.linalg.norm(b - a); u = np.array([-d[1], d[0]])
        if u[1] < 0: u = -u
        lines.append((a - u * r, d))
    out = [lines[0][0]]
    for (p1, d1), (p2, d2) in zip(lines[:-1], lines[1:]):
        # intersect p1 + t d1 = p2 + s d2
        A = np.array([[d1[0], -d2[0]], [d1[1], -d2[1]]]); t = np.linalg.solve(A, p2 - p1)[0]
        out.append(p1 + d1 * t)
    last_p, last_d = lines[-1]
    out.append(top[-1] - np.array([-last_d[1], last_d[0]]) * r * (1 if last_d[0] >= 0 else -1))
    return [tuple(map(float, p)) for p in out]


def _dense(poly, step):
    """Resample a polyline keeping its corners exactly."""
    poly = [np.array(p, float) for p in poly]
    out = [poly[0]]
    for a, b in zip(poly[:-1], poly[1:]):
        n = max(1, int(math.ceil(np.linalg.norm(b - a) / step)))
        out += [a + (b - a) * k / n for k in range(1, n + 1)]
    return [[round(float(c), 4) for c in p] for p in out]



def rails():
    out=[]
    def add(id,kind,pts,side=None,radius=None):
        r=dict(id=id,kind=kind,points=_dense(pts,.5))
        if side is not None:r['side']=side
        if radius is not None:r['radius']=radius
        out.append(r)
    for q in QUARTERS:
        x=q['lip']+q['sign']*COPING_R; z=q['radius']+q['vert']
        add(q['id']+'_coping','coping',[(x,q['y0'],z),(x,q['y1'],z)],[-q['sign'],0],COPING_R)
    b=BOWL; ring=bowl_ring(b['floor_radius']+b['radius']+COPING_R,b['radius']+b['vert'])
    add('bowl_coping','coping',ring+[ring[0]],radius=COPING_R)
    for t in TERRACES:
        radius={'kit_handrail':.045,'handrail_sml':.065}[t['handrail']]
        for i,(y,p) in enumerate(terrace_rails(t)):add(t['id']+'_handrail_'+str(i),'rail',[(x,y,z) for x,z in p],radius=radius)
        for side in (-1,1):
            y=t['stair0']-.7 if side<0 else t['stair1']
            for offset,sgn in [(0,-1),(.7,1)]:add(t['id']+'_hubba_'+str(side)+'_'+str(sgn),'ledge',[(x,y+offset,z) for x,z in hubba_profile(t)],[0,sgn])
    for g in GRIND_LINES:add(g['id'],'rail',grind_line(g['pieces']),radius=g['radius'])
    for m in MODULES:
        if m.get('grind')=='line':add(m['id'],'rail',M.line(m),radius=m.get('radius'))
        if m.get('grind')=='edges':
            for i,(pts,side) in enumerate(M.edges(m)):add(m['id']+('-1' if i==0 else '1'),'ledge',pts,list(side))
    add(CURVE_BAR['id'],'rail',arc_points(CURVE_BAR),radius=BAR_R)
    for side in (-1,1):
        add(CURVE_LEDGE['id']+str(side),'ledge',arc_points(CURVE_LEDGE,CURVE_LEDGE['radius']+side*CURVE_LEDGE['width']/2))
    for p in PADS:
        for y,sgn in [(p['y0'],-1),(p['y1'],1)]:add(p['id']+str(sgn),'ledge',[(p['x0'],y,p['height']),(p['x1'],y,p['height'])],[0,sgn])
        for x,sgn in [(p['x0'],-1),(p['x1'],1)]:add(p['id']+'_end'+str(sgn),'curb',[(x,p['y0'],p['height']),(x,p['y1'],p['height'])],[sgn,0])
    # The wave has rolling shoulders, not an artificial ledge along the curved side.
    q=QUARTERS[0]; rr=13+COPING_R; z=q['radius']+q['vert']
    arc=[(-23+rr*math.cos(a),-23+rr*math.sin(a),z) for a in np.linspace(math.pi,2*math.pi,121)]
    add('mini_curve_coping','coping',arc,radius=COPING_R)
    return out
