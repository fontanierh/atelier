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

# The terrain and trail samplers read world.layout's generated outputs.
BUILT=all((yori.OUT/name).is_file() for name in
          ('farhills.npy','heightmap.npy','world.json','megapark/trail.json'))


class NorthernLandscape(unittest.TestCase):
    @unittest.skipUnless(BUILT,'needs world.layout')
    def test_raised_northern_ground_has_no_absolute_height_rock_band(self):
        x=np.array([0.,550.,1200.]);y=np.full_like(x,2950.)
        colours=M.colours(x,y,H.north_height(x,y))
        self.assertTrue(np.all(colours[:,1]>colours[:,0]*1.3),colours)
        y[:]=3000.
        np.testing.assert_allclose(M.colours(x,y,H.north_height(x,y)),far_palette(x,y),atol=1e-12)

    @unittest.skipUnless(BUILT,'needs world.layout')
    def test_snow_keeps_crater_rim_exposed_and_collects_in_bowl(self):
        x,y,z=M.surface_grid(H.north_base_height)
        radius=np.hypot(x-550,y-1930)
        snow=M.snow(x,y,H.north_base_height)
        self.assertLess(float(snow[(radius>85)&(radius<115)].mean()),.15)
        floor_white=float((snow[radius<35]>.5).mean())
        self.assertGreater(floor_white,.6)
        self.assertLess(floor_white,.9)
        self.assertLess(float((snow[(radius>50)&(radius<85)]>.5).mean()),.4)
        self.assertTrue(np.all((snow>=0)&(snow<=1)))

    @unittest.skipUnless(BUILT,'needs world.layout')
    def test_snow_texture_preserves_linear_bytes_and_world_orientation(self):
        import json
        import tempfile
        from PIL import Image
        field=M.snow_grid(H.north_base_height)
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)
            M.export_snow_mask(path,H.north_base_height)
            image=Image.open(path/'north_snow.png')
            self.assertEqual(image.mode,'L')
            self.assertEqual(image.size,(1024,1024))
            np.testing.assert_array_equal(np.asarray(image),field)
            meta=json.loads((path/'north_snow.json').read_text())
            self.assertTrue(meta['linear'])
        # Asymmetric points detect a flipped PNG or swapped world axes.
        for iy,ix in ((310,417),(541,526),(690,488)):
            x=M.SNOW_BOUNDS[0]+ix*M.SNOW_STEP
            y=M.SNOW_BOUNDS[1]+iy*M.SNOW_STEP
            self.assertAlmostEqual(float(M.snow(x,y,H.north_base_height)),int(field[iy,ix])/255.,places=12)
        x,y,z=M.surface_grid(H.north_base_height)
        outside=(x<M.SNOW_BOUNDS[0])|(x>M.SNOW_BOUNDS[2])|(y<M.SNOW_BOUNDS[1])|(y>M.SNOW_BOUNDS[3])
        authored=M.snow_cover(x,y,z)
        self.assertEqual(float(authored[outside].max()),0.,'Snow would be lost beyond the texture footprint')

    def test_species_transition_is_shared_continuous_and_preserves_roots(self):
        from forest.ecotone import tuscan_mask,northern_ecotone
        x=np.linspace(-400,1500,1901)
        south=tuscan_mask(x,np.full_like(x,2999.75))
        north=tuscan_mask(x,np.full_like(x,3000.25))
        self.assertLess(float(np.mean(south!=north)),.015)
        self.assertFalse(tuscan_mask(x,np.full_like(x,2500.)).any())
        self.assertTrue(tuscan_mask(x,np.full_like(x,3500.)).all())
        rows=[[float(xx),3000.,100.,37.,1.] for xx in x[::50]]
        instances={'Tree_Forest_Maple':rows.copy()}
        northern_ecotone(instances)
        actual=[row for group in instances.values() for row in group]
        self.assertEqual(len(actual),len(rows))
        self.assertEqual(sorted(tuple(row[:4]) for row in actual),sorted(tuple(row[:4]) for row in rows))

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
