"""City placement parameters and data functions, independent from mesh construction."""



STATION = (1185., 290.)


X0, X1 = 1128., 1300.


Y0, Y1 = 295.8, 306.


RAIL = -.67


BED = RAIL-.72


SHOPS = [('HD_Shop_05', 1143., 249.), ('HD_Shop_11', 1219.5, 249.)]


SHELTER = (1146.2, 1150.0, 265.4, 276.2)


KIOSK = (1221., 288.)


LANE_BREAK = (1240., 280., 322.)


PAD = dict(asset='HD_StationYard', x=(X0+X1)/2, y=(Y0+Y1)/2, yaw=180, half_width=(X1-X0)/2, front=-(Y1-Y0)/2,
           back=(Y1-Y0)/2, fade_x=4., fade_y=4., group='public')


def floor_z():
    from hidamari import layout
    return float(layout.street_height(STATION[0], STATION[1]-11.5))


def place(put, inst, height, buildings):
    """@cc [owner:fontanierh,label:correctness] hidamari-operating-terminus
    Hidamari's town platform MUST serve the Belmonte trains. No decorative railcar, shed end wall or duplicate
    track may occupy the service's clearance. The platform surface MUST meet the station floor plus 0.25 m.
    """
    z = floor_z()
    inst.pop('HD_Railcar', None)
    buildings.append({'asset': 'HD_StationYard', 'position': [PAD['x'], PAD['y'], z+BED], 'yaw': 180,
                      'width': X1-X0, 'depth': Y1-Y0, 'terrain_pad': True})
    boxes = [(X0-2, X1+1, 294., Y1+4), (SHELTER[0]-.5, SHELTER[1]+.5, SHELTER[2]-.5, SHELTER[3]+.5),
             (KIOSK[0]-2.2, KIOSK[0]+2.2, KIOSK[1]-2.6, KIOSK[1]+2.6)]
    boxes += [(x-13.5, x+13.5, y-11.6, y+11.6) for _, x, y in SHOPS]
    for name, items in inst.items():
        if name.startswith('HD_Shop_') or not items: continue
        inst[name] = [p for p in items if not any(a < p[0] < b and c < p[1] < d for a, b, c, d in boxes)]
