"""Selected logical zeppelin geometry; no regional export callback."""
from zeppelin.primitives import GOLD, M, PLANK, WOOD, math, xlathe
from zeppelin.layout import PROPELLER_RADIUS

def propeller():
 scale=PROPELLER_RADIUS/math.hypot(.09,1.16)
 m=M('ZP_Propeller');xlathe(m,(0,0,0),[(-.11,0),(-.1,.19),(.13,.19),(.20,0)],GOLD)
 for side in [-1,1]:
  pts=[(-.055,-.09,side*.12),(-.055,-.23,side*.75),(-.055,-.10,side*1.12),(-.055,.09,side*1.16),(-.055,.15,side*.62),(-.055,.09,side*.12)]
  pts=[(x,y*scale,z*scale) for x,y,z in pts]
  for x in [-.055,.055]:m.poly([(x,y,z) for _,y,z in (pts if x<0 else pts[::-1])],PLANK)
  for i in range(len(pts)):
   a=pts[i];b=pts[(i+1)%len(pts)];m.poly([(-.055,a[1],a[2]),(.055,a[1],a[2]),(.055,b[1],b[2]),(-.055,b[1],b[2])],WOOD)
 return m
