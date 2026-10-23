"""Explicit shared Brinecove authoring parameters; no geometry or exports."""
from brinecove.paths import MODELS as ASSETS
import json

HAS_STATUE = (ASSETS / 'pirate-queen-statue.glb').exists()
HAS_FIGUREHEAD = (ASSETS / 'galleon-figurehead.glb').exists()
HAS_WHEEL = (ASSETS / 'ships-wheel.glb').exists()
HAS_HULL = (ASSETS / 'galleon-hull.glb').exists()
HULL = (json.loads((ASSETS / 'galleon-hull.provenance.json').read_text())['processing']
        if HAS_HULL else None)
