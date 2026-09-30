"""What the two sea materials share, so the open sea and the harbor water read as one sea from any distance.

M_Sea (import_southwest.py) covers the big sea plane; M_HarborWater (harbor_material.py) covers the harbor's HD_Sea
rectangle, which sits on top of it. Both fade into the painted sky dome with distance, and the harbor water calms to
the open sea's look along its outer edges, so neither the horizon nor the rectangle shows a line.
"""

# The painted sky dome just above the horizon, as the camera sees it: gen_textures.sky() `hor` (sRGB .34 .52 .76, stored
# in 8 bits) in linear, times the MI_Sky tint 1.35 (setup_project.py). The dome is unlit and the exposure is fixed, so a
# far sea whose only light is this emissive colour is exactly the colour of the sky it meets.
HORIZON = (0.126, 0.311, 0.720)

# Share of the dome colour by pixel depth D (cm): none within 70 m, .17 at 600 m, .3 at 1 km, .65 at 3 km, ~1 by 12 km.
# The lit colour and the specular sheen fade out by the same share.
FAR_FADE = 'return 1-exp(-max(D-7000.,0.)/280000.);'

# The open sea's deep water (M_Sea): the harbor water takes these along its outer edges.
DEEP = (0.006, 0.030, 0.078)
ROUGHNESS = 0.32
SPECULAR = 0.6
