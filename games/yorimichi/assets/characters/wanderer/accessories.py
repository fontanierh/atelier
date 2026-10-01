"""Small, restrained accessory motion baked into the villager's clips."""
SECONDARY={
    'hat':dict(kind='flap',stiffness=240,damping=16,gain=-.009,limit=(-.09,.035)),
    'scarf_L':dict(kind='pendulum',length=.14,stiffness=75,damping=8,limit_x=(-.40,.015),limit_y=(-.16,.16)),
    'scarf_R':dict(kind='pendulum',length=.12,stiffness=85,damping=9,limit_x=(-.36,.015),limit_y=(-.16,.16)),
    'bag':dict(kind='pendulum',length=.12,stiffness=80,damping=9,limit_x=(-.28,.01),limit_y=(-.06,.08),
               push='L',bounce=dict(stiffness=440,damping=16,limit=.008)),
}
