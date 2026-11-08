"""Geometry adapters for resolved v4 JSON modules; no authored layout lives here."""
import math

import numpy as np

from . import bowls, dsl, ground, junctions, prado, primitives as P, solids
from .curves import Curve, Line


class GeometryError(ValueError):
    """A resolved design cannot be represented without changing its geometry."""


def finite(value, name, *, positive=False):
    value = float(value)
    if not math.isfinite(value) or (positive and value <= 0):
        raise GeometryError(f'{name} must be finite' + (' and positive' if positive else ''))
    return value


def side(spec):
    """Translate rider L/R wall metadata to primitive side metadata.

    The design's rider left is the primitive path's negative normal.
    """
    kind = spec['type']
    if kind == 'none':
        return P.Side('flush')
    if kind != 'bowl':
        raise GeometryError(f'unsupported v4 wall type {kind!r}; a vert/bank needs an explicit module')
    fade = spec.get('fade')
    return P.Side('bowl', height=finite(spec['h'], 'wall.h', positive=True),
                  radius=finite(spec['R'], 'wall.R', positive=True),
                  width=finite(spec.get('cap', P.BOWL_CAP), 'wall.cap', positive=True),
                  fade=None if fade is None else tuple(fade), outer=spec.get('outer'))


class ResolvedCurve(Curve):
    """A smooth interpolant through the resolver's plan samples and headings."""
    def __init__(self, geo):
        self.s = np.asarray(geo['s'], 'f8')
        points = np.column_stack([geo['x'], geo['z']])
        heading = np.radians(geo['h'])
        if (self.s.ndim != 1 or len(self.s) < 2 or self.s[0] != 0
                or np.any(np.diff(self.s) <= 0) or not np.isfinite(points).all()
                or not np.isfinite(heading).all()):
            raise GeometryError('resolved path needs finite, strictly increasing station samples')
        self.length = float(self.s[-1])
        self.points = points
        self.directions = np.c_[np.cos(heading), np.sin(heading)]
        probes = np.unique(np.r_[self.s, (self.s[:-1] + self.s[1:]) / 2])
        speeds = np.linalg.norm(self._eval(probes, 1), axis=1)
        if np.max(np.abs(speeds - 1)) > .02:
            raise GeometryError('resolved path is not an arc-length path within 2%; resolve a smoother plan')

    def _eval(self, t, order):
        t = np.atleast_1d(np.asarray(t, 'f8'))
        i = np.clip(np.searchsorted(self.s, t, side='right')-1, 0, len(self.s)-2)
        length = self.s[i+1]-self.s[i]
        u = ((t-self.s[i])/length)[:,None]
        a,b = self.points[i],self.points[i+1]
        v,w = self.directions[i]*length[:,None],self.directions[i+1]*length[:,None]
        if order == 0:
            return (2*u**3-3*u**2+1)*a+(u**3-2*u**2+u)*v+(-2*u**3+3*u**2)*b+(u**3-u**2)*w
        if order == 1:
            return ((6*u*u-6*u)*a+(3*u*u-4*u+1)*v+(-6*u*u+6*u)*b+(3*u*u-2*u)*w)/length[:,None]
        return ((12*u-6)*a+(6*u-4)*v+(-12*u+6)*b+(6*u-2)*w)/length[:,None]**2

    def point(self, t):
        return self._eval(t, 0)

    def tangent(self, t):
        d = self._eval(t, 1)
        return d / np.linalg.norm(d, axis=1, keepdims=True)

    def curvature(self, t):
        t = np.atleast_1d(t)
        a, b = self._eval(t, 1), self._eval(t, 2)
        return (a[:, 0] * b[:, 1] - a[:, 1] * b[:, 0]) / np.linalg.norm(a, axis=1) ** 3

    def breaks(self):
        return self.s.copy()


def plan_curve(geo):
    h = np.asarray(geo['h'], 'f8')
    points = np.c_[geo['x'], geo['z']]
    if np.ptp(h) < 1e-8:
        path = Line(points[0], points[-1])
        if abs(path.length - float(geo['L'])) > 1e-6:
            raise GeometryError(f"{geo['id']}: straight plan length disagrees with resolved profile")
        return path
    return ResolvedCurve(geo)


def profile(y, degrees, parts):
    if not parts:
        raise GeometryError('grounded profile must contain explicit parts')
    for p in parts:
        if p[0] not in ('line', 'arc') or not math.isfinite(float(p[1])) or float(p[1]) < 0:
            raise GeometryError(f'invalid resolved profile part {p!r}')
        if p[0] == 'arc' and (float(p[1]) <= 0 or not math.isfinite(float(p[2]))):
            raise GeometryError(f'invalid resolved circular profile {p!r}')
    return P.from_additions(finite(y, 'profile.y'), finite(degrees, 'profile.angle'), parts)


def module_ports(built, geo):
    """Read actual complete riding-section boundary chains, including caps."""
    result = {}
    for label in ('start', 'end'):
        pose = geo[label]
        heading = junctions.direction(pose['h'])
        result[label] = junctions.boundary_row(built.mesh, np.array([pose['x'], pose['z']]), heading,
                                               level=False)
    return result


def build_module(segment, geo, terrain):
    """@cc [owner:fontanierh,label:correctness] v4-real-open-gap
    A gap MUST retain separate launch and receiver solids with no riding sheet
    over its open interval. Unsupported structural modules MUST fail closed;
    primitive fold, thickness and topology exceptions MUST propagate.
    """
    kind, name = geo['kind'], geo['id']
    if kind == 'half_bowl':
        raise GeometryError(f'{name}: half-bowl requires its explicit outer vert profile')
    if kind == 'elbow':
        return build_elbow(segment,geo,terrain)
    if kind not in ('straight', 'shared', 'turn', 'half_bowl', 'contour', 'link', 'bowl_entry', 'rollin', 'gap'):
        raise GeometryError(f'{name}: unsupported structural module {kind!r}')
    if segment.get('support', 'earth') not in ('earth', 'tower'):
        raise GeometryError(f'{name}: unsupported support; explicit piers/undersides required')
    path = plan_curve(geo)
    # Design L/R use the opposite convention from primitives' +normal left.
    left, right = side(geo['wr']), side(geo['wl'])
    if kind == 'rollin' and segment.get('support') == 'tower':
        from dataclasses import replace
        fade=finite(segment.get('tower_crest_fade_m',10.),'tower_crest_fade_m',positive=True)
        left=replace(left,fade=(fade,(left.fade or (0.,0.))[1])) if left.kind=='bowl' else left
        right=replace(right,fade=(fade,(right.fade or (0.,0.))[1])) if right.kind=='bowl' else right
    if kind == 'gap':
        required = ('launch_parts', 'landing_parts', 'launch_y', 'landing_y', 'launch_deg', 'landing_deg')
        missing = [key for key in required if key not in geo]
        if missing:
            raise GeometryError(f'{name}: missing exact gap profile fields {missing}')
        launch = profile(geo['launch_y'], geo['launch_deg'], geo['launch_parts'])
        landing = profile(geo['landing_y'], geo['landing_deg'], geo['landing_parts'])
        intervals = geo['air_intervals']
        if len(intervals) != 1:
            raise GeometryError(f'{name}: a gap must have exactly one open interval')
        lip, knuckle = map(float, intervals[0])
        if not 0 < lip < knuckle < path.length:
            raise GeometryError(f'{name}: invalid open interval')
        if abs(float(launch.end[0]) - lip) > 1e-6 or abs(knuckle + float(landing.end[0]) - path.length) > 1e-6:
            raise GeometryError(f'{name}: grounded gap profiles disagree with exact open interval')
        built=P.jump_line(path, launch, landing, knuckle-lip, geo['W'], left=left, right=right,
                          ground=terrain, feature=name, land_width=segment.get('land_width', geo['W']), on_ground=True)
        return gap_rail(built,segment,geo,path,terrain)
    prof = profile(geo['start']['y'], geo['start']['a'], geo['profile_parts'])
    if abs(float(prof.end[0]) - path.length) > 1e-6 or abs(float(prof.end[1]) - geo['end']['y']) > 1e-6:
        raise GeometryError(f'{name}: exact profile endpoints disagree with resolved layout')
    return P.ramp(path, prof, geo['W'], left=left, right=right, ground=terrain, feature=name,
                  on_ground=True)


def build_ground(spec, built, terrain):
    """Ground owns the complement of actual primitive foot loops."""
    if 'outline' not in spec:
        raise GeometryError('ground geometry requires an explicit native xyz outline')
    options = dict(spec.get('geometry', {}))
    allowed = {'skirt', 'max_edge', 'grade', 'hmin', 'raster', 'blend', 'smooth', 'relax', 'max_slope', 'apron'}
    if set(options)-allowed:
        raise GeometryError(f'unknown ground geometry settings {sorted(set(options)-allowed)}')
    return ground.ground(np.asarray(spec['outline'], 'f8'), holes=built.foot,
                         guide=np.asarray(spec.get('guide', []), 'f8').reshape(-1,3),
                         controls=np.asarray(spec.get('controls', []), 'f8').reshape(-1,3), **options)


class DesignBowlPlan(bowls.Plan):
    """Parameterized Prado clover/pockets with the JSON's exact plan and floors."""
    def __init__(self, spec, ports=()):
        self.spec = spec
        self.centre = np.asarray(spec['centre'], 'f8')
        self.scale = np.asarray(spec['scale'], 'f8')
        if self.scale.shape != (2,) or (self.scale <= 0).any():
            raise GeometryError('bowl.scale must contain two positive dimensions')
        a = math.radians(finite(spec['axis_deg'], 'bowl.axis_deg'))
        self.rotation = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
        self.deep, self.shallow = float(spec['floor_y']), float(spec['shallow_y'])
        if abs(float(spec['wall']['deck'])-bowls.DECK)>1e-9:
            raise GeometryError('bowl.wall.deck differs from the existing compiler deck width; parameterized deck offset is required')
        wall = spec['wall']; rim = self.deep + float(wall['h']); radius = float(wall['R'])
        if self.shallow < self.deep or self.shallow >= rim:
            raise GeometryError('bowl shallow floor must lie between deep floor and rim')
        # Radius and vertical band are derived from the declared common wall envelope.
        anchors = []
        for floor in sorted(set([self.shallow, self.deep]), reverse=True):
            h = rim-floor
            anchors.append((h, radius, max(0.,h-radius)))
        extents = []
        for item in spec['lobes']:
            c, r = np.asarray(item['c']), finite(item['r'], 'lobe.r', positive=True)
            extents += [c-r, c+r]
        for item in spec.get('pockets', []):
            r = finite(item['r'], 'pocket.r', positive=True)
            extents += [np.asarray(item[k])+v*r for k in ('a','b') for v in (-1,1)]
        if not extents:
            raise GeometryError('bowl needs at least one explicit lobe')
        extents = np.asarray(extents)
        pad = max(float(spec['lobe_blend']), float(spec['pocket_blend'])) + radius + float(wall['deck'])
        lo, hi = extents.min(0)-pad, extents.max(0)+pad
        box = self.native(np.array([[lo[0],lo[1]],[hi[0],lo[1]],[hi[0],hi[1]],[lo[0],hi[1]]]))
        super().__init__(rim, {'crater_bowl': self.deep}, anchors,
                         {'crater_bowl': self.shape}, [], list(ports), box, box)

    def wall(self, height):
        # A shallow floor truncates the same declared circular transition;
        # it must not silently shrink the JSON radius to fit its height.
        radius = float(self.spec['wall']['R'])
        return radius, max(0.,float(height)-radius)

    def local(self, q):
        return (np.atleast_2d(np.asarray(q,'f8'))-self.centre) @ self.rotation / self.scale

    def native(self, q):
        return (np.atleast_2d(q)*self.scale) @ self.rotation.T+self.centre

    def shape(self, q):
        q = self.local(q); d = None
        for lb in self.spec['lobes']:
            v = np.linalg.norm(q-np.asarray(lb['c']),axis=1)-float(lb['r'])
            d = v if d is None else bowls.smin(d,v,float(self.spec['lobe_blend']))
        for p in self.spec.get('pockets',[]):
            d = bowls.smin(d,prado._capsule(q,p['a'],p['b'],p['r']),float(self.spec['pocket_blend']))
        return d * self.scale.min()

    def floor(self, q):
        length = float(self.spec.get('floor_blend_m',18.))
        return self.deep+(self.shallow-self.deep)*bowls.smootherstep(self.local(q)[:,0]/length)


def build_bowl(spec, ports=()):
    plan = DesignBowlPlan(spec, ports)
    inserts = []
    for i,item in enumerate(spec.get('spines',[])):
        a,b = np.asarray(item['a']),np.asarray(item['b'])
        endpoints = plan.native([a,b]); floor = plan.floor(endpoints)
        if np.ptp(floor) > 1e-6:
            raise GeometryError(f'bowl spine {i} crosses a changing floor; explicit varying spine geometry required')
        h = plan.rim-float(floor[0]); r = min(float(spec['wall']['R']),h)
        inserts.append(prado.spine(plan,a,b,floor=float(floor[0]),height=h,radius=r,
                                   feature=f'crater_bowl.spine{i}'))
    built = bowls.compile_plan(plan,on_ground=True,inserts=inserts)
    built.checks.extend(c for item in inserts for c in item.checks)
    built.checks.append(dict(kind='v4_bowl_source',parameters=spec))
    return built


def tower_deck(spec, rollins, terrain):
    """Build a deck only when every actual crest row belongs to its perimeter."""
    centre = np.asarray(spec['centre'],'f8'); size = np.asarray(spec['size'],'f8')
    a = math.radians(float(spec['heading'])); u = np.array([math.cos(a),math.sin(a)]); n=np.array([-u[1],u[0]])
    polygon = np.asarray(spec.get('outline', [centre+i*size[0]/2*u+j*size[1]/2*n
                                             for i,j in ((-1,-1),(1,-1),(1,1),(-1,1))]),'f8')
    y = float(spec['deck_y']); corners=np.c_[polygon[:,0],np.full(len(polygon),y),polygon[:,1]]
    rows=[]
    for built,geo in rollins:
        pose=geo['start']; row=junctions.boundary_row(built.mesh,np.array([pose['x'],pose['z']]),
                                                     junctions.direction(pose['h']),level=True)
        if np.max(np.abs(row[:,1]-y))>1e-6:
            raise GeometryError('tower roll-in crest must be on its declared deck')
        # A rectangle may not silently expand or lose a piece to fit an interior crest.
        for p in row[:,[0,2]]:
            delta=np.roll(polygon,-1,axis=0)-polygon
            t=np.clip(((p-polygon)*delta).sum(1)/(delta*delta).sum(1),0,1)
            if np.linalg.norm(polygon+t[:,None]*delta-p,axis=1).min()>1e-6:
                raise GeometryError(f"{geo['id']}: crest is not on tower outline; supply a compatible JSON tower.outline")
        rows.append(row)
    loop=junctions._hull_with_samples([corners]+rows)
    def is_portal(a,b):
        for row in rows:
            d=row[-1]-row[0]; length2=float(d@d)
            t=(np.array([a,b])-row[0])@d/length2
            residual=np.array([a,b])-(row[0]+t[:,None]*d)
            if np.linalg.norm(residual,axis=1).max()<1e-7 and t.min()>=-1e-8 and t.max()<=1+1e-8:
                return True
        return False
    # The deck and side walls must use the same perimeter stations. Subdividing
    # a side independently leaves T-junctions on every long deck edge.
    dense=[]
    for a,b in zip(loop,np.roll(loop,-1,axis=0),strict=True):
        count=1 if is_portal(a,b) else max(1,math.ceil(np.linalg.norm(b-a)/P.WALL_ROW))
        dense.extend(a+np.arange(count)[:,None]/count*(b-a))
    loop=np.asarray(dense)
    top=solids.polygon(loop,outward=[0,1,0],feature='tower',role=dsl.RIDING)
    floor=np.asarray(terrain(loop[:,0],loop[:,2]),'f8')
    if (floor>=y).any():
        raise GeometryError('tower concrete core must stand above the declared terrain')
    # A common vertical parameter also preserves both sides of each corner on
    # sloping terrain, where neighbouring wall heights differ.
    levels=max(1,math.ceil(float((y-floor).max())/P.WALL_ROW))
    u=np.linspace(0,1,levels+1)
    columns=[]
    for p,fy in zip(loop,floor,strict=True):
        bottom=p.copy();bottom[1]=fy
        column=p[None,:]*(1-u[:,None])+bottom[None,:]*u[:,None]
        for (built,_),row in zip(rollins,rows,strict=True):
            if np.linalg.norm(row[[0,-1]][:,[0,2]]-p[[0,2]],axis=1).min()>1e-7:
                continue
            v=built.mesh.V
            selected=v[(np.linalg.norm(v[:,[0,2]]-p[[0,2]],axis=1)<1e-7)&(v[:,1]<=y+1e-7)]
            if len(selected) and selected[:,1].min()<y-1e-7:
                heights=np.unique(selected[:,1])[::-1]
                if abs(heights[-1]-fy)>1e-7:
                    raise GeometryError('tower portal side and roll-in disagree on their terrain foot')
                column=np.tile(p,(len(heights),1));column[:,1]=heights
        columns.append(column)
    walls=[]
    for i,(a,b) in enumerate(zip(loop,np.roll(loop,-1,axis=0),strict=True)):
        if is_portal(a,b):
            continue
        delta=b-a; outward=[delta[2],0.,-delta[0]]
        polygon=np.r_[columns[i],columns[(i+1)%len(loop)][::-1]]
        walls.append(solids.polygon(polygon,outward=outward,feature='tower.support',role=dsl.SIDE))
    mesh=dsl.Mesh.concat([top,*walls])
    base_y=min(float(terrain(loop[:,0],loop[:,2]).min()),float(mesh.V[:,1].min()))-P.MIN_WALL
    body=solids.prism(loop[:,[0,2]],base_y,y,feature='tower.support',
                      material=dsl.CONCRETE,top_role=dsl.BASE,side_role=dsl.BASE)
    solids.check_closed(body,name='tower.concrete_core')
    bearings=[dict(target_feature='tower',polygon=loop.tolist())]
    for (_,geo),row in zip(rollins,rows,strict=True):
        lower=row[[-1,0]].copy();lower[:,1]=base_y
        bearings.append(dict(target_feature=geo['id'],polygon=np.r_[row,lower].tolist()))
    return P.Built(mesh,checks=[dict(kind='tower',feature='tower',deck_y=y,parameters=spec),
                                dict(kind='v4_support',feature='tower.support',type='closed_concrete_core',
                                     bearings=bearings,ground_interface=True,buried_base_y=base_y,
                                     body_triangles=body.triangles().tolist())])


def variable_channel(origin, heading, length, width_start, width_end, y, left, right, terrain, feature):
    """A level tapered channel, using existing bowl-side solids and validators."""
    if length <= 0:
        raise GeometryError(f'{feature}: taper needs a positive length')
    direction=junctions.direction(heading); normal=np.array([-direction[1],direction[0]])
    stations=np.linspace(0,length,max(1,math.ceil(length/.5))+1)
    u=stations/length; widths=width_start+(width_end-width_start)*u*u*(3-2*u)
    count=max(1,math.ceil(max(width_start,width_end)/(dsl.RIDING_TESS.max_edge/math.sqrt(2))))
    weights=np.linspace(.5,-.5,count+1)
    centre=np.asarray(origin)+stations[:,None]*direction
    plan=centre[:,None,:]+widths[:,None,None]*weights[None,:,None]*normal
    grid=np.stack([plan[:,:,0],np.full(plan.shape[:2],y),plan[:,:,1]],axis=-1)
    riding=solids.grid(grid,outward=[0,1,0],feature=feature,role=dsl.RIDING)
    parts=[riding]+P._close_transverse(grid,feature=feature,ground=terrain,front=left,back=right,
                                      ends=('flush','flush'),closed=False,end_rows=[grid[0],grid[-1]],on_ground=True)
    mesh,foot=P._finish(parts,feature,riding,on_ground=True)
    return P.Built(mesh,foot=foot,checks=[dict(kind='v4_taper',feature=feature,length_m=length,
                                               clear_widths_m=[width_start,width_end],y=y)])


def build_elbow(segment, geo, terrain):
    """Exact J-owned wide mouths; reject planning elbows that cannot fit them."""
    name=geo['id']; turn=float(segment['angle'])
    if not 0 < abs(turn) < 180:
        raise GeometryError(f'{name}: exact J elbow requires a turn strictly between zero and 180 degrees')
    if abs(geo['start']['a'])>1e-8 or abs(geo['end']['a'])>1e-8 or np.ptp(geo['y'])>1e-8:
        raise GeometryError(f'{name}: exact wide-mouth elbow requires a level entry; set predecessor end_deg=0')
    heading=float(geo['start']['h']); A=junctions.direction(heading); B=junctions.direction(heading+turn)
    normal=(B-A)/np.linalg.norm(B-A); tangent=np.array([-normal[1],normal[0]])
    cap_left=float(geo['wr'].get('cap',P.BOWL_CAP)); cap_right=float(geo['wl'].get('cap',P.BOWL_CAP))
    if abs(cap_left-cap_right)>1e-9:
        raise GeometryError(f'{name}: symmetric J cut requires equal shoulder caps')
    mouth=finite(segment.get('mouth_w',36.),'elbow.mouth_w',positive=True)
    envelope=mouth+cap_left+cap_right; apron=finite(segment.get('apron',6.),'elbow.apron',positive=True)
    an=-float(A@normal); bn=float(B@normal)
    din=(apron+envelope/2*abs(float(A@tangent)))/an
    dout=(apron+envelope/2*abs(float(B@tangent)))/bn
    corner=float(geo['corner']); before=corner-din; after=float(geo['L'])-corner-dout
    taper=finite(segment.get('funnel_m',segment.get('mouth_len',40.)),'elbow.funnel_m',positive=True)
    if before < taper-1e-6 or after < taper-1e-6:
        raise GeometryError(f'{name}: wide mouths do not fit resolved segment; require approach >= {din+taper:.6g} m '
                            f'and mouth_len >= {dout+taper:.6g} m (explicit funnel_m={taper:g}); '
                            f'available straight tapers {before:.6g}/{after:.6g} m')
    qp=segment.get('qp',{})
    radius=finite(qp.get('R',6.),'elbow.qp.R',positive=True)
    height=finite(qp.get('h',radius+float(qp.get('vert',1.))),'elbow.qp.h',positive=True)
    vert=finite(qp.get('vert',height-radius),'elbow.qp.vert')
    if vert<0 or abs(height-radius-vert)>1e-8:
        raise GeometryError(f'{name}: qp.h must equal qp.R + qp.vert')
    if float(segment.get('drift',0.)) != 0:
        raise GeometryError(f'{name}: nonzero drift needs resolver exit_corner semantics; planning elbow has none')
    origin=np.array([geo['start']['x'],geo['start']['z']]); W=origin+A*corner
    pin=W-A*din; pout=W+B*dout; y=float(geo['start']['y'])
    # Shoulder heights vanish at both exact J-owned cuts while their caps remain.
    from dataclasses import replace
    inlet_left=replace(side(geo['wr']),fade=(0.,taper))
    inlet_right=replace(side(geo['wl']),fade=(0.,taper))
    outlet_left=replace(side(geo['wr']),fade=(taper,0.))
    outlet_right=replace(side(geo['wl']),fade=(taper,0.))
    incoming=variable_channel(origin,heading,before,float(geo['W']),mouth,y,inlet_left,inlet_right,terrain,name+'.input')
    outgoing=variable_channel(pout,heading+turn,after,mouth,float(geo['W']),y,outlet_left,outlet_right,terrain,name+'.output')
    rows=[junctions.boundary_row(incoming.mesh,pin,A,level=True),
          junctions.boundary_row(outgoing.mesh,pout,B,level=True)]
    reach=max(abs(din*float(A@tangent))+envelope/2/an,abs(dout*float(B@tangent))+envelope/2/bn)
    spec=dict(line=name,index=0,grade_t=0.,heading_in=heading,heading_out=heading+turn,
              corner=W,exit_corner=W,n=normal,t=tangent,y=y,r=radius,vert=vert,
              s=corner,s_in=before,s_out=corner+dout,drift=0.,centre=W,
              half_length=max(reach+2.,float(qp.get('lip_min',40.))/2),
              lip_min=float(qp.get('lip_min',40.)),deck=float(qp.get('deck',2.)),width=envelope)
    junction=junctions.elbow(spec,ground=terrain,on_ground=True,rows=rows)
    result=P.Built.concat([incoming,junction,outgoing])
    result.foot=solids.check_open(result.mesh,name=name)
    result.checks.append(dict(kind='v4_elbow',feature=name,parameters=segment,
                             mouth_clear_m=mouth,mouth_including_caps_m=envelope,owned_ports=[r.tolist() for r in rows]))
    return result


def gap_rail(built, segment, geo, path, terrain):
    """Owner-selected standard rainbow: raised round bar between gap endpoints.

    rail=true uses height .75m, arch rise 10% of open gap (minimum 2m),
    rider-right offset floor_width/2-1.5m. JSON rail objects override these
    compiler conventions; exact settings are emitted for physical review.
    """
    from . import rails
    flag=segment.get('rail')
    if not flag:
        return built
    if not isinstance(flag,(bool,dict)):
        raise GeometryError('rail must be true/false or an explicit rainbow settings object')
    settings=dict(flag) if isinstance(flag,dict) else {}
    allowed={'height_m','rise_m','offset_m','radius_m','post_radius_m','spacing_m','sides'}
    if set(settings)-allowed:
        raise GeometryError(f'unknown rainbow settings {sorted(set(settings)-allowed)}')
    lip,knuckle=map(float,geo['air_intervals'][0]); opening=knuckle-lip
    values=dict(height_m=.75,rise_m=max(2.,opening*.1),offset_m=max(0.,geo['W']/2-1.5),
                radius_m=rails.RAIL_RADIUS,post_radius_m=rails.POST_RADIUS,spacing_m=rails.POST_SPACING,sides=12)
    values.update(settings)
    if (int(values['sides']) != values['sides'] or not 3 <= int(values['sides']) <= 64
            or float(values['post_radius_m']) >= float(values['radius_m'])
            or float(values['spacing_m']) <= 2*float(values['post_radius_m'])):
        raise GeometryError('rainbow needs 3..64 tube sides, thinner posts and spacing greater than post diameter')
    for key,value in values.items():
        finite(value,'rail.'+key,positive=key not in ('offset_m',))
    count=max(2,math.ceil(opening/.5));u=np.linspace(0,1,count+1);stations=lip+opening*u
    xy=path.point(stations)+path.normal(stations)*float(values['offset_m'])
    checks=next(c for c in built.checks if c['kind']=='air')
    y=(1-u)*checks['lip'][1]+u*checks['landing_start'][1]+float(values['height_m'])+4*u*(1-u)*float(values['rise_m'])
    axis=np.c_[xy[:,0],y,xy[:,1]]
    mesh,rail=rails.round_rail(axis,ground=terrain,feature=geo['id']+'.rainbow',radius=float(values['radius_m']),
                               post_radius=float(values['post_radius_m']),spacing=float(values['spacing_m']),sides=int(values['sides']))
    built.mesh=dsl.Mesh.concat([built.mesh,mesh]);built.rails.append(rail)
    built.checks.append(dict(kind='v4_rainbow',feature=rail.feature,parameters=values,
                              physical_status='new derived geometry; native grind and support review required'))
    return built
