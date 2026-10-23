"""Construct only HD_NorthRockC from declared parameters and final data."""
from hidamari.gate_rock_mesh import gate_rock


def construct(city):
    return gate_rock('HD_NorthRockC')
