"""Layered autumn/evergreen cover for the exposed eastern Hidamari hills.

Only appends instances. Existing terrain, mountain, buildings and paths are
unchanged. Dedicated opaque low-detail trees use the existing distant-tree gate.
"""
import math
import numpy as np
from hidamari import mountains


def triangular(u,v,z00,z10,z01,z11):
    return np.where(u>=v,z00*(1-u)+z10*(u-v)+z11*v,z00*(1-v)+z11*u+z01*(v-u))


def ground(x,y,height,backdrop_grid,terrain_axes,north_height):
    """Sample the exported triangle surfaces, including the lowered far-hill grid."""
    far=backdrop_grid().copy();axis=np.linspace(-3200,3200,far.shape[0])
    xx,yy=np.meshgrid(axis,axis);mask=mountains.contains(xx,yy)
    far[mask]=np.minimum(far[mask],north_height(xx,yy)[mask]-25)
    fx=np.clip((x+3200)/6400*(len(axis)-1),0,len(axis)-1.001)
    fy=np.clip((y+3200)/6400*(len(axis)-1),0,len(axis)-1.001)
    ix=fx.astype(int);iy=fy.astype(int);u=fx-ix;v=fy-iy
    z=triangular(u,v,far[iy,ix],far[iy,ix+1],far[iy+1,ix],far[iy+1,ix+1])
    mask=mountains.contains(x,y)
    z[mask]=north_height(x[mask],y[mask])
    mask=(x>=300)&(x<=1420)&(y>=-300)&(y<=500)
    if np.any(mask):
        xs,ys=map(np.asarray,terrain_axes());px=x[mask];py=y[mask]
        i=np.clip(np.searchsorted(xs,px)-1,0,len(xs)-2);j=np.clip(np.searchsorted(ys,py)-1,0,len(ys)-2)
        x0,x1=xs[i],xs[i+1];y0,y1=ys[j],ys[j+1]
        city=triangular((px-x0)/(x1-x0),(py-y0)/(y1-y0),height(x0,y0),height(x1,y0),height(x0,y1),height(x1,y1))
        z[mask]=np.maximum(z[mask],city)
    return z


def append(instances,buildings,height,backdrop_grid,terrain_axes,north_height,road_x,road_y):
    rng=np.random.default_rng(9147)
    # A jittered canopy lattice avoids random bare holes and obvious planting rows.
    gx,gy=np.meshgrid(np.arange(320.,3190.,10.),np.arange(-330.,2990.,10.))
    x=gx.ravel()+rng.uniform(-4.6,4.6,gx.size);y=gy.ravel()+rng.uniform(-4.6,4.6,gy.size)
    # Eastern slopes outside the old north-forest footprint, plus a softer city edge.
    edge=380+22*np.sin(x*.009)+15*np.sin(x*.022)
    east_edge=1345+30*np.sin(y*.011)+22*np.sin(y*.027)
    east=(x>east_edge)&(y>-170)&((x>2100+100*np.sin(y*.008))|(y<900))
    belt=(y>edge)&(y<620)&(x<2340)
    keep=east|belt
    keep&=mountains.trail_distance(x,y)>15
    keep&=~((x<1265)&np.any(abs(y[:,None]-np.asarray(road_y))<16,axis=1))
    keep&=~((y<365)&np.any(abs(x[:,None]-np.asarray(road_x))<16,axis=1))
    # A little open ground at the forest edge; continuous canopy on the bare hills.
    frontier=np.where(east,x-east_edge,y-edge)
    keep&=rng.random(len(x))<(.45+.55*mountains.smooth(frontier/65))
    for b in buildings:
        cx,cy,_=b['position'];a=math.radians(b['yaw'])
        dx=x-cx;dy=y-cy;lx=dx*math.cos(a)+dy*math.sin(a);ly=-dx*math.sin(a)+dy*math.cos(a)
        keep&=~((abs(lx)<b['width']/2+13)&(abs(ly)<b['depth']/2+13))
    x=x[keep];y=y[keep];z=ground(x,y,height,backdrop_grid,terrain_axes,north_height)
    valid=(z>4)&((x>2320)|(z<215+20*np.sin(x*.009)))
    x=x[valid];y=y[valid];z=z[valid]
    patch=np.sin(x*.013+np.sin(y*.008)*2)+.6*np.cos(y*.017)
    choices=rng.random(len(x));kind=np.where(choices<.40,'Green',np.where(choices<.68,'Pine',np.where(patch>0,'Gold','Rust')))
    scale=rng.uniform(1.25,1.85,len(x));yaw=rng.uniform(0,360,len(x))
    # Front clusters taper in height instead of making a uniform high hedge.
    d=np.minimum(np.where(x<1420,abs(y-(380+22*np.sin(x*.009)+15*np.sin(x*.022))),1e6),np.where(y<900,abs(x-(1345+30*np.sin(y*.011)+22*np.sin(y*.027))),1e6))
    scale*=.65+.35*mountains.smooth(d/160)
    # Leaf-based town trees form an irregular, human-scale transition. The
    # mountain path gets the same detailed margin; opaque crowns stay behind it.
    leafy=((d<70+20*np.sin(x*.019+y*.013))&(x<1450)&(y<700))|((mountains.trail_distance(x,y)<45)&(y<1300))
    names=np.char.add('HD_NorthTreeBackdrop',kind)
    names[leafy]=np.where(rng.random(np.count_nonzero(leafy))<.38,'Tree_Ginkgo','Tree_Maple_A')
    scale[leafy]=rng.uniform(.70,1.30,np.count_nonzero(leafy))
    # Preserve the existing forest and skip new crowns already covered by it.
    # This saves overdraw at the join without thinning the newly covered hills.
    bins={}
    for old_name,points in instances.items():
        if not old_name.startswith('HD_NorthTree'):continue
        for ox,oy,_,_,os in points:
            bins.setdefault((math.floor(ox/12),math.floor(oy/12)),[]).append((ox,oy,os))
    unique=np.ones(len(x),dtype=bool)
    for i,(px,py) in enumerate(zip(x,y)):
        if leafy[i] or d[i]<90:continue
        bx,by=math.floor(px/12),math.floor(py/12)
        unique[i]=not any((px-ox)**2+(py-oy)**2<(4*os+2)**2
                          for dx in (-1,0,1) for dy in (-1,0,1)
                          for ox,oy,os in bins.get((bx+dx,by+dy),()))
    x,y,z,yaw,scale,names=(a[unique] for a in (x,y,z,yaw,scale,names))
    ranges={}
    for name in sorted(set(names)):
        mask=names==name
        entries=np.stack((x[mask],y[mask],z[mask]-.20*scale[mask],yaw[mask],scale[mask]),axis=-1).tolist()
        dest=instances.setdefault(name,[]);start=len(dest);dest.extend(entries);ranges[name]=[start,len(dest)]
    return {'seed':9147,'instance_ranges':ranges,'count':len(x),'root_embed_per_scale':.20}
