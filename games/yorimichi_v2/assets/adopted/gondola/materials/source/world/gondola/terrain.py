"""Gondola contact queries over explicitly owned final terrain products.

Construction receives verified build products. These queries do not establish
their freshness and never fill holes using another surface.
"""
import numpy as np


class Ground:
    """@cc [owner:fontanierh,label:correctness] gondola-ground-ownership
    Base queries MUST choose one final terrain owner by its declared footprint,
    including deterministic seam ownership. Missing coverage MUST fail without
    clamping or trying a neighbour. Walking contact MUST explicitly select the
    exported North Trail where its triangles cover the query; it MUST NOT choose
    a maximum across terrain owners. Terrain support remains a separate query.
    """
    def __init__(self, *, city, mountain, valley, apron, trail,
                 city_bounds, mountain_bounds, valley_bounds, apron_bounds):
        self.surfaces = dict(city=city, mountain=mountain, valley=valley, apron=apron)
        self.bounds = dict(city=city_bounds, mountain=mountain_bounds,
                           valley=valley_bounds, apron=apron_bounds)
        self.trail = trail
        if any(surface.stage != 'final' for surface in [*self.surfaces.values(), trail]):
            raise ValueError('Gondola ground requires final products')
        if city_bounds[3] != mountain_bounds[1] or mountain_bounds[3] != apron_bounds[1]:
            raise ValueError('Gondola owner bands must share their authored seams')

    @staticmethod
    def _inside(xy, bounds):
        return ((xy[:, 0] >= bounds[0]) & (xy[:, 0] <= bounds[2]) &
                (xy[:, 1] >= bounds[1]) & (xy[:, 1] <= bounds[3]))

    def base(self, xy):
        xy = np.asarray(xy, float)
        if xy.ndim != 2 or xy.shape[1] != 2 or not np.isfinite(xy).all():
            raise ValueError('Ground queries require finite N by 2 world metres')
        y = xy[:, 1]
        bands = dict(city=y < self.bounds['mountain'][1],
                     mountain=(y >= self.bounds['mountain'][1]) & (y < self.bounds['apron'][1]))
        north = y >= self.bounds['apron'][1]
        bands['valley'] = north & self._inside(xy, self.bounds['valley'])
        bands['apron'] = north & ~bands['valley']
        owners = np.empty(len(xy), object)
        height = np.empty(len(xy), float)
        for key, selected in bands.items():
            if not selected.any():
                continue
            if not self._inside(xy[selected], self.bounds[key]).all():
                raise ValueError(f'Gondola query outside declared {key} footprint')
            surface = self.surfaces[key]
            height[selected] = surface.upper(*xy[selected].T).height
            owners[selected] = surface.owner
        return height, owners

    def contact(self, xy):
        xy = np.asarray(xy,float)
        if xy.ndim != 2 or xy.shape[1] != 2 or not np.isfinite(xy).all():
            raise ValueError('Ground queries require finite N by 2 world metres')
        hit = self.trail.upper(*xy.T, require=False)
        height,owners = np.empty(len(xy),float),np.empty(len(xy),object)
        if (~hit.covered).any():
            height[~hit.covered],owners[~hit.covered] = self.base(xy[~hit.covered])
        height[hit.covered] = hit.height[hit.covered]
        owners[hit.covered] = self.trail.owner
        return height, owners
