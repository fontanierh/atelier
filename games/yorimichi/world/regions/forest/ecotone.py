"""Patchwise species blending across the northern foothills."""
def northern_ecotone(instances):
    """Patchwise species mixing across the foothill-to-Tuscan transition."""
    import numpy as np
    from hidamari.mountains import noise, smooth
    from belmonte.layout import BOUNDS
    for name in ('Tree_Forest_Maple', 'Tree_Forest_Ginkgo', 'Tree_Forest_Oak', 'Tree_Forest_Pine'):
        rows=np.asarray(instances.get(name,[]),float).reshape(-1,5)
        if not len(rows):continue
        x,y=rows[:,0],rows[:,1]
        share=smooth((y-2710.)/400.)
        patch=(noise(x,y,100.,84)+1)*.5
        moved=(x>BOUNDS[0]-180)&(x<BOUNDS[2]+180)&(patch<share)
        instances[name]=rows[~moved].tolist()
        target='Tree_Tuscan_Pine' if name.endswith('Pine') else 'Tree_Tuscan_Oak'
        instances.setdefault(target,[]).extend(rows[moved].tolist())
