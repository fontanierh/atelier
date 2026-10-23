"""Construct only HD_Shop_13 from declared parameters and final data."""
from hidamari.kit import sento as kit_sento
from hidamari.lettering_mesh import lettering


def construct(city):
    return kit_sento.build('HD_Shop_13', 0, lettering)
