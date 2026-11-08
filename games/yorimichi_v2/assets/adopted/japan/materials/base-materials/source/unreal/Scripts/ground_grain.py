"""The same Sunburst detail, coordinates and field scale on both sides of every ground join."""


def code(texture, sampler, position, result='groundDetail'):
    return f'''float3 floorFine=Texture2DSample({texture},{sampler},{position}.xy/900.).rgb*2;
float3 floorStand=Texture2DSample({texture},{sampler},{position}.xy/4500.+.31).rgb*2;
float3 floorField=Texture2DSample({texture},{sampler},{position}.xy/16000.+.67).rgb*2;
float3 {result}=floorFine*lerp(float3(1,1,1),floorStand,.55)*lerp(float3(1,1,1),floorField,.35);'''
