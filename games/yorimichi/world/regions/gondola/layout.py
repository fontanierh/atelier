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


def mesh_names():
    names=[f'GD_{station}_{piece}' for station in STATIONS for piece in ('Foundation','Access')]
    names += [f'GD_{line["id"]}_{index}_Tower' for line in LINES for index in range(len(line['towers']))]
    names += [f'GD_{line["id"]}_Rope_LOD{lod}' for line in LINES for lod in (0,1,2)]
    return names
