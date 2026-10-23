"""Selected Hidamari geometry; no sibling construction or export on import."""
from hidamari.environment import M
from hidamari.layout import height
import math


def inland_water():
    # Separate mesh: water must never inherit the bank/bridge collision.
    m=M('HD_InlandWater')
    for i in range(48):
        a=i*2*math.pi/48;b=(i+1)*2*math.pi/48
        m.poly([(1030,284,28.8),(1030+46*math.cos(a),284+32*math.sin(a),28.8),(1030+46*math.cos(b),284+32*math.sin(b),28.8)],'water_city')
    for y in range(-130,-5):
        z=max(.0,float(height(848,y))-1.8);nz=max(.0,float(height(848,y+1))-1.8)
        m.poly([(840,y,z),(856,y,z),(856,y+1,nz),(840,y+1,nz)],'water_city')
    return m
