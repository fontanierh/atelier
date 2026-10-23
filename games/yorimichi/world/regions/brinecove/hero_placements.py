"""Hero placement data only; no model import or sibling geometry generation."""
from brinecove import layout as L
from brinecove import hero_math as kit
from brinecove.paths import MODELS


def placements(hull):
    """{model slug: [(x, y, z, yaw, scale, pitch)...]} in layout metres; hull is the galleon hull's provenance."""
    result = {'pirate-queen-statue': [(L.STATUE[0], L.STATUE[1], 12.0, 0.0, 1.0, 0.0)]}
    if hull and (MODELS / 'galleon-hull.glb').exists():
        # Keel a quarter of the hull's height below the sea.
        depth = hull['top_z'] * 0.24
        result['galleon-hull'] = [(x, y, -0.35 - depth * scale, yaw, scale, 0.0) for _, x, y, yaw, scale, _ in L.SHIPS]
    else:
        # Two carved figureheads on the moored galleons, bracketed onto the stem under the bowsprit.
        result['galleon-figurehead'] = [(*kit.local(x, y, yaw, 0.0, 30.4 * scale), -1.1 + 4.6 * scale, yaw, 0.78, -32)
                                        for _, x, y, yaw, scale, _ in L.SHIPS[:2]]
        name, x, y, yaw, scale, sails = L.SHIPS[0]
        result['ships-wheel'] = [(*kit.local(x, y, yaw, 0.0, -16.5 * scale), -1.1 + 4.72 * scale, yaw + 90, 0.9, 0.0)]
    # The harbor cannon is procedural now (landmarks.cannon, placed by modules.props).
    # The quay anchor is procedural now (landmarks.anchor, placed by modules.props).
    result['harbor-capstan'] = [(x, y, 5.35, yaw, 1.0, 0.0) for x, y, yaw in ((8, -24, 0), (238, -50, 34))]
    return result
