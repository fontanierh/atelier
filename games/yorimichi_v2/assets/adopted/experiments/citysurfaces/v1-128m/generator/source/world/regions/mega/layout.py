"""Sloanyard-scale forest extension: the trail, the clearing and the ramp's place, in metres. The ramp's shape is in
`ramp.py`."""
import numpy as np
from village.layout import spline,nearest,sample,upper_surface,smooth
ORIGIN=(65.,242.,66.8)
TRAIL_WIDTH=8.
GAP=10.4
BOUNDS=(20.,220.,150.,292.)

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
    world['mega']={'origin':list(ORIGIN),'width':TRAIL_WIDTH,'gap':GAP,'trail':path.tolist(),
        'ladder':[-2.,-4.65,0.], 'edit_bounds':list(BOUNDS),'removed':removed}
    world['shots'] += [[35,208,oz+27.2,32,-21],[55,226,oz+3.2,40,5],[96,218,oz+51.2,90,-65]]
