"""Construct only HD_Shop_03 from declared parameters and final data."""
from hidamari.kit import bakery_western as kit_bakery_western
from hidamari.lettering_mesh import lettering


def construct(city):
    return kit_bakery_western.build('HD_Shop_03', 0, lettering)
