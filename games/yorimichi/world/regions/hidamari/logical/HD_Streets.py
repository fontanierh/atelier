"""Construct only HD_Streets from declared parameters and final data."""
from hidamari.streets_mesh import streets


def construct(city):
    return streets(city)
