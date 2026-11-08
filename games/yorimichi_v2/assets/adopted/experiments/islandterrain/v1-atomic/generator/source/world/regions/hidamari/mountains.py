"""Northern foothills and a distant volcanic summit, in Blender world metres.

One sampled surface drives mesh, trees, trail and map. The accessible trail rises
gradually out of the park; the large summit is a scenic landmark beyond it.
"""
import math
from functools import lru_cache
import numpy as np
from megapark import placement as megapark
from craterpark import placement as craterpark

from belmonte import layout as belmonte
from belmonte.layout import SOUTH_JOIN
from hidamari.natural_terrain import (  # noqa: F401 - preserve the established mountains API
    BASE_RADIUS, CRAG_STEP, CREST, DEPTH, FLOOR_RADIUS,
    FORMER, LIFT, LOW_STRETCH, MEGAPARK_SHOULDER, RIM_RADIUS,
    STEP, TRAIL, VOLCANO, smooth, trail_distance,
    noise, polar, rim_radius, wall_foot, apron_height,
    stretch, lifted, drainage, former_drainage, drainage_field,
    _foothills, _cone, _former_cone, caldera_floor, natural_height,
    _barycentric, downslope_noise, GRID_ORIGIN,
)

# The foothills reach north to Belmonte's southern join (belmonte/layout.py).
BOUNDS = (*GRID_ORIGIN, 2400., SOUTH_JOIN)
SNOW_STEP = 2.5
SNOW_BOUNDS = (VOLCANO[0]-1280., VOLCANO[1]-1280., VOLCANO[0]-1280.+1023*SNOW_STEP, VOLCANO[1]-1280.+1023*SNOW_STEP)

def contains(x,y):
    return (x>=BOUNDS[0])&(x<=BOUNDS[2])&(y>=BOUNDS[1])&(y<=BOUNDS[3])


def raw_height(x,y,base,shoulder=None):
    x,y=np.broadcast_arrays(np.asarray(x,float),np.asarray(y,float))
    north=np.maximum(y-500,0)
    # The Mega Park sits in the western foothills and Crater Park on the caldera floor; the relief around each is eased
    # to meet its edges.
    target=megapark.terrain(x,y,natural_height(x,y),natural_height)
    target=craterpark.terrain(x,y,target,natural_height)
    leave=smooth(north/180)
    if shoulder is not None:
        # West of the city the far hills' shoulder (`shoulder`, the base at y=500) stood 40-60 m over the apron, a trough
        # across the Mega Park trail; the ground now leaves the shoulder within 60 m, before the far hills rise again,
        # and falls gently from it north to the foothills.
        west=smooth((420-x)/220)
        d=np.asarray(shoulder)-.11*north-target
        target=target+west*(1-smooth((y-760)/160))*(d+np.sqrt(d*d+36))/2
        leave=leave*(1-west)+smooth(north/60)*west
    # Along Belmonte's apron (belmonte/terrain.py collar) the north edge is joined as it stands, so the volcano's
    # northern foot runs on into the valley; east of the apron it eases back to the country as on the other sides.
    north_edge=1-(1-smooth((BOUNDS[3]-y)/210))*(1-smooth((belmonte.BOUNDS[2]+belmonte.APRON-x)/250))
    edge=smooth((x-BOUNDS[0])/200)*smooth((BOUNDS[2]-x)/200)*north_edge*leave
    return np.asarray(base)*(1-edge)+target*edge

def surface_grid(base_sampler):
    return _surface_grid(base_sampler, _park_identity())


def _park_identity():
    if craterpark.is_v4():
        from craterpark.v2 import v4_placement
        return v4_placement.identity()
    return None


@lru_cache(maxsize=4)
def _surface_grid(base_sampler, park_identity):
    xs=np.arange(BOUNDS[0],BOUNDS[2]+1,STEP);ys=np.arange(BOUNDS[1],BOUNDS[3]+1,STEP)
    x,y=np.meshgrid(xs,ys)
    z=raw_height(x,y,base_sampler(x,y),base_sampler(x,np.full_like(y,BOUNDS[1])))
    # The Mega Park trail's bed (megapark/trail.py) runs through the western foothills, and the Mega Park air station
    # stands on a levelled pad by the park's top road (zeppelin/layout.py).
    from megapark import trail as park_trail
    from zeppelin.layout import megapark_pad
    # Neither raises the ground under the park (megapark.terrain keeps it below the park's surfaces).
    carved=park_trail.carve(x,y,z,reach=park_trail.CARVE_COARSE[0],fade=park_trail.CARVE_COARSE[1])
    z=np.where(megapark.contains(x,y),np.minimum(z,carved),carved)
    return x,y,megapark_pad(x,y,z)

def _cell(x,y):
    x,y=np.broadcast_arrays(np.asarray(x,float),np.asarray(y,float))
    ix=np.clip(np.floor((x-BOUNDS[0])/STEP).astype(int),0,int((BOUNDS[2]-BOUNDS[0])/STEP)-1)
    iy=np.clip(np.floor((y-BOUNDS[1])/STEP).astype(int),0,int((BOUNDS[3]-BOUNDS[1])/STEP)-1)
    return ix,iy,np.clip((x-BOUNDS[0])/STEP-ix,0,1),np.clip((y-BOUNDS[1])/STEP-iy,0,1)


def height(x,y,base_sampler,*,carved=True):
    """Barycentric sampling of the single cached grid exported as actual collision, with the first row next to the
    city as sheets() emits it (_city_edge_row), so placement stands on the rendered surface."""
    ix,iy,u,v=_cell(x,y)
    z=surface_grid(base_sampler)[2]
    out=_barycentric(z[iy,ix],z[iy,ix+1],z[iy+1,ix],z[iy+1,ix+1],u,v)
    out=_city_edge_row(ix,iy,u,v,z,out)
    if carved:
        from train import earthworks
        out=earthworks.carve(x,y,out)
    return out

def _city_edge_row(ix,iy,u,v,z,out):
    """The first row's cells along the city's north edge exactly as sheets() triangulates them: the bottom edge is the
    city's polyline (layout.city_north_edge, the 5 m vertices snapped onto it); a cell with city knots inside fans
    them to its top-left corner, plus the (b, c, d) triangle; any other cell keeps the a-c split."""
    row=(iy==0)
    if not np.any(row):return out
    from hidamari.layout import city_north_edge
    kx,kz=city_north_edge()
    x0=BOUNDS[0]+ix*STEP;x1=x0+STEP
    row&=(x0>=kx[0])&(x1<=kx[-1])
    if not np.any(row):return out
    i,uu,vv,a,b=ix[row],u[row],v[row],x0[row],x1[row]
    za,zb,zc,zd=np.interp(a,kx,kz),np.interp(b,kx,kz),z[1,i+1],z[1,i]
    inner=np.searchsorted(kx,b,side='left')>np.searchsorted(kx,a,side='right')
    plain=_barycentric(za,zb,zd,zc,uu,vv)
    # Fan: the ray from the top-left corner d through the point meets the bottom polyline at xb.
    xb=a+uu*STEP/np.maximum(1-vv,1e-12)
    fan=np.where(xb<=b,(1-vv)*np.interp(np.minimum(xb,b),kx,kz)+vv*zd,zd+(zc-zd)*uu-(zc-zb)*(1-vv))
    out=np.array(out,float,copy=True)
    out[row]=np.where(inner,fan,plain)
    return out

def on_grid(x,y,field):
    """field(x, y) at the grid's nodes round each (x, y), sampled as height() samples the grid: what the ground would be
    if field were the grid."""
    ix,iy,u,v=_cell(x,y)
    def node(i,j):
        return field(BOUNDS[0]+i*STEP,BOUNDS[1]+j*STEP)
    return _barycentric(node(ix,iy),node(ix+1,iy),node(ix,iy+1),node(ix+1,iy+1),u,v)

def colours(x,y,z):
    """The ground's vertex colours: grass on the apron, forest green, and rock high up."""
    rock_noise=noise(x,y,26,9)*.65+noise(x,y,85,20)*.35
    radius=polar(x,y)[2]
    floor=apron_height(y)
    # Rising backdrop ground is still woodland. Exposed rock belongs to the
    # actual volcanic relief above its local apron, not an absolute elevation.
    forest=smooth((z-floor-135*LIFT+noise(x,y,125,27)*28)/(160*LIFT))*smooth((stretch(1120)-radius)/180)
    # Light grey granite with a trace of lavender (the Sunburst targets: lit faces about sRGB 165, 162, 168); a bluer mix
    # read purple under the sky light. Sparse olive lichen.
    rock=np.stack([.150+.028*rock_noise,.145+.028*rock_noise,.155+.030*rock_noise],axis=-1)
    lichen=smooth((noise(x,y,12,99)-.5)/.20)
    rock*=np.stack([1+.04*lichen,1+.07*lichen,1-.12*lichen],axis=-1)
    green=np.stack([.055+.015*noise(x,y,85,12),.11+.018*noise(x,y,90,14),np.full_like(x,.035)],axis=-1)
    colors=green*(1-forest[...,None])+rock*forest[...,None]
    # An olive alpine meadow between the forest's ceiling and the cliffs (f_city2), patchy, scattered with pines.
    meadow=(smooth((z-lifted(270)+noise(x,y,70,86)*25)/(30*LIFT))*smooth((lifted(360)-z+noise(x,y,90,87)*30)/(30*LIFT))
            *smooth((noise(x,y,45,88)+.55)/.3)*smooth((stretch(1120)-radius)/180))
    grass=np.stack([.15+.03*noise(x,y,30,89),.165+.02*noise(x,y,30,89),np.full_like(x,.045)],axis=-1)
    colors=colors*(1-.85*meadow[...,None])+grass*.85*meadow[...,None]
    # The south edge meets the city's grass (x 300-1420) in its light apron grass, and the far hills' forest floor
    # (build_terrain.py FarHills, M_ForestGround) elsewhere in that floor's colour, as the north edge does: a light band
    # there read as a pale strip against the dark forest below it.
    city=smooth((x-240)/60)*smooth((1480-x)/60)
    edge=np.array((.24,.30,.12))*city[...,None]+np.array((.055,.11,.035))*(1-city[...,None])
    apron=smooth((y-500)/190)
    colors=edge*(1-apron[...,None])+colors*apron[...,None]
    # Round the Mega Park the ground under the closed canopy is forest floor, leaf litter and moss (megapark/forest.py).
    from megapark import forest as megapark_forest
    under=megapark_forest.floor(x,y)*(1-smooth((z-205)/30))
    litter=noise(x,y,40,41)
    floor=np.stack([.066+.018*litter,.062+.014*litter,np.full_like(x,.026)],axis=-1)
    colors=colors*(1-under[...,None])+floor*under[...,None]
    t=smooth((y-(SOUTH_JOIN-420))/420)
    join=smooth(np.clip(t+t*(1-t)*noise(x,y,140,82)*.7,0,1))
    palette=np.array([.055,.11,.035])
    return colors*(1-join[...,None])+palette*join[...,None]

def shade_height(z,step):
    shade_z=z.copy()
    for _ in range(max(1,round(16/(step*step)))):
        padded=np.pad(shade_z,1,mode='edge')
        shade_z=(padded[1:-1,1:-1]+padded[:-2,1:-1]+padded[2:,1:-1]+padded[1:-1,:-2]+padded[1:-1,2:])/5
    return shade_z

def relief_curvature(z,step=STEP):
    dy,dx=np.gradient(shade_height(z,step),step,step)
    lap=np.gradient(dx,step,axis=1)+np.gradient(dy,step,axis=0)
    for _ in range(round(3*(10/step)**2)):
        padded=np.pad(lap,1,mode='edge')
        lap=(padded[1:-1,1:-1]+padded[:-2,1:-1]+padded[2:,1:-1]+padded[1:-1,:-2]+padded[1:-1,2:])/5
    return smooth((-lap-.002)/.006),smooth((lap-.001)/.005)



def snow_cover(x,y,z,step=STEP):
    """Snow in drainage hollows and the crater bowl, with bare convex crests."""
    _,_,radius,angle=polar(x,y)
    signed=np.full(x.shape,-1e9)
    pinch=.65+.35*smooth((noise(x,y,55,52)+.4)/.8)
    # Each gully holds its own share of snow, and about half hold none, so the flanks never read as a sunburst; those
    # that hold it run long and unbroken from the crest (the city target's few couloirs, not many short dashes).
    segments=drainage();per=len(segments)//40
    rng=np.random.default_rng(413)
    share=rng.uniform(.6,1.,40)*(rng.random(40)>.5)
    # Most tributaries stay bare, and every ribbon wanders, so the flank never shows ruled lines.
    branch=rng.random(40)<.3
    wx,wy=x+noise(x,y,60,58)*10,y+noise(x,y,60,59)*10
    for k,(a,b) in enumerate(segments):
        if not share[k//per] or (k%per>=5 and not branch[k//per]):
            continue
        dx,dy=b[0]-a[0],b[1]-a[1]
        t=np.clip(((wx-a[0])*dx+(wy-a[1])*dy)/(dx*dx+dy*dy),0,1)
        distance=np.hypot(wx-a[0]-t*dx,wy-a[1]-t*dy)
        # The ribbons widen with the cone, so the cap keeps its share of snow.
        width=(a[2]*(1-t)+b[2]*t)*pinch*LIFT*1.1*share[k//per]
        signed=np.maximum(signed,np.where(width>0,np.maximum(width,2.),0)-distance)
    # Rock frays each streak's edges further down.
    breakup=downslope_noise(radius,angle,38,31,.4)*6+noise(x,y,83,32)*4+downslope_noise(radius,angle,14,33,.4)*2.5
    signed+=noise(x,y,25,19)*2+.3*breakup*smooth((radius-stretch(150))/160)
    # Noise stretched downslope (the cone's radius), so rock breaks a streak into lengths, not round holes.
    streak=lambda s,seed:downslope_noise(radius,angle,s,seed)
    # Gaps along each streak below the rim, where ribs of rock cross it.
    signed-=3*smooth((streak(30,34)+streak(12,35)*.4-.45)/.3)*smooth((radius-rim_radius(angle)-20)/40)
    # Each seeded ribbon already has a different reach; this broad weather
    # field breaks the snowline without a concentric cut across every gully.
    ribbons=smooth(signed/6)*smooth((stretch(640)+noise(x,y,220,51)*120-radius)/120)
    dy,dx=np.gradient(shade_height(z,step),step,step)
    nz=1/np.sqrt(1+dx*dx+dy*dy)
    crest,gully=relief_curvature(z,step)
    # Small sheltered patches on the high benches, broken by fine noise rather than broad blobs.
    patches=noise(x,y,32,41)+noise(x,y,13,42)*.45+noise(x,y,90,43)*.4
    faces=smooth((z-lifted(420))/(90*LIFT))*smooth((nz-.85)/.08)*smooth((patches-.6)/.2)*(1-crest)
    ring=lambda r,s,seed:noise(np.cos(angle)*r,np.sin(angle)*r,s,seed)
    foot=wall_foot(angle);rim_r=rim_radius(angle)
    # The caldera floor is grey cinder with snow lying in patches and in drifts along the wall's foot.
    floor_r=foot-10+25*ring(240.,60.,95)
    floor=smooth((floor_r-radius)/12)*smooth((noise(x,y,48,96)*.75+noise(x,y,19,98)*.3+.06)/.22)
    drifts=(smooth((radius-foot+30)/20)*smooth((foot+12-radius)/10)
            *smooth((downslope_noise(radius,angle,22,94)+ring(300.,45.,92)*.5-.1)/.3))
    # Snow on the inner wall's flatter ledges and benches, broken by fine noise (the targets' snow between crags).
    ledges=(smooth((nz-.80)/.06)*smooth((patches-.55)/.2)*smooth((radius-foot-5)/10)*smooth((rim_r-12-radius)/10))
    # Broad couloirs down the inner wall (the zeppelin target): snow gathered in its hollows from just under the crest
    # to the foot, tens of metres wide and wandering, so they never read as thin frozen falls; no fan at the foot, which
    # stood up behind the park as white blades from the rim.
    wander=angle+noise(x,y,70,99)*.06
    lane=noise(np.cos(wander)*470,np.sin(wander)*470,30.,97)+.5*gully+.3*downslope_noise(radius,wander,35,91)
    # Each narrows upward to a point at its own height under the crest: a flat top stood up as a slab from the rim.
    top=rim_r-12-20*smooth((noise(np.cos(wander)*470,np.sin(wander)*470,25.,93)+.4)/.8)
    up=np.clip((radius-foot)/np.maximum(rim_r-foot,1.),0,1)
    chutes=smooth((lane-.38-.35*up*up)/.14)*smooth((radius-foot+15)/12)*smooth((top-radius)/8)
    bowl=np.maximum.reduce([floor,drifts,ledges,chutes])
    rim=np.exp(-((radius-rim_r)/28)**2)
    inside=smooth((rim_r-20-radius)/14)
    # Many short streaks follow the relief's own hollows high on the cone, broken by rock.
    hollows=(smooth((gully-.35)/.3)*smooth((z-lifted(320))/(110*LIFT))
             *smooth((downslope_noise(radius,angle,30,36)+downslope_noise(radius,angle,12,37)*.5+.3)/.3))
    snow=np.maximum.reduce([np.maximum(ribbons*(1-.75*crest),hollows)*(1-inside),
                            faces*(1-inside),bowl])
    snow=np.clip(snow,0,1)*(1-.92*rim*(1-bowl))
    # Outside, snow lies heaviest in a broken collar just under the crest, gathering in its hollows.
    collar=(smooth((radius-rim_r-14)/16)*smooth((rim_r+60+35*ring(470.,80.,45)-radius)/35)
            *smooth((noise(x,y,17,44)+noise(x,y,8,46)*.3+.6*gully-.15)/.25)*(1-.5*crest))
    # Snowfields just under the crest between bare rock ribs, stretched downslope; lower down only thin couloirs
    # (the ribbons) hold snow, so the far views read rock with a few streaks (f_belmonte, f_city2).
    flank=(smooth((radius-rim_r-10)/20)*smooth((rim_r+110+40*ring(470.,90.,57)-radius)/50)
           *smooth((downslope_noise(radius,angle,45,55,.5)+noise(x,y,18,56)*.35+.5*gully-.7*crest-.35)/.2))
    snow=np.maximum(snow,flank)
    line=smooth((z-lifted(230)-noise(x,y,180,83)*40*LIFT)/(90*LIFT))
    # The collar and the chutes hold snow on steeper ground than the open slopes do; nothing else lies on rock past
    # about 55 degrees.
    steep=np.maximum(collar*smooth((nz-.45)/.15),chutes*smooth((nz-.40)/.12))
    cover=np.clip(np.maximum(snow*smooth((nz-.55)/.10),steep),0,1)
    # Rock breaks every patch into many small pieces (the targets' snow among broken granite, not cut-out blobs).
    rock=noise(x,y,7,120)+noise(x,y,3,121)*.5+noise(x,y,16,122)*.4
    return cover*smooth((rock+1.)/.3)*line

def snow_grid(base_sampler):
    return _snow_grid(base_sampler, _park_identity())


@lru_cache(maxsize=4)
def _snow_grid(base_sampler, park_identity):
    xs=np.arange(SNOW_BOUNDS[0],SNOW_BOUNDS[2]+1,SNOW_STEP)
    ys=np.arange(SNOW_BOUNDS[1],SNOW_BOUNDS[3]+1,SNOW_STEP)
    x,y=np.meshgrid(xs,ys)
    cover=snow_cover(x,y,height(x,y,base_sampler,carved=False),SNOW_STEP)
    # The same bytes drive the material and planting; filtering is bilinear.
    return np.rint(np.clip(cover,0,1)*255).astype(np.uint8)


# Preserve callers that explicitly clear derived caches after changing a sampler.
surface_grid.cache_clear = _surface_grid.cache_clear
snow_grid.cache_clear = _snow_grid.cache_clear

def snow(x,y,base_sampler):
    x,y=np.broadcast_arrays(np.asarray(x,float),np.asarray(y,float))
    field=snow_grid(base_sampler)
    px=np.clip((x-SNOW_BOUNDS[0])/SNOW_STEP,0,field.shape[1]-1.001)
    py=np.clip((y-SNOW_BOUNDS[1])/SNOW_STEP,0,field.shape[0]-1.001)
    ix=px.astype(int);iy=py.astype(int);u=px-ix;v=py-iy
    value=((field[iy,ix].astype(float)*(1-u)+field[iy,ix+1]*u)*(1-v)
           +(field[iy+1,ix]*(1-u)+field[iy+1,ix+1]*u)*v)/255.
    inside=(x>=SNOW_BOUNDS[0])&(x<=SNOW_BOUNDS[2])&(y>=SNOW_BOUNDS[1])&(y<=SNOW_BOUNDS[3])
    return np.where(inside,value,0.)

def _r8_png(field):
    """A greyscale 8-bit PNG of `field` (uint8, row zero first)."""
    import struct,zlib
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    rows=b''.join(b'\0'+row.tobytes() for row in field)
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',field.shape[1],field.shape[0],8,0,0,0,0))
            +chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b''))

def export_snow_mask(output,base_sampler):
    """Linear R8 PNG, row zero at minimum world y, sampled at texel centres."""
    import json
    field=snow_grid(base_sampler)
    assert not any(np.any(edge) for edge in (field[0],field[-1],field[:,0],field[:,-1])),'Snow mask clips its footprint'
    png=_r8_png(field)
    (output/'north_snow.png').write_bytes(png)
    meta={'bounds':SNOW_BOUNDS,'step_m':SNOW_STEP,'size':[field.shape[1],field.shape[0]],
          'linear':True,'row_zero_world_y':SNOW_BOUNDS[1],'filter':'bilinear, clamp, texel-centred',
          # The ground material's exposed-rock band (mountain_material.py) and its join to Belmonte's palette.
          'volcano_m':list(VOLCANO),'rock_radius_m':[float(stretch(940)),float(stretch(1120))],
          'rock_prominence_m':[130*LIFT,250*LIFT],'south_join_m':SOUTH_JOIN}
    (output/'north_snow.json').write_text(json.dumps(meta,indent=2)+'\n')
    print('NORTH SNOW MASK',field.shape,len(png),'bytes',flush=True)

# The caldera floor's painted ground (tools/craterpark_textures.py 'crater_floor', the editor park's Sunburst floor):
# M_NorthMountains lays it over the floor and the foot of the wall, CRATER_REACH beyond the wall's foot, fading over
# CRATER_FADE, so the crags above keep their rock.
CRATER_REACH = 20.
CRATER_FADE = 25.

def crater_floor(x,y):
    """How much of the painted crater floor lies at (x, y): 1 on the caldera floor, 0 up the wall's crags."""
    _,_,radius,angle=polar(x,y)
    return smooth((wall_foot(angle)+CRATER_REACH-radius)/CRATER_FADE)

def crater_grid():
    """crater_floor on the snow mask's texels (the same footprint and step), uint8."""
    xs=np.arange(SNOW_BOUNDS[0],SNOW_BOUNDS[2]+1,SNOW_STEP)
    ys=np.arange(SNOW_BOUNDS[1],SNOW_BOUNDS[3]+1,SNOW_STEP)
    x,y=np.meshgrid(xs,ys)
    return np.rint(np.clip(crater_floor(x,y),0,1)*255).astype(np.uint8)

def export_crater_mask(output):
    """north_crater.png/json: crater_floor as a linear R8 PNG on the snow mask's footprint (row zero at minimum world
    y, texel centres), for M_NorthMountains."""
    import json
    field=crater_grid()
    assert not any(np.any(edge) for edge in (field[0],field[-1],field[:,0],field[:,-1])),'Crater mask clips its footprint'
    png=_r8_png(field)
    (output/'north_crater.png').write_bytes(png)
    meta={'bounds':SNOW_BOUNDS,'step_m':SNOW_STEP,'size':[field.shape[1],field.shape[0]],
          'linear':True,'row_zero_world_y':SNOW_BOUNDS[1],'filter':'bilinear, clamp, texel-centred'}
    (output/'north_crater.json').write_text(json.dumps(meta,indent=2)+'\n')
    print('NORTH CRATER MASK',field.shape,len(png),'bytes',flush=True)

def sheets(base_sampler):
    """@cc [owner:fontanierh,label:correctness] north-mountain-sheet-order
    Preserve the existing grid, gate holes, apron part order and authored
    colours/mask/normals before the single earthworks.sheet call. The only
    vertices added to the grid are HD_Terrain's own edge vertices along the
    city's north edge (layout.city_north_edge), inserted into the first row's
    cells with interpolated attributes so the two meshes share that edge. Return that
    natural sheet and the final sheet without resampling attributes after carve.
    No-line identity and earthworks interpolation remain unchanged.
    """
    xs=np.arange(BOUNDS[0],BOUNDS[2]+1,STEP);ys=np.arange(BOUNDS[1],BOUNDS[3]+1,STEP)
    x,y,z=surface_grid(base_sampler)
    colors=colours(x,y,z)
    crest,gully=relief_curvature(z)
    _,_,radius,angle=polar(x,y)
    prominence=z-apron_height(y)
    exposed=smooth((prominence-135*LIFT)/(120*LIFT))*smooth((stretch(1120)-radius)/180)
    cavity=(1-.45*gully)*(1+.15*crest)
    rim=np.exp(-((radius-rim_radius(angle))/40)**2)
    colors*=((1-exposed)+exposed*cavity*(1-.35*rim))[...,None]
    dy,dx=np.gradient(z,STEP,STEP)
    # Steep exposed rock reads as darker cliff bands with uneven strata, so walls are crags rather than smooth clay.
    nz=1/np.sqrt(1+dx*dx+dy*dy)
    cliff=smooth((.8-nz)/.22)*exposed
    strata=.5+.5*np.sin(z*.6+noise(x,y,40,61)*3.)
    colors*=(1-cliff*(.22+.14*strata))[...,None]
    # Olive lichen and moss on the rock's gentler, upward faces (the targets' granite), never on the cliffs.
    moss=smooth((noise(x,y,18,99)+noise(x,y,6,98)*.3-.25)/.18)*smooth((nz-.68)/.15)*exposed
    colors=colors*(1-.75*moss[...,None])+np.array([.20,.21,.055])*.75*moss[...,None]
    normals=np.stack([-dx,-dy,np.ones_like(z)],-1)
    normals/=np.linalg.norm(normals,axis=-1,keepdims=True)
    # Soft continuous snow masks replace hard clipped lavender polygons.
    mask=snow(x,y,base_sampler)
    # The gate's finer patch replaces these cells by the Mega Park's air station (megapark/gate.py, HD_NorthGate).
    from megapark import gate
    faces=[]
    width=len(xs)
    P=np.stack([x,y,z],-1).reshape(-1,3);A=np.dstack([colors,mask]).reshape(-1,4);N=normals.reshape(-1,3)
    # Along the city's north edge (y=BOUNDS[1]) the edge belongs to HD_Terrain, whose 4 m knots fall between these 5 m
    # ones where its profile bends (x 300-370 by up to 0.11 m, Op410 review): its own edge vertices are inserted into the
    # first row's cells, fanned to their top corners, so both meshes share one edge polyline.
    from hidamari.layout import city_north_edge
    knots=city_north_edge();extra=[]
    # The foothills' own edge vertices there move onto that polyline (by up to 0.06 m), so the edge is the city's.
    on=(xs>=knots[0][0])&(xs<=knots[0][-1])
    P[np.flatnonzero(on),2]=np.interp(xs[on],*knots)
    for j in range(len(ys)-1):
        for i in range(len(xs)-1):
            if gate.cell_inside(x[j,i],y[j,i],STEP):continue
            a=j*width+i;b=a+1;c=a+width+1;d=a+width
            inner=[] if j else [(kx,kz) for kx,kz in zip(*knots) if xs[i]<kx<xs[i+1]]
            if not inner:
                faces.extend([(a,b,c),(a,c,d)]);continue
            chain=[a]
            for kx,kz in inner:
                t=(kx-xs[i])/(xs[i+1]-xs[i]);n=N[a]*(1-t)+N[b]*t
                chain.append(len(P)+len(extra));extra.append(((kx,ys[0],kz),A[a]*(1-t)+A[b]*t,n/np.linalg.norm(n)))
            chain.append(b)
            faces.extend([(p,q,d) for p,q in zip(chain,chain[1:])]+[(b,c,d)])
    if extra:
        P=np.concatenate([P,[e[0] for e in extra]]);A=np.concatenate([A,[e[1] for e in extra]]);N=np.concatenate([N,[e[2] for e in extra]])
    faces=np.asarray(faces,dtype=np.int32)
    used=np.unique(faces);remap=np.full(len(P),-1,dtype=np.int32);remap[used]=np.arange(len(used))
    parts=[(P[used],remap[faces],A[used],N[used])]
    parts+=[_apron_part(*grid,base_sampler) for grid in apron_grids(xs,ys)]
    offsets=np.cumsum([0]+[len(p[0]) for p in parts])
    sheet=dict(vertices=np.concatenate([p[0] for p in parts]),faces=np.concatenate([p[1]+o for p,o in zip(parts,offsets)]),
               colours=np.concatenate([p[2] for p in parts]),normals=np.concatenate([p[3] for p in parts]))
    from train import earthworks  # the Belmonte railway's cuttings, banks and portal holes (RAILWAY_EARTHWORKS=0: none)
    return sheet,earthworks.sheet(sheet)


def mesh(base_sampler):
    """Existing direct callers receive the same final attributed sheet."""
    return sheets(base_sampler)[1]


def apron_grids(xs,ys):
    """The far hills' last coarse cells round the foothills' south, west and east edges, as (x, y) axes. build_terrain.py
    lowers every far-hill vertex under the foothills 25 m, so these cells sag from the edge down to their lowered corners,
    and the ground's edge stood over a 20-30 m open slit (the hole seen from the zeppelin west of the city, and the trees
    floating east of it). An apron at the far hills' own height closes each, from the edge to the coarse grid's first
    unlowered line, where it meets the far hills exactly. North of y=3200 Belmonte's ground joins instead."""
    FAR_AXIS=_far_axis()
    step=FAR_AXIS[1]-FAR_AXIS[0]
    south=FAR_AXIS[FAR_AXIS<BOUNDS[1]][-1];west=FAR_AXIS[FAR_AXIS<BOUNDS[0]][-1];east=FAR_AXIS[FAR_AXIS>BOUNDS[2]][0]
    def axis(a,b):return np.linspace(a,b,max(2,int(math.ceil((b-a)/STEP))+1))
    rows=ys[ys<=FAR_AXIS[-1]]
    assert step>STEP
    return [(np.concatenate([[west],xs,[east]]),axis(south,BOUNDS[1])),(axis(west,BOUNDS[0]),rows),(axis(BOUNDS[2],east),rows)]

def apron_cell_open(x,y):
    """Whether an apron cell is the far hills' (not the city's terrain, nor the Mega Park trail's approach, which have
    their own edges)."""
    from megapark.trail import in_approach
    city=(x>=300)&(x<=1420)&(y>=-300)&(y<=BOUNDS[1])
    return ~city&~in_approach(x,y)

def skirt_height(x,y,base_sampler):
    """The apron's ground: the far hills' (hidamari/layout.py far_height), eased in the south band to the foothills'
    base at their edge (it is lifted beside the city), so the apron meets both exactly."""
    from hidamari.layout import far_height
    x,y=np.broadcast_arrays(np.asarray(x,float),np.asarray(y,float))
    south=_far_axis()[_far_axis()<BOUNDS[1]][-1]
    t=np.clip((y-south)/(BOUNDS[1]-south),0,1)*(y<BOUNDS[1])
    edge=np.asarray(base_sampler(x,np.full_like(y,BOUNDS[1])),float)-far_height(x,np.full_like(y,BOUNDS[1]))
    return np.where(y<BOUNDS[1],far_height(x,y)+edge*t,np.asarray(base_sampler(x,y),float))

def in_apron(x,y):
    """Whether (x, y) lies on the apron (apron_grids), off the foothills' own footprint."""
    x,y=np.broadcast_arrays(np.asarray(x,float),np.asarray(y,float))
    axis=_far_axis();south=axis[axis<BOUNDS[1]][-1];west=axis[axis<BOUNDS[0]][-1];east=axis[axis>BOUNDS[2]][0]
    band=(x>=west)&(x<=east)&(y>=south)&(y<=min(BOUNDS[3],axis[-1]))&~contains(x,y)
    out=np.zeros(x.shape,bool)
    if band.any():out[band]=apron_cell_open(x[band],y[band])
    return out

def _far_axis():
    from hidamari.layout import backdrop_grid
    return np.linspace(-3200,3200,backdrop_grid().shape[0])     # build_terrain.py's FarHills grid

def _apron_part(ax,ay,base_sampler):
    x,y=np.meshgrid(ax,ay);z=skirt_height(x,y,base_sampler)
    tint=np.dstack([colours(x,y,z),snow(x,y,base_sampler)])
    w=len(ax);faces=[]
    open_=apron_cell_open((x[:-1,:-1]+x[1:,1:])/2,(y[:-1,:-1]+y[1:,1:])/2)
    for j,i in zip(*np.nonzero(open_)):
        a=j*w+i;b=a+1;c=a+w+1;d=a+w
        faces.extend([(a,b,c),(a,c,d)])
    dy,dx=np.gradient(z,ay,ax) if min(z.shape)>1 else (np.zeros_like(z),np.zeros_like(z))
    normals=np.stack([-dx,-dy,np.ones_like(z)],-1);normals/=np.linalg.norm(normals,axis=-1,keepdims=True)
    faces=np.asarray(faces,dtype=np.int32).reshape(-1,3)
    used=np.unique(faces);remap=np.full(x.size,-1,dtype=np.int32);remap[used]=np.arange(len(used))
    return (np.stack([x,y,z],-1).reshape(-1,3)[used],remap[faces],tint.reshape(-1,4)[used],normals.reshape(-1,3)[used])


def trail_mesh(surface):
    from village.mesh import Mesh
    m=Mesh('HD_NorthTrail')
    for a,b in zip(TRAIL,TRAIL[1:]):
        dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
        nx,ny=-dy/length,dx/length
        for k in range(math.ceil(length/2)):
            t=k/math.ceil(length/2);nt=(k+1)/math.ceil(length/2)
            points=[]
            for q,s in [(t,-1),(nt,-1),(nt,1),(t,1)]:
                xx=a[0]+q*dx+nx*s*2.1;yy=a[1]+q*dy+ny*s*2.1
                points.append((xx,yy,float(surface(xx,yy))+.045))
            m.poly(points,(.24,.17,.095))
    # Rounded joins cover the outside wedge at each change in direction.
    for x,y in TRAIL[1:-1]:
        points=[]
        for i in range(16):
            a=i*math.tau/16;xx=x+2.1*math.cos(a);yy=y+2.1*math.sin(a)
            points.append((xx,yy,float(surface(xx,yy))+.05))
        for i in range(16):
            m.poly([(x,y,float(surface(x,y))+.05),points[i],points[(i+1)%16]],(.24,.17,.095))
    return m

def trail_points(surface):
    points=[]
    for a,b in zip(TRAIL,TRAIL[1:]):
        n=math.ceil(math.dist(a,b)/2)
        for k in range(n):
            t=k/n;x=a[0]+(b[0]-a[0])*t;y=a[1]+(b[1]-a[1])*t
            points.append([x,y,float(surface(x,y))])
    x,y=TRAIL[-1];points.append([x,y,float(surface(x,y))])
    return points
