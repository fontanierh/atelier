"""Construct only HD_Shop_06 from declared parameters and final data."""
from hidamari.kit import bookshop as kit_bookshop
from hidamari.lettering_mesh import lettering


def construct(city):
    return kit_bookshop.build('HD_Shop_06', 0, lettering)
