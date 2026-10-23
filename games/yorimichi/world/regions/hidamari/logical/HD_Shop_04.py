"""Construct only HD_Shop_04 from declared parameters and final data."""
from hidamari.kit import corner_cafe as kit_corner_cafe
from hidamari.lettering_mesh import lettering


def construct(city):
    return kit_corner_cafe.build('HD_Shop_04', 0, lettering)
