"""The open-sea look, shared by the sea plane's M_Sea (import_southwest.py) and the Hidamari harbour's M_HarborWater
(harbor_material.py), so the two read as one sea from any distance.

M_Sea covers the big sea plane; M_HarborWater covers the harbour's HD_Sea rectangle, which sits 2.5 cm above it. On
the rectangle's outline the harbour water is exactly the open sea (these waves and this colour), and it turns into
its own lit water over its 200 m border.

The sea's colour is authored as emissive, not left to the engine's lighting. From eye height nearly all the sea is
seen at grazing angles, where Fresnel reflectance runs to 1: the lit material (specular .6) mirrored the sky light's
capture of the dome, blurred with its grey-blue lower hemisphere, and the whole sea came out one flat sheet in the
sky's colour with no horizon. The dome is unlit and the exposure is fixed, so an emissive colour given in the dome's
own units is seen exactly as chosen, next to the sky it has to differ from:

- the body of the water is a deep blue-teal (lighter teal in the shallows);
- a reflection of the painted dome is added with water's Fresnel term on the wave normals, scaled down (REFLECT) so
  the body colour shows; facets turned toward the viewer mirror the bluer sky higher up, so the waves read;
- only where the view grazes the far, flat sea does the reflection strengthen (GRAZE), and a haze toward a colour a
  little darker than the dome's horizon comes in with distance (FAR, HAZE): the sea gets lighter toward the horizon,
  and the horizon stays a soft but visible line;
- white surf where the water meets land, rock, piles or a hull (the scene depth behind the translucent sea), and a
  few white flecks where short wave crests meet.

The engine still lights the surface for sun glints only: black base colour, specular .02. Below .25 the engine scales
its grazing reflection by 50 x F0 (here .08), so the captured sky no longer washes the authored colour out.

Values were chosen against the in-game screenshots: under the fixed exposure and film curve, the dome just above the
horizon (HORIZON) shows about 125,160,194 and its cloud tops about 219,216,214. A film curve fitted to those predicts,
from the beach at eye height, about 51,94,128 at 9 m (wave facets 40,88,122 to 55,98,134), 74,113,151 at 40 m,
95,131,169 at 300 m, 110,143,180 at 1 km and 113,146,182 at the horizon, 12 to 16 levels under the sky; from the
crow's nest (89 m), 49,94,129 at 300 m, 84,121,159 at 2 km and 114,145,182 at the horizon. The surf shows about
200,204,208, a little under the cloud tops.
"""


def num(x):
    """HLSL float literal"""
    return repr(float(x))


def f3(c):
    """HLSL float3 literal"""
    return 'float3(%s)' % ','.join(num(x) for x in c)


# The painted sky dome as the camera sees it: gen_textures.sky() `hor` (sRGB .34 .52 .76) and `zen` (.14 .32 .66),
# stored in 8 bits, in linear, times the MI_Sky tint 1.35 (setup_project.py).
HORIZON = (0.126, 0.311, 0.720)
ZENITH = (0.0235, 0.113, 0.531)

# The water's own colour: deep blue-teal, and a lighter teal over the first SHALLOW_M metres behind the surface.
BODY = (0.004, 0.060, 0.130)
SHALLOW = (0.020, 0.120, 0.125)
SHALLOW_M = 5.0
FOAM = (1.20, 1.25, 1.30)

# Share of the dome reflection: water's Fresnel term times REFLECT, rising to GRAZE where the view grazes the sea
# (sin of the view's elevation under ~.01: beyond ~300 m from the beach, and near the horizon from anywhere).
REFLECT = 0.35
GRAZE = 0.74
GRAZE_POWER = 100.0

# Haze with pixel depth D (cm): 1 - exp(-D / HAZE_CM), .1 at 1 km, .36 at 4 km, .9 at 20 km (the dome), toward the
# dome's horizon colour times FAR: the far sea stays a little darker than the sky above the horizon.
HAZE_CM = 900000.0
FAR = 0.74
FAR_COLOUR = tuple(round(c * FAR, 4) for c in HORIZON)

# The engine's lighting: sun glints on the waves only.
BASE = (0.0, 0.0, 0.0)
ROUGHNESS = 0.15
SPECULAR = 0.02

# Waves: nine crossing trains spread +-54 degrees about the world's wind (world.json wind_dir .30,.95 in Blender axes;
# Unreal's y is negated), wavelengths 21 m down to 1.1 m, deep-water speeds (a 21 m swell moves at 5.7 m/s), slopes
# gentle (.1 rms). Each train fades before its phase changes too fast across a pixel, so the far sea goes flat, not
# noisy.
WIND = -1.2645
K0 = 0.30
A0 = 0.065

# Surf: a band SURF_M metres deep behind the surface near the camera; far away it widens to about one and a half
# pixels, so a cliff 400 m off still gets its white line. None beyond SURF_FAR metres (the dome meets the sea at 20 km).
SURF_M = 1.6
SURF_FAR = (2500.0, 4000.0)
FLECK = 0.45

# P: world position (cm), T: time (s) -> float3(slope x, slope y, crest). The crest is the short trains' sum, -1..1;
# the flecks sit on its rare peaks.
WAVES = '''
float2 p=P.xy*.01;
float2 gx=ddx(p),gy=ddy(p);
float2 slope=0;
float crest=0;
for(int i=0;i<9;i++)
{
    float a=%(wind)s+.95*sin(i*2.39+.5);
    float2 d=float2(cos(a),sin(a));
    float k=%(k0)s*pow(1.45,(float)i);
    float2 f=k*float2(dot(gx,d),dot(gy,d));
    float aa=exp(-.3*dot(f,f));
    float warp=1.8*sin(dot(p,float2(-d.y,d.x))*k*.41+T*.3+i*1.7);
    float ph=dot(p,d)*k+warp-T*sqrt(9.81*k)+i*2.1;
    slope+=d*(cos(ph)*%(a0)s*pow(.92,(float)i)*aa);
    if(i>2)crest+=sin(ph)*aa;
}
return float3(slope,crest/6);
''' % dict(wind=num(WIND), k0=num(K0), a0=num(A0))

# W: WAVES -> world-space normal (the material's tangent_space_normal is off)
NORMAL = 'return normalize(float3(-W.xy,1));'

# W: WAVES, V: camera vector (world, toward the camera), D: pixel depth (cm), L: scene depth behind the surface (cm;
# M_HarborWater, opaque, passes 1e7), P: world position (cm), T: time (s) -> emissive colour
LOOK = '''
float2 p=P.xy*.01;
float3 N=normalize(float3(-W.xy,1));
float nv=saturate(dot(N,V));
// gusts: slow, kilometre-wide patches with a little more or less sky in the water and more or fewer flecks
float gust=.5+.25*sin(p.x*.0041+p.y*.0023+T*.021)+.25*sin(p.y*.0052-p.x*.0017-T*.016);
float graze=pow(saturate(1-V.z),%(graze_power)s);
float fres=(.02+.98*pow(1-nv,5))*lerp(%(reflect)s*(.8+.4*gust),%(graze)s,graze);
float3 R=reflect(-V,N);
float3 sky=lerp(%(horizon)s,%(zenith)s,pow(asin(saturate(R.z))/1.5708,.6));
float l=L*.01;
float3 c=lerp(lerp(%(shallow)s,%(body)s,saturate(l/%(shallow_m)s)),sky,fres);
// surf: white at the waterline, fading over w metres behind the surface, with a wobbling edge and a slow wash
float fp=max(length(ddx(p)),length(ddy(p)));
float w=%(surf_m)s+1.5*fp;
float wob=.5+.25*sin(p.x*.83+p.y*.37+T*.6)+.25*sin(p.y*1.13-p.x*.51-T*.45);
float edge=saturate(1-l/(w*(.55+.9*wob)));
float surf=edge*edge*(3-2*edge)*(.7+.3*sin(T*1.2+l/w*4))*(1-smoothstep(%(far0)s,%(far1)s,D*.01));
float fleck=smoothstep(.58,.84,W.z)*(.6+.8*gust)*%(fleck)s;
c=lerp(c,%(foam)s,saturate(max(surf,fleck)));
return lerp(c,%(far)s,1-exp(-D/%(haze)s));
''' % dict(graze_power=num(GRAZE_POWER), reflect=num(REFLECT), graze=num(GRAZE), horizon=f3(HORIZON), zenith=f3(ZENITH),
           shallow=f3(SHALLOW), body=f3(BODY), shallow_m=num(SHALLOW_M), surf_m=num(SURF_M), far0=num(SURF_FAR[0]),
           far1=num(SURF_FAR[1]), fleck=num(FLECK), foam=f3(FOAM), far=f3(FAR_COLOUR), haze=num(HAZE_CM))

# D: pixel depth (cm) -> the haze's share, as in LOOK (the lit harbour water fades by it)
HAZE = 'return 1-exp(-D/%s);' % num(HAZE_CM)
