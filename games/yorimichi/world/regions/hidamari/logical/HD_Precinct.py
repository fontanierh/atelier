"""Construct only HD_Precinct from declared parameters and final data."""
from hidamari import temple_precinct
from hidamari.environment import M
from hidamari.layout import height


def construct(city):
    return temple_precinct.precinct(M('HD_Precinct'), height)
