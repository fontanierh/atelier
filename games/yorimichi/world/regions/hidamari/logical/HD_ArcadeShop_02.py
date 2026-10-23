"""Construct only HD_ArcadeShop_02 from declared parameters and final data."""
from hidamari import arcade as arcade_kit
from hidamari.lettering_mesh import lettering


def construct(city):
    return arcade_kit.shop(2, lettering)
