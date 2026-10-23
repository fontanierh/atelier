"""Construct only HD_ArcadeGate from declared parameters and final data."""
from hidamari import arcade as arcade_kit
from hidamari.lettering_mesh import lettering


def construct(city):
    return arcade_kit.end_gate(lettering)
