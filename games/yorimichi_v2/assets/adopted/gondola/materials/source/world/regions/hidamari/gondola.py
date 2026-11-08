"""Hidamari-owned ropeway station mouths and terrain access fitting data."""
STATIONS = {
    'hidamari': {'kind':'valley','mouth':(1120.,455.),'name':'Hidamari — Southeast Rim'},
    'southeast': {'kind':'rim','mouth':(1180.,2040.),'name':'Southeast Rim — Hidamari',
                  'platform_lift_m':.75,'access_turn_deg':90.},
    'northwest': {'kind':'rim','mouth':(488.,2795.),'name':'Northwest Rim — Belmonte',
                  'platform_lift_m':2.,'access_fit':{'risers':5,'run_m':3.1,'join_m':1.3}},
    'floor': {'kind':'crater','mouth':(1023.,2177.),'name':'Crater Floor','platform_lift_m':9.},
    'floor_rim': {'kind':'rim','mouth':(1195.,2075.),'name':'Southeast Rim — Crater',
                  'access_turn_deg':180.,'platform_lift_m':10.25,
                  'access_fit':{'risers':52,'run_m':21.38,'join_m':3.2,
                                'tread_m':.28,'flights':[13,13,13,13],'landing_m':1.2}},
}
STATIONS['floor_rim'].update(access_turn_deg=0.,
                             access_fit={'risers':8,'run_m':2.6,'join_m':.6,'tread_m':.25})
