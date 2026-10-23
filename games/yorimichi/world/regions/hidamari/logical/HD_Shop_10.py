"""Construct only HD_Shop_10 from declared parameters and final data."""
from hidamari.kit import izakaya as kit_izakaya
from hidamari.lettering_mesh import lettering


def construct(city):
    return kit_izakaya.build('HD_Shop_10', 1, lettering)
