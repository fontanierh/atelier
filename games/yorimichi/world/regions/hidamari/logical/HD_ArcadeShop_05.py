"""Construct only HD_ArcadeShop_05 from declared parameters and final data."""
from hidamari import arcade as arcade_kit
from hidamari.lettering_mesh import lettering


def construct(city):
    return arcade_kit.shop(5, lettering)
