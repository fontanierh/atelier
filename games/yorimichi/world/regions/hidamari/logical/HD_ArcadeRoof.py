"""Construct only HD_ArcadeRoof from declared parameters and final data."""
from hidamari import arcade as arcade_kit


def construct(city):
    return arcade_kit.roof_panels()
