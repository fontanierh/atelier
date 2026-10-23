"""Construct only HD_PlazaShopSides from declared parameters and final data."""
from hidamari import plaza as plaza_kit


def construct(city):
    return plaza_kit.shop_sides()
