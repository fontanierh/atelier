"""Construct only HD_Shop_15 from declared parameters and final data."""
from hidamari.kit import apartment as kit_apartment
from hidamari.lettering_mesh import lettering


def construct(city):
    return kit_apartment.build('HD_Shop_15', 0, lettering)
