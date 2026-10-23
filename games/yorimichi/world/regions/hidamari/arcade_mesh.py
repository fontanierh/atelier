"""Independent original arcade canopy constructor."""
from hidamari import arcade as arcade_kit
from hidamari.lettering_mesh import lettering

def arcade():
    return arcade_kit.canopy(lettering)
