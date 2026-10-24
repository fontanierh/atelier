"""Produce the coastal projection in the v2 worker's declared job directory."""
import json
from pathlib import Path
import sys


_root = Path(__file__).resolve().parents[5]
sys.path[:0] = [str(_root / 'platform/studio'),
                str(_root / 'games/yorimichi/world'),
                str(_root / 'games/yorimichi/world/regions')]

from brinecove import rim_data


def run(context):
    """@cc [owner:fontanierh,label:correctness] v2-coastal-rim-projection
    The worker MUST project the complete declared FarHills file through the original
    project function and validate the original JSON receiver before requesting its
    sole output. Serialization MUST retain the original atomic_json representation.
    This unit MUST NOT interpret an old stamp or adopt a native result certificate.
    """
    if set(context.inputs) != {'far_final'}:
        raise ValueError('The coastal projection requires exactly its FarHills content slot')
    value = rim_data.project(context.input('far_final'))
    rim_data.read(json.loads(json.dumps(value, allow_nan=False)))
    rim_data.atomic_json(context.output('final-rim.json'), value)
