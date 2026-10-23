"""Construct only HD_LaneEdges from declared parameters and final data."""
from hidamari.lane_edge_mesh import lane_edge_mesh


def construct(city):
    return lane_edge_mesh(city)
