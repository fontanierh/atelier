"""Model the five reference buildings, village furniture and continuous lane.

blender -b --threads 6 --python-exit-code 1 --python games/yorimichi/world/regions/village/build.py
All visible parts share one opaque vertex-colour material. Exported meshes
include deliberately simple UCX volumes; furniture never blocks the lane.
"""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import hashlib, json, math, random, sys
from pathlib import Path
from contextlib import contextmanager
import bpy
import numpy as np
from mathutils import Matrix, Vector

HERE=Path(__file__).resolve().parent
ROOT=yori.REGIONS
from village.layout import BUILDINGS, nearest, sample, upper_surface, smooth, plane, village_point, FOREST_OFFSET_Y
OUT=yori.OUT/'village'
from village import mesh as mesh_kernel
from village.mesh import (Mesh, PALETTE, R, color_variant, window, door, foundation,
                          shell, roof, awning, lantern, pot, bench, export)

def cottage(m,w,d,variant):
    eave=3.25;shell(m,w,d,eave)
    y=-d/2-.12
    doorx=1.50 if variant=='A' else -1.6
    windowx=-1.30 if variant=='A' else .85
    door(m,doorx,y,w=1.25)
    window(m,windowx,y,1.78,w=1.7,glow=variant=='B')
    awning(m,doorx,y,2.7,1.65,.7)
    awning(m,windowx,y,2.75,2.0,.5)
    # Two supported 15 cm risers, with a generous bottom tread.
    for offset,top,depth in [(.55,.15,1.15),(.24,.30,.55)]:
        m.box((doorx,y-offset,(top-.08)/2),(1.75,depth,top+.08),'stone_light',.035)
        m.collider((doorx,y-offset,top/2),(1.75,depth,top))
    for side in (-1,1):
        with m.at((side*w/2,0,0),90*side):window(m,0,-.08,1.85,1.3,1.2)
    with m.at((0,d/2,0),180):window(m,-.4,-.08,1.85,1.3,1.2)
    roof(m,w,d,eave,1.5 if variant=='A' else 1.75)
    lantern(m,doorx-.94,y-.17,2.25,.32)
    pot(m,-w/2+.2,y-.35,scale=1.05,plant=True)
    pot(m,w/2-.2,y-.32,scale=.82,plant=True,key='bluepot')
    bench(m,windowx,y-.55,w=1.7)


def tea_house(m,w,d):
    shell(m,w,d,5.85)
    for side in (-1,1):
        m.box((0,side*(d/2+.08),3.10),(w+.2,.22,.25),'wood')
        for xx in (-w/2,w/2):m.box((xx,0,3.1),(.22,d,.25),'wood')
    y=-d/2-.14
    door(m,-2,y,w=1.55,h=2.25)
    for xx in (.55,2.45):window(m,xx,y,1.77,1.60,1.50,True)
    # Solid split fabric panels with a restrained cup graphic on the right panel.
    for xx in (-2.46,-1.51):
        for k in range(4):
            xa=xx-.445+k*.2225;xb=xa+.2225
            pts=[(xa,y-.24,2.65),(xa,y-.27+.05*math.sin(k),.75+.04*math.sin(k)),
                 (xb,y-.27+.05*math.sin(k+1),.75+.04*math.sin(k+1)),(xb,y-.24,2.65)]
            for face in (pts,pts[::-1]):
                m.poly(face,'rust')
                for j,p in enumerate(face):m.colors[-4+j]=(*PALETTE['rust'],(2.65-p[2])/1.9)
    m.beam((-3.01,y-.25,2.73),(-.96,y-.25,2.73),.07,.08,'wood_light')
    m.poly([(-1.81,y-.268,1.83),(-1.21,y-.268,1.83),(-1.28,y-.268,1.58),(-1.71,y-.268,1.58)][::-1],'paper')
    m.box((-1.51,y-.275,1.49),(.66,.008,.045),'paper')
    m.beam((-1.51,y-.28,1.99),(-1.46,y-.28,2.13),.025,.01,'paper')
    # Wraparound lower roof, with deep eaves beneath an open timber balcony.
    outer=[(-w/2-.82,-d/2-1.26),(w/2+.82,-d/2-1.26),(w/2+.82,d/2+.76),(-w/2-.82,d/2+.76)]
    inner=[(-w/2,-d/2),(w/2,-d/2),(w/2,d/2),(-w/2,d/2)]
    for k in range(4):
        a,b=Vector((*outer[k],3.02)),Vector((*outer[(k+1)%4],3.02))
        c,dv=Vector((*inner[(k+1)%4],3.54)),Vector((*inner[k],3.54))
        m.poly([a,b,c,dv],'roof')
        m.beam(a,b,.14,.17,'roof_edge')
        for t in (.28,.55,.8):m.beam(a.lerp(dv,t),b.lerp(c,t),.045,.045,'roof_edge')
        count=math.ceil((b-a).length/.50)
        for j in range(count):
            m.beam(a.lerp(b,(j+.5)/count),dv.lerp(c,(j+.5)/count),.045,.045,'roof')
    m.box((0,-3.66,3.61),(w+.1,1.08,.18),'wood')
    for yy in (-3.88,-3.45):m.box((0,yy,3.715),(w+.0,.40,.055),'wood_light')
    for xx in np.linspace(-w/2+.1,w/2-.1,9):m.box((float(xx),-4.13,4.15),(.13,.15,.97),'wood_light')
    for zz in (3.96,4.48):m.box((0,-4.13,zz),(w+.16,.18,.13),'wood_light')
    for xx in (-1.40,1.40):window(m,xx,y,4.75,2.1,1.6)
    for side in (-1,1):
        with m.at((side*w/2,0,0),side*90):
            window(m,0,-.1,4.63,1.7,1.55)
            window(m,.55,-.1,1.77,1.35,1.35)
    with m.at((0,d/2,0),180):
        for xx in (-2,2):window(m,xx,-.1,4.63,1.45,1.35)
        window(m,0,-.1,1.9,1.4,1.25)
    roof(m,w,d,5.85,1.95)
    for xx in (-3.70,3.70):
        m.box((xx,-4.04,1.5275),(.18,.18,3.135),'wood')
        lantern(m,xx,-3.9,5.1,.59)
    for yy,top in [(-4.25,.15),(-3.87,.30)]:
        m.box((-2,yy,(top-.06)/2),(1.85,.42,top+.06),'stone_light',.02)
        m.collider((-2,yy,top/2),(1.85,.42,top))
    bench(m,1.55,-4.06,w=2.6)
    pot(m,-3.6,-4.35,key='bluepot',scale=1.25,plant=True)
    pot(m,3.6,-4.32,key='bluepot',scale=1.2,plant=True)


def workshop(m,w,d):
    shell(m,w,d,3.0,True)
    y=-d/2-.13
    # Shaded shopfront display remains exterior scenery; closed wall behind shelves.
    m.box((0,y-.09,1.53),(w-1,.15,2.30),'wood_dark')
    for zz in (.40,1.08,1.84):m.box((0,y-.40,zz),(4.8,.65,.12),'wood_light')
    for xx in (-2.3,0,2.3):m.box((xx,y-.40,.91),(.10,.59,1.90),'wood')
    for row,zz in enumerate((.46,1.14,1.9)):
        for k in range(6):pot(m,-1.98+k*.76,y-.42,zz,scale=.58+R.random()*.35,key='bluepot' if (k+row)%4==0 else 'clay',form=('jar','bowl','bottle','urn')[(k+row)%4])
    awning(m,0,y,2.75,w+1,1.35,'green')
    m.box((0,y-1.35,2.55),(w+1,.035,.23),'green_dark')
    for xx in (-w/2-.2,w/2+.2):
        m.box((xx,y-1.25,1.40),(.15,.16,2.8),'wood')
        m.beam((xx,y-1.25,2.1),(xx+(-.6 if xx>0 else .6),y-1.25,2.62),.1,.1,'wood_light')
    roof(m,w,d,3.0,1.3,'green')
    lantern(m,-2.64,y-1.24,2.10,.50)
    pot(m,w/2+.56,y-.52,0,1.85,'clay')
    pot(m,-w/2-.55,y-.50,0,1.2,'bluepot',True)
    pot(m,1.63,y-1.45,0,1.0,'clay')
    with m.at((w/2,0,0),90):window(m,0,-.1,1.70,1.3,1.15)
    with m.at((0,d/2,0),180):
        door(m,0,-.1,h=2.05)
        for yy,top in [(-.9,.15),(-.5,.30)]:
            m.box((0,yy,(top-.06)/2),(1.65,.45,top+.06),'stone_light',.02)
            m.collider((0,yy,top/2),(1.65,.45,top))


def storehouse(m,w,d):
    shell(m,w,d,3.65)
    y=-d/2-.10
    door(m,0,y,w=1.65,h=2.65)
    for offset,top,depth in [(.55,.15,1.15),(.24,.30,.55)]:
        m.box((0,y-offset,(top-.08)/2),(2.0,depth,top+.08),'stone_light',.035)
        m.collider((0,y-offset,top/2),(2.0,depth,top))
    # Turn the gable towards the front, like the narrow storehouse in the concept.
    with m.at(yaw=90):roof(m,d,w,3.65,1.45)
    for zz in (.80,2.45):
        for xx in (-.76,.76):m.box((xx,y-.18,zz),(.21,.075,.09),'metal')
    with m.at((w/2,0,0),90):window(m,0,-.1,2.65,.65,.65)


def garden(m):
    # Compact roofed well with no raised platform or perimeter fence.
    with m.at((0,-1.65,0),90):
        for row in range(3):
            for k in range(12):
                a=(k+.5*(row%2))*math.tau/12
                with m.at((math.cos(a)*(.79+R.uniform(-.018,.018)),math.sin(a)*.79,.16+row*.27+R.uniform(-.012,.012)),math.degrees(a)+R.uniform(-3,3)):
                    m.box((0,0,0),(.34+R.uniform(-.015,.015),.41+R.uniform(-.012,.012),.29),color_variant('well_stone',.13),.06)
        for k in range(12):
            a=k*math.tau/12
            with m.at((math.cos(a)*.80,math.sin(a)*.80,.86),math.degrees(a)):
                m.box((0,0,0),(.40,.43,.17),color_variant('well_cap',.10),.045)
        m.poly([(math.cos(i*math.tau/16)*.65,math.sin(i*math.tau/16)*.65,.3) for i in range(16)],'water')
        m.collider((0,0,.43),(1.85,1.85,.88))
        for xx in (-1.02,1.02):
            m.box((xx,0,1.27),(.16,.18,2.6),'wood_light',.02)
            m.collider((xx,0,1.3),(.17,.20,2.6))
            m.beam((xx,0,2.02),(xx*.50,0,2.53),.095,.11,'wood')
        m.beam((-1.13,0,1.70),(1.17,0,1.70),.14,.14,'wood_dark')
        m.beam((1.18,0,1.7),(1.18,0,1.4),.075,.09,'wood_light')
        m.beam((1.18,0,1.4),(1.4,0,1.4),.08,.08,'wood')
        m.beam((0,0,1.72),(0,0,.92),.025,.025,'soil')
        # Broad overlapping wooden shingles, with a closed pitched underside.
        for side in (-1,1):
            pts=[(-1.34,0,2.82),(1.34,0,2.82),(1.34,side*.97,2.28),(-1.34,side*.97,2.28)]
            if side<0:pts.reverse()
            m.poly(pts,'wood_dark');m.poly([(x,y,z-.075) for x,y,z in pts[::-1]],'wood')
            for row in range(4):
                for col in range(7):
                    x=-1.34+(col+.5)*2.68/7
                    a=row/4;b=(row+1)/4
                    pts=[(x-.187,side*a*.97,2.85-a*.54),(x+.187,side*a*.97,2.85-a*.54),
                         (x+.18,side*b*1.01,2.85-b*.54+.015),(x-.18,side*b*1.01,2.85-b*.54+.015)]
                    m.poly(pts if side>0 else pts[::-1],color_variant('wood_light',.16))
            m.beam((-1.37,side*.99,2.3),(1.37,side*.99,2.3),.10,.12,'wood')
        m.beam((-1.4,0,2.86),(1.4,0,2.86),.16,.13,'wood_light')
        # Open staved bucket with two dark hoops and a curved wooden handle.
        with m.at((.22,-.55,.95)):
            m.lathe((0,0,0),[(0,.18),(.33,.23),(.35,.23),(.35,.19),(.06,.15)],'wood_light',12)
            for zz in (.07,.28):m.lathe((0,0,0),[(zz,.20+zz*.14),(zz+.035,.205+zz*.14)],'wood_dark',12)
            for k in range(8):
                a=k*math.pi/8;b=(k+1)*math.pi/8
                m.beam((math.cos(a)*.22,0,.33+math.sin(a)*.22),(math.cos(b)*.22,0,.33+math.sin(b)*.22),.025,.025,'wood')
    # Face the well from its side; leave the maple trunk and its roots clear.
    z=float(upper_surface(HEIGHTS,102,86.5))-float(plane(99,85))-.015
    with m.at((3,1.5,z),0):bench(m,0,0,w=2.2)
    for x,y,r in [(-1.4,-3.0,.35),(-2.0,-2.1,.32),(-1.65,-.6,.30),(-.95,.5,.36),(.0,.9,.28)]:
        with m.at((x,y,-.03),R.uniform(0,180)):
            m.box((0,0,0),(r*1.8,r*1.4,.10),color_variant('stone_light',.1),.07)


def sign(m):
    m.box((0,0,1.03),(.16,.17,2.16),'wood')
    # The board itself points along local +X; both faces carry the same world
    # direction, so reading the back cannot send the player towards the road.
    profile=[(-.60,1.61),(.42,1.61),(.75,1.85),(.42,2.09),(-.60,2.09)]
    front=[(x,-.065,z) for x,z in profile];back=[(x,.065,z) for x,z in profile]
    m.poly(front,'wood_light');m.poly(back[::-1],'wood_light')
    for k in range(5):m.poly([front[k],back[k],back[(k+1)%5],front[(k+1)%5]],'wood')
    for side in (-1,1):
        y=side*.085
        m.beam((-.46,y,1.86),(-.20,y,2.02),.055,.025,'paper')
        m.beam((-.20,y,2.02),(.06,y,1.86),.055,.025,'paper')
        m.box((-.20,y,1.78),(.30,.025,.15),'paper')
        m.box((.24,y,1.83),(.25,.026,.065),'paper')
        pts=[(.33,y,1.94),(.59,y,1.83),(.33,y,1.72)]
        m.poly(pts if side>0 else pts[::-1],'paper')
    m.collider((0,0,1),(.17,.17,2))


def ground(world,h):
    m=Mesh('Village_Ground');paths=[np.array(p) for p in world['village']['paths']]
    # One continuous ground patch: unions avoid z-fighting at forks and aprons.
    step=.5;axisx=np.arange(64,179+step,step);axisy=np.arange(-32,108+FOREST_OFFSET_Y+step,step)
    x,y=np.meshgrid(axisx,axisy)
    distance=np.full(x.shape,np.inf);z=np.zeros(x.shape)
    for path in paths:
        d,zz=nearest(x,y,path);closer=d<distance
        z=np.where(closer,zz,z);distance=np.minimum(distance,d)
    # Follow the actual exported triangulated terrain surface, never a floating decal.
    terrain=upper_surface(h,x,y)
    z=terrain+.035
    # Narrow woodland trail, gently widening only inside the hamlet.
    half_width=1.3+.6*smooth((y-(FOREST_OFFSET_Y-12))/12)
    signed=distance-half_width+.16*np.sin(x*.73)*np.cos(y*.57)+.045*np.sin(x*2.7+y*1.7)
    apron_signed=np.full(x.shape,np.inf)
    for b in world['village']['buildings']:
        bx,by,bz=b['position'];a=math.radians(b['yaw'])
        lx=(x-bx)*math.cos(a)+(y-by)*math.sin(a)
        ly=-(x-bx)*math.sin(a)+(y-by)*math.cos(a)
        front=np.maximum.reduce([np.abs(lx)-(b['width']/2+1),ly+b['depth']/2-.2,-ly-b['depth']/2-4.2])
        apron_signed=np.minimum(apron_signed,front)
        # Narrow doorstep paths connect the five aprons to the lane network.
        door=np.array([bx+math.sin(a)*(b['depth']/2+2),by-math.cos(a)*(b['depth']/2+2),bz])
        allpoints=np.concatenate(paths)
        target=allpoints[np.argmin(np.linalg.norm(allpoints[:,:2]-door[:2],axis=1))]
        connection,_=nearest(x,y,np.array([door,target]))
        apron_signed=np.minimum(apron_signed,connection-1.05)
    # Small fountain forecourt and one pedestrian connection, with a planted
    # island around it. A full oval of paving made the village read as a track.
    court=np.hypot((x-99),1.1*(y-FOREST_OFFSET_Y-13.0))-3.8
    approach,_=nearest(x,y,np.array([village_point(88.,11.,20.4),village_point(99.,13.,20.5)]))
    apron_signed=np.minimum(apron_signed,np.minimum(court,approach-1.1))
    signed=np.minimum(signed,apron_signed)
    verge_colour=smooth((signed+.40)/.40)
    # Never paint across the asphalt: clip the dirt precisely at its shoulder.
    road_distance,_=nearest(x,y,np.array(world['road']))
    signed=np.maximum(signed,world['road_width']/2+.025-road_distance)
    for j in range(len(axisy)-1):
        for i in range(len(axisx)-1):
            corners=[(i,j),(i+1,j),(i+1,j+1),(i,j+1)]
            if min(signed[jj,ii] for ii,jj in corners)>0:continue
            base=np.array(PALETTE['lane'])
            variation=.017*math.sin(x[j,i]*.31)*math.sin(y[j,i]*.37)
            # Clip each triangle at the signed verge. Smooth edges, no grid stairs.
            triangles=[(0,1,2),(0,2,3)] if z[j,i]+z[j+1,i+1]>=z[j,i+1]+z[j+1,i] else [(0,1,3),(1,2,3)]
            for triangle in triangles:
                verts=[(np.array([x[jj,ii],y[jj,ii],z[jj,ii]]),signed[jj,ii]) for ii,jj in [corners[k] for k in triangle]]
                clipped=[]
                for k,(b,db) in enumerate(verts):
                    a,da=verts[k-1]
                    if (da<=0)!=(db<=0):clipped.append(a+(b-a)*(da/(da-db)))
                    if db<=0:clipped.append(b)
                if len(clipped)>=3:
                    m.poly(clipped,tuple(base+variation))
                    for k,p in enumerate(clipped):
                        base=np.array(PALETTE['lane'])
                        variation=.024*math.sin(p[0]*.31)*math.sin(p[1]*.37)+.007*math.sin(p[0]*1.1+p[1]*.82)
                        u=(p[0]-axisx[i])/step;v=(p[1]-axisy[j])/step
                        edge=(verge_colour[j,i]*(1-u)*(1-v)+verge_colour[j,i+1]*u*(1-v)+verge_colour[j+1,i]*(1-u)*v+verge_colour[j+1,i+1]*u*v)
                        base=base*(1-edge)+np.array([.20,.205,.065])*edge
                        m.colors[-len(clipped)+k]=(*tuple(base+variation),0)
    return m



def edges(world,h):
    m=Mesh('Village_Edges')
    runs=[[(70,-3),(70,18),(74,22)],[(76,36),(84,40),(93,40)],[(110,43),(119,35)],[(130,15),(130,4),(125,-10)]]
    paths=[np.array(p) for p in world['village']['paths']]
    runs=[[village_point(*p) for p in run] for run in runs]
    for run in runs:
        for a,b in zip(run[:-1],run[1:]):
            a=np.array(a,dtype=float);b=np.array(b,dtype=float);length=np.linalg.norm(b-a)
            count=math.ceil(length/.95);direction=(b-a)/length
            yaw=math.degrees(math.atan2(direction[1],direction[0]))
            for i in range(count):
                p=a+(b-a)*(i+.5)/count
                if min(float(nearest(*p,path)[0]) for path in paths)<3.8:continue
                z=float(sample(h,*p))
                with m.at((*p,z),yaw):
                    m.box((0,0,.12),(length/count-.025,.48,.60),color_variant('stone'),.05)
                    m.collider((0,0,.16),(length/count,.48,.55))
                    if i%3==0:
                        m.box((0,0,.78),(.14,.14,.96),'wood_light')
                    for zz in (.73,1.06):m.box((0,0,zz),(length/count,.095,.085),'wood_light')
    return m



def main():
    global WORLD, HEIGHTS
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'assets').mkdir(exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mat=bpy.data.materials.new('VillagePalette');mat.use_nodes=True
    nodes=mat.node_tree.nodes;vc=nodes.new('ShaderNodeVertexColor');vc.layer_name='Color'
    bsdf=nodes.get('Principled BSDF');mat.node_tree.links.new(vc.outputs['Color'],bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value=.92;bsdf.inputs['Specular IOR Level'].default_value=.10
    world=json.loads((yori.OUT/'world.json').read_text());h=np.load(yori.OUT/'heightmap.npy')
    WORLD,HEIGHTS=world,h
    mesh_kernel.HEIGHTS = h
    mesh_kernel.OUT = OUT
    manifest={};objects={}
    for name,_,_,w,d in BUILDINGS:
        m=Mesh(name)
        if name.endswith('TeaHouse'):tea_house(m,w,d)
        elif name.endswith('CottageA'):cottage(m,w,d,'A')
        elif name.endswith('CottageB'):cottage(m,w,d,'B')
        elif name.endswith('Workshop'):workshop(m,w,d)
        else:storehouse(m,w,d)
        objects[name],manifest[name]=export(m,mat)
    for name,fn in [('Village_Garden',garden),('Village_Sign',sign)]:
        m=Mesh(name);fn(m);objects[name],manifest[name]=export(m,mat)
    m=ground(world,h);objects[m.name],manifest[m.name]=export(m,mat)
    m=edges(world,h);objects[m.name],manifest[m.name]=export(m,mat)
    from village.decorations import furnish,planting,threshold
    for fn in (furnish,planting,threshold):
        m=fn(sys.modules[__name__]);objects[m.name],manifest[m.name]=export(m,mat)
    # A usable modelling scene: actual layout, separated editable mesh assets.
    for name,obj in objects.items():
        p=world['instances'][name][0]
        obj.location=p[:3];obj.rotation_euler.z=math.radians(p[3])
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'Village.blend'))
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    sources=[HERE/'build.py',HERE/'mesh.py',HERE/'layout.py',HERE/'decorations.py',HERE/'references/concept.png',HERE/'references/buildings.png',HERE/'references/polish.png',HERE/'references/forest-approach.png',HERE/'references/well-nook.png']
    sources=[p for p in sources if p.exists()]  # the concept images stay in the prototype archive
    identity={'sources':{str(p.relative_to(ROOT)):sha(p) for p in sources},
        'world_sha256':sha(yori.OUT/'world.json'),'heightmap_sha256':sha(yori.OUT/'heightmap.npy'),
        'exports':{p.name:sha(p) for p in sorted((OUT/'assets').glob('*.fbx'))}}
    (OUT/'build-identity.json').write_text(json.dumps(identity,indent=2)+'\n')
    print('VILLAGE BUILD COMPLETE',sum(v['triangles'] for v in manifest.values()),'triangles',flush=True)

if __name__=='__main__':main()
