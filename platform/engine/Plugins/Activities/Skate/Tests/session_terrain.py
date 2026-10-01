"""Deterministic collision/rail fixtures for transition and long-session parity.

These are offline solver inputs, separate from the game's art and level layout.
Scenario names describe attempts; the recorded state census establishes which
state owners were actually exercised rather than assuming a successful trick.
"""
import math
import random


def terrain_world():
    triangles=[]
    def triangle(a,b,c):triangles.append([list(a),list(b),list(c)])
    def strip(left,right):
        for a,b,c,d in zip(left,left[1:],right[1:],right):
            triangle(a,b,c);triangle(a,c,d)
    def flat(cx,cz,wx,wz,y=0):
        strip([(cx-wx,y,cz-wz),(cx-wx,y,cz+wz)],[(cx+wx,y,cz-wz),(cx+wx,y,cz+wz)])
    flat(0,0,20,20)
    # Two true circular transitions connected by ten metres of flat bottom.
    # Forty-eight chords per quarter keep contact changes visible in the trace.
    quarter=[(5+3*math.sin(i*math.pi/96),3*(1-math.cos(i*math.pi/96))) for i in range(49)]
    profile=[(-z,y) for z,y in reversed(quarter)]+quarter
    strip([(40,y,z) for z,y in profile],[(60,y,z) for z,y in profile])
    # Enclosed circular bowl, with a four-metre bottom radius and 2.5 m walls.
    rings=[]
    for i in range(33):
        theta=i*math.pi/64;r=4+2.5*math.sin(theta);y=2.5*(1-math.cos(theta))
        rings.append([(100+r*math.cos(j*math.tau/64),y,r*math.sin(j*math.tau/64)) for j in range(64)])
    for j in range(64):triangle((100,0,0),rings[0][(j+1)%64],rings[0][j])
    for inner,outer in zip(rings,rings[1:]):
        for j in range(64):
            k=(j+1)%64;triangle(inner[j],inner[k],outer[k]);triangle(inner[j],outer[k],outer[j])
    flat(150,0,15,20)
    # Rail collision geometry and grind curve agree in location and height.
    x0,x1,y0,y1,z0,z1=149.96,150.04,0,0.5,-5,5
    vertices=[(x,y,z) for x,y,z in ((x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),(x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1))]
    for a,b,c,d in ((3,7,6,2),(0,1,5,4),(0,4,7,3),(1,2,6,5),(0,3,2,1),(4,5,6,7)):
        triangle(vertices[a],vertices[b],vertices[c]);triangle(vertices[a],vertices[c],vertices[d])
    return dict(triangles=triangles,rails=[[[150,0.5,-5],[150,0.5,0],[150,0.5,5]]],spawn=[0,0,0],heading=0)


def terrain_scenarios():
    cases=[];generation=0
    def add(name,spawn,velocity,controls,goofy=False,difficulty='normal',heading=0):
        nonlocal generation
        generation+=1
        commands=[dict(op='activate',spawn=list(spawn),heading=heading,goofy=goofy,difficulty=difficulty,trucks=.5,generation=generation,
                       velocity=list(velocity),pop=1.15,spin=1.6,push_power=1.45,push_speed=1.15)]
        for override in controls:commands.append(dict(dict(op='step',dt=1/60,buttons=0,left=[0,0],right=[0,0],triggers=[0,0]),**override))
        cases.append(dict(name=name,commands=commands))
    for goofy in (False,True):
        stance='goofy' if goofy else 'regular'
        for speed in (5,8,11):
            add(f'{stance}/halfpipe/coast/{speed}',(50,0,0),(0,0,speed),[{} for _ in range(600)],goofy)
        add(f'{stance}/halfpipe/pump',(50,0,0),(0,0,7),[dict(right=[0,-23000] if i%120<45 else [0,0]) for i in range(1200)],goofy)
        add(f'{stance}/halfpipe/pop',(50,0,0),(0,0,7),[dict(right=[0,-32767] if 30<=i<48 else [0,32767] if i in (48,49) else [0,0]) for i in range(600)],goofy)
        add(f'{stance}/bowl/coast',(100,0,0),(0,0,8),[{} for _ in range(900)],goofy)
        add(f'{stance}/bowl/carve',(100,0,0),(0,0,7),[dict(left=[9000,0] if 90<=i<600 else [0,0],right=[0,-16000] if 180<=i<220 else [0,0]) for i in range(900)],goofy)
        add(f'{stance}/rail/ollie',(150,0,-10),(0,0,5),[dict(right=[0,-32767] if 20<=i<38 else [0,32767] if i in (38,39) else [0,0]) for i in range(480)],goofy)
        add(f'{stance}/rail/drop',(150,1,-4),(0,-1,4),[{} for _ in range(360)],goofy)
        for difficulty in ('easy','hardcore'):
            add(f'{stance}/halfpipe/difficulty/{difficulty}',(50,0,0),(0,0,9),[dict(left=[6000,0] if 90<=i<150 else [0,0]) for i in range(480)],goofy,difficulty)
    rng=random.Random(0x2010)
    controls=[]
    for i in range(3600):
        if i%24==0:left=[rng.randint(-22000,22000),rng.randint(-18000,18000)];right=rng.choice(([0,0],[0,-16000],[0,-30000],[0,30000]));buttons=rng.choice((0,0,0,0x1000))
        controls.append(dict(left=list(left),right=list(right),buttons=buttons))
    add('long/generated-flat', (0,0,0),(0,0,4),controls)
    return cases
