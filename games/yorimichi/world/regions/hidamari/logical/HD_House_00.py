"""Construct only HD_House_00 from declared parameters and final data."""
from hidamari.kit import house as kit_house
from hidamari.lettering_mesh import lettering


def construct(city):
    return kit_house.build('HD_House_00', 0, lettering)
