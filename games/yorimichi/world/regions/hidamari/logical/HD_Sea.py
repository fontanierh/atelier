"""Construct only HD_Sea from declared parameters and final data."""
from hidamari.sea_mesh import sea_mesh


def construct(city):
    return sea_mesh()
