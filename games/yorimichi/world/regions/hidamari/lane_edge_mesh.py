"""One city logical constructor; no sibling export or construction."""
from hidamari import city_poles
from hidamari import lane_edges
from hidamari import layout
from hidamari.environment import M
from hidamari.environment import v
from hidamari.layout import ROAD_X
from hidamari.layout import ROAD_Y
from hidamari.layout import height


def lane_edge_mesh(city):
    m=M('HD_LaneEdges');v.PALETTE.update(lane_edges.PALETTE)
    print('HIDAMARI LANE EDGES',lane_edges.build(m,height,city['buildings'],ROAD_X,ROAD_Y,layout.road_width,city_poles.KEEP_OUT),flush=True)
    return m
