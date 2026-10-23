"""One Brinecove constructor or shared geometry primitive; no sibling generation."""
from brinecove import falls
from brinecove import landmarks as LM
from brinecove.geom import Builder
from brinecove.procedural.hero_presence import HAS_STATUE
from brinecove.procedural.lighthouse import lighthouse
from brinecove.procedural.statue import statue


def landmarks():
    b = Builder('06_landmarks')
    lighthouse(b)
    if not HAS_STATUE:
        statue(b)
    LM.fort(b)
    # The two-tier waterfall, its canyon river, rope bridge and ledge shrine (falls.py).
    falls.waterfall(b)
    return b
