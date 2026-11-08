"""The caldera's conifers (docs/CRATERPARK.md, "Dressing"): four Tripo models after the owner's pick D, a mixed grove of
twisted Japanese black pines with cloud-pad crowns and tiered sugi cedars. Their sources are committed in
assets/craterpark/trees/<folder>/raw/output_model_url.glb (job.json records the Tripo task; the reference sheets they
were made from are in sugi_black_pine/ and sugi_cedar/).

world/regions/hidamari/props.py fits each one like the city's Tripo street props (treehouse/props.py fit): stood on
z = 0, its height scaled to HEIGHT metres, one textured material, no collision, and its distance LODs decimated to
LODS. editor_floor.py plants them where the crater floor's clusters of conifers stand, into park.json `trees`.
Pure Python: Blender and the numpy build both import it.
"""
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[4] / 'assets' / 'craterpark' / 'trees'

# mesh key: (source folder, family, height in metres at scale 1, crown radius in metres at scale 1). The crown radius
# is the farthest any of the model's vertices reaches from its trunk's axis in plan (the fit checks it).
TREES = {
    'Tree_Caldera_BlackPine_A': ('black_pine_a', 'pine', 8., 4.3),
    'Tree_Caldera_BlackPine_B': ('black_pine_b', 'pine', 8., 3.7),
    'Tree_Caldera_Cedar_A': ('cedar_a', 'cedar', 12., 3.5),
    'Tree_Caldera_Cedar_B': ('cedar_b', 'cedar', 12., 3.4),
}
SCALE = (.85, 1.25)      # the range each planted tree is scaled by
PINE_SHARE = .5          # the share of clusters that are pines (the rest are cedars)...
MIXED = .25              # ...and the share of each cluster's trees of the other family
# Distance LODs: (share of LOD0's triangles, Unreal screen size, how). At a 90 degree view a tree drops to a third of
# its triangles from about 30 m (a pine; 45 m a cedar), to a tenth from 80-115 m and to a few hundred, which keep its
# silhouette, from 200-290 m. 'weld': the model with its vertices welded (Tripo splits them at every UV seam, and a
# decimation keeps those edges, so it shreds the crowns into slivers), decimated. 'shell': welded, thickened by SHELL[0]
# and remeshed on SHELL[1] voxels (shares of the height) into one closed volume, so the cedars' thin tiers and the pines'
# pads keep their mass, decimated, its UVs taken from the nearest faces of the model. A shell is decimated in two parts,
# below and above BASE[0] of the height, the lower part to BASE[1] of the LOD's triangles: decimated whole, the trunk
# goes first and the last cedar LOD floated a metre over its root.
LODS = ((1., 1., None), (.3, .25, 'weld'), (.1, .1, 'shell'), (.03, .04, 'shell'))
SHELL = (.02, .02)
BASE = (.1, .1)
FLOAT = .15              # metres the lowest point of a LOD may stand off the ground (editor_floor sinks it deeper, by scale)
TARGET = .055            # the texture's mean linear luminance over the surface (the old cones' dark green, about .05)


def source(key):
    """The committed Tripo model of a tree."""
    return SOURCE / TREES[key][0] / 'raw' / 'output_model_url.glb'


def family(name):
    """The mesh keys of one family ('pine' or 'cedar'), in order."""
    return [key for key, entry in TREES.items() if entry[1] == name]
