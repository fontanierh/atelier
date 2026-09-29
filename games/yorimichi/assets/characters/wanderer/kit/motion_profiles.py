"""Shared accessory tuning for foot locomotion and skate animation baking."""

CAPE_BOY={
    'hood':dict(kind='flap',stiffness=150,damping=10,gain=.022,limit=(-.04,.40)),
    'bag':dict(kind='pendulum',length=.15,stiffness=30,damping=4.5,limit_x=(-.07,.45),limit_y=(-.05,.45),
               bounce=dict(stiffness=320,damping=9,limit=.022)),
    'sash_L':dict(kind='pendulum',length=.12,stiffness=40,damping=5,limit_x=(-.65,.06),limit_y=(-.35,.35),push='R'),
    'sash_R':dict(kind='pendulum',length=.16,stiffness=32,damping=4.5,limit_x=(-.65,.06),limit_y=(-.35,.35),push='L'),
}

WANDERER={
 'scarf':dict(kind='chain',bones=('scarf_01','scarf_02','scarf_03'),length=.12,stiffness=(45,30,22),damping=(6,5,4),limit_x=(-.5,.12),limit_y=(-.4,.4)),
 'sash':dict(kind='chain',bones=('sash_01','sash_02'),length=.15,stiffness=(38,26),damping=(5.5,4.5),limit_x=(-.6,.05),limit_y=(-.35,.35),push='R'),
 'bag_L':dict(kind='pendulum',bones=('bag_L',),length=.16,stiffness=34,damping=5,limit_x=(-.55,.05),limit_y=(-.04,.35),push='L',bounce=dict(stiffness=380,damping=11,limit=.012)),
 'bag_R':dict(kind='pendulum',bones=('bag_R',),length=.16,stiffness=34,damping=5,limit_x=(-.55,.05),limit_y=(-.35,.04),push='R',bounce=dict(stiffness=380,damping=11,limit=.012)),
 'hat':dict(kind='flap',bones=('hat',),stiffness=220,damping=14,gain=-.010,limit=(-.12,.03)),
 'hair_tie':dict(kind='pendulum',bones=('hair_tie',),length=.06,stiffness=90,damping=7,limit_x=(-.25,.25),limit_y=(-.25,.25)),
}
