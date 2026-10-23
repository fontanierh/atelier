"""Selected logical zeppelin geometry; no regional export callback."""
from zeppelin.primitives import M, PLANK, np, rail

def gangway():
 m=M('ZP_Gangway')
 for y in np.arange(.10,1.3,.20):m.box((0,float(y),-.06),(1.7,.20,.12),PLANK)
 for x in [-.88,.88]:rail(m,(x,0),(x,1.30),0)
 return m
