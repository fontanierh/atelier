"""Patchwise species blending across the northern foothills."""
def tuscan_mask(x,y):
    from hidamari.mountains import noise,smooth
    from belmonte.layout import BOUNDS
    share=smooth((y-2850.)/300.)
    return (x>BOUNDS[0]-180)&(x<BOUNDS[2]+180)&((noise(x,y,100.,84)+1)*.5<share)


def kinds(x,y,z):
    import numpy as np
    from hidamari.mountains import noise,smooth
    patch=noise(x,y,75.,78)
    kind=np.where(patch<-.26,'Pine',np.where(patch<.25,'Rust','Gold'))
    altitude=smooth((z-170)/90)*smooth((900-np.hypot(x-550,y-1930))/150)
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
