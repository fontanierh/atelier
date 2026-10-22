"""Sunburst-guided timber cabin, fishing pier and quiet autumn shoreline."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import sys,json,math,random
from pathlib import Path
import bpy,numpy as np
ROOT=yori.REGIONS
import village.build as lib
from village.build import Mesh,roof,window,door,pot,lantern
from village.layout import upper_surface
from forest_lake.layout import CENTER,RADII,WATER,CABIN,radius
OUT=yori.OUT/'forest_lake';random.seed(719)
WOOD=(.19,.083,.029);DARK=(.064,.031,.015);PLANK=(.32,.18,.076);STONE=(.24,.25,.21)

def bench(m,x,y,z):
    m.box((x,y,z+.48),(1.8,.46,.12),PLANK,.02)
    for dx in [-.64,.64]:m.box((x+dx,y,z+.22),(.14,.37,.44),DARK)

def main():
    OUT.mkdir(exist_ok=True);(OUT/'assets').mkdir(exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True);lib.OUT=OUT
    mat=bpy.data.materials.new('LakePalette');mat.use_nodes=True
    vc=mat.node_tree.nodes.new('ShaderNodeVertexColor');vc.layer_name='Color'
    mat.node_tree.links.new(vc.outputs['Color'],mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
    h=np.load(yori.OUT/'heightmap.npy');world=json.loads((yori.OUT/'world.json').read_text());report={}
    def save(m):_,report[m.name]=lib.export(m,mat)
    m=Mesh('Lake_Cabin')
    with m.at(CABIN,-135):
        # Full foundation to soil, solid timber walls with readable shoji panels.
        m.box((0,0,.10),(7.1,5.1,.50),STONE,.06)
        m.box((0,0,1.7),(7,5,2.9),(.49,.40,.26))
        for x in [-3.5,-1.8,0,1.8,3.5]:
            for y in [-2.53,2.53]:m.box((x,y,1.8),(.16,.15,3.0),DARK)
        for y in [-2.53,2.53]:
            for z in [.4,1.1,3.12]:m.box((0,y,z),(7.15,.16,.16),WOOD)
        # Vertical warm cedar lower cladding.
        for x in np.arange(-3.4,3.5,.25):
            for y in [-2.55,2.55]:m.box((x,y,.75),(.23,.08,.7),tuple(c*random.uniform(.9,1.1) for c in WOOD))
        roof(m,7,5,3.22,1.6)
        # Continuous upward-facing underlay closes overlapping tile-row slits.
        for side in [-1,1]:
            for j in range(24):
                a=j/24;b=(j+1)/24
                def rz(t):return 3.22+1.6*(1-t)**1.10+.10*t**6+.005
                pts=[(-4.15,side*3.175*a,rz(a)),(4.15,side*3.175*a,rz(a)),(4.15,side*3.175*b,rz(b)),(-4.15,side*3.175*b,rz(b))]
                m.poly(pts if side>0 else pts[::-1],(.024,.036,.052))
        door(m,0,-2.62,.34,1.25,2.25)
        for x in [-2.3,2.3]:window(m,x,-2.62,1.85,1.35,1.3,True)
        with m.at((0,0,0),180):
            for x in [-2.0,2.0]:window(m,x,-2.63,1.85,1.1,1.1)
        for side in [-1]:
            with m.at((side*3.53,0,0),side*90):window(m,0,-.02,1.85,1.4,1.3)
        # Ground-supported porch, 17cm risers and clear central door access.
        m.box((0,-3.4,.19),(7.2,1.8,.38),STONE,.025)
        for y in np.arange(-4.24,-2.55,.19):m.box((0,y,.39),(7.15,.178,.08),PLANK,.006)
        for x in [-3.35,3.35]:m.box((x,-4.05,1.66),(.18,.18,2.6),WOOD)
        for x in [-3.5,3.5]:m.beam((x,-2.7,3.13),(x,-4.35,2.95),.12,.18,WOOD)
        porch_roof=[(-3.65,-2.55,3.22),(3.65,-2.55,3.22),(3.65,-4.5,3.0),(-3.65,-4.5,3.0)]
        m.poly(porch_roof,(.03,.045,.061));m.poly(porch_roof[::-1],(.03,.045,.061))
        m.box((-2,-4.55,.12),(1.65,.62,.24),STONE,.025)
        bench(m,2.15,-3.55,.43);lantern(m,-.95,-2.9,2.3,.34)
        pot(m,-2.95,-3.3,.43,.9,'clay')
        # Side wood store, supported canopy and individually stacked cut logs.
        m.box((4.1,.5,.04),(1.15,2.6,.24),STONE,.02)
        for y in [-.65,1.65]:m.box((4.52,y,1.1),(.12,.12,2.2),WOOD)
        store_roof=[(3.5,-.9,2.55),(3.5,1.9,2.55),(4.85,1.9,2.1),(4.85,-.9,2.1)]
        m.poly(store_roof,(.035,.046,.062));m.poly(store_roof[::-1],(.035,.046,.062))
        m.beam((4.52,-.8,2.18),(4.52,1.8,2.18),.14,.14,WOOD)
        for z in [.3,.58,.86,1.14]:
            for y in np.arange(-.45,1.55,.28):
                ends=[[(xx,y+.14*math.cos(a),z+.14*math.sin(a)) for a in np.linspace(0,math.tau,9)[:-1]] for xx in [3.65,4.43]]
                m.poly(ends[1],PLANK)
                for k in range(8):kk=(k+1)%8;m.poly([ends[0][k],ends[0][kk],ends[1][kk],ends[1][k]],DARK)
        # Jetty: pier runs from porch towards deep water; substantial piles below waterline.
        for y in np.arange(-13,-4.3,.22):m.box((0,y,.31),(2.0,.205,.12),tuple(c*random.uniform(.91,1.09) for c in PLANK),.005)
        for y in [-5,-8,-11,-13]:
            for x in [-.86,.86]:
                m.box((x,y,-.6),(.2,.2,2.5),DARK)
                m.box((x,y,-1.6),(.44,.44,.42),STONE,.02)
            m.box((0,y,.16),(2.15,.18,.22),WOOD)
        for y in np.arange(-14.5,-11,.22):m.box((0,y,.31),(4.3,.205,.12),PLANK,.005)
        for x in [-2,2]:
            for y in [-14.3,-11.3]:m.box((x,y,-.5),(.22,.22,2.9),WOOD)
        bench(m,1.1,-12.2,.37)
        pot(m,-1.3,-12.5,.37,.7,'wood_light')
        # Fishing rod reaches above water, with thin suspended line.
        m.beam((-.8,-13.3,.38),(-1.7,-16.4,2.2),.036,.036,WOOD)
        m.beam((-1.7,-16.4,2.2),(-1.7,-16.4,-.59),.007,.007,(.35,.32,.22))
        # Small open clinker rowboat: pointed bow, hollow hull, interior ribs and two seats.
        with m.at((-3.4,-15.5,-.46),10):
            rings=[]
            for z,scale in [(-.28,.63),(-.05,.9),(.28,1.)]:
                ring=[(math.sin(a)*.65*scale,math.cos(a)*1.65*scale,z) for a in np.linspace(0,2*math.pi,17)[:-1]];rings.append(ring)
            m.poly(list(reversed(rings[0])),DARK)
            floor=[(x*1.3354,y*1.3354,-.10) for x,y,z in reversed(rings[0])]
            assert np.cross(np.array(floor[1])-floor[0],np.array(floor[2])-floor[0])[2]>0
            assert CABIN[2]-.46-.10>WATER+.05
            m.poly(floor,WOOD)
            for j in range(2):
                for i in range(16):k=(i+1)%16;m.poly([rings[j][i],rings[j][k],rings[j+1][k],rings[j+1][i]],WOOD if j==0 else PLANK)
            # Inner hull must face inward too (single-sided material).
            for i in range(16):
                k=(i+1)%16;m.poly([rings[0][i],rings[2][i],rings[2][k],rings[0][k]],WOOD)
                m.beam(rings[2][i],rings[2][k],.055,.055,PLANK)
            for y in [-.65,.55]:m.box((0,y,.13),(1.13,.25,.09),PLANK)
            m.beam((-.4,-.7,.28),(.45,.9,.28),.045,.045,WOOD)
        m.beam((-2,-12,.60),(-2.85,-15.6,-.17),.025,.025,(.26,.22,.12))
    from forest_lake.details import cabin,islet
    with m.at(CABIN,-135):cabin(m)
    # Deeper cedar browns keep the joinery distinct from warm plaster and paper.
    m.colors=[tuple(v*.68 for v in c[:3])+(c[3],) if c[0]<.6 and c[1]<.28 and c[0]>c[1]*1.4 and c[1]>c[2]*1.4 else c for c in m.colors]
    save(m)
    # Irregular shoreline: terrain, water and placement share exactly the same shape.
    m=Mesh('Lake_Water');n=160
    for i in range(n):
        pts=[]
        for a in [2*math.pi*i/n,2*math.pi*(i+1)/n]:
            rr=.975*(1+.045*math.sin(3*a)+.035*math.cos(5*a));pts.append((CENTER[0]+RADII[0]*rr*math.cos(a),CENTER[1]+RADII[1]*rr*math.sin(a),WATER))
        m.poly([(CENTER[0],CENTER[1],WATER),*pts],(.025,.17,.15))
    save(m)
    m=Mesh('Lake_Trail');path=np.array(world['forest_lake']['trail']);v=np.gradient(path[:,:2],axis=0);v/=np.linalg.norm(v,axis=1)[:,None];normal=np.column_stack([-v[:,1],v[:,0]])
    for i in range(len(path)-1):
        points=[]
        for k,side in [(i,-1),(i+1,-1),(i+1,1),(i,1)]:
            p=path[k,:2]+normal[k]*side*1.25;points.append((*p,float(upper_surface(h,*p))+.045))
        m.poly(points,(.24,.15,.075))
    save(m)
    m=Mesh('Lake_Shore');plants=Mesh('Lake_Plants')
    for i in range(100):
        a=random.uniform(0,math.tau);r=random.uniform(.99,1.065)*(1+.045*math.sin(3*a)+.035*math.cos(5*a));x=CENTER[0]+RADII[0]*r*math.cos(a);y=CENTER[1]+RADII[1]*r*math.sin(a)
        if x>-67 and y<229:continue
        z=float(upper_surface(h,x,y))
        if i%2==0:
            # Ground-intersecting faceted stones, no free-floating instances.
            with m.at((x,y,z-.15),random.uniform(0,360)):
                sx=random.uniform(.45,1.5);sy=random.uniform(.4,1.1);sz=random.uniform(.5,1.1)
                points=[(sx*math.cos(a),sy*math.sin(a),0) for a in np.linspace(0,math.tau,7)[:-1]]
                top=[(px*.7,py*.7,sz*random.uniform(.8,1.05)) for px,py,_ in points]
                m.poly(top,STONE)
                for j in range(6):k=(j+1)%6;m.poly([points[j],points[k],top[k],top[j]],tuple(c*random.uniform(.85,1.13) for c in STONE))
        for j in range(random.randint(5,11)):
            px=x+random.uniform(-.65,.65);py=y+random.uniform(-.65,.65);pz=float(upper_surface(h,px,py))-.06;height=random.uniform(.35,.95)
            if pz<WATER-.35:continue
            dx=random.uniform(-.2,.2);dy=random.uniform(-.2,.2)
            col=random.choice([(.19,.26,.07),(.32,.33,.12),(.28,.37,.13)])
            for width in [(.04,0),(0,.04)]:
                pts=[(px-width[0],py-width[1],pz),(px+width[0],py+width[1],pz),(px+dx,py+dy,pz+height)]
                plants.poly(pts,col);plants.poly(pts[::-1],col)
            if j%4==0:plants.beam((px+dx,py+dy,pz+height-.15),(px+dx,py+dy,pz+height+.08),.045,.045,(.52,.43,.22))
    # Sparse autumn leaves seated on bank and approach, never suspended in water.
    for i in range(450):
        x=random.uniform(-131,-41);y=random.uniform(202,267);r=radius(x,y)
        if not 1.03<r<1.27 or (abs(x-CABIN[0])<7 and abs(y-CABIN[1])<7):continue
        z=float(upper_surface(h,x,y))+.025;sz=random.uniform(.08,.18)
        plants.poly([(x-sz,y,z),(x,y-sz*.6,z),(x+sz,y,z+.008),(x,y+sz*.6,z)],random.choice([(.48,.20,.036),(.61,.39,.06),(.36,.11,.022)]))
    # Small grouped lily leaves break up the near-water edge without blocking walking.
    for i in range(55):
        a=random.choice([.4,1.7,3.4,4.6])+random.uniform(-.16,.16)
        rr=random.uniform(.80,.93);x=CENTER[0]+RADII[0]*rr*math.cos(a);y=CENTER[1]+RADII[1]*rr*math.sin(a)
        if float(upper_surface(h,x,y))>WATER-.15:continue
        rad=random.uniform(.13,.32)
        pts=[(x+rad*math.cos(t),y+rad*math.sin(t),WATER+.015) for t in np.linspace(.2,math.tau-.2,10)]
        plants.poly([(x,y,WATER+.016),*pts],(.17,.27,.095))
    islet(m,plants)
    save(m);save(plants)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'ForestLake.blend'))
    (OUT/'manifest.json').write_text(json.dumps(report,indent=2))
    print('LAKE BUILD COMPLETE',report,flush=True)
if __name__=='__main__':main()
