"""The northern woodland remains green; the crater has an exposed rock rim."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'world'))
import yori  # noqa: E402,F401
from hidamari import mountains as M, layout as H  # noqa: E402
from belmonte.appearance import far_palette  # noqa: E402
from megapark import gate  # noqa: E402
from communitypark import layout as community  # noqa: E402


class NorthernLandscape(unittest.TestCase):
    def test_raised_northern_ground_has_no_absolute_height_rock_band(self):
        x=np.array([0.,550.,1200.]);y=np.full_like(x,2950.)
        colours=M.colours(x,y,H.north_height(x,y))
        self.assertTrue(np.all(colours[:,1]>colours[:,0]*1.3),colours)
        y[:]=3000.
        np.testing.assert_allclose(M.colours(x,y,H.north_height(x,y)),far_palette(x,y),atol=1e-12)

    def test_snow_keeps_crater_rim_exposed_and_collects_in_bowl(self):
        x,y,z=M.surface_grid(H.north_base_height)
        radius=np.hypot(x-550,y-1930)
        snow=M.snow_grid(H.north_base_height)
        self.assertLess(float(snow[(radius>85)&(radius<115)].mean()),.25)
        self.assertGreater(float(snow[radius<35].mean()),.7)
        self.assertTrue(np.all((snow>=0)&(snow<=1)))

    def test_fine_cells_are_excluded_at_both_patch_edges(self):
        for bounds,inside in [(gate.GATE,gate.cell_inside),(community.PATCH,community.cell_inside)]:
            x0,y0,x1,y1=bounds
            self.assertTrue(inside(x1-M.STEP,y1-M.STEP,M.STEP))
            self.assertFalse(inside(x1,y1,M.STEP))

    def test_asymmetric_crater_has_a_bowl_inside_a_broken_rim(self):
        x,y=np.meshgrid(np.arange(350.,755.,5.),np.arange(1730.,2135.,5.))
        z=M.natural_height(x,y);radius=np.hypot(x-550,y-1930)
        angles=np.arange(64)*np.pi/32
        radii=np.arange(60.,150.,5.)
        crest=M.natural_height(550+np.cos(angles[:,None])*radii,1930+np.sin(angles[:,None])*radii)
        floor=np.median(z[radius<25]);rim=np.median(crest.max(axis=1))
        self.assertGreater(rim-floor,40.)
        self.assertLess(rim-floor,70.)
        self.assertLess(float(z.max()),590.)


if __name__=='__main__':unittest.main()
