"""One city logical constructor; no sibling export or construction."""
from hidamari import city_poles
from hidamari.environment import M
from hidamari.environment import v


def wire_mesh(city):
    m=M('HD_Wires');v.PALETTE['hd_wire']=(.018,.018,.02)
    print('HIDAMARI WIRES',city_poles.wires(m,city['poles'],'hd_wire'),flush=True);return m
