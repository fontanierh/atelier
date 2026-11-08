"""Complete native logical names and physical LOD roster, independent of the build controller."""
PROPS=tuple('HD_P_'+slug for slug in (
    'vending_machine','kei_truck','scooter','bicycle','postbox','phone_booth','bus_stop','stone_lantern',
    'komainu','jizo','water_basin','sake_barrels','produce_stand','garbage_station','potted_plants','ac_unit',
    'propane_tanks','curve_mirror','hokora','tanuki','fire_buckets','drink_crates','planter_box','laundry_stand',
    'street_bench','bonsai_shelf','yatai','kei_car','taxi','town_bus','bicycle_shelter','lantern_sign'))
TREES=tuple('Tree_Caldera_'+name for name in ('BlackPine_A','BlackPine_B','Cedar_A','Cedar_B'))


def members():
    return (*PROPS,*(name if lod==0 else name+'_LOD'+str(lod) for name in TREES for lod in range(4)))

