"""Construct only HD_ClockHall from declared parameters and final data."""
from hidamari import plaza as plaza_kit
from hidamari.layout import height
from hidamari.lettering_mesh import lettering


def construct(city):
    return plaza_kit.clock_hall(lettering, height)
