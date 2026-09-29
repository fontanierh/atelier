"""Wanderer V2, constructed from the generated orthographic model sheet."""
import math
import bpy
from mathutils import Vector
import mesh_tools as G
import shoe
from wanderer_hair import build_hair

PALETTE={
    'skin':'E9B780','skin_shadow':'CD945F','ear':'C98B59',
    'hair':'423D3B','hair_light':'49423F','hair_dark':'373333','ink':'29282A',
    'green':'70734F','green_light':'7E805C','green_dark':'595F40',
    'cream':'E4D9C5','cream_light':'EEE2CC','cream_shadow':'CFC3AC',
    'blue':'454F5D','blue_light':'505B68','blue_dark':'343E4A',
    'red':'AC5537','red_dark':'89432C','red_light':'B76240',
    'leather':'725139','leather_light':'805E43','leather_dark':'563D2B',
    'sole':'AA8659','hat':'C8A064','hat_light':'D3AD70','hat_dark':'B68E53',
}

def head():
    ob=G.loft('Warm angular face',[(0,-.078,1.044,.003,.004),
        (0,-.019,1.074,.066,.088),(0,.006,1.119,.100,.119),
        (0,.010,1.178,.101,.128),(0,.011,1.252,.091,.129),
        (0,.012,1.338,.055,.073)],'skin','head',n=16)
    for p in ob.data.polygons:p.use_smooth=True
    ob.data.vertices[2*16+12].co.y=-.128
    ob.data.vertices[2*16+12].co.z=1.124
    G.loft('Short neck',[(0,.012,.982,.035,.033),(0,.010,1.135,.038,.035)],'skin','neck',n=8)
    for s,suf in ((1,'L'),(-1,'R')):
        G.box('Simple eye '+suf,(s*.055,-.102,1.1705),(.017,.002,.035),'ink','eye_'+suf,.0015,rotation=(0,0,s*.49))
        G.ribbon('Quiet eyebrow '+suf,[(s*.037,-.117,1.210),(s*.072,-.096,1.213)],.0045,'hair_dark','head',thickness=.001)
        rim=[(s*.099,-.030,1.180),(s*.121,-.025,1.179),(s*.132,-.016,1.163),
             (s*.128,-.007,1.133),(s*.111,-.005,1.118),(s*.100,-.017,1.125)]
        centre=Vector((s*.116,-.016,1.150))
        inset=[tuple(centre+(Vector(v)-centre)*.62+Vector((-s*.005,0,0))) for v in rim]
        n=len(rim);faces=[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]+[tuple(range(n,2*n))]
        ear=G.mesh('Faceted ear '+suf,rim+inset,faces,'skin','head',face_colours=['skin']*n+['skin_shadow'])
        for p in ear.data.polygons:p.use_smooth=True
    build_hair()

def torso_weights(p):
    # The cream underlayer, jacket opening and scarf roots travel together.
    return G.weights_z(p[2],[(.70,'pelvis'),(.81,'spine'),(.965,'chest'),(1.045,'chest')])

def coat_weight(p):
    if p[2]>=.725:return torso_weights(p)
    side='L' if p[0]>0 else 'R'
    thigh=max(0,min(.82,(.725-p[2])/.135)) if p[1]<.02 else 0
    return {'pelvis':1-thigh,'thigh_'+side:thigh}

def clothes():
    G.loft('Ivory shirt',[(0,0,.680,.135,.082),(0,0,.746,.141,.089),
        (0,.004,.870,.134,.088),(0,.007,.980,.120,.080),(0,.013,1.046,.052,.040)],'cream',torso_weights,n=12)
    G.panel('Shirt lower fold',[(-.098,-.091,.733),(-.057,-.096,.705),(-.004,-.099,.729),(.027,-.098,.705),(.092,-.091,.734)],
            [(0,1,2),(2,3,4)],'cream_shadow',torso_weights,.002)
    # Open haori: a broad back/sides with a large consistent front opening.
    angles=[.40,.72,1.05,1.40,1.70,2.08,2.48,2.85,math.pi,3.43,3.80,4.20,4.58,4.88,5.23,5.56,5.883]
    rings=[(.075,.071,1.036),(.150,.107,.964),(.156,.112,.830),(.173,.119,.600)]
    v=[]
    for rx,ry,z in rings:
        for a in angles:
            x=rx*math.sin(a);y=-ry*math.cos(a)
            v.append((x,y,z))
    n=len(angles)
    faces=[(j*n+i,j*n+i+1,(j+1)*n+i+1,(j+1)*n+i) for j in range(3) for i in range(n-1)]
    G.panel('Open moss haori',v,faces,'green',coat_weight,.008)
    for s in (-1,1):
        # Lapel remains outside the shirt and shares torso/hip deformation.
        pts=[(s*.029,-.069,1.036),(s*.054,-.096,.993),(s*.066,-.112,.897),
             (s*.074,-.122,.736),(s*.075,-.127,.598),(s*.111,-.121,.601),
             (s*.098,-.118,.745),(s*.093,-.109,.901),(s*.083,-.073,1.019)]
        G.panel('Broad haori lapel '+str(s),pts,[(0,1,7,8),(1,2,6,7),(2,3,5,6),(3,4,5)],'green_light',coat_weight,.005)
    G.loft('Dark trouser waistband',[(0,0,.664,.151,.091),(0,0,.715,.144,.088)],'blue_dark','pelvis',n=12)
    G.loft('Rust sash',[(0,0,.701,.148,.096),(0,0,.737,.145,.094)],'red','pelvis',n=12)
    G.loft('Thin leather belt',[(0,0,.682,.153,.098),(0,0,.704,.151,.098)],'leather','pelvis',n=12)
    # The scarf is a folded neckerchief with two short, readable tails.
    G.loft('Folded neckerchief',[(0,.008,1.000,.079,.072),(0,.012,1.034,.083,.075),
        (0,.012,1.063,.057,.050)],'red','chest',n=10,cap=False)
    for s in (-1,1):
        G.panel('Scarf front fold '+str(s),[(s*.008,-.100,.986),(s*.089,-.067,1.031),(s*.068,-.061,1.063),(s*.006,-.100,1.016)],
                [(0,1,2,3)],'red_light','chest',.007)
    G.box('Compact scarf knot',(0,-.120,1.008),(.055,.031,.058),'red','chest',.008,rotation=(0,0,.09))
    G.ribbon('Left scarf tail',[(-.018,-.130,.995),(-.029,-.142,.935),(-.040,-.139,.862)],[.042,.046,.040],'red','scarf_L',thickness=.008)
    G.ribbon('Right scarf tail',[(.022,-.132,.995),(.043,-.145,.938),(.059,-.141,.884)],[.040,.045,.038],'red_light','scarf_R',thickness=.008)

def hands(s,suf):
    dx=s*.011;dz=-.036
    def point(x,y,z):return (x+dx,y,z+dz)
    G.loft('Simple palm '+suf,[(s*.260+dx,-.011,.661+dz,.020,.020),(s*.269+dx,-.014,.616+dz,.029,.021),
        (s*.270+dx,-.016,.588+dz,.026,.019)],'skin','hand_'+suf,n=8)
    for i in range(4):
        x=s*(.247+i*.015)
        pts=[point(x,-.016,.603-(.004 if i==3 else 0)),point(x+s*.003,-.025,.571+abs(i-1)*.007),point(x+s*.001,-.040,.553+abs(i-1)*.007)]
        G.tube('Finger %d %s'%(i,suf),pts,[.009,.008,.006],'skin','finger_%d_%s'%(i,suf),sides=5,depth=.86)
    G.tube('Thumb '+suf,[point(s*.247,-.009,.626),point(s*.224,-.022,.602),point(s*.221,-.041,.580)],
           [.013,.011,.008],'skin','thumb_'+suf,sides=6)

def limbs():
    for s,suf in ((1,'L'),(-1,'R')):
        sh,el,wr=Vector((s*.112,0,.985)),Vector((s*.195,-.002,.800)),Vector((s*.271,-.011,.613))
        d=(wr-el).normalized()
        def armweight(p,suf=suf):
            return G.weights_z(p[2],[(.630,'forearm_'+suf),(.766,'forearm_'+suf),(.828,'upperarm_'+suf),(.985,'upperarm_'+suf)])
        G.tube('Broad haori sleeve '+suf,[tuple(sh),tuple(el),tuple(wr-d*.050)], [.055,.074,.079],'green',armweight,sides=8)
        G.tube('Ivory turned cuff '+suf,[tuple(wr-d*.064),tuple(wr-d*.024),tuple(wr-d*.012)], [.085,.085,.067],'cream_light','forearm_'+suf,sides=8)
        G.tube('Exposed wrist '+suf,[tuple(wr-d*.026),tuple(wr+d*.015)],[.027,.024],'skin','hand_'+suf,sides=8)
        hands(s,suf)
        G.loft('Calf '+suf,[(s*.130,.005,.107,.033,.034),(s*.128,.004,.190,.035,.036),(s*.122,.002,.258,.040,.039)],'skin','shin_'+suf,n=8)
        def pantsweight(p,suf=suf):
            return G.weights_z(p[2],[(.24,'shin_'+suf),(.333,'shin_'+suf),(.407,'thigh_'+suf),(.60,'thigh_'+suf),(.688,'pelvis')])
        G.loft('Cropped trousers '+suf,[(s*.075,0,.686,.081,.091),(s*.087,-.002,.591,.091,.099),
            (s*.103,-.008,.443,.094,.105),(s*.115,-.002,.286,.094,.089),(s*.120,0,.241,.065,.061)],'blue',pantsweight,n=8,cap=False,phase=math.pi/8)
        G.loft('Gathered trouser hem '+suf,[(s*.120,0,.239,.065,.062),(s*.119,0,.260,.068,.064)],'blue_dark','shin_'+suf,n=8,phase=math.pi/8)
        G.panel('Large trouser fold '+suf,[(s*.088,-.104,.600),(s*.143,-.106,.453),(s*.151,-.092,.302),(s*.125,-.109,.438)],
            [(0,1,3),(1,2,3)],'blue_light',pantsweight,.001)
        G.loft('Cream ankle cuff '+suf,[(s*.130,.005,.118,.042,.040),(s*.128,.004,.172,.042,.040)],'cream_light','shin_'+suf,n=8)
        first=len(G.PARTS);shoe.build(s*.130,suf)
        # Keep the shared footprint/contact convention, with a thinner sole band.
        for ob in G.PARTS[first:]:
            for v in ob.data.vertices:
                if abs(v.co.z-(shoe.SOLE_Z+shoe.THICKNESS))<1e-5:v.co.z=shoe.SOLE_Z+.014
    G.panel('Trouser crotch',[(-.070,-.092,.681),(.070,-.092,.681),(.050,-.101,.596),(0,-.101,.569),(-.050,-.101,.596)],
        [(0,1,2,3,4)],'blue','pelvis',.006)

def accessories():
    # A single small pouch on the front hip, with a flap large enough to read.
    G.box('Belt pouch',(.167,-.108,.638),(.111,.065,.145),'leather','bag',.007)
    G.panel('Pouch flap',[(.108,-.145,.713),(.221,-.145,.714),(.216,-.153,.659),(.191,-.156,.649),(.112,-.154,.663)],
        [(0,1,2,3,4)],'leather_light','bag',.008)
    G.box('Pouch tab',(.172,-.164,.665),(.026,.012,.031),'leather_dark','bag',.002)
    G.ribbon('Pouch belt loop',[(.158,-.106,.720),(.155,-.140,.700),(.155,-.145,.681)],.025,'leather_dark','bag',thickness=.005)
    # Simple twelve-panel conical hat. No woven microgeometry or texture noise.
    n=12;centre_z=.828;radius=.244;back_y=.134
    v=[(radius*math.sin(2*math.pi*i/n),back_y,centre_z+radius*math.cos(2*math.pi*i/n)) for i in range(n)]
    v += [(0,.306,centre_z)]+[(x,back_y-.010,z) for x,y,z in v]
    faces=[(i,(i+1)%n,n) for i in range(n)]
    faces += [(i,n+1+i,n+1+(i+1)%n,(i+1)%n) for i in range(n)]
    faces += [tuple(range(n+1,2*n+1))]
    colors=['hat_light' if i in (0,1,10,11) else 'hat_dark' if i in (5,6,7) else 'hat' for i in range(n)]
    colors+=['hat_dark']*n+['hat_dark']
    G.mesh('Twelve broad hat panels',v,faces,'hat','hat',face_colours=colors)
    for s in (-1,1):
        G.ribbon('Hat shoulder strap '+str(s),[(s*.071,.107,1.024),(s*.095,.036,1.035),(s*.101,-.071,.982),
            (s*.104,-.119,.921)],.019,'leather',torso_weights,thickness=.005)

def build_model():
    G.PARTS.clear();G.PALETTE.update(PALETTE)
    head();clothes();limbs();accessories()
    return list(G.PARTS)
