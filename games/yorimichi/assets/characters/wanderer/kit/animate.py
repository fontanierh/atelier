"""In-place, 60 Hz clips authored on the short-legged reference proportions.

Body mechanics: the pelvis drops at every heel strike and rises over the stance leg (a walk is lowest at
double support, a run lowest at mid-stance), the swing-side hip drops while the shoulders stay level, the
chest counter-rotates the pelvis, the head stays level and nods with the bounce, arms carry a forward
bias with elbows that fold as they come forward. Secondary parts are simulated from the attachment
accelerations (see motion.py), and a lifted thigh pushes the sash tail out of its way.
"""
import json
import math
import sys
from math import sin,cos,pi
from pathlib import Path
import bpy
from mathutils import Vector,Matrix,Euler
from rig import aim_matrix,two_bone
import shoe
sys.path.insert(0,str(Path(__file__).resolve().parent))
import motion
from motion import smooth,keys

ACTIONS={
    'Idle':dict(duration=4,loop=True),
    'Walk':dict(duration=58/60,loop=True,speed=.85,stance=.60,lift=.060,arm=.34),
    'Jog':dict(duration=44/60,loop=True,speed=1.75,stance=.32,lift=.115,arm=.49),
    'Run':dict(duration=40/60,loop=True,speed=2.90,stance=.25,lift=.160,arm=.64),
    # Full sprint: a longer, lower stride with a real flight phase, so fast running is a different gait instead of the
    # run clip played at 2.5x. Blended in above the run sample; only speeds beyond it raise the play rate.
    'Sprint':dict(duration=40/60,loop=True,speed=5.50,stance=.135,lift=.28,arm=.92,lean=36,sprint=True,toe=34,takeoff=.08,landing=.03,bounce=.018,flight_rise=.015),
    'CrouchIdle':dict(duration=3,loop=True,crouch=True),
    'CrouchWalk':dict(duration=1.1,loop=True,speed=.50,stance=.72,lift=.04,arm=.20,crouch=True),
    'JumpStart':dict(duration=.14),'JumpRise':dict(duration=.55),
    'DoubleJump':dict(duration=.75),
    'Fall':dict(duration=1.1,loop=True),'Land':dict(duration=.44),'HardLand':dict(duration=.70),
    'Dodge':dict(duration=.74),'Interact':dict(duration=1.35),'Wave':dict(duration=2.4),
    'SitDown':dict(duration=1.2),'SitIdle':dict(duration=3,loop=True),'StandUp':dict(duration=1.1),
    'Climb':dict(duration=1.2,loop=True),'Glide':dict(duration=2.4,loop=True),
    'TurnLeft':dict(duration=.70),'TurnRight':dict(duration=.70),
}
for settings in ACTIONS.values():
    settings['frames']=round(settings['duration']*60)+1
    settings['duration']=(settings['frames']-1)/60

# Secondary bodies: how each accessory hangs from its bone's parent. Angles are radians about the armature axes.
from motion_profiles import CAPE_BOY as SECONDARY

def smoother(t):
    """Zero velocity and acceleration at both ends of an authored interval."""
    t=max(0.0,min(1.0,t))
    return t*t*t*(10+t*(-15+6*t))

def soft_min(a,b,width=.008):
    # A conservative, differentiable reach limit: never switches constraints
    # abruptly when a foot lands or becomes airborne.
    return .5*(a+b-math.hypot(a-b,width))

def quintic(t,a,b,va=0.0,vb=0.0):
    """Hermite segment with endpoint tangents and zero endpoint acceleration."""
    d=b-a
    return a+va*t+(10*d-6*va-4*vb)*t**3+(-15*d+8*va+7*vb)*t**4+(6*d-3*va-3*vb)*t**5

def foot_cycle(phase,cfg):
    stance=cfg['stance']
    stride=cfg['speed']*cfg['duration']
    span=stride*stance
    if not cfg.get('crouch'):
        running=stance<.5
        heel=-5 if running else -9
        toe=cfg.get('toe',26 if running else 19)
        centre=.065 if running else .018
        if phase<stance:
            u=phase/stance
            pitch=heel*(1-smoother(u/.24))+toe*smoother((u-.65)/.35)
            return centre-span/2+stride*phase,0,math.radians(pitch),True
        u=(phase-stance)/(1-stance)
        # Match the support foot's velocity AND acceleration at takeoff and
        # touchdown. A cubic with .35 of that tangent made the old foot snap.
        tangent=stride*(1-stance)
        # Brief reversals bound the foot's reach. One polynomial across the
        # entire swing overshoots far beyond the short legs' range.
        # The reversal distance scales with the stride; a sprint kicks the heel up instead of far back.
        takeoff,landing=cfg.get('takeoff',.12),cfg.get('landing',.075)
        start,end=centre+span/2,centre-span/2
        rear,front=start+tangent*takeoff/2,end-tangent*landing/2
        if u<takeoff: y=quintic(u/takeoff,start,rear,tangent*takeoff,0)
        elif u>1-landing: y=quintic((u-1+landing)/landing,front,end,0,tangent*landing)
        else: y=rear+(front-rear)*smoother((u-takeoff)/(1-takeoff-landing))
        apex=(.36 if cfg.get('sprint') else .30) if running else .43
        lift=cfg['lift']*(smoother(u/apex) if u<apex else 1-smoother((u-apex)/(1-apex)))
        fold=(50 if cfg.get('sprint') else 36) if running else 12
        pitch=toe+(fold-toe)*smoother(u/.28)+(heel-fold)*smoother((u-.28)/.62)
        return y,lift,math.radians(pitch),False
    if phase<stance:
        u=phase/stance
        pitch=math.radians(-8*(1-smooth(u/.15))+20*smooth((u-.80)/.20))
        return -span/2+stride*phase,0,pitch,True
    u=(phase-stance)/(1-stance)
    m=.35*stride*(1-stance)
    y=(2*u**3-3*u*u+1)*span/2+(-2*u**3+3*u*u)*(-span/2)+(2*u**3-3*u*u+u)*m
    return y,cfg['lift']*sin(pi*u)**1.6,math.radians(20*(1-u)-8*u-18*sin(pi*u)),False

class Animator:
    def __init__(self,arm,actions=None,secondary=None):
        self.arm=arm
        self.actions=ACTIONS if actions is None else actions
        self.secondary=SECONDARY if secondary is None else secondary
        self.rest={b.name:b.matrix_local.copy() for b in arm.data.bones}
        self.parents={b.name:b.parent.name if b.parent else None for b in arm.data.bones}
        self.length={b.name:b.length for b in arm.data.bones}
        self.M={}

    def inherited(self,n):
        p=self.parents[n]
        return self.M[p]@self.rest[p].inverted()@self.rest[n] if p else self.rest[n].copy()

    def rotate(self,n,degrees=(0,0,0),shift=None):
        m=self.inherited(n)
        r=Euler(tuple(math.radians(a) for a in degrees),'XYZ').to_matrix()
        result=(r@m.to_3x3()).to_4x4()
        result.translation=m.translation
        if shift is not None: result.translation+=shift
        self.M[n]=result

    def finish(self):
        for n in self.rest:
            if n not in self.M: self.M[n]=self.inherited(n)
            p=self.parents[n]
            localrest=self.rest[p].inverted()@self.rest[n] if p else self.rest[n]
            local=self.M[p].inverted()@self.M[n] if p else self.M[n]
            self.arm.pose.bones[n].matrix_basis=localrest.inverted()@local

    def pose(self,name,t,secondary=None):
        cfg=self.actions[name]
        u=max(0,min(1,t/cfg['duration']))
        phase=u%1
        a=2*pi*phase
        gait='stance' in cfg
        crouch=cfg.get('crouch',False)
        idle=name in ('Idle','CrouchIdle','SitIdle')
        pelvis=Vector((0,0,-.012))
        lean,twist,roll,head,headyaw,nod,breath=0,0,0,0,0,0,0
        feet,pitches,contacts={},{},{}
        self.M={'root':self.rest['root'].copy()}
        if gait:
            run=name in ('Run','Jog','Sprint')
            sprint=cfg.get('sprint',False)
            # lowest at double support (walk) or mid-stance (run), and over the stance foot sideways
            pelvis=Vector((.010*sin(a),0,-.035-.011*cos(2*a)))
            if run: pelvis.z=-.018+.026*cos(2*a+.8)
            lean=5 if name=='Walk' else 10 if name=='Jog' else 14
            twist=(5 if run else 3)*sin(a)
            roll=-(2.2 if run else 3.2)*sin(a)          # swing-side hip drops
            nod=(2.2 if run else 1.3)*cos(2*a+(.8 if run else 0))
            if not crouch:
                # Weight settles after contact, then rises through push-off.
                # The head and shoulder gestures stay quieter than the legs.
                pelvis=Vector(((.006 if run else .008)*sin(a),0,
                    (-.065-.020*cos(2*a-4*pi*.11)) if run else (-.050-.007*cos(2*a-4*pi*.08))))
                lean=cfg.get('lean',3 if name=='Walk' else 12 if name=='Jog' else 20)
                twist=(3.5 if run else 2.5)*sin(a)
                roll=-(1.6 if run else 2.2)*sin(a)
                nod=(.8 if run else .45)*cos(2*a-4*pi*.11)
                if sprint:
                    # Loads deeper at contact, rises through the flight; the shoulders swing harder against the hips.
                    pelvis=Vector((.005*sin(a),0,-.055-cfg.get('bounce',.024)*cos(2*a-4*pi*.10)))
                    twist=6.0*sin(a); roll=-2.0*sin(a); nod=1.2*cos(2*a-4*pi*.10)
        elif idle:
            # weight shift over one leg, two breaths per loop, a glance to the side and back
            ws=sin(a);breath=sin(2*a)
            pelvis=Vector((.007*ws,0,-.012+.0025*breath))
            roll=-1.4*ws;twist=1.5*ws
            headyaw=14*keys(u,[(.22,0),(.36,1),(.58,1),(.74,0)])
            head=-2*keys(u,[(.22,0),(.36,1),(.58,1),(.74,0)])+.4*breath
            lean=.4*breath
        else:
            pelvis.z+=.0025*sin(a)
            head=.5*sin(a)
        if crouch:
            pelvis.z=-.16+.005*cos(2*a)+(.002*breath if idle else 0)
            lean=20+lean
        for s,suf,offset in ((1,'L',0),(-1,'R',.5)):
            y,lift,pitch,contact=foot_cycle((phase+offset)%1,cfg) if gait else (.005,0,0,True)
            r=Matrix.Rotation(pitch,3,'X')
            ankle=self.rest['foot_'+suf].translation
            sole=[Vector((0,edge-ankle.y,shoe.SOLE_Z-ankle.z)) for edge in (shoe.HEEL_Y,shoe.TOE_Y)]
            pivot=sole[0] if pitch<0 else sole[1]
            z=shoe.SOLE_Z-min((r@v).z for v in sole)+lift
            if gait and not crouch and not contact:
                swing=((phase+offset)%1-cfg['stance'])/(1-cfg['stance'])
                # In the air the pivot moves smoothly from toe to heel. Taking
                # min(heel, toe) there introduced a cusp as the shoe levelled.
                pivot=sole[1].lerp(sole[0],smoother(swing))
                z=ankle.z+pivot.z-(r@pivot).z+lift
            width=(.108 if name in ('Jog','Run','Sprint') else .120) if gait and not crouch else .130
            feet[suf]=Vector((s*width,y+pivot.y-(r@pivot).y,z))
            pitches[suf],contacts[suf]=pitch,contact
        if name=='JumpStart':
            pelvis.z=keys(u,[(0,-.012),(.40,-.055),(1,.008)])
            lean=keys(u,[(0,8),(.4,14),(1,5)])
        elif name=='DoubleJump':
            # Sunburst reference: compact tuck, a single front somersault,
            # then open early enough to be upright before a normal landing.
            tuck=smoother((u-.05)/.20)*(1-smoother((u-.57)/.27))
            pelvis.z=-.020-.045*tuck
            lean=5+15*tuck
            for s,suf in ((1,'L'),(-1,'R')):
                feet[suf]=Vector((s*.12,.035-.275*tuck,.13+.36*tuck))
                pitches[suf]=math.radians(-12*tuck)
                contacts[suf]=False
        elif name in ('JumpRise','Fall'):
            lean=5 if name=='Fall' else -3+6*u
            for s,suf in ((1,'L'),(-1,'R')):
                feet[suf]+=Vector((s*.01,.045+s*.025,.09+.035*sin(pi*u) if name=='JumpRise' else .045+.012*sin(a+s)))
                contacts[suf]=False
        elif name in ('Land','HardLand'):
            pelvis.z=keys(u,[(0,-.012),(.23,-.20 if name=='HardLand' else -.12),(.42,-.15 if name=='HardLand' else -.09),(1,-.012)])
            lean=keys(u,[(0,5),(.24,26 if name=='HardLand' else 17),(1,0)])
        elif name=='Dodge':
            pelvis.z=keys(u,[(0,-.012),(.2,-.22),(.55,-.23),(1,-.012)])
            lean=keys(u,[(0,0),(.3,32),(.7,26),(1,0)])
            for s,suf in ((1,'L'),(-1,'R')):
                feet[suf].y=s*.12*sin(pi*u)
                feet[suf].z+=max(0,s*sin(2*pi*u))*.065
                contacts[suf]=False
        elif name=='Interact':
            e=sin(pi*u)**2
            pelvis.z=-.07*e
            lean,head=21*e,15*e
        elif name=='Wave':
            twist,head=4*sin(pi*u)**2,-3*sin(pi*u)
        elif name in ('SitDown','SitIdle','StandUp'):
            seat=smooth(u) if name=='SitDown' else 1-smooth(u) if name=='StandUp' else 1
            pelvis.z=-.012-.51*seat+(.002*breath if idle else 0)
            pelvis.y=.10*seat
            lean=8*seat+12*sin(pi*seat)+lean
            for suf in feet:
                feet[suf].y=-.235*seat
                contacts[suf]=False
        elif name=='Climb':
            lean=-3
            for s,suf in ((1,'L'),(-1,'R')):
                feet[suf]=Vector((s*.13,-.22,.28+.10*sin(a+(0 if s==1 else pi))))
                contacts[suf]=False
        elif name=='Glide':
            lean=8
            for s,suf in ((1,'L'),(-1,'R')):
                feet[suf]+=Vector((s*.01,.04,.07+.01*sin(a+s)))
                contacts[suf]=False
        elif name.startswith('Turn'):
            sign=1 if name=='TurnLeft' else -1
            twist=sign*15*sin(pi*u)
            for s,suf in ((1,'L'),(-1,'R')):
                feet[suf].y+=.035*s*sign*sin(pi*u)
                feet[suf].z+=.021*max(0,s*sin(2*pi*u))
                contacts[suf]=False
        if gait and cfg.get('flight_rise',0):
            # A small whole-body bound during double flight. Move both feet and
            # pelvis together so extra airtime reads as a jump, not knee tuck.
            # The quartic sine has zero velocity/acceleration at both contacts.
            step_phase=phase%.5
            flight=max(0.0,(step_phase-cfg['stance'])/(.5-cfg['stance']))
            rise=cfg['flight_rise']*sin(pi*flight)**4
            pelvis.z+=rise
            for foot in feet.values(): foot.z+=rise
        # Lower the pelvis instead of stretching a planted leg beyond its reach.
        for suf in feet:
            if gait and not crouch:
                rotation=Euler(tuple(math.radians(v) for v in (lean*.18,roll,twist*.4)),'XYZ').to_matrix()
                hip=self.rest['pelvis'].translation+rotation@(self.rest['thigh_'+suf].translation-self.rest['pelvis'].translation)
                hip+=Vector((pelvis.x,pelvis.y,0))
                delta=feet[suf]-hip
                reach=self.length['thigh_'+suf]+self.length['shin_'+suf]-.014
                h=math.sqrt(max(.001,reach*reach-delta.x**2-delta.y**2))
                pelvis.z=soft_min(pelvis.z,feet[suf].z+h-hip.z)
            elif contacts[suf]:
                hip=self.rest['thigh_'+suf].translation+pelvis
                delta=feet[suf]-hip
                reach=self.length['thigh_'+suf]+self.length['shin_'+suf]-.005
                h=math.sqrt(max(.001,reach*reach-delta.x**2-delta.y**2))
                pelvis.z=min(pelvis.z,feet[suf].z+h-self.rest['thigh_'+suf].translation.z)
        # Spine chain: the pelvis rolls and twists, the chest counters both, the head ends up level.
        # A run folds at the hips as well as the spine: the pelvis carries a third of the lean, the chest the rest.
        hip_fold=.34 if gait and not crouch and name in ('Run','Jog','Sprint') else .18
        self.rotate('pelvis',(lean*hip_fold,roll,twist*.4),pelvis)
        self.rotate('spine',(lean*(.6-hip_fold)-1.2*breath,-roll*.55,-twist*.35))
        self.rotate('chest',(lean*.4-1.6*breath,-roll*.35,-twist*.35))
        self.rotate('neck',(-lean*.48,0,headyaw*.3))
        self.rotate('head',(head-lean*.30+nod,-roll*.10,twist*.3+headyaw*.7))     # eyes stay on the road as the body leans
        for s,suf,offset in ((1,'L',0),(-1,'R',pi)):
            shoulder=self.inherited('upperarm_'+suf).translation
            x=a+offset
            forward=(1-cos(x))/2                       # 1 when this arm is at its front extreme
            run=gait and name in ('Run','Jog','Sprint')
            wrist_flex=0.0
            if gait:
                swing=cfg.get('arm',.018)*(cos(x)-.15)
                bend=(.95+.35*forward) if run else (.26+.24*forward)
                spread=.33 if run else .29
                inward=s*(.20-(.12 if run else .05)*forward)
                if not crouch:
                    swing=cfg['arm']*(cos(x+.12)-.12)
                    forward=(1-cos(x+.12))/2
                    bend=(1.03+.16*forward) if run else (.25+.16*forward)
                    spread=.23 if run else .22
                    inward=s*(.14-.045*forward)
                    if run:
                        # Running arms: a quick drive forward and a slower return (skewed phase), the swing centred behind the
                        # body. Run/Sprint hold the elbow angle; Jog keeps its relaxed folding motion.
                        # Open the upper arms and keep the hands outside the hips, as in the approved
                        # Sunburst rear-view concept; preserve the existing alternating drive and foot timing.
                        xs=x+.22*sin(x)
                        swing=cfg['arm']*(cos(xs)+.20)                 # positive = behind: the swing is centred behind the body
                        fl=(1-cos(xs-.55))/2
                        bend=pi/2 if name in ('Run','Sprint') else .50+.62*fl
                        spread=(.65 if cfg.get('sprint') else .68 if name=='Run' else .58)+.04*(1-fl)
                        # Keep elbows visible beyond the cape silhouette, then angle the
                        # forearms medially so the wrists sit clearly inside the elbows.
                        # Jog's shorter swing needs more torso clearance than the fast gaits.
                        inward=s*(.20-.02*fl) if name=='Jog' else -s*(.30+.10*fl)
                        wrist_flex=(-.30+.55*(1-cos(xs-.95))/2)*.35
                        forward=fl
            else:
                swing=.012*sin(x)+(.010*breath if idle else 0)
                bend=.18+(.03*breath if idle else 0)
                spread=.27
                inward=s*.20
            if crouch: bend=.60
            if name=='JumpStart': swing=keys(u,[(0,0),(.5,.55),(1,-.9)]);bend=.5
            elif name=='DoubleJump': swing=-.40-.10*tuck;bend=1.15;spread=.70;inward=s*.12
            elif name=='JumpRise': swing=-.9+.35*u;bend=.8;spread=.40
            elif name=='Fall': swing=-.35;spread=.66;bend=.45
            elif name in ('Land','HardLand'): swing=-.5*sin(pi*u);bend=.5
            elif name=='Dodge': swing=-.65;bend=1.2
            elif name=='Interact' and s==1: swing=-.95*sin(pi*u)**2;bend=.3
            elif name in ('SitDown','SitIdle','StandUp'):
                seat=smooth(u) if name=='SitDown' else 1-smooth(u) if name=='StandUp' else 1
                swing=-.85*seat;bend=.45;spread=.10
            upper=Vector((s*spread,sin(swing),-cos(swing))).normalized()
            lower=Vector((inward,sin(swing-bend),-cos(swing-bend))).normalized()
            if gait and name in ('Run','Sprint'):
                # Spread and medial forearm aim would otherwise vary the true 3D
                # elbow angle even with a constant sagittal bend. Keep the forearm
                # perpendicular to the upper arm throughout the shoulder swing.
                outward=Vector((s,0,0))
                lateral=(outward-upper*upper.dot(outward)).normalized()
                sagittal=upper.cross(lateral).normalized()
                if sagittal.dot(lower)<0: sagittal=-sagittal
                # Leave space beside the shorts on the backswing, then carry the
                # fists inward in front. Both basis vectors preserve the 90° bend.
                lateral_amount=(.10-.30*forward)/math.sqrt(1-upper.x*upper.x)
                lower=lateral*lateral_amount+sagittal*math.sqrt(1-lateral_amount*lateral_amount)
            elbow=shoulder+upper*self.length['upperarm_'+suf]
            wrist=elbow+lower*self.length['forearm_'+suf]
            if name=='Wave' and s==1:
                e=sin(pi*u)**.6
                target=Vector((.24+.023*sin(10*pi*u),-.09,1.16+.02*cos(10*pi*u)))
                wrist=wrist.lerp(target,e)
            elif name in ('Climb','Glide'):
                wrist=Vector((s*(.19 if name=='Climb' else .38),-.17 if name=='Climb' else 0,
                    1.10+(.06*sin(a+offset) if name=='Climb' else .02*sin(a))))
            elif name in ('SitDown','SitIdle','StandUp'):
                wrist=wrist.lerp(Vector((s*.145,-.16,.365)),seat)
            delta=wrist-shoulder
            reach=self.length['upperarm_'+suf]+self.length['forearm_'+suf]-.001
            if delta.length>reach: wrist=shoulder+delta.normalized()*reach
            if name in ('Wave','Climb','Glide','SitDown','SitIdle','StandUp'):
                elbow=two_bone(shoulder,wrist,self.length['upperarm_'+suf],self.length['forearm_'+suf],(s,-.1,0))
            lower=(wrist-elbow).normalized()
            self.M['upperarm_'+suf]=aim_matrix(self.rest['upperarm_'+suf],shoulder,elbow)
            self.M['forearm_'+suf]=aim_matrix(self.rest['forearm_'+suf],elbow,wrist)
            self.M['hand_'+suf]=aim_matrix(self.rest['hand_'+suf],wrist,wrist+lower*self.length['hand_'+suf])
            if not (name=='Wave' and s==1):
                hand_twist=pi*(.46 if gait and run and not crouch else .38)      # thumbs up in a run
                if gait and run and not crouch:   # flex about the wrist's lateral axis before the palm twist: extended at the back, curled at the chin
                    self.M['hand_'+suf]=self.M['hand_'+suf]@Matrix.Rotation(wrist_flex,4,'X')
                self.M['hand_'+suf]=self.M['hand_'+suf]@Matrix.Rotation(s*hand_twist,4,'Y')
            # fingers curl with effort: a loose fist in a run (the index straighter, the tips folded, the thumb over them),
            # slightly open in a walk, relaxed otherwise
            fist=(gait and run and not crouch) or name=='DoubleJump'
            curl=-.95 if name in ('Run','Jog','Sprint','Dodge','DoubleJump') else -.35 if gait else -.15
            for i in range(4):
                n='finger_%d_%s'%(i,suf)
                c=curl*(.62+.13*i) if fist else curl*(1-.08*i)
                self.M[n]=self.inherited(n)@Matrix.Rotation(c,4,'X')
                tip='finger_tip_%d_%s'%(i,suf)
                if tip in self.rest: self.M[tip]=self.inherited(tip)@Matrix.Rotation(c*(.9 if fist else .5),4,'X')
            if 'thumb_'+suf in self.rest:
                self.M['thumb_'+suf]=self.inherited('thumb_'+suf)@Matrix.Rotation(-.55 if fist else -.15,4,'X')
            hip=self.inherited('thigh_'+suf).translation
            ankle=feet[suf]
            delta=ankle-hip
            reach=self.length['thigh_'+suf]+self.length['shin_'+suf]-.001
            if delta.length>reach:
                if contacts[suf]:
                    horizontal=Vector((delta.x,delta.y,0))
                    limit=math.sqrt(max(0,reach*reach-delta.z*delta.z))
                    if horizontal.length>limit: horizontal*=limit/horizontal.length
                    ankle=hip+Vector((horizontal.x,horizontal.y,delta.z))
                else: ankle=hip+delta.normalized()*reach
            pole=(s*.45,-.25,1) if name in ('SitDown','SitIdle','StandUp') else (0,-1,0)
            knee=two_bone(hip,ankle,self.length['thigh_'+suf],self.length['shin_'+suf],pole)
            self.M['thigh_'+suf]=aim_matrix(self.rest['thigh_'+suf],hip,knee)
            self.M['shin_'+suf]=aim_matrix(self.rest['shin_'+suf],knee,ankle)
            pitches['thigh_'+suf]=math.degrees(math.atan2(hip.y-knee.y,hip.z-knee.z))
            foot=(Matrix.Rotation(pitches[suf],3,'X')@self.rest['foot_'+suf].to_3x3()).to_4x4()
            foot.translation=ankle
            self.M['foot_'+suf]=foot
            blink=max(0,1-abs(t-cfg['duration']*.68)/.085) if idle else 0
            self.M['eye_'+suf]=self.inherited('eye_'+suf)@Matrix.Diagonal(Vector((1,1-.94*blink,1,1)))
        # Secondary bodies: simulated values when given, otherwise at rest (first pass records the anchors).
        anchors={}
        for bone in self.secondary:
            anchors[bone]=self.inherited(bone).translation.copy()
            if secondary and bone in secondary:
                rx,ry,dz=secondary[bone]
                self.rotate(bone,(math.degrees(rx),math.degrees(ry),0),Vector((0,0,dz)) if dz else None)
        if name=='DoubleJump':
            # Rotate the skeleton around its body centre, never the capsule or
            # camera. Dense keys retain the full turn across quaternion wrapping.
            pivot=Vector((0,0,.78))
            turn=Matrix.Translation(pivot)@Matrix.Rotation(2*pi*smoother((u-.07)/.76),4,'X')@Matrix.Translation(-pivot)
            self.M={bone:turn@matrix for bone,matrix in self.M.items()}
        self.finish()
        return dict(contacts=contacts,t=t,anchors=anchors,thigh_pitch={'L':pitches['thigh_L'],'R':pitches['thigh_R']})

def simulate_secondary(records,cfg,profiles=None):
    """Drive every accessory from its anchor's acceleration over the clip; returns per-frame bone values."""
    profiles=SECONDARY if profiles is None else profiles
    dt=1/60;loop=bool(cfg.get('loop'));frames=cfg['frames']
    samples=motion.loop_samples(records,frames,loop)
    result={}
    for bone,spec in profiles.items():
        acc=motion.acceleration([r['anchors'][bone] for r in samples],dt,loop)
        if spec['kind']=='flap':
            drive=[-a.z*spec['gain'] for a in acc]
            lo,hi=spec['limit']
            angles=motion.spring(drive,dt,loop,spec['stiffness'],spec['damping'],max(abs(lo),abs(hi)))
            values=[(min(hi,max(lo,x)),0.0,0.0) for x in angles]
        else:
            push=None
            if spec.get('push'):
                push=[math.radians(max(0.0,r['thigh_pitch'][spec['push']]-6.0)*.9) for r in samples]
            swing=motion.pendulum(acc,dt,loop,spec['length'],spec['stiffness'],spec['damping'],spec['limit_x'],spec['limit_y'],push)
            bounce=[0.0]*len(samples)
            if spec.get('bounce'):
                b=spec['bounce'];bounce=motion.spring([-a.z for a in acc],dt,loop,b['stiffness'],b['damping'],b['limit'])
            values=[(th,ph,dz) for (th,ph),dz in zip(swing,bounce)]
        result[bone]=motion.expand(values,frames,loop)
    return [{bone:result[bone][i] for bone in profiles} for i in range(frames)]

def build_actions(arm,out,actions=None,secondary=None):
    actions=ACTIONS if actions is None else actions
    secondary=SECONDARY if secondary is None else secondary
    animator=Animator(arm,actions,secondary)
    arm.animation_data_create()
    targets={}
    for name,cfg in actions.items():
        action=bpy.data.actions.new(name)
        action.use_fake_user=True
        arm.animation_data.action=action
        first=[animator.pose(name,(frame-1)/60) for frame in range(1,cfg['frames']+1)]
        motion_values=simulate_secondary(first,cfg,secondary)
        records=[]
        for frame in range(1,cfg['frames']+1):
            record=animator.pose(name,(frame-1)/60,motion_values[frame-1])
            records.append(dict(contacts=record['contacts'],t=record['t']))
            for pb in arm.pose.bones:
                for prop in ('location','rotation_quaternion','scale'):
                    pb.keyframe_insert(prop,frame=frame,group=pb.name)
        targets[name]=records
        print('ACTION',name,cfg['frames'],flush=True)
    (out/'animation_manifest.json').write_text(json.dumps(actions,indent=2)+'\n')
    (out/'animation_targets.json').write_text(json.dumps(targets,separators=(',',':')))
    arm.animation_data.action=bpy.data.actions['Idle']
    bpy.context.scene.frame_set(1)
