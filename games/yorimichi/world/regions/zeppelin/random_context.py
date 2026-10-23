"""Restore the original sequential producer's entropy without constructing siblings."""
import math
import numpy as np


def restore(asset, primitive, village):
    """@cc [owner:fontanierh,label:correctness] zeppelin-original-random-context
    Selected constructors MUST begin at the original seed-980/seed-76 stream positions.
    Replaying entropy MUST NOT construct or export siblings. Counts and draw order MUST
    remain bound to the immutable original producer by the conservation controls.
    """
    primitive.seed(980);village.seed(76)
    if asset=='ZP_Airship':return
    # The ship consumes three plank colour draws per original deck plank.
    for _ in np.arange(-1.62,1.65,.20):
        for _ in range(3):primitive.uniform(.95,1.05)
    stations=('ZP_Woodland','ZP_City','ZP_MegaPark','ZP_Belmonte')
    if asset not in stations:return
    for index in range(stations.index(asset)):
        # Original village roof, door and potted plant colour stream.
        for _ in range(2*math.ceil((6.4+1.3)/.48)*math.ceil(((4.5+1.35)/2)/.55)+6+7):village.random()
        for _ in range(len(np.arange(-10,11,1.))*len(np.arange(-8.8,-5.1,1.))*3):primitive.uniform(.97,1.03)
        for _ in range(len(np.arange(-3.,1.05,.22))*3):primitive.uniform(.97,1.03)
        for _ in range(21):
            primitive.uniform(-.55,.55);primitive.uniform(-.25,.25);primitive.choice((0,1,2))
        if index==2:
            for _ in range(len(np.arange(-170.5,-156.2+.1,.24))*3):primitive.uniform(.95,1.05)
