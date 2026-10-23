"""Construct only HD_NorthApproach from declared parameters and final data."""
from megapark import trail as park_trail


def construct(city):
    return park_trail.approach_mesh()
