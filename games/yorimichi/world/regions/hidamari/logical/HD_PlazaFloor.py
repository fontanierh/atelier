"""Construct only HD_PlazaFloor from declared parameters and final data."""
from hidamari import plaza as plaza_kit
from hidamari.layout import height


def construct(city):
    return plaza_kit.floor(height)
