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

    Each retained interval is proved against all original samples. Since both
    curves are piecewise linear, the sample maximum bounds the whole interval.
    """
    points=np.asarray(points,float)
    if len(points)<2 or tolerance<=0 or not np.isfinite(points).all():
        raise ValueError('Invalid rope mesh simplification')
    keep={0,len(points)-1}; pending=[(0,len(points)-1)]
    while pending:
        first,last=pending.pop()
        if last-first<2:
            continue
        a,b=points[first],points[last]; ab=b-a
        q=points[first+1:last]; length2=float(ab@ab)
        t=np.clip((q-a)@ab/length2,0,1) if length2 else np.zeros(len(q))
        distance=np.linalg.norm(q-(a+t[:,None]*ab),axis=1)
        index=int(np.argmax(distance))
        if distance[index]>tolerance:
            middle=first+index+1;keep.add(middle)
            pending.extend(((first,middle),(middle,last)))
    return points[sorted(keep)]
