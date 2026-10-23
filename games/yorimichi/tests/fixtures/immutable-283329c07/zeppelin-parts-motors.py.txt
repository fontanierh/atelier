"""Selected logical zeppelin geometry; no regional export callback."""
from zeppelin.primitives import GOLD, M, SAGE, xlathe
from zeppelin.layout import PROPELLER_CENTERS

def motors():
 m=M('ZP_Motors')
 # Direct envelope mounts; motors rotate only their separate blade mesh.
 for _,y,z in PROPELLER_CENTERS:
  side=1 if y>0 else -1
  m.beam((3.,side*3.65,z),(3.,y,z),.30,.30,SAGE)
  m.box((3.,side*3.85,z),(.55,.20,.52),GOLD,.025)
  xlathe(m,(2.25,y,z),[(0,0),(.18,.41),(.8,.5),(1.2,.32),(1.32,0)],SAGE)
  xlathe(m,(3.45,y,z),[(0,.19),(.24,.19),(.31,0)],GOLD)
 return m
