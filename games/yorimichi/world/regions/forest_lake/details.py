"""Small-scale joinery and shoreline landmarks from the Sunburst reference."""
import math,random
import numpy as np
from village.build import window,pot
WOOD=(.17,.073,.024);DARK=(.065,.029,.012);EDGE=(.23,.12,.045)

def lean_roof(m,x,y,w,d,z,rise):
    # y is outer eave; positive y runs back to wall. Opaque slab under every tile.
    points=[(x-w/2,y,z),(x+w/2,y,z),(x+w/2,y+d,z+rise),(x-w/2,y+d,z+rise)]
    m.poly(points,(.023,.037,.055));m.poly([(a,b,c-.055) for a,b,c in points[::-1]],DARK)
    nx=math.ceil(w/.42);ny=math.ceil(d/.4)
    for row in range(ny):
        for col in range(nx):
            xx=x-w/2+col*w/nx;yy=y+row*d/ny;zz=z+rise*row/ny
            color=(.029+col%3*.003,.043+row%2*.004,.063+col%3*.004)
            m.poly([(xx,yy,zz+.045),(xx+w/nx,yy,zz+.045),(xx+w/nx,yy+d/ny,zz+rise/ny+.032),(xx,yy+d/ny,zz+rise/ny+.032)],color)
            m.beam((xx,yy,zz+.045),(xx+w/nx,yy,zz+.045),.025,.035,color)
    for xx in [x-w/2,x+w/2]:m.beam((xx,y,z-.015),(xx,y+d,z+rise-.015),.12,.14,WOOD)
    m.beam((x-w/2,y,z-.015),(x+w/2,y,z-.015),.11,.16,WOOD)

def cabin(m):
    # Staggered stone footing around the cabin and porch, rooted below the soil.
    for row in range(2):
        for side in [-1,1]:
            for i in range(9):
                x=-3.48+(i+.5)*6.96/9
                m.box((x,side*2.56,-.015+row*.21),(.75,.22,.195),(.25+(i%3)*.015,.25+(i%3)*.015,.22+(i%3)*.012),.03)
            for i in range(6):
                m.box((side*3.56,-2.45+(i+.5)*4.9/6,-.015+row*.21),(.22,.79,.195),(.28,.285,.25),.03)
    for i in range(10):
        x=-3.6+(i+.5)*.72
        m.box((x,-4.27,.17),(.69,.19,.30),(.27+(i%3)*.013,.275+(i%3)*.013,.24),.045)
    # Tiled porch canopy, full thickness, with short diagonal post braces.
    lean_roof(m,0,-4.52,7.3,1.97,3.04,.22)
    for x in [-3.35,3.35]:
        side=1 if x<0 else -1
        m.beam((x,-4.05,2.3),(x+side*.65,-4.05,2.89),.10,.10,EDGE)
        m.beam((x,-4.05,2.3),(x,-3.35,3.),.10,.10,EDGE)
    for side in [-1,1]:
        m.box((side*3.575,0,3.11),(.15,5.2,.19),DARK)
        for y in [-2.47,2.47]:m.box((side*3.57,y,1.75),(.15,.18,2.8),WOOD)
    # Compact shed dormer sunk into the main roof, matching the reference silhouette.
    m.box((-.35,-.65,4.45),(1.65,1.35,.88),(.40,.31,.18))
    window(m,-.35,-1.34,4.60,1.17,.37,True)
    for x in [-1.19,.49]:m.box((x,-.65,4.59),(.09,1.45,.72),WOOD)
    lean_roof(m,-.35,-1.53,2.05,1.7,4.95,.14)
    # Visible trim on wood-store roof and a practical rain barrel.
    for y in [-.92,1.92]:m.beam((3.48,y,2.56),(4.86,y,2.11),.10,.14,WOOD)
    for i in range(7):
        y=-.9+i*.4;m.beam((3.5,y,2.575),(4.85,y,2.125),.025,.03,(.04,.055,.078))
    pot(m,4.0,-1.45,.0,1.15,'wood_light')
    for zz in [.12,.44]:
        m.lathe((4.,-1.45,zz),[(-.018,.31),(.018,.31)],(.07,.08,.075),12)
    # Woven creel, supported on the porch away from the entrance.
    m.box((-2.0,-2.96,.62),(.46,.34,.38),(.29,.17,.073),.04)
    for z in [.48,.56,.64,.72]:m.box((-2.,-3.135,z),(.45,.025,.018),EDGE)
    m.beam((-2.16,-2.96,.81),(-2.1,-2.96,.94),.025,.025,DARK)
    m.beam((-2.1,-2.96,.94),(-1.9,-2.96,.94),.025,.025,DARK)
    m.beam((-1.9,-2.96,.94),(-1.84,-2.96,.81),.025,.025,DARK)
    # Rope bindings make the pier posts read as joinery rather than loose cubes.
    for x in [-2,2]:
        for y in [-14.3,-11.3]:
            for z in [.54,.59,.64]:
                m.box((x,y,z),(.265,.265,.026),(.34,.27,.14),.02)

def islet(m,plants):
    # Rocks rise from the lake bed, with an exposed planted crown to the NW.
    cx,cy=-109.,246.
    for i,(dx,dy,sx,sy,sz) in enumerate([(0,0,2.3,1.8,2.1),(1.7,.3,1.4,1.3,1.35),(-1.5,-.6,1.25,1.1,1.25),(.6,-1.6,1.0,.9,1.1)]):
        ring=[(cx+dx+sx*math.cos(a),cy+dy+sy*math.sin(a),74.45) for a in np.linspace(0,math.tau,8)[:-1]]
        top=[(cx+dx+(x-cx-dx)*.57,cy+dy+(y-cy-dy)*.57,74.45+sz*(.92+.08*math.sin(k*2))) for k,(x,y,z) in enumerate(ring)]
        m.poly(top,(.25,.27,.23))
        middle=[(cx+dx+(x-cx-dx)*.87,cy+dy+(y-cy-dy)*.87,74.45+sz*.65) for x,y,z in ring]
        for k in range(7):
            kk=(k+1)%7
            m.poly([ring[k],ring[kk],middle[kk],middle[k]],(.22+k%3*.018,.24+k%3*.018,.215+k%3*.014))
            m.poly([middle[k],middle[kk],top[kk],top[k]],(.27+k%2*.018,.285+k%2*.018,.25+k%2*.014))
    # Small grass tufts rooted into the crown. Maple uses the existing tree asset.
    for i in range(15):
        x=cx+.4+math.sin(i*2.4)*.4;y=cy+.15+math.cos(i*2.4)*.35
        pts=[(x-.045,y,76.3),(x+.045,y,76.3),(x+.1,y+.08,76.9+(i%3)*.08)]
        plants.poly(pts,(.20,.27,.08));plants.poly(pts[::-1],(.20,.27,.08))
