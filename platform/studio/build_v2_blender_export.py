"""Declared D2 entry point; execute only through the existing staged Blender worker."""
from atelier.build_v2.blender_ops import run_export_piece


def run(context):
    run_export_piece(context)
