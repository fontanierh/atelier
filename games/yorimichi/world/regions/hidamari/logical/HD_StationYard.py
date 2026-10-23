"""Construct only HD_StationYard from declared parameters and final data."""
from hidamari import station_yard
from hidamari.environment import M
from hidamari.layout import height


def construct(city):
    return station_yard.yard(M('HD_StationYard'), height)
