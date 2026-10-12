"""Branching leaf-card crowns shared by island and Mediterranean trees.

The same seeded branches and lobes generate every detail level. They use the
island's existing foliage normals, wind weights and atlas material convention.
"""
import math
import random

from mathutils import Vector

from forest.specs import TUSCAN, FOREST


def tree(name, kind, seed, height, spread, leaf):
    import build_assets as A
    rng = random.Random(seed)
    mesh = A.Mesh(name); bark = A.MATS['Bark']; foliage = A.MATS[leaf]
    lean = Vector((rng.uniform(-.35, .35), rng.uniform(-.35, .35), 0))
    fork_height = height * (.25 if kind == 'olive' else .58 if kind == 'stone-pine' else .26 if kind == 'oak' else .44)
    fork = lean + Vector((0, 0, fork_height))
    bends = [Vector((0, 0, -.25)), lean*.4+Vector((.13, -.08, fork_height*.45)), fork]
    radius = .58 if kind == 'olive' else .48 if kind in ('oak','stone-pine') else .32
    for i, (a, b) in enumerate(zip(bends, bends[1:])):
        mesh.tube(a, b, radius*(1-i*.24), radius*(.75-i*.25), bark, n=10, uvscale=(1, .4))
    lobes = []
    if kind in ('cypress', 'cedar'):
        mesh.tube(fork, lean+Vector((0, 0, height*.94)), .17, .035, bark, n=8)
        for level in range(9):
            t = level/8
            z = height*(.12+.85*t) if kind=='cypress' else height*(.19+.74*t)
            width = spread*(.34*(1-t)**.65+.025) if kind=='cypress' else spread*(.5*(1-t)+.05)
            width *= .72+.28*math.sin(math.pi*t)**.5
            centre = lean*(z/height)+Vector((rng.uniform(-.12,.12),rng.uniform(-.12,.12),z))
            lobes.append((centre, (width, width, height*(.06 if kind=='cypress' and level==8 else .10 if kind=='cypress' else .115))))
    elif kind == 'pine':
        mesh.tube(fork, lean+Vector((0,0,height*.91)), .17, .04, bark, n=8)
        for level in range(7):
            t=level/6
            for side in range(3):
                angle=side*math.tau/3+level*1.8
                radius=spread*(.37*(1-t)+.045)
                centre=lean+Vector((math.cos(angle)*radius*.55,math.sin(angle)*radius*.55,height*(.47+.45*t)))
                lobes.append((centre,(radius,radius,height*.07)))
    elif kind=='olive':
        for leader in range(3):
            angle=leader*math.tau/3+.25
            reach=spread*.25
            centre=Vector((math.cos(angle)*reach,math.sin(angle)*reach,height*(.63+.06*(leader%2))))
            joint=fork+(centre-fork)*.55+Vector((.25,-.18,.15))
            if getattr(mesh,'branch_detail',True):
                mesh.tube(fork,joint,.26,.19,bark,n=8)
                mesh.tube(joint,centre,.19,.07,bark,n=7)
            lobes.append((centre,(spread*.24,spread*.24,height*.22)))
            for side in (-1,1):
                offset=Vector((math.cos(angle+side*.9),math.sin(angle+side*.9),.35))*spread*.11
                lobes.append((centre+offset,(spread*.16,spread*.16,height*.15)))
    else:
        umbrella = kind == 'stone-pine'
        centre_z = .85 if umbrella else .62 if kind=='oak' else .68
        depth = height*(.095 if umbrella else .21 if kind=='oak' else .15)
        lobes.append((lean+Vector((0,0,height*(.91 if umbrella else .83))), (spread*.30,spread*.30,depth)))
        for ring, count in ((0, 6), (1, 4)):
            for i in range(count):
                angle=i*math.tau/count+ring*.63+rng.uniform(-.22,.22)
                reach=spread*(.30 if ring == 0 else .18)
                centre=lean+Vector((math.cos(angle)*reach,math.sin(angle)*reach,
                                    height*(centre_z+(ring-.5)*.10)+rng.uniform(-.25,.25)))
                lobes.append((centre,(spread*rng.uniform(.22,.27),spread*rng.uniform(.22,.27),depth)))
    for centre, radii in (lobes if getattr(mesh,'branch_detail',True) else []):
        branch_end=fork+(centre-fork)*.78
        thickness=.23 if kind in ('olive','oak','stone-pine') else .11
        mesh.tube(fork-Vector((0,0,.12)),branch_end,thickness,.045,bark,n=6,uvscale=(1,.5))
        middle=fork+(centre-fork)*.55
        twig=middle+Vector((rng.uniform(-.7,.7),rng.uniform(-.7,.7),.5))
        mesh.tube(middle,twig,.035,.009,bark,n=5)
    volumes=[r[0]*r[1]*r[2] for _,r in lobes]
    cards=2100 if kind in ('oak','stone-pine','cypress') else 1700
    card_size=.58 if kind == 'cypress' else .82 if kind == 'olive' else .95
    normal_centre=lean+Vector((0,0,height*.53))
    for (centre,radii), volume in zip(lobes,volumes):
        count=max(1,round(cards*volume/sum(volumes)))
        mesh.begin_canopy(count)
        size=card_size*min(1.,max(.3,radii[0]/(spread*.30))) if kind=='cypress' else card_size
        A.leaf_canopy(mesh,centre,radii,count,size,
                      foliage,rng,normal_center=normal_centre,vertical_bias=.30)
    obj=mesh.build()
    if '_LOD' not in name:obj['trunk_collision']=[(.58 if kind=='olive' else .48 if kind in ('oak','stone-pine') else .32)*1.25,0.,0.,-.25,*fork]
    return obj
