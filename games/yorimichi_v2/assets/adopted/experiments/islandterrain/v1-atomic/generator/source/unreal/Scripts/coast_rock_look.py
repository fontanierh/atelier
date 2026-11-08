"""Colour detail for the owned coastal rock slot, in world centimetres."""

# Committed Sunburst colour asset. The mean is measured after the sRGB transfer,
# as Unreal samples an sRGB texture in linear space. Keep the vertex geology tint.
TEXTURE = 'environment/textures/volcanic-rock.jpg'
TEXTURE_SHA256 = '9389cb40cf88f6962ad74e32c62d4a639144dc4ad2cb7cfefc50627155677473'
LINEAR_LUMINANCE = .0908408217639082
TILE_METRES = 24.


def code():
    """@cc [owner:fontanierh,label:correctness] coastal-rock-colour-only
    Rock detail MUST stay in CoastRock, preserve its vertex geology colour and
    geometric normal, and use explicit world scale and linear texture values.
    It MUST NOT change meadow/sand, atmosphere, lighting or any ground position.
    """
    return f'''
float3 colour=lerp(C.rgb/12.92,pow((C.rgb+.055)/1.055,2.4),step(.04045,C.rgb));
float3 weights=pow(abs(N),4.);
weights/=max(weights.x+weights.y+weights.z,1.e-5);
float3 q=P/{TILE_METRES*100.:.1f};
float3 stone=Texture2DSample(Rock,RockSampler,q.yz).rgb*weights.x
            +Texture2DSample(Rock,RockSampler,q.xz).rgb*weights.y
            +Texture2DSample(Rock,RockSampler,q.xy).rgb*weights.z;
float grain=dot(stone,float3(.2126,.7152,.0722))/{LINEAR_LUMINANCE:.12f};
return colour*lerp(1.,clamp(grain,.35,1.75),.65);
'''
