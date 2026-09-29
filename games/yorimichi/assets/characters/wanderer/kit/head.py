"""Head proportions taken from the original front and side portrait crops.

Front: chin (112,228), eyes at y=170, 1.75 mm / source pixel.
Side: chin y=233, eyes y=180, 1.90 mm / source pixel.
The independently scaled crops agree on eye height and crown height.
"""
import math
import mesh_tools as G

FRONT_SCALE=.00175
SIDE_SCALE=.00190

def front(u,v): return ((u-112)*FRONT_SCALE,1.100+(228-v)*FRONT_SCALE)
def side(u,v): return (-(u-90)*SIDE_SCALE,1.100+(233-v)*SIDE_SCALE)

def build_head():
    # Narrow cheeks, a short jaw, and a curved front surface. The old flat shield
    # exposed both eyes in profile and made the face much wider than the source.
    ob=G.loft('Measured head volume',[
        (0,-.084,1.100,.002,.002),
        (0,-.020,1.130,.067,.087),
        (0,.003,1.170,.091,.117),
        (0,.012,1.220,.095,.123),
        (0,.012,1.280,.088,.122),
        (0,.012,1.333,.054,.071)],'skin','head',n=16)
    for p in ob.data.polygons: p.use_smooth=True
    G.loft('Neck',[(0,.015,1.008,.034,.032),(0,.011,1.182,.038,.035)],'skin','neck',n=8)
    # The tiny nose is part of the continuous face surface, so it has no
    # separate seam or needle-like shadow in the front view.
    front_nose=ob.data.vertices[2*16+12]
    front_nose.co.y=-.125
    front_nose.co.z=1.165
    ob.data.update()
    for s,suf in ((1,'L'),(-1,'R')):
        G.box('Eye '+suf,(s*.049,-.098,1.2015),(.018,.002,.035),'ink','eye_'+suf,.002,
              rotation=(0,0,s*.49))
        G.ribbon('Eyebrow '+suf,[(s*.031,-.107,1.241),(s*.062,-.088,1.243)],
                 .005,'hair_dark','head',thickness=.001)
        # An ear is a volume on the SIDE of the head, not a front-facing cuboid.
        trace=[(83,169),(93,172),(98,181),(96,190),(99,200),(89,204),(77,197),(73,183)]
        widths=[.105,.116,.123,.124,.113,.108,.096,.101]
        rim=[(s*x,*side(u,v)) for x,(u,v) in zip(widths,trace)]
        inner=[(s*(x-.006),*side(86+(u-86)*.62,186+(v-186)*.64)) for x,(u,v) in zip(widths,trace)]
        back=[(s*.089,y,z) for _,y,z in rim]
        n=len(rim)
        verts=rim+inner+back
        faces=[(i,(i+1)%n,(i+1)%n+n,i+n) for i in range(n)]
        faces += [tuple(range(n,2*n))]
        faces += [(i,2*n+i,2*n+(i+1)%n,(i+1)%n) for i in range(n)]
        faces += [tuple(range(2*n,3*n))]
        colours=['skin']*n+['skin_shadow']+['skin']*(n+1)
        ear=G.mesh('Sculpted ear '+suf,verts,faces,'skin','head',face_colours=colours)
        for p in ear.data.polygons: p.use_smooth=True
    from hair import build_hair
    build_hair()
