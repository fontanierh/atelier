"""Loaded spans joined to the kit's straight, level sheave trains."""
import math
import numpy as np


def span_height(s, length, za, zb, *, sag=.035, shoulder=40.):
    """Parabolic loaded span, eased into zero-slope support contacts.

    The central span keeps the authored sag. Within each shoulder a cubic
    Hermite segment meets both the support's level tangent and the parabola's
    exact value and derivative. Supports include their actual train extents;
    the span starts at the last sheave and ends at the next first sheave.
    """
    if not np.isfinite([length,za,zb,sag,shoulder]).all() or length <= 0 or shoulder <= 0 or sag < 0:
        raise ValueError('Invalid rope span')
    x = np.asarray(s, float)
    if not np.isfinite(x).all() or np.any(x < 0) or np.any(x > length):
        raise ValueError('Rope span query outside support interval')
    w = min(shoulder, length/2)
    slope = (zb-za)/length

    def parabola(q):
        t = q/length
        return za + (zb-za)*t - 4*sag*length*t*(1-t)

    def derivative(q):
        return slope - 4*sag*(1-2*q/length)

    def hermite(t, a, b, da, db):
        return (2*t**3-3*t**2+1)*a + (t**3-2*t**2+t)*da + (-2*t**3+3*t**2)*b + (t**3-t**2)*db

    z = parabola(x)
    z = np.where(x < w, hermite(x/w, za, parabola(w), 0, w*derivative(w)), z)
    z = np.where(x > length-w, hermite((x-length+w)/w, parabola(length-w), zb,
                                    w*derivative(length-w), 0), z)
    return z


def centre_profile(supports, *, train_half=1.6, step=.05, sag=.035):
    """@cc [owner:fontanierh,label:correctness] gondola-shared-rope-path
    The generated rope, grip placements and runtime samples MUST use this one
    support profile, with level sheave contacts and continuous span tangents.
    Production MUST separately refuse actual jaw or hardware clearance failures.

    Supports are (longitudinal distance, rope z, is_tower). Station contacts
    have no train extension here: their kit-owned loops provide that geometry.
    """
    if (len(supports) < 2 or not np.isfinite([step,train_half,sag]).all() or
            not np.isfinite(np.asarray(supports,float)).all() or step <= 0 or train_half <= 0 or sag < 0):
        raise ValueError('A rope line requires two stations and a positive sample step')
    if any(b[0] <= a[0] for a,b in zip(supports,supports[1:])):
        raise ValueError('Rope supports must be ordered')
    pts = []
    for i, ((s0,z0,tower0),(s1,z1,tower1)) in enumerate(zip(supports,supports[1:])):
        left, right = s0+(train_half if tower0 else 0), s1-(train_half if tower1 else 0)
        if right <= left:
            raise ValueError('Overlapping support contact trains')
        if not pts:
            pts.append((s0,z0))
        if left > pts[-1][0]:
            pts.append((left,z0))
        x = np.linspace(0,right-left,max(2,math.ceil((right-left)/step)+1))
        z = span_height(x,right-left,z0,z1,sag=sag)
        pts.extend(zip(left+x[1:],z[1:]))
        if tower1:
            pts.append((s1+train_half,z1))
    return np.asarray(pts,float)


def station_frame(mouth, other, platform_z, mouth_x):
    mouth,other=np.asarray(mouth,float),np.asarray(other,float)
    along=(other-mouth)/np.linalg.norm(other-mouth)
    lateral=np.array([-along[1],along[0]])
    return mouth-mouth_x*along,along,lateral,float(platform_z)


def placed(points, frame):
    origin,along,lateral,z=frame
    points=np.asarray(points,float)
    return np.c_[origin+points[:,0,None]*along+points[:,1,None]*lateral,points[:,2]+z]


def closed_circuit(profile, a, b, station_path, gauge):
    """Join the kit's grip loops to both tracks without a separate runtime curve.

    Profile endpoints are the kit's exact rope exits in world longitudinal
    metres. The loops use the horizontal running rail through the released-grip
    station, including the same bullwheel turn as the static kit.
    """
    profile=np.asarray(profile,float)
    loop_a=placed(station_path,a); loop_b=placed(station_path,b)
    origin,along,lateral,z=a
    # Mouth is the station frame's origin plus its authored mouth distance.
    mouth=loop_a[-1,:2]-profile[0,0]*along-gauge/2*lateral
    straight=np.c_[mouth+profile[:,0,None]*along,profile[:,1]]
    outbound=straight.copy(); outbound[:,:2]+=gauge/2*lateral
    inbound=straight[::-1].copy(); inbound[:,:2]-=gauge/2*lateral
    sections=[loop_a,outbound,loop_b,inbound]
    for previous,following in zip(sections,sections[1:]+sections[:1]):
        if np.linalg.norm(previous[-1]-following[0])>1e-6:
            raise ValueError('Gondola loop and span do not share their endpoint')
    return np.concatenate([section[:-1] for section in sections]+[sections[0][:1]])


def simplify(points, tolerance):
    """Polyline reduction with a declared maximum point-to-segment error.

    Grow each shortcut with exponential search, then refine its endpoint. Every
    accepted interval is checked against all original samples, using both ideal
    endpoints and their float32 storage conversion used by Mesh.tube/Blender.
    Since both curves are piecewise linear, complete segments are bounded too.
    """
    points=np.asarray(points,float)
    if len(points)<2 or not math.isfinite(tolerance) or tolerance<=0 or not np.isfinite(points).all():
        raise ValueError('Invalid rope mesh simplification')

    with np.errstate(over='ignore'):
        stored=points.astype(np.float32).astype(float)
    if not np.isfinite(stored).all():
        raise ValueError('Unrepresentable rope mesh coordinates')

    def fits(first,last):
        q=points[first:last+1]
        for endpoints in (points,stored):
            a,b=endpoints[first],endpoints[last];ab=b-a;length2=float(ab@ab)
            t=np.clip((q-a)@ab/length2,0,1) if length2 else np.zeros(len(q))
            if np.linalg.norm(q-a-t[:,None]*ab,axis=1).max()>tolerance:
                return False
        return True

    keep=[0]
    while keep[-1]<len(points)-1:
        first=keep[-1];last=first+1;stride=2
        if not fits(first,last):
            raise ValueError('Rope axis allowance is below float32 coordinate precision')
        while True:
            candidate=min(first+stride,len(points)-1)
            if not fits(first,candidate):
                break
            last=candidate
            if last==len(points)-1:
                break
            stride*=2
        if last<len(points)-1:
            high=candidate
            while high-last>1:
                middle=(last+high)//2
                if fits(first,middle):
                    last=middle
                else:
                    high=middle
        keep.append(last)
    return points[keep]


def near_rope_tolerance(groove_error_mm):
    """Use the measured 2 mm jaw allowance with a ten-percent safety reserve.

    Distance to a curve is 1-Lipschitz under a bounded Hausdorff displacement.
    simplify bounds that displacement across complete original segments, so
    the original groove maximum plus this axis bound stays strictly below 2 mm.
    """
    if not math.isfinite(groove_error_mm) or not 0<=groove_error_mm<1.9995:
        raise ValueError('No remaining near-rope contact allowance')
    return .9*(2.-groove_error_mm-.0005)/1000.


def recover_rope_vertices(expected, local, world, nearest):
    """@cc [owner:fontanierh,label:correctness] gondola-fbx-world-transform
    FBX correspondence MUST preserve the world transform of every matched
    control point. Local matching tolerance MUST NOT forgive physical groove
    or hardware error; those checks MUST use the transformed world vertices.

    Correspondence tolerance identifies vertices only. Physical contact uses
    the returned world positions, including every imported transform error.
    """
    expected,local,world=(np.asarray(points,float) for points in (expected,local,world))
    if (any(points.ndim!=2 or points.shape[1]!=3 or not len(points) or not np.isfinite(points).all()
            for points in (expected,local,world)) or local.shape!=world.shape):
        raise ValueError('Incomplete rope FBX vertices')
    unique,inverse=np.unique(expected,axis=0,return_inverse=True)
    if unique.shape!=local.shape or len(np.unique(local,axis=0))!=len(local):
        raise ValueError('Rope FBX read-back changed emitted vertex count')
    indices=np.asarray([nearest(point) for point in unique],int)
    allowance=max(1e-6,float(np.spacing(np.abs(expected).astype(np.float32)).max())*2)
    if (len(set(indices))!=len(local) or np.any(indices<0) or np.any(indices>=len(local)) or allowance>.001):
        raise ValueError('Rope FBX read-back vertex correspondence is ambiguous')
    error=float(np.linalg.norm(local[indices]-unique,axis=1).max())
    if error>allowance:
        raise ValueError('Rope FBX read-back displaced emitted control points')
    recovered=world[indices][inverse]
    return recovered,{'matched_vertices':len(recovered),'control_point_error_m':error,
                      'control_point_allowance_m':allowance,'control_point_frame':'mesh-local',
                      'world_transform_applied':True,
                      'world_displacement_m':float(np.linalg.norm(recovered-expected,axis=1).max())}


def float32_cm_axes(vertices, ring_counts, sides=12):
    """Ring centres after the emitted vertices enter Unreal's float32 cm buffer."""
    vertices=np.asarray(vertices,float)
    if (vertices.ndim!=2 or vertices.shape[1]!=3 or not np.isfinite(vertices).all() or
            len(ring_counts)!=2 or any(n<2 for n in ring_counts) or
            len(vertices)!=sum(ring_counts)*sides):
        raise ValueError('Incomplete stored rope rings')
    stored=(vertices*100).astype(np.float32).astype(float)/100
    if not np.isfinite(stored).all():
        raise ValueError('Unrepresentable stored rope rings')
    result=[];start=0
    for count in ring_counts:
        end=start+count*sides
        result.append(stored[start:end].reshape(count,sides,3).mean(axis=1))
        start=end
    return result


def stored_groove_audit(profile, axes, groove, path_type, radius):
    """@cc [owner:fontanierh,label:correctness] gondola-stored-rope-contact
    Production MUST check emitted rope axes in their centimetre float32 storage
    representation against unquantized shared runtime grip frames, both ways,
    preserving the 2 mm groove and 0.095 m hardware-clearance refusals.

    Compare stored axes with unquantized runtime frames and actual jaw samples.

    The two short, flat kit-owned overlaps are separate segments: no fictitious
    bridge fills any gap between a station's rope and the exported span.
    """
    profile=np.asarray(profile,float);groove=np.asarray(groove,np.float32).astype(float)
    if (len(axes)!=2 or groove.shape!=(114,3) or not np.isfinite(groove).all() or
            not np.isfinite(profile).all() or len(profile)<2):
        raise ValueError('Incomplete stored rope contact inputs')
    extended=np.vstack(([profile[0,0]-.4,profile[0,1]],profile,[profile[-1,0]+.4,profile[-1,1]]))
    path=path_type([(s,0,z) for s,z in extended],radius)
    samples=np.arange(path.s[1],path.s[-2]+1e-8,.2)
    worst=0.;poses=0
    for side,axis in zip((-1,1),axes):
        axis=np.asarray(axis,float)
        if (axis.ndim!=2 or axis.shape[1]!=3 or len(axis)<2 or not np.isfinite(axis).all() or
                np.any(np.diff(axis[:,0])<=0)):
            raise ValueError('Incomplete stored rope axis')
        kit=np.array([[[profile[0,0]-.4,0,profile[0,1]],[profile[0,0],0,profile[0,1]]],
                      [[profile[-1,0],0,profile[-1,1]],[profile[-1,0]+.4,0,profile[-1,1]]]])
        segments=np.concatenate((np.stack((axis[:-1],axis[1:]),axis=1),kit))
        for arc in samples:
            G=np.asarray(path.grip_frame(float(arc),(0,side,0)),float)
            points=groove@G[:3,:3].T+G[:3,3]
            # Every groove point is within .3m of the grip origin. Segments
            # outside this window cannot beat the nearby rope's .045m radius.
            if np.max(np.linalg.norm(points-G[:3,3],axis=1))>=.3:
                raise ValueError('Stored rope groove search window is insufficient')
            selected=segments[(segments[:,:,0].max(axis=1)>=G[0,3]-.8)&
                              (segments[:,:,0].min(axis=1)<=G[0,3]+.8)]
            if not len(selected):raise ValueError('Missing stored rope segment')
            a=selected[:,0];v=selected[:,1]-a;length2=np.sum(v*v,axis=1)
            if np.any(length2<=0):raise ValueError('Degenerate stored rope segment')
            t=np.clip(np.sum((points[:,None,:]-a)*v,axis=2)/length2,0,1)
            distances=np.linalg.norm(points[:,None,:]-a-t[:,:,None]*v,axis=2).min(axis=1)
            worst=max(worst,float(np.abs(distances-radius).max())*1000);poses+=1
    # Five micrometres cover the short kit overlap's local-coordinate storage;
    # the world span itself uses the recovered, centimetre-quantized vertices.
    bound=worst+.005
    return {'poses':poses,'directions':[-1,1],'points_per_pose':len(groove),
            'max_error_mm':worst,'bound_mm':bound,'pass':bound<=2.,
            'representation':'fbx-float32-cm-ring-axis'}
