"""Selected Hidamari geometry; no sibling construction or export on import."""
from hidamari.construction import simple_roof
from hidamari.environment import M
from hidamari.environment import v
import numpy as np


def pavilion(name='HD_Pavilion',w=10,d=8):
    m=M(name)
    for x in [-w/2,w/2]:
        for y in [-d/2,d/2]:m.box((x,y,1.7),(.25,.25,4.6),'wood');m.collider((x,y,1.7),(.3,.3,4.6))
    simple_roof(m,w+1,d+1,4,1.8)
    if name=='HD_Pavilion':
        v.bench(m,-2,2,0,w=3);v.bench(m,2,2,0,w=3)
    if name=='HD_Market':
        for x in np.arange(-w/2+2,w/2,3):
            m.box((x,0,.8),(2.5,2,.15),'wood_light')
            for dx in (-.98,.98):
                for dy in (-.72,.72):m.box((x+dx,dy,.35),(.13,.13,.78),'wood')
            for k in range(4):m.box((x-1+k*.6,-.3,1.03),(.45,1.1,.3),'blue',.05)
            m.collider((x,0,.5),(2.5,2,1))
    return m
