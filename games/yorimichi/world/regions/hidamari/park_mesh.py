"""Selected Hidamari geometry; no sibling construction or export on import."""
from hidamari import pond_garden
from hidamari.environment import M
from hidamari.layout import height
import math


def park():
    m=M('HD_Park')
    # The lakeside pavilion's northeast post crosses the excavated pond edge.
    # A masonry footing joins the bank and continues below the water surface;
    # its top matches the surrounding stone walk (rather than floating a post).
    m.box((989.5,268.5,29.5275),(2.2,2.2,2.655),'stone')
    # Pond sits in excavated ground; a simple boardwalk gives a clear crossing.
    for i in range(64):
        a=i*2*math.pi/64;b=(i+1)*2*math.pi/64
        inner=lambda t,z:(1030+46*math.cos(t),284+32*math.sin(t),z)
        outer=lambda t:(1030+51*math.cos(t),284+37*math.sin(t),30.85)
        m.poly([inner(a,30.85),outer(a),outer(b),inner(b,30.85)],'stone_light')
        m.poly([inner(a,30.85),inner(b,30.85),inner(b,28.5),inner(a,28.5)],'stone')
    for i in range(64):
        a=i*2*math.pi/64;b=(i+1)*2*math.pi/64
        if abs(math.sin(a))<.12:continue
        x,y=1030+49*math.cos(a),284+35*math.sin(a)
        nx,ny=1030+49*math.cos(b),284+35*math.sin(b)
        m.box((x,y,31.4),(.12,.12,1.2),'wood')
        m.beam((x,y,32),(nx,ny,32),.09,.09,'wood')
    from hidamari import garden_bridge
    garden_bridge.add(m)
    return pond_garden.add(m,height)
