"""Selected Hidamari geometry; no sibling construction or export on import."""
from hidamari.environment import M


def gate_rock(name):
    from megapark import gate
    m=M(name);seed,size=gate.ROCKS[name]
    for points,colour in gate.rock(seed,size):m.poly(points,colour)
    return m
