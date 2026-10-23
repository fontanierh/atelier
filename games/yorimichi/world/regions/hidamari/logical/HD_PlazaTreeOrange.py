"""Construct only HD_PlazaTreeOrange from declared parameters and final data."""
from hidamari import plaza as plaza_kit


def construct(city):
    return plaza_kit.tree(orange=True)
