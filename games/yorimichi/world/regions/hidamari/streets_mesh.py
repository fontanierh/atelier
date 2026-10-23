"""Selected Hidamari geometry; no sibling construction or export on import."""
from hidamari import arrival
from hidamari import living_streets
from hidamari.environment import M
from hidamari.layout import ROAD_X
from hidamari.layout import ROAD_Y
from hidamari.layout import height
import itertools
import math
import numpy as np


def streets(city):
    m=M('HD_Streets')
    # Each street at its own width (layout.road_width; the arrival road, last, is a broad one). On the hillside west
    # of the town the arrival road is arrival.py's ribbon: a broad strip there paved the slope beside it.
    arrival=len(city['roads'])-1
    for k,(path,(paving,asphalt)) in enumerate(itertools.zip_longest(city['roads'],city.get('road_widths',[]),fillvalue=(8,3.8))):
        for width,key,offset in [(paving,'paving',.045),(asphalt,'asphalt',.065)]:
            quads=[];cross=np.linspace(-width,width,math.ceil(width*2)+1)
            for a,b in zip(path,path[1:]):
                dx=b[0]-a[0];dy=b[1]-a[1];length=math.hypot(dx,dy)
                if length<.01 or (k==arrival and a[0]<400):continue
                nx,ny=-dy/length,dx/length
                for lo,hi in zip(cross[:-1],cross[1:]):
                    quads.append([(p[0]+s*nx,p[1]+s*ny) for p,s in [(a,lo),(b,lo),(b,hi),(a,hi)]])
            if not quads:continue
            points=np.asarray(quads);zs=height(points[:,:,0],points[:,:,1])+offset
            for quad,zs_quad in zip(points,zs):m.poly([(float(p[0]),float(p[1]),float(z)) for p,z in zip(quad,zs_quad)],key)
    return living_streets.add(m,city,height,ROAD_X,ROAD_Y)
