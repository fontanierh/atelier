"""Canonical Stable query/anchor data, independently of rendered exports."""
from hidamari_stable import layout as L


def placements(pad_z, platform_z, road_z, slots):
    CITY_SLOTS = slots
    stalls = L.stalls(); rooms = L.rooms()
    doors = [dict(id=f'door_{s["id"]}', mesh='StallDoor', pivot=s['door']['pivot'], yaw=0., slide=s['door']['slide'],
                  travel=s['door']['travel'], stall=s['id']) for s in stalls]
    doors += [dict(id=f'door_{k}', mesh='RoomDoor', pivot=r['door']['pivot'], yaw=0., slide=r['door']['slide'],
                   travel=r['door']['travel'], room=k) for k, r in rooms.items()]
    lods = lambda base: [f'glb/{base}_LOD{k}.glb' for k in (0, 1, 2)]
    return dict(
        version=1, name=L.NAME,
        frame='stable frame: Blender metres, x east, y north, z up; origin on the pad top at site.origin; yaw 0. '
              'Island = site.origin + p; Unreal centimetres = (100 x, -100 y, 100 z). Yaw degrees counter-clockwise from +x.',
        site=dict(origin=[L.SITE[0], L.SITE[1], pad_z], yaw_deg=L.YAW, pad=list(L.COMPOUND), grade=dict(slope=L.GRADE_SLOPE, reach=L.GRADE_REACH),
                  hippodrome_platform_z=platform_z,
                  unreal_origin_cm=[L.SITE[0] * 100, -L.SITE[1] * 100, pad_z * 100]),
        meshes=[
            dict(name='SM_HS_Stable', lods=lods('SM_HS_Stable'), lod_screen_sizes=list(L.LOD_SCREEN_SIZES),
                 collision='glb/SM_HS_Stable_Collision.glb', at=[0, 0, 0], yaw=0., blocks=True),
            dict(name='SM_HS_Ground', file='glb/SM_HS_Ground.glb', at=[0, 0, 0], yaw=0., blocks=True, collision='complex',
                 slots=CITY_SLOTS['SM_HS_Ground']),
            dict(name='SM_HS_Road', file='glb/SM_HS_Road.glb', at=[0, 0, 0], yaw=0., blocks=True, collision='complex',
                 slots=CITY_SLOTS['SM_HS_Road']),
            dict(name='SM_HS_RoadSign', file='glb/SM_HS_RoadSign.glb', at=[0, 0, 0], yaw=0., blocks=True, collision='complex'),
            dict(name='SM_HS_StallDoor', lods=lods('SM_HS_StallDoor'), instances='doors[mesh=StallDoor]', collision='box'),
            dict(name='SM_HS_RoomDoor', lods=lods('SM_HS_RoomDoor'), instances='doors[mesh=RoomDoor]', collision='box'),
        ],
        barn=dict(centre=list(L.BARN_CENTRE), length=L.BARN_LENGTH, width=L.BARN_WIDTH, floor_z=L.FLOOR_Z,
                  eave_z=L.EAVE_Z, ridge_z=round(L.RIDGE_Z, 3), aisle=[L.AISLE_Y0, L.AISLE_Y1], aisle_door=list(L.AISLE_DOOR),
                  doorways=[[L.BARN_X0, L.BARN_CENTRE[1]], [L.BARN_X1, L.BARN_CENTRE[1]]]),
        stalls=[dict(id=s['id'], box=list(s['box']), door=s['door'], plaque=s['plaque'], horse=s['horse']) for s in stalls],
        rooms={k: dict(box=list(r['box']), door=r['door']) for k, r in rooms.items()},
        doors=doors,
        sign=dict(text=L.NAME, centre=L.SIGN['centre'], normal=L.SIGN['normal'], size=L.SIGN['size'], gate=list(L.GATE['at'])),
        notice_board=dict(**L.notice_board(), use='transfers'),
        spots=L.spots(),
        yard=dict(rect=list(L.YARD), trough=L.TROUGH, hitch=L.HITCH, lanterns=L.LANTERNS),
        paddock=dict(rect=list(L.PADDOCK), gate=L.PADDOCK_GATE),
        road=dict(width=L.ROAD_WIDTH, street_end=list(L.STREET_END),
                  points=[[round(x, 3), round(y, 3), round(z, 3)] for (x, y), z in zip(L.road_points(2.), road_z)]),
        clearance=L.clearance(),
        collision=[dict(name=b['name'], box=list(b['box'])) for b in L.aabb_boxes()],
    )
