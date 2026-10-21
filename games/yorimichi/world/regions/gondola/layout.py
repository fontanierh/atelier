"""Approved three-line network, with support spacing fitted to final terrain."""
from regions.hidamari.gondola import STATIONS as HD
from regions.belmonte.gondola import STATIONS as BM

STATIONS = HD | BM
LINES = (
    {'id':'L1','stations':('hidamari','southeast'),
     'towers':((35.,13.),(425.,20.),(970.,16.),(1510.,28.))},
    {'id':'L2','stations':('belmonte','northwest'),
     'towers':((70.,28.),(615.,24.),(1160.,28.),(1705.,28.))},
    {'id':'L3','stations':('floor','floor_rim'),
     'towers':((30.,20.),(158.,20.))},
)
