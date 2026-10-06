"""Build the full-scale plywood mini-mega and its woodland trail."""
import sys as _sys; from pathlib import Path as _Path; _sys.path.insert(0, str(_Path(__file__).resolve().parents[2])); import yori  # noqa: E402,F401
import sys,json,math,hashlib
from pathlib import Path
import bpy
import numpy as np
ROOT=yori.REGIONS
import village.build as meshlib
from village.build import Mesh
from mega.layout import ORIGIN
from mega.ramp import profiles,rollout,WIDTH
from village.layout import upper_surface
OUT=yori.OUT/'mega'

def behind(profile,p,clear=.15):
    """p, moved back along the ride's normal until it is at least `clear` behind the ply: a brace ending under the vert's
    near-vertical face would otherwise poke its beam through it."""
    a=np.array(profile);p=np.array(p,float);seg=a[1:]-a[:-1];L=np.linalg.norm(seg,axis=1)
    s=np.clip(((p-a[:-1])*seg).sum(1)/L**2,0,1);foot=a[:-1]+s[:,None]*seg;k=np.linalg.norm(p-foot,axis=1).argmin()
    n=np.array([-seg[k,1],seg[k,0]])/L[k];depth=float((p-foot[k])@n)   # >0 on the riding side
    return tuple(p-(depth+clear)*n) if depth>-clear else tuple(p)

def main():
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'assets').mkdir(exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mat=bpy.data.materials.new('MegaPalette');mat.use_nodes=True
    vc=mat.node_tree.nodes.new('ShaderNodeVertexColor');vc.layer_name='Color'
    mat.node_tree.links.new(vc.outputs['Color'],mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
    mat.node_tree.nodes['Principled BSDF'].inputs['Roughness'].default_value=.92
    meshlib.OUT=OUT
    # Mega_Ramp is everything ridden or stood on and is the ramp's collision. Mega_Trim is look only (AMegaRamp gives
    # it no collision): the seams between the sheets and the coping, so no wheel catches on a millimetre of trim.
    m=Mesh('Mega_Ramp');trim=Mesh('Mega_Trim');wood=(.16,.073,.027);edge=(.25,.13,.055);ply=(.52,.32,.13);metal=(.08,.085,.078)
    for profile in profiles():
        # The backing sheet sits 15 cm behind the ply along its normal, so it stays behind the vert's true vertical.
        t=np.gradient(np.array(profile),axis=0);t/=np.linalg.norm(t,axis=1)[:,None]
        back=(np.array(profile)-.15*np.column_stack([-t[:,1],t[:,0]])).tolist()
        for i,(a,b) in enumerate(zip(profile[:-1],profile[1:])):
            x,z=a;xx,zz=b;(bx,bz),(bxx,bzz)=back[i],back[i+1]
            shade=1+.018*math.sin((x+xx)*.9)
            m.poly([(x,-4,z),(xx,-4,zz),(xx,4,zz),(x,4,z)],tuple(c*shade for c in ply))
            m.poly([(bx,4,bz),(bxx,4,bzz),(bxx,-4,bzz),(bx,-4,bz)],wood)
            for y in [-4,4]:
                m.poly([(x,y,z),(bx,y,bz),(bxx,y,bzz),(xx,y,zz)],edge)
            if i%12==0:m.beam((x,-4,z-.25),(x,4,z-.25),.12,.15,wood)
            # Fine seams between the sheets: a strip 1 mm above the ply along its normal.
            if i%32==0:
                L=math.hypot(xx-x,zz-z);tx,tz=(xx-x)/L,(zz-z)/L;nx,nz=-tz,tx
                (x0,z0),(x1,z1)=[(x+s*.004*tx+.001*nx,z+s*.004*tz+.001*nz) for s in (-1,1)]
                trim.poly([(x0,-4,z0),(x1,-4,z1),(x1,4,z1),(x0,4,z0)],edge)
        a=np.array(profile)
        for x in np.arange(a[0,0],a[-1,0]+.01,2.8):
            z=float(np.interp(x,a[:,0],a[:,1]))-.2
            for y in [-3.75,0,3.75]:
                m.box((x,y,z/2-.05),(.22,.22,z+.10),wood)
                m.box((x,y,-.04),(.60,.60,.25),(.23,.22,.17),.025)
            nx=min(x+2.8,a[-1,0]);nz=float(np.interp(nx,a[:,0],a[:,1]))-.3
            if min(z,nz)>.7:
                nx,nz=behind(a,(nx,nz))
                for y in [-3.75,3.75]:
                    m.beam((x,y,.18),(nx,y,nz),.12,.13,wood)
        for y in [-4.035,4.035]:
            for a,b in zip(profile[:-1],profile[1:]):
                if y<0 and b[0]>43 and a[0]<53:continue   # the rollout leaves over this side
                m.beam((a[0],y,a[1]-.1),(b[0],y,b[1]-.1),.09,.13,edge)
    route=np.array(rollout());tangent=np.gradient(route[:,:2],axis=0)
    tangent/=np.linalg.norm(tangent,axis=1)[:,None]
    normal=np.column_stack([-tangent[:,1],tangent[:,0]])
    for i in range(len(route)-1):
        points=[]
        for k,side in [(i,-1),(i+1,-1),(i+1,1),(i,1)]:
            p=route[k,:2]+normal[k]*side*1.8
            points.append((*p,route[k,2]))
        m.poly(points,ply)
        for a,b in [(points[0],points[1]),(points[2],points[3])]:
            m.poly([a,(a[0],a[1],0),(b[0],b[1],0),b],edge)
    # Tower platform is included in first profile. Rails surround three sides,
    # leaving the roll-in and the side ladder opening clear.
    for x in [-3,0]:
        for y in [-4,4]:m.box((x,y,11.25),(.14,.14,1.25),wood)
    for z in [11.15,11.85]:
        m.beam((-3,-4,z),(-3,4,z),.11,.11,edge)
        m.beam((-3,4,z),(0,4,z),.11,.11,edge)
        m.beam((-.7,-4,z),(0,-4,z),.11,.11,edge)
    # Ladder leans towards deck. Rungs remain evenly spaced in world height.
    for x in [-2.6,-1.5]:m.beam((x,-5.55,.0),(x,-4.,11.75),.11,.14,edge)
    for z in np.arange(.30,11.0,.30):
        y=-5.55+z/11.75*1.55
        m.beam((-2.6,y,z),(-1.5,y,z),.075,.075,edge)
    end,top=profiles()[1][-1]
    # The deck behind the vert starts on the wall's own top edge: no face of it stands at the lip.
    b,f=top-.2,end+2.7
    for poly in [[(end,-4,top),(f,-4,top),(f,4,top),(end,4,top)],[(end,-4,b),(end,4,b),(f,4,b),(f,-4,b)],
                 [(f,-4,b),(f,4,b),(f,4,top),(f,-4,top)],[(end,-4,b),(f,-4,b),(f,-4,top),(end,-4,top)],
                 [(f,4,b),(end,4,b),(end,4,top),(f,4,top)]]:m.poly(poly,ply)
    trim.beam((end,-4,top),(end,4,top),.065,.065,metal)
    for x in [end+.15,end+2.7]:
        for y in [-4,4]:m.box((x,y,(top+1)/2),(.20,.20,top+1),wood)
    for z in [top+.55,top+1.05]:
        m.beam((end+2.7,-4,z),(end+2.7,4,z),.11,.11,edge)
        for y in [-4,4]:m.beam((end,y,z),(end+2.7,y,z),.11,.11,edge)
    # Quiet rest spot beside the return route.
    m.box((-7,-7,.52),(2,.48,.13),edge)
    for x in [-7.75,-6.25]:m.box((x,-7,.22),(.16,.38,.5),wood)
    m.box((-8,-6,1.05),(.14,.14,2.3),wood)
    m.box((-8,-6,1.9),(1.25,.13,.64),edge,.03)
    # Skateboard pictogram, geometrically modelled.
    m.box((-8,-6.08,1.9),(.7,.025,.15),(.72,.60,.34),.03)
    for x in [-8.23,-7.77]:m.box((x,-6.10,1.78),(.09,.05,.09),(.72,.60,.34),.02)
    objects={};report={}
    objects[m.name],report[m.name]=meshlib.export(m,mat)
    objects[trim.name],report[trim.name]=meshlib.export(trim,mat)
    world=json.loads((yori.OUT/'world.json').read_text());h=np.load(yori.OUT/'heightmap.npy')
    path=np.array(world['mega']['trail']);m=Mesh('Mega_Trail')
    tangent=np.gradient(path[:,:2],axis=0);tangent/=np.linalg.norm(tangent,axis=1)[:,None]
    normal=np.column_stack([-tangent[:,1],tangent[:,0]])
    for i in range(len(path)-1):
        for side in [-1,1]:
            points=[]
            for k,offset in [(i,0),(i+1,0),(i+1,side*1.35),(i,side*1.35)]:
                p=path[k,:2]+normal[k]*offset
                points.append((*p,float(upper_surface(h,*p))+.045))
            if side<0:points.reverse()
            m.poly(points,(.26,.14,.046))
    objects[m.name],report[m.name]=meshlib.export(m,mat)
    objects['Mega_Ramp'].location=objects['Mega_Trim'].location=ORIGIN
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/'ForestMega.blend'))
    report['dimensions']={'roll_in_height_m':10.7,'gap_m':10.4,'quarter_pipe_height_m':6.1,'width_m':8.}
    (OUT/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print('MEGA BUILD COMPLETE',report,flush=True)
if __name__=='__main__':main()
