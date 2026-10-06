"""The mini-mega's riding geometry, in metres from its origin; one profile drives the mesh and its collision. Only
`world.mega` and the map read it, so a change here leaves the terrain and placement (`layout.py`) alone."""
import math
import numpy as np
from village.layout import smooth

WIDTH=8.

def bezier(points,n=100):
    a,b,c,d=np.array(points,float)
    return [(a*(1-t)**3+3*b*t*(1-t)**2+3*c*t*t*(1-t)+d*t**3).tolist() for t in np.linspace(0,1,n+1)]

def profiles():
    roll=[[-3.,10.7],[0.,10.7]]+bezier([(0,10.7),(4,10.7),(2,.45),(16.5,.45)],180)[1:]
    roll+=bezier([(16.5,.45),(20,.45),(24,1.285),(27.5,2.7)],100)[1:]
    # The landing drops from its knuckle at a straight 35 degrees, then a 4 m transition meets the flat: a short gap
    # flown at a lower takeoff speed still lands on the slope, not on a flattened run-out.
    a,r=math.radians(35),4.
    drop=2.7-.45-r*(1-math.cos(a));x1=37.9+drop/math.tan(a);cx=x1+r*math.sin(a)
    land=[[37.9,2.7]]+[[cx-r*math.sin(t),.45+r*(1-math.cos(t))] for t in np.linspace(a,0,60)]
    land.append([56.,.45])
    # Exact circular transition ends in true vertical: no over-vertical hook.
    land += [[56+5.65*math.sin(t),.45+5.65*(1-math.cos(t))] for t in np.linspace(0,math.pi/2,151)[1:]]
    return [roll,land]

def rollout():
    # Tangent-continuous return route, descending gently onto the clearing.
    p=np.array(bezier([(52,0,.455),(44,0,.455),(43,-8,.12),(47,-12,.055)],120))
    # Stay flush while overlapping the main flat; descend beyond its edge.
    p[:,2]=.455-.4*smooth((np.abs(p[:,1])-4.3)/7.7)
    return p.tolist()
