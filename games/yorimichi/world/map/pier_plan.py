"""Sunset Pier's map footprint and riding features, from its gameplay contract."""
import math


def world_point(park, x, y):
    a=math.radians(park.get('yaw_deg',0.));c,s=math.cos(a),math.sin(a)
    ox,oy=park['origin'][:2]
    return ox+x*c-y*s,oy+x*s+y*c


def deck_polygon(park):
    x0,x1=park['deck']['x'];y0,y1=park['deck']['y']
    return [world_point(park,x,y) for x,y in ((x0,y0),(x1,y0),(x1,y1),(x0,y1))]


def draw_pier(draw,at,px_per_m,park):
    """Draw the same geometry through either the full sheet or a repaint crop's projection."""
    draw.polygon([at(*p) for p in deck_polygon(park)],fill=(214,208,189),outline=(107,107,99),width=max(1,round(px_per_m)))
    def local(x,y):return at(*world_point(park,x,y))
    for name,(x0,x1,y0,y1) in park.get('features',{}).items():
        colour=(172,189,175) if any(k in name for k in ('return','mini','flow','kicker','hip')) else (230,221,201)
        draw.polygon([local(x,y) for x,y in ((x0,y0),(x1,y0),(x1,y1),(x0,y1))],fill=colour)
    for rail in park['rails']:
        pts=[local(p[0],p[1]) for p in rail['points']]
        if rail['id']=='bowl_coping':draw.polygon(pts,fill=(112,172,169))
        draw.line(pts,fill=(81,126,122),width=max(1,round(.6*px_per_m)),joint='curve')
    for species,rows in park.get('trees',{}).items():
        colour=(179,111,61) if 'Maple' in species else (65,111,73)
        for x,y,z,yaw,scale in rows:
            cx,cy=local(x,y);r=2.5*scale*px_per_m
            draw.ellipse((cx-r,cy-r,cx+r,cy+r),fill=colour)
