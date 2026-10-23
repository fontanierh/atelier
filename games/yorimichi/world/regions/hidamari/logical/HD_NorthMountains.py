"""Construct only HD_NorthMountains from declared parameters and final data."""
from hidamari.layout import north_base_height
from hidamari.sheet_mesh import SheetMesh
from north_mountain_surface import generate as mountain_surface
import yori


def construct(city):
    return SheetMesh('HD_NorthMountains', mountain_surface(north_base_height, yori.OUT / 'terrain/HD_NorthMountains'))
