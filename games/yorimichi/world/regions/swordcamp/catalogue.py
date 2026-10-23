"""Logical identities only: adding an entry cannot change another constructor's source input."""
ASSETS = {
    'SM_RoninKasa': ('kasa', 'build_kasa', {}),
    'SM_GuardJingasa': ('jingasa', 'build_jingasa', {}),
    'SM_CaptainKabuto': ('kabuto', 'build_kabuto', {}),
    'SM_RoninMenpo': ('menpo', 'build_menpo', {}),
    'SM_RoninDo': ('do', 'build_do', {}),
    'SM_RoninSode': ('sode', 'build_sode', {}),
    'SM_RoninSashimono': ('sashimono', 'build_sashimono', {}),
    'SM_RoninKatana': ('sword', 'build_sword', dict(blade_len=.72, hilt_len=.24, curve=.030, sheathed=False)),
    'SM_RoninNodachi': ('sword', 'build_sword', dict(blade_len=1.06, hilt_len=.34, curve=.046, sheathed=False)),
    'SM_RoninWakizashi': ('sword', 'build_sword', dict(blade_len=.46, hilt_len=.16, curve=.018, sheathed=True, red_saya=False)),
    'SM_CampJinmaku': ('jinmaku', 'build_jinmaku', {}),
    'SM_CampFirePit': ('firepit', 'build_firepit', {}),
    'SM_CampWeaponRack': ('weapon_rack_clean', 'build_weapon_rack_clean', {}),
    'SM_CampBales': ('bales_and_chest', 'build_bales_and_chest', {}),
}
