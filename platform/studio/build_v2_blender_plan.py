"""Declared whole-payload planner entry point, without geometry extraction or re-encoding."""
from atelier import mesh_ir
from atelier.build_v2.blender_ops import emit_whole_payload, run_plan


def run(context):
    if set(context.inputs) != {'source'}:
        raise ValueError('Whole-payload planner requires exactly its declared source file')
    source = context.input('source')
    if source.is_symlink() or not source.is_file() or source.stat().st_size > mesh_ir.MAX_BYTES:
        raise ValueError('Whole-payload source must be one bounded regular MeshIR file')
    raw = source.read_bytes()
    run_plan(context, lambda root: emit_whole_payload(root, raw, parent=context.params['parent']))
