"""Selected Hidamari geometry; no sibling construction or export on import."""
from hidamari import harbor as harbor_kit
from hidamari import working_harbor
from hidamari.lettering_mesh import lettering
from hidamari.layout import height
import math
import numpy as np


def harbor():
    m=harbor_kit.Mesh('HD_Harbor')
    # The 6.4 m lighthouse foot used to overhang a 3.4 m breakwater. Give it
    # an octagonal pier head supported below water, rather than flattening sea.
    m.lathe((440,-225,0),[(-4.,4.1),(2.25,4.1),(2.48,3.9)],'stone_light',8)
    m.poly([(440+3.9*math.cos(k*math.tau/8),-225+3.9*math.sin(k*math.tau/8),2.48) for k in range(8)],'stone_light')
    # Quay retaining wall, with a continuous protected promenade along the water.
    for a,b in [((420,-126),(900,-126)),((420,-126),(420,-225)),((420,-225),(760,-225))]:
        m.beam((*a,.65),(*b,.65),3,3.3,'stone')
        m.beam((*a,2.35),(*b,2.35),3.4,.25,'stone_light')
        length=math.dist(a,b);n=math.ceil(length/3)
        for t in np.linspace(0,1,n):
            x=a[0]*(1-t)+b[0]*t;y=a[1]*(1-t)+b[1]*t
            if a[1]==b[1]==-126 and min(abs(x-p) for p in range(480,840,60))<2:continue
            if math.hypot(x-440,y+225)<4.5:continue
            m.box((x,y,3.0),(.13,.13,1.1),'wood_dark')
        if a[1]==b[1]==-126:
            cuts=[a[0]]
            for px in range(480,840,60):cuts.extend([px-1.65,px+1.65])
            cuts.append(b[0])
            for endpoint in cuts[1:-1]:m.box((endpoint,-126,3.0),(.13,.13,1.1),'wood_dark')
            for lo,hi in zip(cuts[::2],cuts[1::2]):m.beam((lo,-126,3.5),(hi,-126,3.5),.09,.09,'wood_dark')
        elif a[1]==b[1]==-225:
            for lo,hi in [(a[0],435.5),(444.5,b[0])]:m.beam((lo,-225,3.5),(hi,-225,3.5),.09,.09,'wood_dark')
        else:m.beam((*a,3.5),(*b,3.5),.09,.09,'wood_dark')
    for x in range(480,840,60):
        m.box((x,-147.9,2.365),(3.0,44.2,.33),'wood_light')
        # Continuous rails stop at the quay, with a post at every endpoint.
        for side in [-1,1]:
            for yy in [-170,*range(-166,-126,4),-126]:
                m.box((x+side*1.35,yy,3.015),(.13,.13,1.06),'wood')
            m.beam((x+side*1.35,-170,3.5),(x+side*1.35,-126,3.5),.08,.08,'wood')
        m.beam((x-1.35,-170,3.5),(x+1.35,-170,3.5),.08,.08,'wood')
    # Connecting ramps from land to breakwater (same level near the seafront).
    m.box((423,-124,2.35),(14,12,.25),'paving')
    for x in [840,856]:
        for y in range(-122,-5,2):
            if abs(y+90)<9 or abs(y-15)<9:continue
            z=float(height(x,y))
            m.box((x,y,z/2),(.4,2.02,z),'stone')
            m.box((x,y,z+.65),(.12,.12,1.3),'wood')
            m.beam((x,y,z+1.25),(x,y+2,float(height(x,y+2))+1.25),.10,.10,'wood')
    return working_harbor.add(harbor_kit.dress_harbor(m,height),height,lettering)
