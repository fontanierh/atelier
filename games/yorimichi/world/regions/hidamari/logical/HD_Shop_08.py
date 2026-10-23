"""Construct only HD_Shop_08 from declared parameters and final data."""
from hidamari.kit import machiya as kit_machiya
from hidamari.lettering_mesh import lettering


def construct(city):
    return kit_machiya.build('HD_Shop_08', 1, lettering)
