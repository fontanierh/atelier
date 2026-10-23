"""Construct only HD_Station from declared parameters and final data."""
from hidamari.kit import station as kit_station
from hidamari.lettering_mesh import lettering


def construct(city):
    return kit_station.build('HD_Station', 0, lettering)
