"""Skate pier geometry in park-local metres (see layout.py). No bpy: MeshData only.

Riding surfaces are the collision (complex as simple), so every ramp surface is one clean
shared-vertex patch, ramps start exactly on floor grid lines and the floor has holes under
solid features (no coplanar overlap, no lips)."""
import math
import numpy as np
import layout as L
import modules as MOD
from geom import MeshData, PAL

XS, YS = L.grid_lines()


def P(axis, u, w, z):
    return (u, w, z) if axis == 'x' else (w, u, z)


def wl(lines, a, b, extra=()):
    v = sorted(set([round(x, 6) for x in L.lines_between(lines, a, b)] + [round(a, 6), round(b, 6)] + [round(e, 6) for e in extra]))
    out = [v[0]]
    for x in v[1:]:
        if x - out[-1] > 1e-4: out.append(x)
    return out


def ramp(m, prof, axis, wlines, color, want, tag='paint', color_fn=None):
    rows = [[P(axis, u, w, z) for w in wlines] for u, z in prof]
    return m.grid(rows, color, tag, True, want, color_fn)


def side_fan(m, axis, w, pts_uz, anchor_uz, color, want, tag='wall'):
    m.fan_polygon([P(axis, u, w, z) for u, z in pts_uz], P(axis, anchor_uz[0], w, anchor_uz[1]), color, tag, want)


def wall(m, axis, u, w0, w1, z0, z1, color, want, tag='wall', wlines=None, zsteps=None):
    """Vertical wall at constant `axis` coordinate u (axis 'x': wall in the y-z plane)."""
    ws = wlines if wlines is not None else [w0, w1]
    n = zsteps or max(1, int(math.ceil((z1 - z0) / 0.6)))
    zs = [z0 + (z1 - z0) * k / n for k in range(n + 1)]
    rows = [[P(axis, u, w, z) for w in ws] for z in zs]
    m.grid(rows, color, tag, False, want)


def flat(m, x0, x1, y0, y1, z, color, tag='concrete', want=(0, 0, 1), xl=None, yl=None, color_fn=None):
    xs = xl if xl is not None else wl(XS, x0, x1)
    ys = yl if yl is not None else wl(YS, y0, y1)
    rows = [[(x, y, z) for y in ys] for x in xs]
    return m.grid(rows, color, tag, False, want, color_fn)


def railing(m, pts, height, color='railing', post_every=2.0, post=0.06, top_r=0.028, mid_r=0.02, base_z=None):
    """Posts and two round rails along a straight run a->b (x, y, z-base)."""
    a = np.array(pts[0], float); b = np.array(pts[1], float)
    L_ = np.linalg.norm(b[:2] - a[:2]); n = max(1, int(math.ceil(L_ / post_every)))
    for k in range(n + 1):
        p = a + (b - a) * k / n
        m.box((p[0] - post / 2, p[1] - post / 2, p[2] - 0.03), (p[0] + post / 2, p[1] + post / 2, p[2] + height - top_r), color, 'railing')
    m.tube([a + (0, 0, height - top_r), b + (0, 0, height - top_r)], top_r, color, 'railing', sides=8)
    m.tube([a + (0, 0, height * .5), b + (0, 0, height * .5)], mid_r, color, 'railing', sides=6)


def steel_side_band(m, axis, w, u0, u1, z_top, out_sign, zlen=L.STEEL_BAND, proud=0.002):
    """Vertical flange of the steel angle on a side face, 2 mm proud."""
    ww = w + out_sign * proud
    want = (0, out_sign, 0) if axis == 'x' else (out_sign, 0, 0)
    m.poly([P(axis, u0, ww, z_top - zlen), P(axis, u1, ww, z_top - zlen), P(axis, u1, ww, z_top), P(axis, u0, ww, z_top)], 'steel', 'steel', want=want)


def steel_side_band_sloped(m, axis, w, top_uz, out_sign, zlen=L.STEEL_BAND, proud=0.002):
    ww = w + out_sign * proud
    want = (0, out_sign, 0) if axis == 'x' else (out_sign, 0, 0)
    for (u0, z0), (u1, z1) in zip(top_uz[:-1], top_uz[1:]):
        m.poly([P(axis, u0, ww, z0 - zlen), P(axis, u1, ww, z1 - zlen), P(axis, u1, ww, z1), P(axis, u0, ww, z0)], 'steel', 'steel', want=want)


def ledge_box(m, x0, x1, y0, y1, h, top_color='concrete_light', side_color='concrete_light', steel_x=False, steel_y=True):
    b = L.STEEL_BAND
    xs = wl(XS, x0, x1, extra=((x0 + b, x1 - b) if steel_x else ()))
    ys = wl(YS, y0, y1, extra=((y0 + b, y1 - b) if steel_y else ()))
    lx, ly = len(xs) - 2, len(ys) - 2
    def col(i, j):
        if steel_y and j in (0, ly): return 'steel'
        if steel_x and i in (0, lx): return 'steel'
        return top_color
    flat(m, x0, x1, y0, y1, h, top_color, 'concrete', xl=xs, yl=ys, color_fn=col)
    wall(m, 'y', y0, x0, x1, -0.05, h, side_color, (0, -1, 0), wlines=xs, zsteps=1)
    wall(m, 'y', y1, x0, x1, -0.05, h, side_color, (0, 1, 0), wlines=xs, zsteps=1)
    wall(m, 'x', x0, y0, y1, -0.05, h, side_color, (-1, 0, 0), wlines=ys, zsteps=1)
    wall(m, 'x', x1, y0, y1, -0.05, h, side_color, (1, 0, 0), wlines=ys, zsteps=1)
    if steel_y:
        steel_side_band(m, 'x', y0, x0, x1, h, -1); steel_side_band(m, 'x', y1, x0, x1, h, 1)
    if steel_x:
        steel_side_band(m, 'y', x0, y0, y1, h, -1); steel_side_band(m, 'y', x1, y0, y1, h, 1)



# ----------------------------------------------------------------------------- rideable structures
def quarter(m,q):
    prof=L.quarter_profile(q); ys=wl(YS,q['y0'],q['y1']); h=prof[-1][1]; sign=q['sign']; lip=q['lip']; back=lip+sign*q['deck']
    ramp(m,prof,'x',ys,'sage',(-sign,0,1),'transition',lambda i,j: 'coping' if i>=46 else 'tile' if i==45 else 'sage')
    edge=prof[-1][0]
    flat(m,min(edge,back),max(edge,back),q['y0'],q['y1'],h,'concrete_light',yl=ys)
    wall(m,'x',back,q['y0'],q['y1'],0,h,'sage',(sign,0,0),wlines=ys)
    for y,side in [(q['y0'],-1),(q['y1'],1)]:
        if q['id'].startswith('mini') and side==-1:continue  # continuous curved return
        side_fan(m,'x',y,prof,(lip,0),'sage',(0,side,0))
        if not ((q['id']=='east_return' and side==-1) or (q['id']=='mini_west' and side==1)):
            m.poly([(edge,y,0),(back,y,0),(back,y,h),(edge,y,h)],'sage',want=(0,side,0))


def mini_return(m):
    # A continuous 180-degree corner links the two mini walls into an open horseshoe.
    q=L.QUARTERS[1];h=q['radius']+q['vert']; prof=[(x+23,z) for x,z in L.quarter_profile(q)]
    prof += [(15.5,h)]
    # The rounded south back is a rideable skirt, rather than a vertical wall.
    prof += [(15.5+3*u,h*(1-3*u*u+2*u*u*u)) for u in np.linspace(0,1,25)[1:]]
    angles=np.linspace(math.pi,2*math.pi,121)
    rows=[[( -23+r*math.cos(a),-23+r*math.sin(a),z) for a in angles] for r,z in prof]
    ids=[[m.vert(p) for p in row] for row in rows]
    distance=np.r_[0,np.cumsum(np.linalg.norm(np.diff(np.array(prof),axis=0),axis=1))]
    widths=np.linspace(0,40.8,len(angles))  # whole tile repeats at the two quarter joins
    for i in range(len(ids)-1):
        for k in range(len(angles)-1):
            p=rows[i][k];want=(-23-p[0],-23-p[1],1) if i<64 else (0,0,1)
            color='tile' if i==45 else 'coping' if 46<=i<64 else 'terracotta' if i==64 else 'sage'
            m.face([ids[i][k],ids[i][k+1],ids[i+1][k+1],ids[i+1][k]],color,'transition',True,want,
                   uv=[(widths[k],distance[i]),(widths[k+1],distance[i]),(widths[k+1],distance[i+1]),(widths[k],distance[i+1])])
    # A west 50cm deck flare joins the wider access deck without leaving a crack.
    m.poly([(-39,-23,h),(-38.5,-23,h),(-38.5,-22,h),(-39,-22,h)],'concrete_light',want=(0,0,1))


def bank(m,b):
    prof=L.bank_profile(b);axis=b['axis']; widths=wl(YS if axis=='x' else XS,b['w0'],b['w1'])
    ramp(m,prof,axis,widths,'concrete',P(axis,b['sign'],0,2),'paint')
    for w,sign in [(b['w0'],-1),(b['w1'],1)]:
        side_fan(m,axis,w,prof,(b['top'],0),'sage',P(axis,0,sign,0))


def terraces(m):
    for t in L.TERRACES:
        x0,x1,y0,y1,h=[t[k] for k in ('x0','x1','y0','y1','height')]
        flat(m,x0,x1,y0,y1,h,'concrete_light')
        # West side opens onto its return bank.
        access=next(b for b in L.BANKS if b['id']==t['id']+'_access')
        for y,side in [(y0,-1),(y1,1)]:
            if y not in (17.,21.) and (access['axis']!='y' or abs(y-access['top'])>1e-6):wall(m,'y',y,x0,x1,0,h,'terracotta',(0,side,0))
        for a,b in [(t['stair0']-.7,t['stair0']),(t['stair1'],t['stair1']+.7)]:
            wall(m,'x',x1,a,b,0,h,'terracotta',(1,0,0))
        if MOD.available():
            for item in L.terrace_modules(t):module(m,item)
        else:
            # Stand-ins on the modules' lines: the set's top tread continues the deck, its risers follow.
            ys=wl(YS,t['stair0'],t['stair1']);rise=h/t['steps']
            flat(m,x1,x1+t['tread'],t['stair0'],t['stair1'],h,'concrete',xl=[x1,x1+t['tread']],yl=ys)
            for y,side in [(t['stair0'],-1),(t['stair1'],1)]:wall(m,'y',y,x1,x1+t['tread'],0,h,'terracotta',(0,side,0))
            for k in range(t['steps']):
                x=x1+(k+1)*t['tread'];z=h-k*rise
                wall(m,'x',x,t['stair0'],t['stair1'],z-rise,z,'concrete',(1,0,0),wlines=ys,zsteps=1)
                if k<t['steps']-1:
                    flat(m,x,x+t['tread'],t['stair0'],t['stair1'],z-rise,'concrete',xl=[x,x+t['tread']],yl=ys)
                    for y,side in [(t['stair0'],-1),(t['stair1'],1)]:wall(m,'y',y,x,x+t['tread'],0,z-rise,'terracotta',(0,side,0))
            for item in L.terrace_modules(t):
                if item['finish']=='painted':module(m,item)
        prof=L.hubba_profile(t)
        for a in (t['stair0']-.7,t['stair1']):
            ramp(m,prof,'x',[a,a+.05,a+.65,a+.7],'concrete_light',(0,0,1),'concrete',lambda i,j:'steel' if j in (0,2) else 'concrete_light')
            for y,side in [(a,-1),(a+.7,1)]:
                side_fan(m,'x',y,prof,(prof[0][0],0),'terracotta',(0,side,0))
                # Close the base of the sloped side and the two end caps.
                m.poly([(prof[0][0],y,0),(prof[-1][0],y,0),(prof[-1][0],y,prof[-1][1])],'terracotta',want=(0,side,0))
            for x,z in [prof[0],prof[-1]]:wall(m,'x',x,a,a+.7,0,z,'terracotta',(-1 if x==prof[0][0] else 1,0,0))


def street_link(m):
    profiles=[]
    for name in ('four','seven'):
        back=L.bank_profile(next(b for b in L.BANKS if b['id']==name+'_back'))
        front=L.bank_profile(next(b for b in L.BANKS if b['id']==name+'_left'))
        profiles.append(sorted(back+front))
    xs=sorted(set([x for prof in profiles for x,z in prof]+list(np.linspace(L.footprints()['street_link'][0],L.footprints()['street_link'][1],113))))
    ys=np.linspace(17,21,33)
    rows=[]
    for y in ys:
        t=(y-17)/4;t=t*t*(3-2*t)
        low,high=[np.interp(xs,[p[0] for p in prof],[p[1] for p in prof],left=0,right=0) for prof in profiles]
        rows.append([(x,y,float(z)) for x,z in zip(xs,low*(1-t)+high*t)])
    m.grid(rows,'concrete_light','transition',True,(0,0,1))


def flow_table(m,f=None):
    f=f or L.FUNBOX; prof,_=L.funbox_profile(f)
    ys=sorted(set(wl(YS,f['y0'],f['y1'])+list(np.linspace(f['y0'],f['y1'],53))))
    def cross(y):
        t=min(1.,(y-f['y0'])/3.,(f['y1']-y)/3.)
        return t*t*(3-2*t)
    rows=[[(x,y,z*cross(y)) for y in ys] for x,z in prof]
    m.grid(rows,'sage','transition',True,(0,0,1))


def bowl(m):
    b=L.BOWL;r=b['radius'];h=r+b['vert'];rf=b['floor_radius'];cr=L.COPING_R
    rings=[L.bowl_ring(rf+r*math.sin(a),r*(1-math.cos(a))) for a in np.linspace(0,math.pi/2,46)]
    rings += [L.bowl_ring(rf+r,h-cr)]
    rings += [L.bowl_ring(rf+r+cr*(1-math.cos(a)),h-cr+cr*math.sin(a)) for a in np.linspace(math.pi/36,math.pi/2,18)]
    rings += [L.bowl_ring(rf+r+.6,h),L.bowl_ring(rf+r+b['deck'],h)]
    # S-curve wraps every outside face, giving multiple roll-ins and return lines.
    rings += [L.bowl_ring(rf+r+b['deck']+b['skirt']*u,h*(1-3*u*u+2*u*u*u)) for u in np.linspace(0,1,57)[1:]]
    ids=[[m.vert(p) for p in row] for row in rings];n=len(ids[0])
    profile=np.r_[0,np.cumsum(np.linalg.norm(np.diff(np.array(rings)[:,0],axis=0),axis=1))]
    lip=np.array(rings[45]); width=np.r_[0,np.cumsum(np.linalg.norm(np.diff(np.vstack([lip,lip[0]]),axis=0),axis=1))]
    width*=round(width[-1]/1.2)*1.2/width[-1]  # close the tiled perimeter on a whole repeat
    for j in range(len(ids)-1):
        for k in range(n):
            kn=(k+1)%n
            color='tile' if j==45 else 'coping' if 46<=j<64 else 'terracotta' if j==64 else 'concrete_light' if j==65 else 'sage'
            m.face([ids[j][k],ids[j][kn],ids[j+1][kn],ids[j+1][k]],color,'transition',True,(b['x']-rings[j][k][0],b['y']-rings[j][k][1],1) if j<64 else (0,0,1),
                   uv=[(width[k],profile[j]),(width[k+1],profile[j]),(width[k+1],profile[j+1]),(width[k],profile[j+1])])


def _finish(item, n):
    """(tag, colour) for one face of a module, from its finish and which way the face looks."""
    finish, colour = item['finish'], item['colour']
    if finish == 'painted': return 'rail', colour
    if finish == 'steel': return 'steel', 'steel'
    if finish == 'wood': return 'wood', 'timber'
    if finish == 'stairs':
        if n[2] > .7: return 'concrete', 'concrete_light'
        a = math.radians(item['yaw']); down = (math.sin(a), -math.cos(a))    # the downhill direction (local -y)
        if n[0]*down[0] + n[1]*down[1] > .7: return 'joint', 'concrete_dark'  # risers
        return 'wall', 'terracotta'
    return 'concrete', 'concrete_light' if n[2] > .7 else colour


def module(m, item):
    """An extracted obstacle (modules.py) in the pier's own surfaces: painted bars and handrails, two-tone stairs, steel
    angles on ledge lips. Without the fetched meshes, a stand-in on the same lines and footprint."""
    if not MOD.available():
        return stand_in(m, item)
    index = {}
    def vert(p):
        key = tuple(round(float(c), 5) for c in p)
        if key not in index: index[key] = m.vert(key)
        return index[key]
    smooth = item['finish'] == 'painted'
    joints = L.joints(item['id'])
    for tri in MOD.triangles(item):
        n = np.cross(tri[1]-tri[0], tri[2]-tri[0]); size = np.linalg.norm(n)
        if size < 1e-10: continue
        n = n / size
        if any(abs(n[:2] @ d) > .9 and np.all(np.abs((tri[:, :2] - at) @ d) < .002) for at, d in joints): continue
        tag, colour = _finish(item, n)
        m.face([vert(p) for p in tri], colour, tag, smooth, want=tuple(n))
    if item.get('grind') == 'edges' and item['finish'] == 'concrete' and item['part'] != 'bench':
        for pts, (sx, sy) in MOD.edges(item):
            (x0, y0, z), (x1, y1, _) = pts[0], pts[-1]
            if abs(sy) > .5: steel_side_band(m, 'x', y0, min(x0, x1), max(x0, x1), z, 1 if sy > 0 else -1)
            else: steel_side_band(m, 'y', x0, min(y0, y1), max(y0, y1), z, 1 if sx > 0 else -1)


def stand_in(m, item):
    """A procedural obstacle where the extracted mesh is missing: bars and handrails as a tube on their line with posts
    at the ends, solids as concrete boxes on their footprint."""
    if item['finish'] in ('painted', 'steel') and 'line' in MOD.part(item['part']):
        width = MOD.part(item['part'])['bounds'][1][0] - MOD.part(item['part'])['bounds'][0][0]
        r = min(.045, width/2); colour = item['colour'] if item['finish'] == 'painted' else 'steel'
        tag = 'rail' if item['finish'] == 'painted' else 'steel'
        pts = [(x, y, z-r) for x, y, z in MOD.line(item)]
        # A line of several pieces is one tube, drawn with its first piece: no caps buried at the joints.
        pieces = next((g['pieces'] for g in L.GRIND_LINES if item['id'] in g['pieces'] and len(g['pieces']) > 1), None)
        if pieces is None:
            m.tube(pts, r, colour, tag, sides=10)
        elif pieces[0] == item['id']:
            m.tube([(x, y, z-r) for x, y, z in L.grind_line(pieces)], r, colour, tag, sides=10)
        for x, y, z in (pts[0], pts[-1]):
            m.box((x-r, y-r, 0), (x+r, y+r, z), colour, tag)
        return
    x0, x1, y0, y1 = MOD.footprint(item)
    ledge_box(m, x0, x1, y0, y1, MOD.height(item), steel_y=item.get('grind') == 'edges')


def park_features():
    m=MeshData('SM_SkateParkFeatures')
    for q in L.QUARTERS:quarter(m,q)
    for b in L.BANKS:bank(m,b)
    terraces(m);street_link(m);flow_table(m);bowl(m);mini_return(m)
    for hip in L.HIPS:flow_table(m,hip)
    for p in L.PADS:ledge_box(m,p['x0'],p['x1'],p['y0'],p['y1'],p['height'],side_color='sage',steel_x=True)
    for item in L.MODULES:module(m,item)
    f=L.CURVE_BAR
    m.tube(L.arc_points(f,z=f['height']-L.BAR_R),L.BAR_R,'red','rail',sides=10)
    for x,y,z in L.arc_points(f,z=f['height']-L.BAR_R)[::20]:
        m.box((x-.025,y-.025,0),(x+.025,y+.025,z-L.BAR_R),'red','rail')
    f=L.CURVE_LEDGE;r=f['radius'];w=f['width'];h=f['height']
    rings=[L.arc_points(f,radius=rr) for rr in (r-w/2,r-w/2+.05,r+w/2-.05,r+w/2)]
    m.grid(rings,'concrete_light','concrete',False,(0,0,1),lambda i,j:'steel' if i in (0,2) else 'concrete_light')
    for side,ring in [(-1,rings[0]),(1,rings[-1])]:
        for p,q in zip(ring,ring[1:]):
            m.poly([(p[0],p[1],0),(q[0],q[1],0),q,p],'concrete_dark',want=(side*(p[0]-f['x']),side*(p[1]-f['y']),0))
    for k in (0,-1):
        p,q=rings[0][k],rings[-1][k]
        m.poly([(p[0],p[1],0),(q[0],q[1],0),q,p],'concrete_dark')
    return m


def gardens():
    """A planted waterfront promenade outside the approaches and landings."""
    m = MeshData('SM_SkateParkFurniture'); plants = MeshData('SM_SkateParkPlanting')
    rng = np.random.default_rng(184)
    gardens = [(-72, 62, 10), (-49, 62, 8), (-25, 62, 8), (30, 62, 8), (62, 62, 12),
               (-68, -62, 12), (-43, -62, 8), (2, -62, 10), (40, -62, 12),
               (79, -17, 6), (79, 5, 6), (-80, -38, 6)]
    for cx, cy, span in gardens:
        ring = []
        for end, angle in [(span / 2 - 1, -90), (-span / 2 + 1, 90)]:
            for k in range(25):
                t = math.radians(angle + k * 180 / 24)
                ring.append((cx + end + math.cos(t), cy + math.sin(t)))
        outer = [(x, y, .52) for x, y in ring]
        inner = [(cx + (x - cx) * .88, cy + (y - cy) * .72, .52) for x, y in ring]
        for k, p in enumerate(outer):
            j = (k + 1) % len(outer); q = outer[j]
            m.poly([p, q, inner[j], inner[k]], 'concrete_light', want=(0, 0, 1))
            m.poly([(p[0], p[1], 0), (q[0], q[1], 0), q, p], 'concrete_dark', want=(p[0]-cx, p[1]-cy, 0))
        m.fan_polygon([(x, y, .48) for x, y, z in inner], (cx, cy, .48), 'soil', 'soil', (0, 0, 1))
        # Slatted seats face the skating, with planting behind the seat.
        seat_y = cy - 1.45 if cy > 0 else cy + 1.45
        for j in range(5):
            m.box((cx-span/2+1.5, seat_y-.45+j*.18, .43), (cx+span/2-1.5, seat_y-.30+j*.18, .51), 'timber', 'wood')
        for x in (cx-span/2+2, cx+span/2-2):
            m.box((x-.08, seat_y-.42, 0), (x+.08, seat_y+.42, .43), 'steel', 'steel')
        for _ in range(90):
            xx = cx + rng.uniform(-span/2+.9, span/2-.9); yy = cy + rng.uniform(-.55, .55)
            hh = rng.uniform(.3, 1.15); t = rng.uniform(0, math.tau)
            for off in (0, math.pi/2):
                ux, uy = math.cos(t+off), math.sin(t+off)
                plants.poly([(xx-uy*.045, yy+ux*.045, .48), (xx+uy*.045, yy-ux*.045, .48),
                             (xx+math.cos(t)*.2, yy+math.sin(t)*.2, .48+hh)],
                            'grass_light' if hh > .8 else 'grass', 'leaves')
                plants.faces.append(plants.faces[-1][::-1]); plants.colors.append(plants.colors[-1])
                plants.smooth.append(False); plants.tags.append('leaves')
    # Cedar pavilion sits on the southern waterfront, clear of the sunset line.
    for x in (20., 28., 36.):
        for y in (-64., -58.): m.box((x-.14, y-.14, 0), (x+.14, y+.14, 3.6), 'timber', 'wood')
    for y in (-64., -58.): m.box((19.5, y-.14, 3.45), (36.5, y+.14, 3.75), 'timber', 'wood')
    for x in np.arange(19.5, 36.6, .38):
        m.box((x-.08, -64.4, 3.75), (x+.08, -57.6, 3.88), 'timber', 'wood')
    # A large original wave print gives the north street its identity.
    m.box((35., 64., 0), (44.4, 64.3, 6.55), 'concrete_dark')
    m.poly([(35.2, 63.99, .22), (44.2, 63.99, .22), (44.2, 63.99, 6.22), (35.2, 63.99, 6.22)],
           'concrete_light', 'mural', want=(0, -1, 0))
    return m, plants

def decals():
    """Faded floor paint: the Yorimichi sun and three wave strokes (25 mm above the deck, no collision)."""
    m = MeshData('SM_SkateParkDecals'); z = L.DECAL_Z
    path=[(-76,45),(-40,60),(4,60),(70,53),(77,12),(60,-20),(53,-55),(10,-59),(-37,-58),(-76,-42),(-79,-4)]
    points=[]
    for i,p1 in enumerate(path):
        p0=np.array(path[(i-1)%len(path)]);p1=np.array(p1);p2=np.array(path[(i+1)%len(path)]);p3=np.array(path[(i+2)%len(path)])
        for t in np.linspace(0,1,33)[:-1]:
            points.append(.5*((2*p1)+(-p0+p2)*t+(2*p0-5*p1+4*p2-p3)*t*t+(-p0+3*p1-3*p2+p3)*t*t*t))
    rows=[]
    for i,p in enumerate(points):
        d=points[(i+1)%len(points)]-points[(i-1)%len(points)];d=d/np.linalg.norm(d);normal=np.array([-d[1],d[0]])
        rows.append([(* (p+normal*w),z) for w in (-.85,.85)])
    rows.append(rows[0]);m.grid(rows,'terracotta','decal',False,(0,0,1))
    sun = L.FLOOR_SUN; n = 48
    red = (0.42, 0.075, 0.048); ink = (0.055, 0.10, 0.18)
    radii = list(np.linspace(sun['r'] / 6, sun['r'], 6))
    rings = [[(sun['x'] + r * math.cos(t), sun['y'] + r * math.sin(t), z) for t in 2 * math.pi * np.arange(n) / n] for r in radii]
    c = m.vert((sun['x'], sun['y'], z)); ids = [[m.vert(p) for p in ring] for ring in rings]
    for k in range(n):
        m.face([c, ids[0][k], ids[0][(k + 1) % n]], red, 'decal', want=(0, 0, 1))
        for a in range(len(radii) - 1):
            m.face([ids[a][k], ids[a + 1][k], ids[a + 1][(k + 1) % n], ids[a][(k + 1) % n]], red, 'decal', want=(0, 0, 1))
    for x0, x1, y0 in L.FLOOR_WAVES:
        xs = np.linspace(x0, x1, 57); w = 0.16
        cy = y0 + 0.32 * np.sin(2 * math.pi * (xs - x0) / 2.35)
        dy = np.gradient(cy, xs); nrm = np.column_stack([-dy, np.ones_like(dy)]); nrm /= np.linalg.norm(nrm, axis=1)[:, None]
        left = [m.vert((x - nx * w, y - ny * w, z)) for x, y, (nx, ny) in zip(xs, cy, nrm)]
        right = [m.vert((x + nx * w, y + ny * w, z)) for x, y, (nx, ny) in zip(xs, cy, nrm)]
        for k in range(len(xs) - 1):
            m.face([left[k], left[k + 1], right[k + 1], right[k]], ink, 'decal', want=(0, 0, 1))
    return m


# ----------------------------------------------------------------------------- pier
def pier():
    m = MeshData('SM_SkatePier')
    holes = list(L.footprints().values())
    V = {}
    def vid(i, j):
        if (i, j) not in V: V[(i, j)] = m.vert((XS[i], YS[j], 0.0))
        return V[(i, j)]
    for i in range(len(XS) - 1):
        cx = (XS[i] + XS[i + 1]) / 2
        for j in range(len(YS) - 1):
            cy = (YS[j] + YS[j + 1]) / 2
            if any(x0 < cx < x1 and y0 < cy < y1 for x0, x1, y0, y1 in holes): continue
            joint = any(abs(cx - j) < L.JOINT_W / 2 for j in L.JOINTS_X) or any(abs(cy - j) < L.JOINT_W / 2 for j in L.JOINTS_Y)
            m.face([vid(i, j), vid(i + 1, j), vid(i + 1, j + 1), vid(i, j + 1)], 'joint' if joint else 'concrete', 'deck', False, want=(0, 0, 1))
    # edge fascia (downstand beam) and the slab underside
    hx, hy = L.HALF_X, L.HALF_Y; fz = -0.70; bw = 0.30
    for axis, u, lines, want in (('y', -hy, XS, (0, -1, 0)), ('y', hy, XS, (0, 1, 0)), ('x', -hx, YS, (-1, 0, 0)), ('x', hx, YS, (1, 0, 0))):
        wall(m, axis, u, lines[0], lines[-1], fz, 0.0, 'concrete_dark', want, tag='wall', wlines=list(lines), zsteps=1)
    for axis, u, a, b_, want in (('y', -hy + bw, -hx + bw, hx - bw, (0, 1, 0)), ('y', hy - bw, -hx + bw, hx - bw, (0, -1, 0)),
                                 ('x', -hx + bw, -hy + bw, hy - bw, (1, 0, 0)), ('x', hx - bw, -hy + bw, hy - bw, (-1, 0, 0))):
        wall(m, axis, u, a, b_, fz, -L.SLAB, 'underside', want, tag='underside', zsteps=1)
    for x0, x1, y0, y1 in ((-hx, hx, -hy, -hy + bw), (-hx, hx, hy - bw, hy), (-hx, -hx + bw, -hy + bw, hy - bw), (hx - bw, hx, -hy + bw, hy - bw)):
        m.poly([(x0, y0, fz), (x0, y1, fz), (x1, y1, fz), (x1, y0, fz)], 'underside', 'underside', want=(0, 0, -1))
    ux = np.linspace(-hx + bw, hx - bw, 21); uy = np.linspace(-hy + bw, hy - bw, 13)
    m.grid([[(x, y, -L.SLAB) for y in uy] for x in ux], 'underside', 'underside', False, (0, 0, -1))
    # perimeter railing (blocks, not grindable) with the entrance gap; the platform and the
    # south bank carry their own railings where they meet the edge
    e = hx - L.RAIL_INSET; f = hy - L.RAIL_INSET; gap = (L.ENTRANCE_X - 2.5, L.ENTRANCE_X + 2.5)
    runs = [((-e, f), (gap[0], f)), ((gap[1], f), (e, f)), ((e, f), (e, -f)), ((-e, f), (-e, -f)),
            ((-e, -f), (e, -f))]
    for a, b_ in runs:
        railing(m, [(a[0], a[1], 0.0), (b_[0], b_[1], 0.0)], L.RAILING_H)
    for x, y in L.LAMPS:
        lamp(m, x, y)
    return m


def lamp(m, x, y):
    m.box((x - .16, y - .16, -0.02), (x + .16, y + .16, 0.28), 'concrete_dark', 'concrete')
    m.lathe((x, y, 0.28), [(0, 0.075), (4.25, 0.06), (4.25, 0.0)], 'pole', 'pole', sides=8)
    m.box((x - .19, y - .19, 4.22), (x + .19, y + .19, 4.28), 'lamp_cap', 'pole', bottom=True)
    m.box((x - .16, y - .16, 4.28), (x + .16, y + .16, 4.72), 'lamp', 'lamp')
    m.lathe((x, y, 4.72), [(0, 0.0), (0, 0.26), (0.18, 0.05), (0.18, 0.0)], 'lamp_cap', 'pole', sides=4)


def pilings(h_world):
    import sys
    sys.path.insert(0, str(L.JAPAN))
    from village.layout import sample
    m = MeshData('SM_SkatePierPilings')
    ox, oy, oz = L.ORIGIN
    xs = np.linspace(-L.HALF_X+4, L.HALF_X-4, 19); ys = np.linspace(-L.HALF_Y+4, L.HALF_Y-4, 15)
    cap_top, cap_bot = -L.SLAB, -1.0
    for y in ys:
        m.box((-L.HALF_X + .3, y - .3, cap_bot), (L.HALF_X - .3, y + .3, cap_top), 'underside', 'pile', bottom=True)
        for x in xs:
            bed = float(sample(h_world, ox + x, oy + y)) - oz
            prof = [(bed - 0.6 - cap_bot, 0.30), (cap_top - 0.02 - cap_bot, 0.30), (cap_top - 0.02 - cap_bot, 0.0)]
            base = len(m.faces)
            m.lathe((x, y, cap_bot), [(bed - 0.6 - cap_bot, 0.0)] + prof, 'pile', 'pile', sides=10)
            # wet / algae bands by world height
            for fi in range(base, len(m.faces)):
                cols = []
                for vi in m.faces[fi]:
                    wz = m.verts[vi][2] + oz
                    c = np.array(PAL['pile'])
                    if wz < 0.9: c = c * 0.5 + np.array(PAL['algae']) * 0.5 if wz > -0.4 else np.array(PAL['pile_wet'])
                    cols.append(tuple(c))
                m.colors[fi] = cols
    return m


# ----------------------------------------------------------------------------- path
def path_railing(m, run, height=1.1, every=2.0):
    """Railing following a polyline of base points (x, y, z on the path surface)."""
    run = np.array(run, float)
    d = np.r_[0, np.cumsum(np.linalg.norm(np.diff(run[:, :2], axis=0), axis=1))]
    n = max(1, int(math.ceil(d[-1] / every)))
    for t in np.linspace(0, d[-1], n + 1):
        p = np.array([np.interp(t, d, run[:, i]) for i in range(3)])
        m.box((p[0] - .03, p[1] - .03, p[2] - .03), (p[0] + .03, p[1] + .03, p[2] + height - .028), 'railing', 'railing')
    keep = [0] + [i for i in range(1, len(run) - 1) if int(d[i] // 1.0) != int(d[i - 1] // 1.0)] + [len(run) - 1]
    m.tube([run[i] + (0, 0, height - .028) for i in keep], 0.028, 'railing', 'railing', sides=8)
    m.tube([run[i] + (0, 0, height * .5) for i in keep], 0.02, 'railing', 'railing', sides=6)


def path(pl, h_world):
    """Path in park-local metres: level cross-sections, dark joints every 3 m, edge bands and a
    skirt down past the ground on both sides so it never floats or sinks out of sight."""
    import sys
    sys.path.insert(0, str(L.JAPAN))
    from village.layout import upper_surface
    m = MeshData('SM_SkatePath')
    ox, oy, oz = L.ORIGIN
    Pw, s, n, z = pl['P'], pl['s'], pl['n'], pl['z']
    # sample positions: the profile samples plus 5 cm joint strips every 3 m
    joints = [j for j in np.arange(3.0, s[-1] - 1.0, 3.0)]
    ss = np.unique(np.r_[s, joints, np.array(joints) + 0.05])
    Px = np.interp(ss, s, Pw[:, 0]); Py = np.interp(ss, s, Pw[:, 1]); Z = np.interp(ss, s, z)
    nx = np.interp(ss, s, n[:, 0]); ny = np.interp(ss, s, n[:, 1]); nn = np.hypot(nx, ny); nx /= nn; ny /= nn
    road = np.array(pl['road'])
    def road_z(x, y):
        d = np.hypot(road[:, 0] - x, road[:, 1] - y); i = int(np.argmin(d))
        a, b = (i - 1, i) if i > 0 and (i == len(road) - 1 or d[i - 1] < d[i + 1]) else (i, i + 1)
        A, B = road[a], road[b]; t = np.clip(((x - A[0]) * (B[0] - A[0]) + (y - A[1]) * (B[1] - A[1])) / ((B[0] - A[0]) ** 2 + (B[1] - A[1]) ** 2), 0, 1)
        return float(A[2] + (B[2] - A[2]) * t + 0.06)
    rows = []
    for k in range(len(ss)):
        row = []
        for o in L.PATH_OFFSETS:
            x = Px[k] + nx[k] * o; y = Py[k] + ny[k] * o
            zz = road_z(x, y) if k == 0 else Z[k]
            row.append((x - ox, y - oy, zz - oz))
        rows.append(row)
    jset = set(np.searchsorted(ss, joints))
    edge = {0, len(L.PATH_OFFSETS) - 2}
    def col(i, j):
        if i in jset: return 'joint'
        return 'concrete_dark' if j in edge else 'concrete'
    m.grid(rows, 'concrete', 'path', True, (0, 0, 1), color_fn=col)
    # skirts
    for side, j in ((-1, 0), (1, len(L.PATH_OFFSETS) - 1)):
        top = [rows[k][j] for k in range(len(ss))]
        bot = []
        for (x, y, zz) in top:
            g = float(upper_surface(h_world, x + ox, y + oy)) - oz
            # the terrain may be a little lower between samples: reach well past it
            lowest = min(g, *(float(upper_surface(h_world, x + ox + dx, y + oy + dy)) - oz for dx, dy in ((.7, 0), (-.7, 0), (0, .7), (0, -.7))))
            bot.append((x, y, min(zz - 0.25, lowest - 0.45)))
        ids_t = [m.vert(p) for p in top]; ids_b = [m.vert(p) for p in bot]
        for k in range(len(ss) - 1):
            want = (nx[k] * side, ny[k] * side, 0)
            zt = (top[k][2] + top[k + 1][2]) / 2; zb = (bot[k][2] + bot[k + 1][2]) / 2
            c_top = PAL['skirt']; c_bot = tuple(c * 0.55 for c in PAL['skirt'])
            m.face([ids_b[k], ids_b[k + 1], ids_t[k + 1], ids_t[k]], [c_bot, c_bot, c_top, c_top], 'skirt', False, want=want)
        # guard railing wherever this side stands more than 1.2 m above the ground
        high = np.array([t[2] - g for t, g in zip(top, [float(upper_surface(h_world, x + ox, y + oy)) - oz for x, y, _ in top])]) > 1.2
        k = 0
        while k < len(ss):
            if not high[k]: k += 1; continue
            e = k
            while e + 1 < len(ss) and high[e + 1]: e += 1
            a, b = max(0, k - 4), min(len(ss) - 1, e + 4)
            if ss[b] - ss[a] > 4.0:
                inset = 0.15
                run = [(top[q][0] - nx[q] * side * inset, top[q][1] - ny[q] * side * inset, top[q][2]) for q in range(a, b + 1)]
                path_railing(m, run)
            k = e + 1
    # start cap (under the road edge) and end cap (inside the pier edge beam)
    for k, sgn in ((0, -1), (len(ss) - 1, 1)):
        a = rows[k][0]; b = rows[k][-1]
        ga = min(a[2] - 0.6, float(upper_surface(h_world, a[0] + ox, a[1] + oy)) - oz - 0.45)
        gb = min(b[2] - 0.6, float(upper_surface(h_world, b[0] + ox, b[1] + oy)) - oz - 0.45)
        t = (Px[k] - Px[k - sgn] if k else Px[1] - Px[0], Py[k] - Py[k - sgn] if k else Py[1] - Py[0])
        m.poly([a, b, (b[0], b[1], gb), (a[0], a[1], ga)], 'skirt', 'skirt', want=(t[0] * sgn, t[1] * sgn, 0))
    return m, ss, rows
