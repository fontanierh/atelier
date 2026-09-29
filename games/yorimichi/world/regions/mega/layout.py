"""Sloanyard-scale forest extension. Metres; one profile drives mesh and physics."""
import math
import numpy as np
from village.layout import spline,nearest,sample,upper_surface,smooth
ORIGIN=(65.,242.,66.8)
WIDTH=8.
GAP=10.4
BOUNDS=(20.,220.,150.,292.)

def bezier(points,n=100):
    a,b,c,d=np.array(points,float)
    return [(a*(1-t)**3+3*b*t*(1-t)**2+3*c*t*t*(1-t)+d*t**3).tolist() for t in np.linspace(0,1,n+1)]

def profiles():
    roll=[[-3.,10.7],[0.,10.7]]+bezier([(0,10.7),(4,10.7),(2,.45),(16.5,.45)],180)[1:]
    roll+=bezier([(16.5,.45),(20,.45),(24,1.285),(27.5,2.7)],100)[1:]
    land=bezier([(37.9,2.7),(41.,.65),(44.,.45),(49.,.45)],100)
    land.append([56.,.45])
    # Exact circular transition ends in true vertical: no over-vertical hook.
    land += [[56+5.65*math.sin(t),.45+5.65*(1-math.cos(t))] for t in np.linspace(0,math.pi/2,151)[1:]]
    return [roll,land]

def rollout():
    # Tangent-continuous return route, descending gently onto the clearing.
    p=np.array(bezier([(52,0,.455),(44,0,.455),(43,-8,.12),(47,-12,.055)],120))
    # Stay flush while overlapping the main flat; descend beyond its edge.
    p[:,2]=.455-.4*smooth((np.abs(p[:,1])-4.3)/7.7)
    return p.tolist()

def integrate(world,h):
    before=h.copy();ox,oy,oz=ORIGIN
    start=np.array(world['village']['paths'][0][-1])
    xy,s=spline([start[:2],(162,180),(193,187),(197,205),(176,215),(154,204),(135,188),(112,192),(92,210),(80,223),(60,234)])
    z=start[2]+(oz-start[2])*s/s[-1];path=np.column_stack([xy,z])
    axis=np.linspace(-world['size']/2,world['size']/2,len(h));x,y=np.meshgrid(axis,axis)
    # Oval clearing; preserve a substantial wooded buffer beyond the hamlet.
    radius=np.sqrt(((x-96)/46)**2+((y-242)/20)**2)
    clearing=smooth((1.35-radius)/.35)
    d,pz=nearest(x,y,path);trail=smooth((15-d)/12)
    old_distance,_=nearest(x,y,np.array(world['village']['paths'][0]))
    pad_distance=np.maximum.reduce([np.abs(x-96)-35,np.abs(y-242)-4.5,np.zeros_like(x)])
    trail*=smooth((old_distance-d)/2)*smooth(pad_distance/3)
    h[:]=h*(1-clearing)+oz*clearing
    h[:]=h*(1-trail)+(pz-.055)*trail
    removed={}
    for name,placements in list(world['instances'].items()):
        if not name.startswith(('Tree','Bush','Grass','Rock')) and name!='Litter':continue
        a=np.array(placements,float)
        if not len(a):continue
        px,py=a[:,0],a[:,1]
        local=(px>BOUNDS[0])&(px<BOUNDS[1])&(py>BOUNDS[2])&(py<BOUNDS[3]);ii=np.flatnonzero(local)
        if not len(ii):continue
        lx,ly=px[ii],py[ii];pd,_=nearest(lx,ly,path)
        rr=np.sqrt(((lx-96)/46)**2+((ly-242)/20)**2)
        tree=name.startswith('Tree')
        remove=(pd<(5.4 if tree else 1.8))|(rr<(1.12 if tree else .99))
        keep=np.ones(len(a),bool);keep[ii[remove]]=False
        for k,i in enumerate(ii):
            if remove[k]:continue
            delta=float(sample(h,px[i],py[i])-sample(before,px[i],py[i]))
            if abs(delta)>.001:
                a[i,2]+=delta
                if tree:a[i,2]=min(float(upper_surface(h,px[i]+dx,py[i]+dy)) for dx,dy in [(0,0),(.5,0),(-.5,0),(0,.5),(0,-.5)])-.15
        world['instances'][name]=a[keep].tolist();removed[name]=int(remove.sum())
    world['instances']['Mega_Trail']=[[0,0,0,0,1]]
    world['mega']={'origin':list(ORIGIN),'width':WIDTH,'gap':GAP,'profiles':profiles(),'rollout':rollout(),'trail':path.tolist(),
        'ladder':[-2.,-4.65,0.], 'edit_bounds':list(BOUNDS),'removed':removed}
    world['shots'] += [[35,208,oz+27.2,32,-21],[55,226,oz+3.2,40,5],[96,218,oz+51.2,90,-65]]
