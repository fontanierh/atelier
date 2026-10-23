"""Construct only HD_Arrival from declared parameters and final data."""
from hidamari import arrival
from hidamari.environment import M
from hidamari.layout import height


def construct(city):
    return arrival.arrival(M('HD_Arrival'), height)
