"""Construct only HD_CivicGardens from declared parameters and final data."""
from hidamari import civic_gardens
from hidamari.layout import height
from hidamari.lettering_mesh import lettering


def construct(city):
    return civic_gardens.build(height, city, lettering)
