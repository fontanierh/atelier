"""Construct only HD_PlazaShopSidesCorner from declared parameters and final data."""
from hidamari import plaza as plaza_kit


def construct(city):
    return plaza_kit.shop_sides(raised_rear=True)
