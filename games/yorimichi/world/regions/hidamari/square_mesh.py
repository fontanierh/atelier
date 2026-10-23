"""Selected Hidamari geometry; no sibling construction or export on import."""
from hidamari import living_plaza
from hidamari.lettering_mesh import lettering
from hidamari.layout import height


def square():
    return living_plaza.furniture(height,lettering)
