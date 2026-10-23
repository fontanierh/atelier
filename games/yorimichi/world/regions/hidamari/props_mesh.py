"""Selected Hidamari geometry; no sibling construction or export on import."""
from hidamari.construction import flowerbed
from hidamari.environment import M
from hidamari.environment import v


def prop(name):
    m=M(name)
    if name=='HD_Bench':v.bench(m,0,0,0,w=2.8)
    if name=='HD_Planter':
        flowerbed(m,0,0,0)
    if name=='HD_Lamp':
        m.box((0,0,2.2),(.16,.16,4.4),'wood_dark');v.lantern(m,0,0,4.4,.65)
    if name=='HD_Bollard':m.lathe((0,0,0),[(0,.3),(.15,.33),(.55,.18),(.7,.29)],'metal',8)
    if name=='HD_Crate':
        for i in range(3):m.box((0,0,.22+i*.42),(1.1,.9,.4),'wood_light');m.box((0,0,.42+i*.42),(1.15,.94,.07),'wood')
    return m
