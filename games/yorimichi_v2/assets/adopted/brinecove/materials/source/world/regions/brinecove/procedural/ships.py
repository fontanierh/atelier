"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove import layout as L
from brinecove.geom import Builder
from brinecove.procedural.ship import ship


def ships():
    b = Builder('07_ships')
    for i, spec in enumerate(L.SHIPS):
        name, x, y, yaw, scale, sails = spec
        # The paintings' two pirate galleons fly black canvas; the sloop keeps cream.
        ship(b, x, y, -1.1, yaw, scale, sails=sails, unfinished=False,
             canvas='sail_dark' if name.startswith('galleon') else 'sail')
    # The broken hull on the western rocks is a dark, readable landmark from the harbor mouth.
    ship(b, -492, -246, -2.8, 34, 0.60, sails=False, unfinished=True)
    return b
