"""Readable household vignettes and low planted borders, in metre-scale geometry."""
import math
import numpy as np
from mathutils import Vector


def furnish(api):
    Mesh, P, R = api.Mesh, api.PALETTE, api.R
    m=Mesh('Village_Details')
    world=api.WORLD; h=api.HEIGHTS
    def ground(x,y):return float(api.upper_surface(h,x,y))+.03
    def table(x,y,z,w=1.1,d=.7):
        m.box((x,y,z+.70),(w,d,.10),'wood_light')
        for xx in (-w*.4,w*.4):
            for yy in (-d*.35,d*.35):m.box((x+xx,y+yy,z+.35),(.085,.085,.70),'wood')
        m.collider((x,y,z+.37),(w,d,.74))
    def cup(x,y,z,s=1):
        m.lathe((x,y,z),[(0,.07*s),(.10*s,.095*s),(.13*s,.095*s),(.13*s,.075*s),(.04*s,.068*s)],'bluepot',10)
    def crate(x,y,z,w=.72):
        for zz in (.12,.32,.52):
            for yy in (-.25,.25):m.box((x,y+yy,z+zz),(w,.055,.16),'wood_light')
            for xx in (-w/2,w/2):m.box((x+xx,y,z+zz),(.055,.50,.16),'wood_light')
        m.box((x,y,z+.05),(w,.5,.06),'wood')
        for xx in (-w/2,w/2):
            for yy in (-.23,.23):m.box((x+xx,y+yy,z+.28),(.06,.07,.55),'wood')
    def logs(x,y,z):
        for row in range(3):
            for k in range(4-row):
                with m.at((x+(k+row*.5)*.24,y,z+row*.21)):
                    # Broad cut ends and faceted bark; no hairline grain.
                    m.beam((0,-.46,.13),(0,.46,.13),.21,.21,'wood_dark')
                    m.box((0,-.465,.13),(.18,.014,.18),'wood_light',.035)
    for b in world['village']['buildings']:
        name=b['asset'];w=b['width'];y=-b['depth']/2
        with m.at(b['position'],b['yaw']):
            if name.endswith('TeaHouse'):
                # Service corner at the end of the porch, not on the road.
                table(-2.8,y-2.0,.1,1.65,.8)
                m.box((-2.8,y-2,.88),(1.15,.50,.04),'rust')
                api.pot(m,-2.82,y-2,.90,.33,'clay')
                for xx in (-3.23,-2.39):cup(xx,y-2.02,.91)
                for xx in (-3.9,-1.6):
                    m.box((xx,y-2,.35),(.39,.43,.1),'wood_light')
                    for yy in (-.14,.14):m.box((xx,y-2+yy,.17),(.3,.08,.34),'wood')
                crate(2.8,y-2.05,.1)
                for k in range(9):
                    api.pot(m,2.56+(k%3)*.23,y-2.23+(k//3)*.18,.49,.23,'rust')
                # Warm cloth-covered bench and large low flower box.
                m.box((1.55,y-.86,.50),(2.3,.45,.035),'rust')
                # A small side trellis, rather than an extra building silhouette.
                with m.at((-w/2-.18,-1.2,.10),-90):
                    for xx in (-.75,0,.75):m.box((xx,0,1.3),(.065,.065,2.6),'wood_light')
                    for zz in (.45,.95,1.45,1.95,2.45):m.box((0,0,zz),(1.65,.06,.055),'wood_light')
                    for k in range(29):
                        xx=R.uniform(-.8,.8);zz=R.uniform(.25,2.7);s=R.uniform(.12,.22)
                        pts=[(xx-s,-.045,zz),(xx,-.13,zz+s*.7),(xx+s,-.045,zz),(xx,-.08,zz-s*.8)]
                        m.poly(pts[::-1],api.color_variant('leaf',.30))
            elif name.endswith('Workshop'):
                table(.1,y-2.6,.1,1.9,.80)
                api.pot(m,.12,y-2.6,.88,.63,'clay')
                cup(-.55,y-2.7,.88)
                crate(-2.9,y-1.6,.02,.75)
                api.pot(m,-2.9,y-1.6,.58,.8,'clay')
                api.pot(m,2.5,y-2.0,.06,1.7,'bluepot')
                logs(w/2+.35,y+.3,.06)
            elif name.endswith('CottageA'):
                # Sheltered laundry nook on the rear side.
                for xx in (-2.0,2.0):m.box((xx,2.95,1.25),(.10,.10,2.5),'wood')
                m.beam((-2,2.95,2.4),(2,2.95,2.4),.026,.026,'wood_dark')
                for xx,key in [(-1.15,'rust'),(0,'paper'),(1.1,'bluepot')]:
                    # Faceted cloth; the material gives its free hem a small sway.
                    for k in range(4):
                        a=xx-.42+k*.21;bb=a+.21
                        m.poly([(a,2.95,2.38),(a,2.94+.04*math.sin(k),1.42),
                                (bb,2.94+.04*math.sin(k+1),1.42),(bb,2.95,2.38)],P[key])
                        for j,weight in enumerate((0,1,1,0)):m.colors[-4+j]=(*P[key],weight)
                        m.poly([(a,2.953,2.38),(bb,2.953,2.38),
                                (bb,2.95+.04*math.sin(k+1),1.42),(a,2.95+.04*math.sin(k),1.42)],P[key])
                        for j,weight in enumerate((0,0,1,1)):m.colors[-4+j]=(*P[key],weight)
                crate(w/2+.35,1.8,.03)
            elif name.endswith('CottageB'):
                with m.at((-w/2-.65,-.2,0),-90):logs(-.36,0,-.025)
                with m.at((-w/2-.08,-.2,0),-90):api.awning(m,0,0,1.1,1.9,1.2)
                crate(2.1,y-1.65,0)
                api.pot(m,2.7,y-.95,0,.9,'clay',True)
            else:
                crate(-1.5,y-1.0,.05,.75);crate(-1.48,y-.96,.60,.65)
                api.pot(m,1.55,y-.5,.05,1.35,'clay')
    return m


def planting(api):
    m=api.Mesh('Village_Planting');R=api.R;h=api.HEIGHTS;world=api.WORLD
    paths=[np.array(p) for p in world['village']['paths']]
    # Overlapping, uneven groups rather than an evenly decorated perimeter.
    beds=world['village']['planting_beds']
    def clear(x,y):
        if min(float(api.nearest(x,y,p)[0]) for p in paths)<3.2:return False
        for b in world['village']['buildings']:
            px,py,_=b['position'];a=math.radians(b['yaw']);dx=x-px;dy=y-py
            lx=dx*math.cos(a)+dy*math.sin(a);ly=-dx*math.sin(a)+dy*math.cos(a)
            if abs(lx)<b['width']/2+1.45 and -b['depth']/2-2.8<ly<b['depth']/2+1.1:return False
        # Keep the fountain approach and customer bench open.
        if 95.5<x<102.2 and 10.0+api.FOREST_OFFSET_Y<y<18.0+api.FOREST_OFFSET_Y:return False
        return True
    def rosette(x,y,z,s,flower=False):
        for k in range(5):
            a=k*math.tau/5+R.random()*.3
            base=Vector((x,y,z));tip=base+Vector((math.cos(a)*s,math.sin(a)*s,.50*s))
            side=Vector((-math.sin(a),math.cos(a),0))*.20*s
            mid=base.lerp(tip,.60)+Vector((0,0,.18*s))
            col=api.color_variant('leaf',.25)
            m.poly([base,mid+side,tip,mid-side],col)
            m.poly([base,mid-side,tip,mid+side],col)
        if flower:
            zz=z+.6*s
            m.beam((x,y,z),(x,y,zz),.025,.025,'leaf')
            color=R.choice([(.58,.31,.035),(.73,.67,.47),(.45,.057,.015)])
            for k in range(5):
                a=k*math.tau/5;rr=.17*s;xx=x+rr*math.cos(a);yy=y+rr*math.sin(a)
                m.poly([(xx+math.cos(a+j*math.tau/5)*rr,yy+math.sin(a+j*math.tau/5)*rr,zz+.035*math.sin(j)) for j in range(5)],color)
            m.poly([(x+math.cos(k*math.tau/6)*.06*s,y+math.sin(k*math.tau/6)*.06*s,zz+.035) for k in range(6)],'paper')
    for cx,cy,rx,ry in beds:
        # Soil disks sit below the dense leaves, with small broken stone borders.
        for k in range(42):
            a=R.random()*math.tau;r=math.sqrt(R.random());x=cx+math.cos(a)*r*rx;y=cy+math.sin(a)*r*ry
            if not clear(x,y):continue
            z=float(api.upper_surface(h,x,y))+.05
            rosette(x,y,z,R.uniform(.28,.52),flower=k%3==0)
        for k in range(13):
            a=k*math.tau/13;x=cx+math.cos(a)*rx;y=cy+math.sin(a)*ry
            if not clear(x,y):continue
            z=float(api.upper_surface(h,x,y))
            if k%3==0:
                with m.at((x,y,z),math.degrees(a)):
                    m.box((0,0,.02),(.36,.65,.25),api.color_variant('stone'),.06)
    # Autumn litter is one opaque batched mesh: no per-leaf actor, tick or
    # masked overdraw. Irregular drifts beneath maples, with loose trail leaves.
    rng=np.random.default_rng(2481)
    xs=rng.uniform(69,132,14000);ys=rng.uniform(-12,44,14000)+api.FOREST_OFFSET_Y
    ds=np.minimum.reduce([api.nearest(xs,ys,p)[0] for p in paths])
    near_maple=np.minimum.reduce([np.hypot(xs-x,ys-(y+api.FOREST_OFFSET_Y)) for x,y in [(100,16),(96,38),(94,3),(72,21),(125,29)]])
    patch=.5+.5*np.sin(xs*.49+np.sin(ys*.35))*np.sin(ys*.57)
    probability=np.where(near_maple<4.2,.97,np.where(ds<1.0,.07,.08+.40*patch**3))
    selected=rng.random(len(xs))<probability
    colours=[(.43,.105,.012),(.48,.235,.025),(.30,.073,.014),(.57,.32,.045)]
    def leaf(x,y,z,size,angle):
        # Concise six-vertex folded leaf keeps a dense layer affordable.
        outline=[(-.9,0),(-.25,-.65),(.2,-.42),(1,0),(.15,.65),(-.35,.48)]
        c=R.choice(colours);ca=math.cos(angle);sa=math.sin(angle)
        pts=[(x+(a*ca-b*sa)*size,y+(a*sa+b*ca)*size,z+.008*(i%2)) for i,(a,b) in enumerate(outline)]
        m.poly(pts,c)
    for x,y,d,take in zip(xs,ys,ds,selected):
        if not take or d>14:continue
        in_nook=95.5<x<102.2 and 10+api.FOREST_OFFSET_Y<y<18+api.FOREST_OFFSET_Y
        if not clear(x,y) and d>3.2 and not in_nook:continue
        if math.hypot(x-99,y-(13.35+api.FOREST_OFFSET_Y))<1.0:continue
        half=1.3+.6*float(api.smooth((y-(api.FOREST_OFFSET_Y-12))/12))
        on_dirt=d<half+.15 or math.hypot(x-99,1.1*(y-(13+api.FOREST_OFFSET_Y)))<3.8
        z=float(api.upper_surface(h,x,y))+(.052 if on_dirt else .025)
        leaf(x,y,z,R.uniform(.055,.125),R.random()*math.tau)
        if math.hypot(x-100,y-(16+api.FOREST_OFFSET_Y))<3.6:
            for _ in range(3):
                xx=x+R.uniform(-.16,.16);yy=y+R.uniform(-.16,.16)
                leaf(xx,yy,z+R.uniform(.002,.014),R.uniform(.07,.13),R.random()*math.tau)
    for path in paths:
        for i in range(8,len(path)-4,2):
            p=path[i];t=path[i+1,:2]-path[i-1,:2];t/=np.linalg.norm(t);side=np.array([-t[1],t[0]])
            half=1.3+.6*float(api.smooth((p[1]-(api.FOREST_OFFSET_Y-12))/12))
            for sign in (-1,1):
                for k in range(4):
                    x,y=p[:2]+side*sign*R.uniform(half*.6,half+1.1)+t*R.uniform(-.6,.6)
                    if y< -20:continue
                    d=float(api.nearest(x,y,path)[0])
                    leaf(x,y,float(api.upper_surface(h,x,y))+(.052 if d<half+.15 else .025),R.uniform(.06,.13),R.random()*math.tau)

    return m


def threshold(api):
    m=api.Mesh('Village_Threshold')
    for x in (-3.15,3.15):
        m.box((x,0,1.65),(.23,.26,3.7),'wood')
        m.collider((x,0,1.65),(.25,.28,3.7))
        m.box((x,0,.04),(.47,.52,.55),'stone',.06)
        m.beam((x,0,2.65),(x+(.65 if x<0 else -.65),0,3.30),.14,.14,'wood_light')
    m.box((0,0,3.42),(7.05,.32,.28),'wood_light')
    cap=[(-3.65,3.82),(-2.8,3.66),(0,3.60),(2.8,3.66),(3.65,3.82)]
    for (a,za),(b,zb) in zip(cap,cap[1:]):
        top=[(a,-.36,za),(b,-.36,zb),(b,.36,zb),(a,.36,za)]
        bottom=[(x,y,z-.16) for x,y,z in top]
        m.poly(top,'roof_edge');m.poly(bottom[::-1],'roof_edge')
        for k in range(4):m.poly([top[k],bottom[k],bottom[(k+1)%4],top[(k+1)%4]],'roof')
    m.collider((0,0,3.48),(7.3,.6,.42))
    # Hanging timber waymark, without illegible pseudo-lettering.
    m.box((0,-.19,3.04),(1.30,.13,.52),'wood')
    leaf=[(-.24,0),(-.12,.07),(-.22,.18),(-.07,.15),(0,.34),(.07,.15),(.22,.18),(.12,.07),(.24,0),(.09,-.05),(.06,-.14),(-.06,-.14),(-.09,-.05)]
    m.poly([(x*.8,-.265,3.02+z*.65) for x,z in leaf][::-1],'paper')
    m.beam((0,-.27,2.96),(.04,-.27,2.87),.025,.025,'paper')
    # A modest stone path lantern sits outside the clear riding width.
    m.box((-4.05,0,.14),(.75,.70,.42),'stone',.075)
    m.box((-4.05,0,.61),(.32,.34,.60),'stone_light',.045)
    m.box((-4.05,0,1.03),(.60,.56,.14),'stone')
    m.box((-4.05,0,1.29),(.37,.37,.39),'paper')
    for x in (-.235,.235):
        for y in (-.235,.235):m.box((-4.05+x,y,1.28),(.09,.09,.44),'stone')
    m.lathe((-4.05,0,1.5),[(0,.52),(.12,.46),(.32,.10),(.41,0)],'stone',4)
    m.collider((-4.05,0,.77),(.76,.72,1.9))
    return m
