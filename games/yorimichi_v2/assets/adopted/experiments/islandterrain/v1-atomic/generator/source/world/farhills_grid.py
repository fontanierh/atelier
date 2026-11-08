"""Authoritative original-parent FarHills grid, independent of forest scenery."""
from functools import lru_cache

import numpy as np
from hidamari import mountains
from megapark import trail as park_trail


def source_grid(*, city=True):
    """The original96-parent heights, including existing replacement lowering."""
    from hidamari import layout as H
    from belmonte import terrain as B
    import yori
    axis=np.linspace(-3200.,3200.,96);xx,yy=np.meshgrid(axis,axis)
    grid=H.backdrop_grid().copy() if city else np.load(yori.OUT/'farhills.npy')
    if city:
        mask=mountains.contains(xx,yy)|park_trail.in_approach(xx,yy)
        grid[mask]=np.minimum(grid[mask],H.north_height(xx,yy,carved=False)[mask]-25)
        grid=B.old_backdrop(grid,xx,yy)
    return axis,axis,grid



def mesh_grid(fine_count, *, city=True):
    """@cc [owner:fontanierh,label:correctness] shared-backdrop-source-grid
    Preserve the original96-parent surface through inserted boundary knots,
    including replacement lowering and the no-city fallback. Export and crown
    placement MUST pass source_grid as the original parent topology, before
    applying the separate intended coast/stitch/carve transformations.
    """
    from hidamari import layout as H
    from belmonte import terrain as B
    import yori
    axis,_,grid=source_grid(city=city)
    fine_y=np.unique(np.r_[np.linspace(-300.,300.,fine_count),H.terrain_axes()[1]])
    fine_y=fine_y[(fine_y>=-300.)&(fine_y<=-100.)]
    xs=np.unique(np.r_[axis,-300.,300.,1420.]);ys=np.unique(np.r_[axis,fine_y,-300.,300.,500.])
    xx,yy=np.meshgrid(xs,ys)
    return xs,ys,B.grid_height(axis,axis,grid,xx,yy)



@lru_cache(maxsize=2)
def rail_refinement(*,city=True):
    """@cc [owner:fontanierh,label:correctness] original-grid-railway-sampling
    Derive rail-adjacent parent sampling from the original production earthworks
    planner, before coastal faces can change its mesh-wide density statistic.
    Export and owned placement MUST use the same lattice on immutable generator
    inputs. Shared earthworks defaults and the committed alignment stay unchanged.
    """
    from train import earthworks as E
    line=E.line()
    if line is None:return {}
    xs,ys,z=source_grid(city=city);x,y=np.meshgrid(xs,ys);width=len(xs)
    vertices=np.stack([x,y,z],-1).reshape(-1,3)
    faces=[(j*width+i,j*width+i+1,(j+1)*width+i+1,(j+1)*width+i)
           for j in range(len(ys)-1) for i in range(len(xs)-1)]
    _,_,report=E.polygons(vertices.tolist(),faces,4.,hidden=mountains.contains)
    n=report.get('subdivision',1)
    ax,ay=np.meshgrid(xs[:-1],ys[:-1]);bx,by=np.meshgrid(xs[1:],ys[1:])
    near=np.zeros(ax.shape,bool)
    for u,v in [(0.,0.),(1.,0.),(0.,1.),(1.,1.),(.5,.5),(2/3,1/3),(1/3,2/3)]:
        s,_,_=line.project(ax+(bx-ax)*u,ay+(by-ay)*v)
        near|=np.isfinite(s.reshape(ax.shape))
    return {(int(i),int(j)):n for j,i in zip(*np.nonzero(near))}

