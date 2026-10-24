"""The shared D2 per-piece export body, with no project scheduling or cache access."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'platform/studio'))
from atelier.build_v2.blender_ops import run_export_piece


def run(context):
    run_export_piece(context)
