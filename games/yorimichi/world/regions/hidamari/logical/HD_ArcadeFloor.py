"""Construct only HD_ArcadeFloor from declared parameters and final data."""
from hidamari import arcade as arcade_kit
from hidamari.layout import height


def construct(city):
    return arcade_kit.floor(height)
