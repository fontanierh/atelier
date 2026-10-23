"""Construct only HD_Shrine from declared parameters and final data."""
from hidamari.kit import shrine as kit_shrine
from hidamari.lettering_mesh import lettering


def construct(city):
    return kit_shrine.build('HD_Shrine', 0, lettering)
