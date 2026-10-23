"""Construct only HD_InlandWater from declared parameters and final data."""
from hidamari.water_mesh import inland_water


def construct(city):
    return inland_water()
