"""Selected Hidamari geometry; no sibling construction or export on import."""
from hidamari import arrival
from hidamari import layout
from hidamari.environment import M
from hidamari.environment import v
from hidamari.layout import ROAD_X
from hidamari.layout import ROAD_Y
from hidamari.layout import canal
from hidamari.layout import height
from hidamari.layout import pond
from hidamari.layout import street_height
from hidamari.layout import terrain_axes
import math
import numpy as np
import shorelines


HOUSE_LANES=sorted({y+layout.HOUSE[1]/2+layout.HOUSE_ALLEY/2 for _,_,y,yaw in layout.house_sites() if yaw==180})

HOUSE_X=(min(x for _,x,_,_ in layout.house_sites())-5,max(x for _,x,_,_ in layout.house_sites())+5)

def grass_patch(x,y):
    return (y>235 or (min(abs(y-c) for c in ROAD_Y)>30 and min(abs(x-c) for c in ROAD_X)>20)) and not (660<x<805 and 135<y<215)

def land_use(x,y):
    """The ground's surface at (x, y): lawn in the grass patches, sidewalk paving within 2 m of a street's paving
    (layout.road_width), packed earth in the yards behind."""
    if x<398:   # west of the streets, the hillside (the road is arrival.py's ribbon): paving only under the gate
        return 'hd_walk' if x>384 and arrival.road_distance(x,y)<(x-384)*.65 else 'hd_grass'
    lane=min(abs(y-c) for c in HOUSE_LANES)
    if HOUSE_X[0]<x<HOUSE_X[1] and lane<3.5 and layout._clear_of_hero(x,y):   # asphalt from wall to wall, a concrete ditch along each
        return 'hd_lane_asphalt' if lane<3.1 else 'hd_ditch_concrete'
    if HOUSE_X[0]<x<HOUSE_X[1] and lane<5.85 and layout._clear_of_hero(x,y):return 'hd_garden_gravel'   # the front plots (kit/house.py FRONT)
    if grass_patch(x,y):return 'hd_grass'
    if min(abs(y-c) for c in ROAD_Y)<10 or min(abs(x-c)-layout.road_width(x=c)[0] for c in ROAD_X)<2:return 'hd_walk'
    return 'hd_yard'

def surface(name,xs,ys,color,*,_natural=None):
    m=M(name)
    gx,gy=np.meshgrid(xs,ys);gz=height(gx,gy)
    natural_z=gz.copy() if _natural is not None else None
    if name=='HD_Terrain':
        from train import earthworks
        from zeppelin.layout import city_pad
        gz=earthworks.carve(gx,gy,gz)
        # Keep the bounded air-station apron at its authored level after the
        # railway's broader bank blend. city_pad excludes the track and roads.
        gz=city_pad(gx,gy,gz)
    def emit(points,key,original=None):
        m.poly(points,key)
        if _natural is not None:_natural.poly(points if original is None else original,key)
    for j,y in enumerate(ys[:-1]):
        for i,x in enumerate(xs[:-1]):
            dx=xs[i+1]-x;dy=ys[j+1]-y
            if pond(x+dx/2,y+dy/2) or canal(x+dx/2,y+dy/2):continue
            pts=[(float(gx[jj,ii]),float(gy[jj,ii]),float(gz[jj,ii])) for ii,jj in [(i,j),(i+1,j),(i+1,j+1),(i,j+1)]]
            key='park' if grass_patch(x+dx/2,y+dy/2) else color
            if name=='HD_Terrain':key=land_use(x+dx/2,y+dy/2)
            refine=name=='HD_Terrain' and ((980<x+dx/2<1080 and 224<y+dy/2<242) or (650<x+dx/2<835 and 254<y+dy/2<312))
            if refine and max(dx,dy)>.5:
                sx=np.linspace(x,x+dx,max(2,math.ceil(dx/.5)+1));sy=np.linspace(y,y+dy,max(2,math.ceil(dy/.5)+1))
                xx,yy=np.meshgrid(sx,sy);zz=height(xx,yy)
                for jj in range(len(sy)-1):
                    for ii in range(len(sx)-1):emit([(float(xx[b,a]),float(yy[b,a]),float(zz[b,a])) for a,b in [(ii,jj),(ii+1,jj),(ii+1,jj+1),(ii,jj+1)]],key)
            else:
                original=None if natural_z is None else [(float(gx[jj,ii]),float(gy[jj,ii]),float(natural_z[jj,ii])) for ii,jj in [(i,j),(i+1,j),(i+1,j+1),(i,j+1)]]
                faces=len(m.faces);emit(pts,key,original)
                if name=='HD_Terrain' and y < -125 and len(m.faces)>faces:
                    n=len(m.faces[-1]);p=np.asarray(m.vertices[-n:]);normal=np.cross(p[1]-p[0],p[-1]-p[0])
                    nz=normal[2]/max(np.linalg.norm(normal),1e-9)
                    colours=shorelines.colours(p[:,0],p[:,1],p[:,2],np.full(n,nz),v.PALETTE[key])
                    m.colors[-n:]=[(*c,0.) for c in colours]
                    m.keys[-1]='coast_sand'
                if key=='hd_grass' and y>=-125 and x<300+layout.ISLAND_FADE and len(m.faces)>faces:
                    # the lawn takes the island ground's colour at its edge (x 300), so the two grasses meet without a line
                    lawn=v.PALETTE['hd_grass'];n=len(m.faces[-1])
                    for k,(px,_,_) in enumerate(m.vertices[-n:]):
                        w=float(layout.island_fade(px));m.colors[len(m.colors)-n+k]=(*(i*(1-w)+h*w for i,h in zip(layout.ISLAND_LAWN,lawn)),0)
    # Inset warm stone paving pattern: broad enough to read without fine texture noise.
    if name=='HD_Terrain':
        for y in np.arange(-119,240,6):
            for x in np.arange(380+(3 if int(y)%2 else 0),1300,6):
                if canal(x+2.9,y+2.9) or grass_patch(x+2.9,y+2.9):continue
                # Street kits own paving here; coarse decorative quads pierced curved shoulders.
                if min(abs(y+2.96-c) for c in ROAD_Y)<11:continue
                # Large old paver quads bridge slope breaks and pierce the finer plaza surface.
                if x<802 and x+5.92>660 and y<218 and y+5.92>122:continue
                # The old six-metre decorative quads would bridge the new terraces.
                px=np.array([x,x+2.96,x+5.92]);py=np.array([y,y+2.96,y+5.92])
                gx,gy=np.meshgrid(px,py)
                if np.max(abs(height(gx,gy)-street_height(gx,gy)))>.01:continue
                points=[(xx,yy,float(height(xx,yy))+.013) for xx,yy in [(x,y),(x+5.92,y),(x+5.92,y+5.92),(x,y+5.92)]]
                emit(points,'hd_flag' if int(x+y)%3 else 'hd_flag2')
    return m

def city_terrain_surfaces():
    """@cc [owner:fontanierh,label:correctness] city-terrain-stage-order
    Capture natural geometry immediately before this owner's local coarse-grid
    railway carve and the air-station apron levelling that follows it, alongside
    the unchanged final emitter. Existing fine patches
    and paving MUST keep their independent uncarved height evaluations in both
    stages. Do not regenerate the final surface, change callbacks/face order,
    infer pristine global ground, or change final colours/palette ownership.
    """
    natural=M('HD_Terrain')
    final=surface('HD_Terrain',*terrain_axes(),'paving',_natural=natural)
    return natural,final
