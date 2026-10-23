"""Explicit semantic Stable and coordinated native LOD membership."""
PARTS = ('Barn', 'BarnRoof', 'Gate', 'Yard', 'Paddock')
LOD_PARENTS = (*('SM_HS_' + part for part in PARTS), 'SM_HS_StallDoor', 'SM_HS_RoomDoor')
SINGLE_PARENTS = ('SM_HS_Ground', 'SM_HS_Road', 'SM_HS_RoadSign')
PARENTS = (*LOD_PARENTS, *SINGLE_PARENTS)
SOURCES = (*('SM_HS_' + part + '_LOD' + str(lod) for lod in range(3) for part in (*PARTS, 'StallDoor', 'RoomDoor')),
           *SINGLE_PARENTS)


def selected(key):
    if key not in SOURCES: raise ValueError('Foreign Stable logical source')
    if '_LOD' in key:
        parent, level = key.rsplit('_LOD', 1)
        return parent, int(level)
    return key, None


def context_key(key):
    parent, lod = selected(key)
    part = parent.removeprefix('SM_HS_')
    function = dict(BarnRoof='roof', StallDoor='stall_door', RoomDoor='room_door', RoadSign='road_sign').get(part, part.lower())
    return function + ('' if lod is None else '_LOD' + str(lod))
