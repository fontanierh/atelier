"""Construct only HD_NorthGate from declared parameters and final data."""
from hidamari.layout import north_base_height
from hidamari.sheet_mesh import SheetMesh
from megapark import gate


def construct(city):
    return SheetMesh('HD_NorthGate', gate.mesh(north_base_height))
