"""Broad polygonal hair masses traced from the user's original portrait crops.

No swept tubes, splines or oval cross-sections. Front and side boundaries are
recorded in source-image pixels; the patches meet a closed faceted cranial mass.
"""
import math
import bmesh
import bpy
from mathutils import Vector
import mesh_tools as G
from head import front,side

def lerp_at(z,table):
    if z<=table[0][0]: return table[0][1]
    for (a,x),(b,y) in zip(table,table[1:]):
        if z<=b: return x+(y-x)*(z-a)/(b-a)
    return table[-1][1]

def dimensions(z):
    rx=lerp_at(z,[(1.10,.030),(1.18,.132),(1.24,.165),(1.31,.163),(1.365,.126),(1.405,.055)])
    depth=lerp_at(z,[(1.10,.035),(1.18,.105),(1.24,.166),(1.31,.161),(1.365,.106),(1.405,.027)])
    return rx,depth

def front_surface(u,v,bias=0):
    x,z=front(u,v); rx,depth=dimensions(z)
    return (x,-depth*math.sqrt(max(.06,1-(x/rx)**2))+.008+bias,z)

def outer_silhouette(u,v):
    # These are the rear/lateral tips visible outside the fringe in the front
    # crop. Placing them on the forehead also obscures the ear in profile.
    x,z=front(u,v)
    y=lerp_at(z,[(1.16,.110),(1.21,.095),(1.28,.060),(1.35,.022)])
    return x,y,z

def side_surface(u,v,s):
    y,z=side(u,v); rx,depth=dimensions(z)
    # The back of the cranium is fuller than the forehead.
    depth=max(depth,lerp_at(z,[(1.10,.071),(1.18,.140),(1.28,.168),(1.35,.134),(1.405,.039)]))
    x=s*(rx*math.sqrt(max(.04,1-(y/depth)**2))+.005)
    return (x,y,z)

def patch(name,points,faces,normal,col='hair',thickness=.026):
    # A substantial inner wedge enters the underlying hair mass. A thin bevel at
    # the boundary supplies a chisel edge, while the outside remains broad planes.
    points=list(map(Vector,points)); n=len(points); N=Vector(normal).normalized()
    inner=[p-N*thickness for p in points]
    v=[tuple(p) for p in points+inner]
    f=list(faces)+[tuple(n+i for i in reversed(face)) for face in faces]
    edges={}
    for face in faces:
        for a,b in zip(face,face[1:]+face[:1]):
            key=tuple(sorted((a,b)));edges[key]=edges.get(key,0)+1
    for (a,b),count in edges.items():
        if count==1: f.append((a,b,b+n,a+n))
    ob=G.mesh(name,v,f,col,'head')
    # Broad polygon boundaries are the style; triangulation of the interior
    # must not create the accidental crumpled-paper lighting of a fan mesh.
    me=ob.data
    outer=me.polygons[:len(faces)]
    average={i:Vector() for i in range(n)}
    for face in outer:
        for i in face.vertices: average[i]+=face.normal*face.area
    normals=[tuple(p.normal) for p in me.polygons for _ in p.loop_indices]
    for face in outer:
        face.use_smooth=True
        for loop in face.loop_indices:
            normals[loop]=tuple(average[me.loops[loop].vertex_index].normalized())
    me.normals_split_custom_set(normals)
    return ob

def traced_patch(name,trace,centre,project,normal,col='hair',bias=0):
    points=[project(*p) for p in trace]
    c=Vector(project(*centre))+Vector(normal).normalized()*bias
    points.append(tuple(c));n=len(trace)
    # Pairs of boundary edges share one broad face instead of a smooth tube.
    faces=[]
    for i in range(0,n,2):
        indices=[i,(i+1)%n]
        if i+2<=n: indices.append((i+2)%n)
        indices.append(n)
        faces.append(tuple(indices))
    return patch(name,points,faces,normal,col)

def crown_solid(name,points):
    """Close a few measured 3D corners without extending either silhouette."""
    bm=bmesh.new()
    verts=[bm.verts.new(p) for p in points]
    bmesh.ops.convex_hull(bm,input=verts,use_existing_faces=False)
    bm.verts.index_update()
    v=[tuple(p.co) for p in bm.verts]
    f=[tuple(p.index for p in face.verts) for face in bm.faces]
    bm.free()
    return G.mesh(name,v,f,'hair','head')

def scalp():
    n=16;v=[]
    for j in range(5):
        for i in range(n):
            a=2*math.pi*i/n;x,y=math.sin(a),-math.cos(a)
            f=max(0,math.cos(a));side_amount=abs(math.sin(a))
            z=[1.397,1.369,1.295,1.155+.122*f+.074*side_amount,
               1.105+.176*f+.111*side_amount][j]
            rx,front_r,back_r=[(.038,.020,.035),(.103,.077,.113),(.135,.115,.157),
                              (.117,.104,.140),(.051,.076,.065)][j]
            if j==4 and f<.2: z += [.003,-.006,.006,-.003][i%4]
            v.append((rx*x,(front_r if y<0 else back_r)*y,z))
    faces=[(j*n+i,j*n+(i+1)%n,(j+1)*n+(i+1)%n,(j+1)*n+i) for j in range(4) for i in range(n)]
    faces += [tuple(range(n-1,-1,-1)),tuple(4*n+i for i in range(n))]
    G.mesh('Faceted cranial hair mass',v,faces,'hair','head')

def build_hair():
    start=len(G.PARTS)
    scalp()
    # Side traces deliberately retain the sharp changes in direction visible in
    # the source. They do not taper into the old curved leaf shapes.
    side_patches=[
        ('Nape silhouette',[(18,166),(54,167),(72,180),(83,211),(77,230),(68,225),
          (61,231),(53,224),(43,219),(29,207),(22,202),(19,203),(18,185),(9,189)],(42,193),'hair_dark'),
        ('Middle side plane',[(43,130),(91,136),(105,139),(91,157),(69,174),(49,184),
          (34,180),(18,185),(19,170),(3,169),(12,146),(26,135)],(51,155),'hair'),
        ('Upper side plane',[(67,83),(77,91),(73,110),(65,124),(62,136),(40,135),
          (37,142),(20,143),(22,135),(8,139),(7,116),(39,93)],(48,112),'hair'),
        ('Temple plane',[(123,97),(145,107),(148,132),(138,153),(119,171),(103,180),
          (106,197),(99,190),(92,171),(105,148),(114,124)],(123,143),'hair'),
    ]
    for s in (-1,1):
        for order,(name,trace,centre,col) in enumerate(side_patches):
            if order==2: continue
            def project(u,v,s=s,order=order):
                x,y,z=side_surface(u,v,s)
                if order==3: x*=.73
                else: x-=s*[.012,.006,0][order]
                return x,y,z
            traced_patch(name+' '+str(s),trace,centre,project,(s,0,0),col,.003)
        # One connected surface with two broad crown regions. Separate overlapping
        # patches here made a dark slit that is absent from the reference.
        trace=[(67,83),(77,78),(105,87),(116,100),(121,126),(115,134),(94,138),
            (74,136),(62,136),(40,135),(37,142),(20,143),(22,135),(8,139),
            (7,116),(39,93),(76,104),(74,135),(45,112),(101,109)]
        faces=[(0,16,17,18),(17,7,8,18),(8,9,10,18),(10,11,12,18),
            (12,13,14,18),(14,15,0,18),(0,1,2,19),(2,3,4,19),(4,5,6,19),
            (6,7,17,19),(17,16,19),(16,0,19)]
        patch('Connected side crown '+str(s),[side_surface(u,v,s) for u,v in trace],faces,(s,0,0),'hair',.026)
    # The silhouette's small outer blades are separate from the long fringe.
    traced_patch('Left outer silhouette',[(51,88),(35,115),(14,132),(31,135),(44,129)],
        (35,120),outer_silhouette,(0,-1,0),'hair_dark')
    traced_patch('Right outer silhouette',[(175,102),(206,136),(190,136),(179,127)],
        (187,128),outer_silhouette,(0,-1,0),'hair')
    traced_patch('Left low silhouette',[(38,126),(50,147),(45,169),(27,179),(24,163)],
        (35,153),outer_silhouette,(0,-1,0),'hair_dark')
    traced_patch('Right low silhouette',[(190,132),(197,156),(197,178),(177,172),(174,155)],
        (184,155),outer_silhouette,(0,-1,0),'hair')
    # Exact front boundaries, with a few broad planar faces over the volume.
    traced_patch('Left angular fringe',[(105,59),(96,90),(89,117),(75,137),(58,154),
        (42,167),(35,151),(47,107),(69,73)],(74,112),lambda u,v:front_surface(u,v,-.007),(0,-1,0),'hair',.003)
    traced_patch('Right angular fringe',[(125,64),(151,75),(173,101),(189,133),(179,131),
        (176,157),(165,153),(156,165),(141,137),(135,112)],(154,112),lambda u,v:front_surface(u,v,-.006),(0,-1,0),'hair',.003)
    traced_patch('Centre angular fringe',[(106,58),(126,70),(137,96),(135,116),
        (121,138),(94,153),(94,119),(99,85)],(116,105),lambda u,v:front_surface(u,v,-.014),(0,-1,0),'hair_light',.003)
    # Short lifted crown blade: this is what gives the side reference its nearly
    # horizontal top, rather than the round cap of the rejected construction.
    patch('Forward crown blade',[(.012,.020,1.402),(.119,-.135,1.396),
        (.107,-.121,1.358),(.060,-.066,1.366),(.020,.020,1.381)],
        [(0,1,2,3),(0,3,4)],(0,0,1),'hair',.025)
    # A bent polygonal tuft with an oblique cut, not an oval sprout.
    crown_solid('Bent crown tuft',[(-.009,.049,1.375),(-.021,.089,1.420),
        (-.0175,.057,1.452),(.0525,.114,1.471),(.042,.046,1.426),(.016,.048,1.378)])
    crown_solid('Short crown fork',[(-.021,.055,1.390),(-.108,.120,1.384),
        (-.054,.118,1.410),(-.070,.144,1.402),(-.005,.055,1.389),(-.073,.080,1.368)])
    for ob in G.PARTS[start:]:
        bevel=ob.modifiers.new('Small chisel edge','BEVEL')
        bevel.width=.0012
        bevel.segments=1
        bevel.limit_method='ANGLE'
        bevel.angle_limit=.80
        bevel.harden_normals=True
        bpy.context.view_layer.objects.active=ob
        bpy.ops.object.modifier_apply(modifier=bevel.name)
