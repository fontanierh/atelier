"""Shared city palette and mesh construction frame, without geometry generation."""
import yori
from village import mesh as v

ROOT = yori.REGIONS
OUT = yori.OUT / "hidamari"
v.OUT = OUT
M = v.Mesh

v.PALETTE.update({'hd_grass':(.125,.18,.048),'hd_yard':(.15,.115,.07),'hd_walk':(.185,.165,.135),'hd_flag':(.20,.172,.128),'hd_flag2':(.18,.155,.115),
             'hd_lane_asphalt':(.095,.09,.085),'hd_ditch_concrete':(.25,.24,.22),'hd_garden_gravel':(.22,.20,.165)})
v.PALETTE.update({'paving':(.22,.18,.125),'asphalt':(.085,.08,.073),'park':(.24,.30,.12),'cream':(.66,.57,.41),'blue':(.08,.19,.25),'brick':(.31,.12,.055),'water_city':(.075,.24,.29)})
