"""Construct only HD_NorthRockB from declared parameters and final data."""
from hidamari.gate_rock_mesh import gate_rock


def construct(city):
    return gate_rock('HD_NorthRockB')
