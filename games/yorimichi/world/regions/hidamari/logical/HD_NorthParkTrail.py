"""Construct only HD_NorthParkTrail from declared parameters and final data."""
from hidamari.layout import north_height
from megapark import trail as park_trail


def construct(city):
    return park_trail.trail_mesh(north_height)
