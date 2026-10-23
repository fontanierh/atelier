"""Final city station ground query; independent of Blender and rendered meshes."""
import numpy as np

def city_ground(x,y):
 """HD_Terrain's surface at (x, y): the layout height carved by the railway earthworks and levelled by the air
 station's pad, read off its grid like the mesh, and never below the exact surface."""
 from hidamari.layout import height,terrain_axes
 from train import earthworks
 from zeppelin.layout import city_pad
 def final(gx,gy):return city_pad(gx,gy,earthworks.carve(gx,gy,height(gx,gy)))
 xs,ys=map(np.asarray,terrain_axes())
 i=int(np.clip(np.searchsorted(xs,x)-1,0,len(xs)-2));j=int(np.clip(np.searchsorted(ys,y)-1,0,len(ys)-2))
 gx,gy=np.meshgrid(xs[i:i+2],ys[j:j+2]);z=np.asarray(final(gx,gy),float)
 u=(x-xs[i])/(xs[i+1]-xs[i]);w=(y-ys[j])/(ys[j+1]-ys[j])
 grid=z[0,0]*(1-u)*(1-w)+z[0,1]*u*(1-w)+z[1,0]*(1-u)*w+z[1,1]*u*w
 return float(max(grid,float(np.asarray(final(np.array([x]),np.array([y])),float).ravel()[0])))
