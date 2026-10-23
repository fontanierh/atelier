"""Construct only HD_ParkGrounds from declared parameters and final data."""
from hidamari import park_grounds
from hidamari.environment import M
from hidamari.layout import height


def construct(city):
    return park_grounds.grounds(M('HD_ParkGrounds'), height)
