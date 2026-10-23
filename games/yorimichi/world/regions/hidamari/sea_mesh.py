"""One city logical constructor; no sibling export or construction."""
from hidamari.environment import M
import shorelines


def sea_mesh():
    x0,y0,x1,y1=shorelines.HARBOR_RECT
    sea=M('HD_Sea');sea.poly([(x0,y0,0.),(x1,y0,0.),(x1,y1,0.),(x0,y1,0.)],'water_city');return sea
