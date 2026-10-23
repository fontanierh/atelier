"""Construct only HD_Terrain from declared parameters and final data."""
from city_terrain_surface import generate as city_ground
from hidamari.terrain_mesh import city_terrain_surfaces
import yori


def construct(city):
    return city_ground(city_terrain_surfaces, yori.OUT / 'terrain/HD_Terrain')
