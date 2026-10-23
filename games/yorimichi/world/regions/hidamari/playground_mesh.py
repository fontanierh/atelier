"""Selected Hidamari geometry; no sibling construction or export on import."""
from hidamari.environment import M


def playground():
    m=M('HD_Playground')
    for x in [-3,3]:
        for y in [-1.6,1.6]:m.beam((x,y,0),(x,0,3),.16,.16,'wood_light')
    m.beam((-3.3,0,3),(3.3,0,3),.24,.24,'wood')
    for x in [-1.5,1.5]:
        m.box((x,0,.55),(1,.5,.10),'rust')
        for dx in [-.43,.43]:m.beam((x+dx,0,.6),(x+dx,0,3),.025,.025,'metal')
    return m
