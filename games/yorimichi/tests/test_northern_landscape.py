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

# The terrain and trail samplers read world.layout's generated outputs.
BUILT=all((yori.OUT/name).is_file() for name in
          ('farhills.npy','heightmap.npy','world.json','megapark/trail.json'))


class NorthernLandscape(unittest.TestCase):
    @unittest.skipUnless(BUILT,'needs world.layout')
    def test_raised_northern_ground_has_no_absolute_height_rock_band(self):
        x=np.array([0.,550.,1200.]);y=np.full_like(x,M.BOUNDS[3]-50.)
        colours=M.colours(x,y,H.north_height(x,y))
        self.assertTrue(np.all(colours[:,1]>colours[:,0]*1.3),colours)
        y[:]=M.BOUNDS[3]
        np.testing.assert_allclose(M.colours(x,y,H.north_height(x,y)),far_palette(x,y),atol=1e-12)

    @unittest.skipUnless(BUILT,'needs world.layout')
    def test_snow_keeps_crater_rim_exposed_and_collects_in_bowl(self):
        x,y,z=M.surface_grid(H.north_base_height)
        _,_,radius,angle=M.polar(x,y)
        snow=M.snow(x,y,H.north_base_height)
        self.assertLess(float(snow[np.abs(radius-M.rim_radius(angle))<15].mean()),.15)
        floor_white=float((snow[radius<M.FLOOR_RADIUS-40]>.5).mean())
        self.assertGreater(floor_white,.6)
        self.assertLess(floor_white,.9)
        # Snow still runs down the flanks in gullies, and none lies beyond them.
        flank=(radius>M.RIM_RADIUS+100)&(radius<M.stretch(520))
        self.assertGreater(float((snow[flank]>.5).mean()),.08)
        self.assertEqual(float(snow[radius>M.BASE_RADIUS].max()),0.)
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
        join=M.BOUNDS[3]
        x=np.linspace(-400,1500,1901)
        south=tuscan_mask(x,np.full_like(x,join-.25))
        north=tuscan_mask(x,np.full_like(x,join+.25))
        self.assertLess(float(np.mean(south!=north)),.015)
        self.assertFalse(tuscan_mask(x,np.full_like(x,join-500.)).any())
        self.assertTrue(tuscan_mask(x,np.full_like(x,join+500.)).all())
        rows=[[float(xx),join,100.,37.,1.] for xx in x[::50]]
        instances={'Tree_Forest_Maple':rows.copy()}
        northern_ecotone(instances)
        actual=[row for group in instances.values() for row in group]
        self.assertEqual(len(actual),len(rows))
        self.assertEqual(sorted(tuple(row[:4]) for row in actual),sorted(tuple(row[:4]) for row in rows))

    def test_fine_cells_are_excluded_at_both_patch_edges(self):
        for bounds,inside in [(gate.GATE,gate.cell_inside)]:
            x0,y0,x1,y1=bounds
            self.assertTrue(inside(x1-M.STEP,y1-M.STEP,M.STEP))
            self.assertFalse(inside(x1,y1,M.STEP))

    def test_caldera_floor_holds_a_340_by_390_m_park_under_a_160_m_wall(self):
        cx,cy=M.VOLCANO
        # A 340 x 390 m footprint at any heading lies on the level floor.
        u,v=np.meshgrid(np.linspace(-170,170,35),np.linspace(-195,195,40))
        for heading in np.radians(np.arange(0,180,15)):
            z=M.natural_height(cx+u*np.cos(heading)-v*np.sin(heading),cy+u*np.sin(heading)+v*np.cos(heading))
            self.assertLess(float(np.ptp(z)),3.)
            self.assertLess(float(np.abs(z-M.caldera_floor()).max()),2.)
        # The crest stands at least 160 m over the floor all the way round.
        angles=np.arange(128)*np.pi/64
        radii=np.arange(300.,600.,2.5)
        crest=M.natural_height(cx+np.cos(angles[:,None])*radii,cy+np.sin(angles[:,None])*radii).max(axis=1)
        self.assertGreater(float(crest.min()-M.caldera_floor()),160.)
        self.assertGreater(float(np.ptp(crest)),40.)     # broken, not a drawn circle
        self.assertLess(float(crest.max()),850.)

    def test_the_former_summit_keeps_the_ground_round_the_mega_park(self):
        import math
        a=np.linspace(0,2*math.pi,72,endpoint=False)
        for reach in (350.,550.):
            x=-150+reach*np.cos(a);y=1300+reach*np.sin(a)
            trail_quiet=M.smooth((M.trail_distance(x,y)-15)/100)
            former=M._foothills(x,y,trail_quiet)+M._former_cone(x,y,trail_quiet)
            former=47+(former-47)*M.smooth(np.maximum(y-500,0)/180)
            np.testing.assert_allclose(M.natural_height(x,y),np.maximum(former,M.natural_height(x,y)),atol=1e-9)
            self.assertLess(float(np.abs(M.natural_height(x,y)-former).max()),7.)


if __name__=='__main__':unittest.main()
