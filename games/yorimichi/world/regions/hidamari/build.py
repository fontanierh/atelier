"""Build modular Hidamari assets, surface collision and harbor geometry."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import json,math,sys,hashlib,os
from pathlib import Path
import bpy,numpy as np
from mathutils import Matrix
ROOT=yori.REGIONS
from hidamari.layout import OUT,height,street_height,terrain_axes,pond,canal,generate,ROAD_X,ROAD_Y
from village import build as v
from hidamari import harbor as harbor_kit
from hidamari import arcade as arcade_kit
from hidamari import plaza as plaza_kit
from hidamari import mountains, living_plaza, pond_garden, living_streets, working_harbor, civic_gardens
from hidamari import kit
from hidamari.layout import backdrop_height,north_height,north_base_height
v.OUT=OUT
v.PALETTE.update({'paving':(.22,.18,.125),'asphalt':(.075,.085,.09),'park':(.24,.30,.12),'cream':(.66,.57,.41),'blue':(.08,.19,.25),'brick':(.31,.12,.055),'water_city':(.075,.24,.29)})
M=v.Mesh

def simple_roof(m,w,d,z,rise=2):
    w+=1.1;d+=1.3
    # Closed soffit prevents sky showing through the projecting gable ends.
    m.box((0,0,z-.06),(w,d,.15),'wood_dark')
    for s in [-1,1]:
        pts=[(-w/2,0,z+rise),(w/2,0,z+rise),(w/2,s*d/2,z),( -w/2,s*d/2,z)]
        m.poly(pts[::-1] if s<0 else pts,'roof')
        m.beam((-w/2,s*d/2,z),(w/2,s*d/2,z),.24,.24,'roof_edge')
        for i in range(1,7):
            y=s*d/2*i/7;zz=z+rise*(1-i/7)
            m.beam((-w/2,y,zz),(w/2,y,zz),.055,.055,'roof_edge')
    for x in [-w/2,w/2]:
        m.poly([(x,-d/2,z),(x,d/2,z),(x,0,z+rise)][::-1 if x<0 else 1],'plaster_light')
        m.beam((x,-d/2,z),(x,0,z+rise),.2,.2,'roof_edge');m.beam((x,d/2,z),(x,0,z+rise),.2,.2,'roof_edge')
    m.beam((-w/2,0,z+rise),(w/2,0,z+rise),.3,.25,'roof_edge')

def lettering(m,text,position,size=1.0,color='cream'):
    curve=bpy.data.curves.new('sign','FONT');curve.body=text;
    if any(ord(c)>127 for c in text):curve.font=bpy.data.fonts.load(str(ROOT/'hidamari/fonts/NotoSansJP.ttf'),check_existing=True)
    curve.align_x='CENTER';curve.size=size;curve.extrude=.006;curve.resolution_u=1
    ob=bpy.data.objects.new('sign',curve);bpy.context.collection.objects.link(ob);ob.location=position;ob.rotation_euler.x=math.pi/2
    bpy.context.view_layer.objects.active=ob;ob.select_set(True);bpy.ops.object.convert(target='MESH')
    for face in ob.data.polygons:m.poly([ob.matrix_world@ob.data.vertices[i].co for i in face.vertices],color)
    bpy.data.objects.remove(ob,do_unlink=True)

def shop(i):
    m=M(f'HD_Shop_{i:02d}');w=20+(i%3);d=15+(i%2);floors=2+(i%4==0);h=floors*3.3
    wall=['cream','plaster_light','plaster','wood_light'][i%4]
    m.box((0,0,h/2-.4),(w,d,h+.8),wall);m.collider((0,0,h/2-.6),(w,d,h+1.2))
    m.box((0,0,-.6),(w+.4,d+.4,1.4),'stone')
    for y in [-d/2,d/2]:
        for x in [-w/2,-w/4,0,w/4,w/2]:m.box((x,y,h/2),(.17,.18,h),'wood')
        for z in [0,3.25,h]:m.box((0,y,z),(w+.15,.18,.18),'wood_light')
    for f in range(1,floors):
        for x in [-7,-2.4,2.4,7]:
            v.window(m,x,-d/2-.04,3.3*f+1.5,2.1,1.8,False)
            with m.at((0,0,0),180):v.window(m,x,-d/2-.04,3.3*f+1.5,2.1,1.8,False)
    # Broad storefront glazing and actual small display items, kept out of the street.
    v.door(m,0,-d/2-.08,z=.06,w=1.8,h=2.45)
    for x in [-6,6]:v.window(m,x,-d/2-.07,1.6,5.2,2.25,i%3==0)
    awn=['rust','blue','green','cream'][i%4]
    v.awning(m,0,-d/2-.15,3.3,w=w-.7,depth=1.8,key=awn)
    m.box((0,-d/2-.3,3.96),(w*.7,.20,.7),'wood_dark')
    lettering(m,['BOOKS','BAKERY','TEA','FLOWERS','RAMEN','SKATE','FISH','TOYS','COFFEE','POTTERY','MARKET','MUSIC','TAILOR','SENTO','SWEETS','BICYCLES'][i],(0,-d/2-.45,3.76),.48)
    # Pictorial signs: book, flower, tea, bowls, fish, board, produce, cloth.
    for j in [-1,1]:
        xx=j*5.4
        if i%4==0:
            m.box((xx,-d/2-.43,3.96),(.7,.08,.42),'cream');m.box((xx,-d/2-.49,3.96),(.045,.02,.4),'wood')
        elif i%4==1:
            m.lathe((xx,-d/2-.5,3.8),[(0,0),(.1,.32),(.3,.38)],'cream',8)
        else:m.box((xx,-d/2-.45,3.96),(.7,.07,.23),'paper',.08)
    for x in [-8,8]:
        v.pot(m,x,-d/2-1,.06,.9,'clay',plant=True)
    if i%3==0:
        for x in [-5,5]:
            m.box((x,-d/2-1,.8),(2.8,1.2,.15),'wood_light')
            for xx in [x-1,x+1]:m.box((xx,-d/2-1,.36),(.12,.65,.7),'wood')
            for k in range(6):
                m.box((x-1+k*.38,-d/2-1,1.05),(.28,.55,.35),['rust','green','cream'][k%3],.06)
    simple_roof(m,w,d,h,2.1)
    return m

def civic(name,w,d,h):
    m=M(name);v.shell(m,w,d,h);simple_roof(m,w,d,h,3)
    for x in np.linspace(-w/2+3,w/2-3,int(w/5)):
        v.window(m,float(x),-d/2-.1,h*.65,2.5,2.8,True)
    v.door(m,0,-d/2-.15,.06,3,3.5)
    for side in [-1,1]:
        with m.at((side*w/2,0,0),90*side):
            for x in [-d*.28,0,d*.28]:
                v.window(m,x,-.12,h*.63,2.5,2.8,True)
            m.box((0,-.1,3.7),(d,.18,.2),'wood_light')
    return m

def temple():
    m=M('HD_Temple');v.shell(m,24,17,6.5,True);v.roof(m,26,20,6.5,3.5)
    for side in [-1,1]:
        for row in range(8):
            a=row/8;b=(row+1)/8
            z=lambda t:6.5+3.5*(1-t)**1.10+.10*t**6-.035
            p=[(-13.65,side*10.675*a,z(a)),(13.65,side*10.675*a,z(a)),(13.65,side*10.675*b,z(b)),(-13.65,side*10.675*b,z(b))]
            m.poly(p if side>0 else p[::-1],'roof')
    # Ground-level veranda allows strolling; ceremonial stairs are optional front detail.
    m.box((0,-11,.19),(27,5,.50),'wood_light');m.collider((0,-11,.22),(27,5,.44))
    # Two shallow treads meet the 44 cm veranda instead of a single high jump.
    for yy,top in [(-14.05,.15),(-13.70,.30)]:
        m.box((0,yy,(top-.06)/2),(4.4,.40,top+.06),'stone_light',.02)
        m.collider((0,yy,top/2),(4.4,.40,top))
    # Continuous lean-to canopy connects the outer veranda posts to the roof.
    for x in [-11,-7,7,11]:
        m.box((x,-12,2.90),(.35,.35,5.80),'wood')
        m.collider((x,-12,2.90),(.35,.35,5.80))
    m.box((0,-12,5.80),(27.3,.32,.28),'wood_dark')
    for k in range(28):
        xa=-13.7+k*27.4/28;xb=xa+27.4/28
        points=[(xa,-9.8,6.9),(xb,-9.8,6.9),(xb,-13.5,5.47),(xa,-13.5,5.47)]
        m.poly(points[::-1],'roof');m.poly([(xx,yy,zz-.12) for xx,yy,zz in points],'wood_dark')
        m.beam((xa,-9.8,6.93),(xa,-13.5,5.5),.035,.04,'roof_edge')
    m.box((0,-13.5,5.46),(27.5,.16,.20),'roof_edge')
    # Match the canopy slope in the temple's authored simple collision.
    angle=math.atan2(1.43,3.7)
    old=m.transform.copy()
    m.transform=old @ Matrix.Translation((0,-11.65,6.125)) @ Matrix.Rotation(angle,4,'X')
    m.collider((0,0,0),(27.4,math.hypot(3.7,1.43),.12*math.cos(angle)))
    m.transform=old
    for bx in [-8,8]:
        m.collider((bx,-10.2,.6925),(3.4,.65,.505))
        for xx in [bx-1.35,bx+1.35]:m.box((xx,-10.2,.66),(.18,.65,.44),'wood')
        for j in range(4):m.box((bx,-10.45+j*.17,.90),(3.4,.145,.09),'wood_light')
    v.door(m,0,-8.65,.45,4,4.5)
    for x in [-8,8]:v.window(m,x,-8.65,3,4.8,3.6,True)
    return m

def shrine():
    m=civic('HD_Shrine',7,7,3.8)
    for x in [-4,4]:m.box((x,-8,2.8),(.32,.32,5.6),'rust')
    m.box((0,-8,5.3),(10,.5,.35),'rust');m.box((0,-8,4.7),(8.8,.4,.22),'wood_dark')
    return m

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

def arcade():
    return arcade_kit.canopy(lettering)


def playground():
    m=M('HD_Playground')
    for x in [-3,3]:
        for y in [-1.6,1.6]:m.beam((x,y,0),(x,0,3),.16,.16,'wood_light')
    m.beam((-3.3,0,3),(3.3,0,3),.24,.24,'wood')
    for x in [-1.5,1.5]:
        m.box((x,0,.55),(1,.5,.10),'rust')
        for dx in [-.43,.43]:m.beam((x+dx,0,.6),(x+dx,0,3),.025,.025,'metal')
    return m

def flowerbed(m,x,y,z,w=1.6,d=1.2):
    m.box((x,y,z+.3),(w,d,.6),'stone',.07)
    m.box((x,y,z+.61),(w-.18,d-.18,.05),'soil')
    for i in range(max(3,int(w/.4))):
        for j in range(max(2,int(d/.45))):
            xx=x-w/2+.25+i*(w-.5)/max(1,int(w/.4)-1)
            yy=y-d/2+.25+j*(d-.5)/max(1,int(d/.45)-1)
            zz=z+.66+.06*math.sin(i*3+j)
            m.lathe((xx,yy,zz),[(0,.13),(.18,.28),(.38,.12),(.43,0)],'green',6)
            m.lathe((xx+.04,yy,zz+.32),[(0,.04),(.09,.16),(.14,.13),(.17,0)],'paper' if (i+j)%3 else 'rust',6)

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

def boat():
    return harbor_kit.boat()

def lighthouse():
    m=M('HD_Lighthouse');m.lathe((0,0,0),[(0,3.2),(1,3.2),(1,2.5),(12,1.8)],'cream',12)
    m.lathe((0,0,8),[(0,2.08),(1.7,1.98)],'blue',12)
    m.lathe((0,0,12),[(0,2.6),(.4,2.6),(.4,1.8),(2,1.8)],'paper',12)
    m.lathe((0,0,14),[(0,2.7),(1.5,0)],'roof',12);m.collider((0,0,6),(4,4,12));return m

def grass_patch(x,y):
    return (y>235 or (min(abs(y-c) for c in ROAD_Y)>30 and min(abs(x-c) for c in ROAD_X)>20)) and not (660<x<805 and 135<y<215)

def surface(name,xs,ys,color):
    m=M(name)
    gx,gy=np.meshgrid(xs,ys);gz=height(gx,gy)
    for j,y in enumerate(ys[:-1]):
        for i,x in enumerate(xs[:-1]):
            dx=xs[i+1]-x;dy=ys[j+1]-y
            if (y<-125 and x>380) or pond(x+dx/2,y+dy/2) or canal(x+dx/2,y+dy/2):continue
            pts=[(float(gx[jj,ii]),float(gy[jj,ii]),float(gz[jj,ii])) for ii,jj in [(i,j),(i+1,j),(i+1,j+1),(i,j+1)]]
            key='park' if grass_patch(x+dx/2,y+dy/2) else color
            refine=name=='HD_Terrain' and ((980<x+dx/2<1080 and 224<y+dy/2<242) or (650<x+dx/2<835 and 254<y+dy/2<312))
            if refine and max(dx,dy)>.5:
                sx=np.linspace(x,x+dx,max(2,math.ceil(dx/.5)+1));sy=np.linspace(y,y+dy,max(2,math.ceil(dy/.5)+1))
                xx,yy=np.meshgrid(sx,sy);zz=height(xx,yy)
                for jj in range(len(sy)-1):
                    for ii in range(len(sx)-1):m.poly([(float(xx[b,a]),float(yy[b,a]),float(zz[b,a])) for a,b in [(ii,jj),(ii+1,jj),(ii+1,jj+1),(ii,jj+1)]],key)
            else:m.poly(pts,key)
    # Inset warm stone paving pattern: broad enough to read without fine texture noise.
    if name=='HD_Terrain':
        for y in np.arange(-119,240,6):
            for x in np.arange(380+(3 if int(y)%2 else 0),1300,6):
                if canal(x+2.9,y+2.9) or grass_patch(x+2.9,y+2.9):continue
                # Street kits own paving here; coarse decorative quads pierced curved shoulders.
                if min(abs(y+2.96-c) for c in ROAD_Y)<11:continue
                # Large old paver quads bridge slope breaks and pierce the finer plaza surface.
                if x<802 and x+5.92>660 and y<218 and y+5.92>122:continue
                # The old six-metre decorative quads would bridge the new terraces.
                px=np.array([x,x+2.96,x+5.92]);py=np.array([y,y+2.96,y+5.92])
                gx,gy=np.meshgrid(px,py)
                if np.max(abs(height(gx,gy)-street_height(gx,gy)))>.01:continue
                points=[(xx,yy,float(height(xx,yy))+.013) for xx,yy in [(x,y),(x+5.92,y),(x+5.92,y+5.92),(x,y+5.92)]]
                m.poly(points,(.235,.195,.14) if int(x+y)%3 else (.21,.175,.125))
    return m

def streets(city):
    m=M('HD_Streets')
    for path in city['roads']:
        for width,key,offset in [(8,'paving',.045),(3.8,'asphalt',.065)]:
            quads=[];cross=np.linspace(-width,width,math.ceil(width*2)+1)
            for a,b in zip(path,path[1:]):
                dx=b[0]-a[0];dy=b[1]-a[1];length=math.hypot(dx,dy)
                if length<.01:continue
                nx,ny=-dy/length,dx/length
                for lo,hi in zip(cross[:-1],cross[1:]):
                    quads.append([(p[0]+s*nx,p[1]+s*ny) for p,s in [(a,lo),(b,lo),(b,hi),(a,hi)]])
            if not quads:continue
            points=np.asarray(quads);zs=height(points[:,:,0],points[:,:,1])+offset
            for quad,zs_quad in zip(points,zs):m.poly([(float(p[0]),float(p[1]),float(z)) for p,z in zip(quad,zs_quad)],key)
    return living_streets.add(m,city,height,ROAD_X,ROAD_Y)

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

def square():
    return living_plaza.furniture(height,lettering)


def park():
    m=M('HD_Park')
    # The lakeside pavilion's northeast post crosses the excavated pond edge.
    # A masonry footing joins the bank and continues below the water surface;
    # its top matches the surrounding stone walk (rather than floating a post).
    m.box((989.5,268.5,29.5275),(2.2,2.2,2.655),'stone')
    # Pond sits in excavated ground; a simple boardwalk gives a clear crossing.
    for i in range(64):
        a=i*2*math.pi/64;b=(i+1)*2*math.pi/64
        inner=lambda t,z:(1030+46*math.cos(t),284+32*math.sin(t),z)
        outer=lambda t:(1030+51*math.cos(t),284+37*math.sin(t),30.85)
        m.poly([inner(a,30.85),outer(a),outer(b),inner(b,30.85)],'stone_light')
        m.poly([inner(a,30.85),inner(b,30.85),inner(b,28.5),inner(a,28.5)],'stone')
    for i in range(64):
        a=i*2*math.pi/64;b=(i+1)*2*math.pi/64
        if abs(math.sin(a))<.12:continue
        x,y=1030+49*math.cos(a),284+35*math.sin(a)
        nx,ny=1030+49*math.cos(b),284+35*math.sin(b)
        m.box((x,y,31.4),(.12,.12,1.2),'wood')
        m.beam((x,y,32),(nx,ny,32),.09,.09,'wood')
    from hidamari import garden_bridge
    garden_bridge.add(m)
    return pond_garden.add(m,height)

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

def main():
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'assets').mkdir(exist_ok=True)
    city=generate();text=json.dumps(city,indent=2)+'\n'
    # Atomic, unchanged-content-preserving write: single-asset rebuilds run alongside live captures.
    if not (OUT/'city.json').exists() or (OUT/'city.json').read_text()!=text:
        tmp=OUT/'city.json.tmp';tmp.write_text(text);tmp.replace(OUT/'city.json')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mat=bpy.data.materials.new('HidamariPalette');mat.use_nodes=True
    vc=mat.node_tree.nodes.new('ShaderNodeVertexColor');vc.layer_name='Color';mat.node_tree.links.new(vc.outputs['Color'],mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
    builders={f'HD_Shop_{i:02d}':(lambda i=i:shop(i)) for i in range(16)}
    builders.update({
        'HD_ClockHall':lambda:plaza_kit.clock_hall(lettering,height),
        'HD_Station':lambda:civic('HD_Station',46,18,8),
        'HD_Temple':temple,'HD_Shrine':shrine,'HD_Arcade':arcade,'HD_Playground':playground,
        'HD_Pavilion':pavilion,'HD_Market':lambda:pavilion('HD_Market',38,7),
        'HD_Boat':boat,'HD_Lighthouse':lighthouse,
        'HD_Terrain':lambda:surface('HD_Terrain',*terrain_axes(),'paving'),
        'HD_CivicGardens':lambda:civic_gardens.build(height,city,lettering),
        'HD_Streets':lambda:streets(city),'HD_Harbor':harbor,'HD_Park':park,'HD_Square':square,'HD_InlandWater':inland_water,
    })
    builders.update({f'HD_ArcadeShop_{i:02d}':(lambda i=i:arcade_kit.shop(i,lettering)) for i in range(6)})
    builders['HD_ArcadeGate']=lambda:arcade_kit.end_gate(lettering)
    builders['HD_ArcadeRoof']=arcade_kit.roof_panels
    builders['HD_ArcadeLanterns']=arcade_kit.canopy_lanterns
    builders['HD_ArcadeFloor']=lambda:arcade_kit.floor(height)
    builders['HD_ArcadeTree']=arcade_kit.tree
    builders['HD_PlazaShopSides']=plaza_kit.shop_sides
    builders['HD_PlazaShopSidesCorner']=lambda:plaza_kit.shop_sides(raised_rear=True)
    builders['HD_PlazaShopApproaches']=lambda:plaza_kit.shop_approaches(city,height)
    builders['HD_PlazaFloor']=lambda:plaza_kit.floor(height)
    builders['HD_PlazaFountain']=plaza_kit.fountain
    builders['HD_PlazaWater']=plaza_kit.fountain_water
    builders['HD_PlazaTreeGold']=plaza_kit.tree
    builders['HD_PlazaTreeOrange']=lambda:plaza_kit.tree(orange=True)
    for name in ['HD_Bench','HD_Planter','HD_Lamp','HD_Bollard','HD_Crate']:
        builders[name]=lambda name=name:prop(name)
    def sea_mesh():
        sea=M('HD_Sea');sea.poly([(300,-1600,.025),(1800,-1600,.025),(1800,600,.025),(300,600,.025)],'water_city');return sea
    builders['HD_Sea']=sea_mesh
    # Reference-led kit modules replace legacy shop variants by mesh name.
    builders.update(kit.builders(lettering))
    builders['HD_NorthMountains']=lambda:mountains.mesh(north_base_height)
    builders['HD_NorthTrail']=lambda:mountains.trail_mesh(north_height)
    from megapark import trail as park_trail
    builders['HD_NorthApproach']=park_trail.approach_mesh
    builders['HD_NorthParkTrail']=lambda:park_trail.trail_mesh(north_height)
    for kind in ('Gold','Rust','Pine'):builders['HD_NorthTree'+kind]=lambda kind=kind:mountains.forest_tree(kind)
    for kind in ('Gold','Rust','Pine','Green'):
        builders['HD_NorthTreeBackdrop'+kind]=lambda kind=kind:mountains.forest_tree(kind,backdrop=True)
    only=set(filter(None,os.environ.get('HIDAMARI_ASSETS','').split(',')))
    if only-set(builders):raise ValueError('Unknown city assets: '+str(only-set(builders)))
    manifest=json.loads((OUT/'manifest.json').read_text()) if only and (OUT/'manifest.json').exists() else {}
    for name,build in builders.items():
        if only and name not in only:continue
        mesh=build()
        ob,entry=v.export(mesh,mat);manifest[mesh.name]=entry
        bpy.data.objects.remove(ob,do_unlink=True)
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('HIDAMARI BUILD COMPLETE',len(city['buildings']),'buildings;',len(manifest),'assets;',sum(v['triangles'] for v in manifest.values()),'unique triangles',flush=True)
if __name__=='__main__':main()
