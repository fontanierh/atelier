"""Motion shaping shared by the Japan characters' authored clips.

Secondary parts (hood, sash tails, bags, scarf) are not keyed by hand-tuned sine waves: each one is a small
simulated body hanging from its animated attachment point. The attachment's real acceleration over the clip
drives a damped pendulum (two swing planes), a vertical spring, or a flap, and loops are made seamless by
running the simulation over several cycles and keeping the last one. The result lags, overshoots and settles
the way cloth and leather do, instead of moving in lockstep with the skeleton.
"""
import math
from math import sin,cos,pi
from mathutils import Vector

G=9.81

def smooth(t):
    t=max(0,min(1,t));return t*t*(3-2*t)

def keys(t,points):
    for (a,x),(b,y) in zip(points,points[1:]):
        if a<=t<=b:return x+(y-x)*smooth((t-a)/(b-a))
    return points[0][1] if t<points[0][0] else points[-1][1]

def acceleration(series,dt,loop):
    """Second derivative of a sampled trajectory (central differences; wraps for loops)."""
    n=len(series)
    def at(i):return series[i%n] if loop else series[min(max(i,0),n-1)]
    return [(at(i+1)-2*at(i)+at(i-1))/(dt*dt) for i in range(n)]

def _clamp(x,v,lo,hi):
    if x<lo:return lo,max(v,0.0)
    if x>hi:return hi,min(v,0.0)
    return x,v

def pendulum(acc,dt,loop,length,stiffness,damping,limit_x,limit_y,push=None,cycles=5):
    """Angles (about X, about Y) in radians per frame for a body hanging from an anchor with the given accelerations.
    Rotation about X moves the tail along +Y for positive angles; rotation about Y moves it along -X.
    push[i] (radians, >=0) is an external body pressing the tail forward (negative X angle), e.g. a lifted thigh."""
    n=len(acc);th=ph=vth=vph=0.0;out=[(0.0,0.0)]*n
    for k in range(n*cycles if loop else n):
        i=k%n;a=acc[i]
        ath=(-a.y*cos(th)-(G+a.z)*sin(th))/length-stiffness*th-damping*vth
        aph=(a.x*cos(ph)-(G+a.z)*sin(ph))/length-stiffness*ph-damping*vph
        vth+=ath*dt;vph+=aph*dt;th+=vth*dt;ph+=vph*dt
        th,vth=_clamp(th,vth,limit_x[0],limit_x[1]);ph,vph=_clamp(ph,vph,limit_y[0],limit_y[1])
        if push is not None and th>-push[i]:th=-push[i];vth=min(vth,0.0)
        out[i]=(th,ph)
    return out

def spring(drive,dt,loop,stiffness,damping,limit,cycles=5):
    """Damped spring displacement per frame under a forcing series (e.g. minus the anchor's vertical acceleration)."""
    n=len(drive);x=v=0.0;out=[0.0]*n
    for k in range(n*cycles if loop else n):
        i=k%n
        v+=(drive[i]-stiffness*x-damping*v)*dt;x+=v*dt
        x,v=_clamp(x,v,-limit,limit);out[i]=x
    return out

def loop_samples(records,frames,loop):
    """Loops key their last frame equal to the first; simulate on the unique samples only."""
    return records[:frames-1] if loop and frames>2 else records

def expand(values,frames,loop):
    if loop and frames>2:return list(values)+[values[0]]
    return list(values)
