"""Slim low-poly shoes and the footprint shared with foot-contact animation."""
import mesh_tools as G

SOLE_Z=.0065
THICKNESS=.025
# The upper and sole share exactly the same perimeter; there is no projecting welt.
SECTIONS=[(-.146,.040,.065,.050),(-.129,.055,.077,.054),(-.076,.059,.084,.059),
          (-.025,.056,.101,.066),(.014,.047,.125,.082),(.047,.044,.123,.082),(.056,.033,.109,.075)]
HEEL_Y=SECTIONS[-1][0]
TOE_Y=SECTIONS[0][0]
CENTER_Y=(HEEL_Y+TOE_Y)/2
LENGTH=HEEL_Y-TOE_Y
WIDTH=2*max(s[1] for s in SECTIONS)

def upper(x,suf):
    # One continuous, tapered upper: a low rounded toe rising into the ankle.
    sections=SECTIONS
    verts=[]
    for y,width,top,side in sections:
        verts += [(x+dx,y,z) for dx,z in [(-width,SOLE_Z+THICKNESS),(width,SOLE_Z+THICKNESS),(width,side),
                  (width*.7,top),(-width*.7,top),(-width,side)]]
    faces=[(j*6+i,j*6+(i+1)%6,(j+1)*6+(i+1)%6,(j+1)*6+i)
           for j in range(len(sections)-1) for i in range(6)]
    colours=['leather_light' if j<2 else 'leather' for j in range(len(sections)-1) for _ in range(6)]
    faces += [tuple(range(5,-1,-1)),tuple((len(sections)-1)*6+i for i in range(6))]
    colours += ['leather_light','leather']
    G.mesh('Shoe upper '+suf,verts,faces,'leather','foot_'+suf,face_colours=colours)

def build(x,suf):
    outline=[(x+width,y) for y,width,top,side in SECTIONS]
    outline += [(x-width,y) for y,width,top,side in reversed(SECTIONS)]
    n=len(outline)
    vertices=[(px,y,z) for z in (SOLE_Z,SOLE_Z+THICKNESS) for px,y in outline]
    faces=[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
    faces += [tuple(range(n-1,-1,-1)),tuple(range(n,n*2))]
    G.mesh('Shoe sole '+suf,vertices,faces,'sole','foot_'+suf)
    upper(x,suf)
    G.ribbon('Instep strap '+suf,[(x-.053,-.024,.080),(x-.038,-.020,.109),(x+.038,-.020,.109),(x+.053,-.024,.080)],
        .039,'leather_light','foot_'+suf,normal=(0,-.52,.854),thickness=.004)
