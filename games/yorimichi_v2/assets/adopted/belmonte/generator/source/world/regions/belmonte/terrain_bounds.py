"""The shared physical collar footprint, independent of geometry constructors."""
from belmonte import layout as L

OUTER=(L.BOUNDS[0]-L.APRON,L.SOUTH_JOIN,L.BOUNDS[2]+L.APRON,L.BOUNDS[3]+L.APRON)
