"""Surface detail on the existing eastern rock masses; never changes ground."""
import numpy as np

import shorelines as coast


def rock_faces(x, y, z, normal_z):
    """@cc [owner:fontanierh,label:correctness] coastal-rock-slot-ownership
    Only exposed faces of the editable eastern headland may use CoastRock.
    Sand, smooth meadow and protected town/rail ground MUST keep their old slot.
    The caller MUST restrict this selection to the FarHills material owner.
    """
    x, y, z, normal_z = np.broadcast_arrays(x, y, z, normal_z)
    _, headland = coast.landform_regions(x, y)
    d, rock = coast.field(x, y)
    return ((headland > .25) & (coast.protected_weight(x, y) > .99)
            & (coast.weight(x, y) > .25) & (d > 0.) & (d < 500.)
            & (rock > .25) & (z > 4.) & (normal_z < .85)
            & (coast.meadow_caps(x,y,z,normal_z) <= .2))


def face_colour(x, y, z, normal_z):
    """The existing geology palette, sampled once per exposed rock face."""
    # A face normal selects solid stone, rather than blending a steep face with
    # the smooth meadow normals on its crown. Keep the existing wet/geology grain.
    stone, _ = coast.paint(x, y, z, np.zeros_like(np.asarray(z)))
    return np.clip(stone*(.70+.30*np.asarray(normal_z)[..., None])/.70, 0., 1.)


def crown_zone(x, y, z):
    """Only coastal-owned trees over the rocky headland's front masses."""
    _, headland = coast.landform_regions(x, y)
    d, rock = coast.field(x, y)
    return ((headland > .25) & (coast.protected_weight(x, y) > .99)
            & (rock > .3) & (d > 35.) & (d < 260.) & (z > 12.))


def forest_crowns(x, y, z, slope):
    """@cc [owner:fontanierh,label:correctness] city-cliff-forest-ownership
    Only forest_backdrop's own rows on editable headland crowns may change.
    Use its final ground slope; all outside/protected transforms and its original
    random stream MUST remain unchanged. No terrain or other producer is edited.
    """
    on = crown_zone(x, y, z)
    # Trees stand in small meadow groves above the rock, not on its steep face.
    grove = .5+.5*np.sin(np.asarray(x)/46.+np.asarray(y)/63.)
    keep = ~on | ((np.asarray(slope) < .65) & (grove > .45))
    return keep, np.where(on, .65, 1.)
