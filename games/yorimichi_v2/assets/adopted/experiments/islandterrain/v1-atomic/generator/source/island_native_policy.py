"""Exact derived island material packages; shared painted/foliage assets stay upstream."""
MATERIAL_PACKAGES=tuple('/Game/Japan/Materials/'+name for name in (
    'M_ForestGround','MI_FarForest','MI_Coast','M_CoastRock','MI_CoastRock','MI_Sand','M_Sea'))+(
    '/Game/Japan/Textures/T_CoastRock',)
SIDECARS=('.uexp','.ubulk','.uptnl','.m.ubulk','.upayload')
