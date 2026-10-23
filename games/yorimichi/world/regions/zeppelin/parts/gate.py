"""Selected logical zeppelin geometry; no regional export callback."""
from zeppelin.primitives import GOLD, M, PLANK, WOOD, np

def gate():
 m=M('ZP_Gate')
 for x in np.linspace(0,1.7,8):m.box((float(x),0,.50),(.18,.075,.86),PLANK,.01)
 for z in [.16,.85]:m.box((.85,-.06,z),(1.82,.075,.09),WOOD)
 for z in [.2,.78]:m.box((.02,-.07,z),(.18,.05,.07),GOLD)
 return m
