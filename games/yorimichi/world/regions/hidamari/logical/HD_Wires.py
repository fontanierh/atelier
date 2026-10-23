"""Construct only HD_Wires from declared parameters and final data."""
from hidamari.wire_mesh import wire_mesh


def construct(city):
    return wire_mesh(city)
