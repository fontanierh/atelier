"""Construct only HD_Shop_01 from declared parameters and final data."""
from hidamari.kit import kura as kit_kura
from hidamari.lettering_mesh import lettering


def construct(city):
    return kit_kura.build('HD_Shop_01', 1, lettering)
