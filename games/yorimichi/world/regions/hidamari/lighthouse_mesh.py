"""Selected Hidamari geometry; no sibling construction or export on import."""
from hidamari.environment import M


def lighthouse():
    m=M('HD_Lighthouse');m.lathe((0,0,0),[(0,3.2),(1,3.2),(1,2.5),(12,1.8)],'cream',12)
    m.lathe((0,0,8),[(0,2.08),(1.7,1.98)],'blue',12)
    m.lathe((0,0,12),[(0,2.6),(.4,2.6),(.4,1.8),(2,1.8)],'paper',12)
    m.lathe((0,0,14),[(0,2.7),(1.5,0)],'roof',12);m.collider((0,0,6),(4,4,12));return m
