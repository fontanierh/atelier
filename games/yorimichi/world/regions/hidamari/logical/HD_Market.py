"""Construct only HD_Market from declared parameters and final data."""
from hidamari.pavilion_mesh import pavilion


def construct(city):
    return pavilion('HD_Market', 38, 7)
