"""Resolve historic regional planting families to the current detailed library.

This is a build-time scene migration. Only current asset names reach world.json;
there is no runtime proxy or missing-model fallback.
"""
LEGACY = {
    'Tree_Maple_lo': 'Tree_Maple_A', 'Tree_Broad_lo': 'Tree_Broad_A', 'Tree_Ginkgo_lo': 'Tree_Ginkgo',
    **{'HD_NorthTree'+prefix+kind: target for prefix in ('', 'Backdrop')
       for kind,target in [('Gold','Tree_Forest_Ginkgo'),('Rust','Tree_Forest_Maple'),
                           ('Green','Tree_Forest_Oak'),('Pine','Tree_Forest_Pine')]},
}


def replace_legacy(instances):
    for old, current in LEGACY.items():
        rows = instances.pop(old, [])
        if rows:
            instances.setdefault(current, []).extend(rows)
    assert not any(name.startswith('HD_NorthTree') or name.endswith('_lo') for name in instances)


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
