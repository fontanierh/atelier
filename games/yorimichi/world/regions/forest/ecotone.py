"""Patchwise species blending across the northern foothills."""
def tuscan_mask(x,y):
    from hidamari.mountains import noise,smooth
    from belmonte.layout import BOUNDS,SOUTH_JOIN
    # A broad, warped interleave continues across both terrain producers.
    # Fade the lateral footprint too, so no rectangular species wall appears.
    warp=90*noise(x,y,180.,91)+35*noise(x,y,65.,92)
    share=smooth((y+warp-(SOUTH_JOIN-240.))/560.)
    lateral=smooth((x-(BOUNDS[0]-300))/180)*smooth(((BOUNDS[2]+300)-x)/180)
    threshold=(noise(x,y,75.,84)+1)*.5
    return threshold<share*lateral



def kinds(x,y,z):
    import numpy as np
    from hidamari.mountains import noise,smooth,polar,stretch,lifted,LIFT
    # Independent evergreen and autumn fields avoid contour rings. Strong fine
    # position noise mixes the crowns tree by tree within each drift, so the
    # forest never reads as single-colour blotches, without changing either caller's RNG.
    ever=noise(x,y,95.,80)+.5*noise(x,y,38.,81)+.65*noise(x,y,2.3,83)
    hue=noise(x,y,75.,78)+.5*noise(x,y,30.,82)+.75*noise(x,y,2.3,84)
    kind=np.where(ever<-.33,'Pine',np.where(hue<.11,'Rust','Gold'))
    # Pines take over high on the volcano, at the same share of its slope (hidamari/mountains.py LIFT).
    altitude=smooth((z-lifted(170))/(90*LIFT))*smooth((stretch(900)-polar(x,y)[2])/150)
    return np.where((noise(x,y,60.,79)+1)*.5<altitude,'Pine',kind)


def northern_ecotone(instances):
    """Patchwise species mixing across the foothill-to-Tuscan transition."""
    import numpy as np
    from forest.specs import TUSCAN
    for name in ('Tree_Forest_Maple', 'Tree_Forest_Ginkgo', 'Tree_Forest_Oak', 'Tree_Forest_Pine'):
        rows=np.asarray(instances.get(name,[]),float).reshape(-1,5)
        if not len(rows):continue
        x,y=rows[:,0],rows[:,1]
        moved=tuscan_mask(x,y)
        instances[name]=rows[~moved].tolist()
        target='Tree_Tuscan_Pine' if name.endswith('Pine') else 'Tree_Tuscan_Olive' if name.endswith('Ginkgo') else 'Tree_Tuscan_Oak'
        planted=rows[moved].copy()
        if target!='Tree_Tuscan_Olive':planted[:,4]*=10./TUSCAN[target][2]
        instances.setdefault(target,[]).extend(planted.tolist())
