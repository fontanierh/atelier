"""Construct only HD_NorthTrail from declared parameters and final data."""
from hidamari import mountains
from hidamari.layout import north_height


def construct(city):
    return mountains.trail_mesh(north_height)
