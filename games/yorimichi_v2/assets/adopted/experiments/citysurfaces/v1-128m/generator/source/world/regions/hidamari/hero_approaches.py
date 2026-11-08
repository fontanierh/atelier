"""Flush stone approaches for the station and shrine, on the exported terrain.

Pure geometry: this module can be checked without Blender. Surfaces are split at
terrain cell boundaries, so they never bridge a terrace shoulder or hide a step.
"""
import math
import numpy as np
from hidamari import layout


def _clip(points, boundary):
    """Clip a CCW polygon to a convex CCW boundary (metres, XY)."""
    for a, b in zip(boundary, boundary[1:] + boundary[:1]):
        def side(p):return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])
        result=[]
        if not points:break
        previous=points[-1];sp=side(previous)
        for point in points:
            sq=side(point)
            if (sq>=0)!=(sp>=0):
                t=sp/(sp-sq)
                result.append((previous[0]+t*(point[0]-previous[0]),previous[1]+t*(point[1]-previous[1])))
            if sq>=0:result.append(point)
            previous,sp=point,sq
        points=result
    return points


def _area(points):
    return abs(sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(points,points[1:]+points[:1])))*.5


def approach_specs(city):
    """Local footprints meet existing porch/stair edges; the road stays intact."""
    specs=[]
    pads={p['asset']:p for p in city['terrain_pads'] if p['asset'] in ('HD_Station','HD_Shrine')}
    for asset in ('HD_Station','HD_Shrine'):
        p=pads[asset]
        if p['yaw']!=0:raise ValueError('Hero approaches require the north-facing layout')
        x,y=p['x'],p['y'];start=238.-y  # North edge of the existing y=230 street.
        if asset=='HD_Station':
            shapes=[([(-2.2,start),(2.2,start),(2.2,-25),(-2.2,-25)],'stone'),
                    ([(-2.2,-25),(2.2,-25),(5.,-21),(-5.,-21)],'stone'),
                    ([(-22.,-21),(22.,-21),(24.,-19),(24.,-10.85),(-24.,-10.85),(-24.,-19)],'stone')]
        else:
            # A narrow processional walk, with small gravel shoulders around the
            # torii feet. The basin, bench and lantern remain in their garden.
            shapes=[([(-1.4,start),(1.4,start),(1.4,-4.29),(-1.4,-4.29)],'shrine')]
            for side in (-1,1):
                outline=[(1.4,-9.75),(4.7,-9.75),(5.3,-9.15),(5.3,-7.2),(4.7,-6.6),(1.4,-6.6)]
                if side<0:outline=[(-a,b) for a,b in reversed(outline)]
                shapes.append((outline,'gravel'))
        for polygon,kind in shapes:
            specs.append(dict(asset=asset,kind=kind,datum=p['z'],
                              polygon=[(x+a,y+b) for a,b in polygon],origin=(x,238.)))
    return specs


def hero_approach_faces(city,height):
    """Yield upward faces 14–22 mm above the actual HD_Terrain cell surface.

    Matching the exported grid matters: sampling the analytic blend on a new
    grid can sink an overlay into the rendered terrain. These lots have planar
    cells across X; reject a future layout that violates that instead of guessing
    which diagonal the FBX/Unreal triangulator will choose.
    """
    xs,ys=layout.terrain_axes()
    for spec in approach_specs(city):
        polygon=spec['polygon'];kind=spec['kind'];ox,oy=spec['origin']
        xmin=min(p[0] for p in polygon);xmax=max(p[0] for p in polygon)
        ymin=min(p[1] for p in polygon);ymax=max(p[1] for p in polygon)
        ix0=max(0,int(np.searchsorted(xs,xmin))-1);ix1=min(len(xs)-1,int(np.searchsorted(xs,xmax)))
        iy0=max(0,int(np.searchsorted(ys,ymin))-1);iy1=min(len(ys)-1,int(np.searchsorted(ys,ymax)))
        gx,gy=np.meshgrid(xs[ix0:ix1+1],ys[iy0:iy1+1]);gz=height(gx,gy)
        for j in range(iy1-iy0):
            for i in range(ix1-ix0):
                x0,x1=gx[j,i],gx[j,i+1];y0,y1=gy[j,i],gy[j+1,i]
                shape=_clip([(x0,y0),(x1,y0),(x1,y1),(x0,y1)],polygon)
                if len(shape)<3 or _area(shape)<1e-7:continue
                z00,z10,z01,z11=gz[j,i],gz[j,i+1],gz[j+1,i],gz[j+1,i+1]
                if abs(z00+z11-z10-z01)>.001:
                    raise ValueError(f"Nonplanar approach terrain cell at {x0},{y0}; resample against mesh triangles")
                def lift(points,offset):
                    return [(float(x),float(y),float(z00+(x-x0)/(x1-x0)*(z10-z00)+(y-y0)/(y1-y0)*(z01-z00)+offset)) for x,y in points]
                base=(.235,.228,.207) if kind=='gravel' else (.275,.259,.228)
                yield lift(shape,.014),base
                # Large quiet slabs; a small gravel tessellation only at gate
                # feet. Joints are exposed base skin, not dark raised beams.
                tw,th,gap=(.42,.34,.018) if kind=='gravel' else ((1.4,.95,.025) if kind=='shrine' else (1.6,1.25,.022))
                for row in range(math.floor((min(p[1] for p in shape)-oy)/th),math.floor((max(p[1] for p in shape)-oy)/th)+1):
                    shift=tw*.5*(row%2)
                    for col in range(math.floor((min(p[0] for p in shape)-ox-shift)/tw),math.floor((max(p[0] for p in shape)-ox-shift)/tw)+1):
                        a=ox+shift+col*tw+gap;b=oy+row*th+gap
                        boundary=[(a,b),(a+tw-2*gap,b),(a+tw-2*gap,b+th-2*gap),(a,b+th-2*gap)]
                        if kind=='gravel':
                            w,h=tw-2*gap,th-2*gap
                            boundary=[(a+w*.18,b),(a+w*.77,b),(a+w,b+h*.29),(a+w*.93,b+h*.83),(a+w*.64,b+h),(a+w*.15,b+h*.91),(a,b+h*.55)]
                        tile=_clip(shape,boundary)
                        if len(tile)<3 or _area(tile)<1e-7:continue
                        variation=((row*17+col*31)%7-3)*.004
                        color=(.335,.319,.283) if kind=='stone' else ((.30,.29,.26) if kind=='shrine' else (.27,.267,.245))
                        yield lift(tile,.022),tuple(c+variation for c in color)


def check(city,height):
    """Verify every face vertex and centroid against the exported terrain grid."""
    faces=list(hero_approach_faces(city,height))
    points=np.array([p for poly,_ in faces for p in poly]+[np.mean(poly,axis=0) for poly,_ in faces])
    x,y,z=points.T;xs,ys=layout.terrain_axes()
    i=np.searchsorted(xs,x,side='right')-1;j=np.searchsorted(ys,y,side='right')-1
    z00=height(xs[i],ys[j]);z10=height(xs[i+1],ys[j]);z01=height(xs[i],ys[j+1]);z11=height(xs[i+1],ys[j+1])
    u=(x-xs[i])/(xs[i+1]-xs[i]);v=(y-ys[j])/(ys[j+1]-ys[j])
    surface=z00*(1-u)*(1-v)+z10*u*(1-v)+z01*(1-u)*v+z11*u*v
    offset=z-surface
    assert offset.min()>.013 and offset.max()<.023, 'Paving floats or penetrates terrain'
    assert y.min()==238., 'Approach paints over the street'
    assert np.max(abs(z00+z11-z10-z01))<.001, 'Terrain diagonal is ambiguous'
    for poly,_ in faces:
        assert sum(p[0]*q[1]-q[0]*p[1] for p,q in zip(poly,poly[1:]+poly[:1]))>0, 'Downward face'
    for spec in approach_specs(city):
        if spec['asset']=='HD_Station':
            root=[(1176.5,264.5),(1177.5,264.5),(1177.5,265.5),(1176.5,265.5)]
            assert not _clip(root,spec['polygon']), 'Forecourt enters station tree roots'
    for asset,end in [('HD_Station',-10.85),('HD_Shrine',-4.29)]:
        pad=next(p for p in city['terrain_pads'] if p['asset']==asset)
        assert abs(float(height(pad['x'],pad['y']+end))-pad['z'])<.001, 'Approach misses entrance datum'
    return dict(faces=len(faces),triangles=sum(len(p)-2 for p,_ in faces),
                ground_probes=len(points),offset_mm=[float(offset.min()*1000),float(offset.max()*1000)])


if __name__=='__main__':
    import json
    print(json.dumps(check(json.loads((layout.OUT/'city.json').read_text()),layout.height),indent=2))
