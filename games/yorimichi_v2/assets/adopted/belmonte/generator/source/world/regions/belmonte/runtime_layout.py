"""Placement, map, TV and corridor metadata, independent of geometry exporters."""
import numpy as np

from belmonte import layout as L,planting


SIGN_TRANSLATIONS = {
    'Votre écurie': 'Belmonte Stables',
    'Haras de Belmonte': 'Belmonte Stables',
    'Haras des Aulnes': 'Alder Stables',
    'Écurie du Pont Clair': 'Clearbridge Stables',
    'Domaine des\nTrois Prés': 'Three Meadows\nEstate',
    'Écurie des\nDunes Basses': 'Low Dunes\nStables',
    'Domaine des\nRoches Longues': 'Longstone\nEstate',
    'Écurie de Montfauve': 'Amberhill Stables',
    'MAIRIE': 'TOWN HALL',
    'TAVERNE': 'TAVERN',
}



def clear_railway(plants):
    """Clear the Belmonte railway's corridor (train/corridor.py settle): trees off it, shrubs and grass down to the
    line's soft edge, set on the carved ground; {name: removed}."""
    from train import corridor
    line = corridor.load()
    removed = {}
    if line is None:
        return removed
    for name, transforms in plants.items():
        if not transforms:
            continue
        t = np.asarray([tr['translation_cm'] for tr in transforms], float)
        x, y = t[:, 0] / 100 + L.ORIGIN[0], -t[:, 1] / 100 + L.ORIGIN[1]
        keep, z = corridor.settle(name, x, y, t[:, 2] / 100 + L.ORIGIN[2], line)
        moved = np.abs(z - (t[:, 2] / 100 + L.ORIGIN[2])) > .005
        for tr, zz, m in zip(transforms, z, moved):
            if m:
                tr['translation_cm'] = [tr['translation_cm'][0], tr['translation_cm'][1], round((zz - L.ORIGIN[2]) * 100, 1)]
        if (~keep).any():
            removed[name] = int((~keep).sum())
            plants[name] = [tr for tr, k in zip(transforms, keep) if k]
    return removed



def osteria_landing(data):
    """Place the authored local landing inside the committed taproom's actual transform."""
    assets = {m['source_asset'] for m in data['meshes'] if m['name'] == 'SM_BM_BH_Osteria_Taproom'}
    placements = [p['transform'] for p in data['placements'] if p['asset'] in assets]
    if len(assets) != 1 or len(placements) != 1:
        raise ValueError('Osteria map landing requires exactly one committed taproom placement')
    transform = placements[0]
    # Local plan metres: clear the stool by one metre, at floor level. Placement
    # translation/rotation/scale belong to the source scene, never to this map stop.
    local = np.array([.4, 2.1, 0.]) * [100., -100., 100.] * transform['scale']
    native = planting.rotate(transform['rotation_xyzw'], local) + transform['translation_cm']
    position = native / [100., -100., 100.] + L.ORIGIN
    # Face the front wall relative to the taproom. The map uses plan-space yaw;
    # JapanMap converts its Y axis and negates yaw when loading native runtime data.
    angle = np.radians(-86.)
    forward = planting.rotate(transform['rotation_xyzw'], np.array([np.cos(angle), np.sin(angle), 0.]))
    return position, float(np.degrees(np.arctan2(-forward[1], forward[0])))



TV_BUILDING_SPOTS = (
    ('osteria_front', 'SM_BM_BH_Osteria_Taproom', [10., -750., 230.], 90., [40., -310., 0.], -94., 1.4),
    ('osteria_back', 'SM_BM_BH_Osteria_Taproom', [685., 700., 230.], -90., [360., 350., 0.], 46.2, 1.4),
    ('salon_paris', 'SM_BM_BHip_SalonHall', [-500., -480., 255.], 90., [-500., -50., 15.], -90., 1.4),
    ('salon_bar', 'SM_BM_BHip_SalonHall', [1250., 1437.6, 305.], -90., [1250., 960., 15.], 90., 1.3),
)



def tv_spots(data):
    """Derive the four Belmonte racing TV spots from the committed Osteria and Salon placements."""
    by_name = {}
    for mesh_name in {'SM_BM_BH_Osteria_Taproom', 'SM_BM_BHip_SalonHall'}:
        assets = {m['source_asset'] for m in data['meshes'] if m['name'] == mesh_name}
        placements = [p['transform'] for p in data['placements'] if p['asset'] in assets]
        if len(assets) != 1 or len(placements) != 1:
            raise ValueError(f'TV placement requires exactly one committed {mesh_name} placement')
        by_name[mesh_name] = placements[0]
    out = []
    for spot_id, mesh_name, local_pivot, dyaw, local_watch, dwyaw, scale in TV_BUILDING_SPOTS:
        tr = by_name[mesh_name]
        q = tr['rotation_xyzw']
        t = np.asarray(tr['translation_cm'], float)
        s = np.asarray(tr['scale'], float)
        fwd = planting.rotate(q, np.array([1., 0., 0.]))
        base_yaw = float(np.degrees(np.arctan2(fwd[1], fwd[0])))
        pivot = (planting.rotate(q, np.asarray(local_pivot, float) * s) + t).round(2).tolist()
        watch = (planting.rotate(q, np.asarray(local_watch, float) * s) + t).round(2).tolist()
        yaw = round(((base_yaw + dyaw + 180.) % 360.) - 180., 2)
        if abs(yaw + 180.) < 1e-6:
            yaw = 180.
        watch_yaw = round(((base_yaw + dwyaw + 180.) % 360.) - 180., 2)
        out.append({'id': spot_id, 'pivot_cm': pivot, 'yaw': yaw, 'watch_cm': watch, 'watch_yaw': watch_yaw,
                    'scale': float(scale * max(abs(v) for v in s[:2]))})
    return out



def map_zones(town_z,data):
    """@cc [owner:fontanierh,label:correctness] belmonte-indoor-map-stop
    Indoor stops MUST follow Belmonte's origin and land on their committed floors below
    the roofs, with a clear standing footprint. The salon faces the counters and the
    osteria follows its taproom transform and faces the front wall. Outdoor stops MUST
    retain their default landing trace.
    """
    osteria, osteria_yaw = osteria_landing(data)
    return [
        {'key': 'belmonte', 'name': 'Belmonte · town square', 'x': L.ORIGIN[0],
         'y': L.ORIGIN[1] - 18., 'z': town_z, 'yaw': 90.,
         'hint': 'Town, estates and countryside racecourses north of the volcano'},
        {'key': 'belmonte_course', 'name': 'Belmonte · racecourse',
         'x': 385., 'y': 4255. + L.NORTH_SHIFT, 'z': float(L.ORIGIN[2] + 30.2), 'yaw': 90.,
         'hint': 'Explore the turf and sand course and its grandstands'},
        {'key': 'belmonte_training', 'name': 'Belmonte · training grounds',
         'x': 230., 'y': 4560. + L.NORTH_SHIFT, 'z': float(L.ORIGIN[2] + 30.2), 'yaw': 0.,
         'hint': 'Countryside arenas and practice grounds'},
        # Haras Valley's salon.inside, moved one metre west off the hall fixture; face the counters.
        {'key': 'belmonte_salon', 'name': 'Belmonte · Betting Hall',
         'x': L.ORIGIN[0] + 67.8, 'y': L.ORIGIN[1] + 306.8, 'z': float(L.ORIGIN[2] + 30.2),
         'yaw': 0., 'above_m': 1.5,
         'hint': 'The betting hall by the racecourse: betting counters'},
        {'key': 'belmonte_osteria', 'name': 'Belmonte · Osteria',
         'x': float(osteria[0]), 'y': float(osteria[1]), 'z': float(osteria[2]),
         'yaw': osteria_yaw, 'above_m': 1.5,
         'hint': 'The tavern on the piazza'},
    ]

