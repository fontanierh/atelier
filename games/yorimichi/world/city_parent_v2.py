"""Validate one complete original city plan and emit only consumed parent facts."""
import json
from pathlib import Path
import shutil

from atelier.build_v2.recipe_job import unpack_root
from region_mesh_parts import validate


def run(context):
    """@cc [owner:fontanierh,label:correctness] city-parent-facts-stop-sibling-geometry
    Projection MUST validate the complete original parent plan and every payload
    with the existing source validator before publication. It MUST emit exactly
    parent, source_material_slots and source_collision_hulls; geometry counts,
    sibling digests, membership and payloads MUST NOT leak into native finish keys.
    No generated checkout scan, native work or source regeneration MAY run.
    """
    if context.params or set(context.inputs)!={'source'} or set(context.outputs)!={'plan.json'}:raise ValueError('City parent projection requires exactly its declared source and output')
    root=Path(context.input('source'));archive=root/'products/0-0.tree.tar'
    if root.resolve()!=root or not root.is_dir() or [p for p in root.rglob('*') if p.is_file()]!=[archive] or any(p.is_symlink() for p in root.rglob('*')):
        raise ValueError('City parent requires the exact complete frozen planner ROOT')
    scratch=context.output_dir/'.city-plan'
    if scratch.exists():raise ValueError('City parent scratch must be fresh')
    try:
        manifest=unpack_root(archive,scratch)
        if manifest['kind']!='directory':raise ValueError('City parent ROOT must be the complete original planner directory')
        plan=validate(scratch)
        facts={'parent':plan['parent'],'source_material_slots':plan['slots'],'source_collision_hulls':plan['source_collision_hulls']}
        context.output('plan.json').write_text(json.dumps(facts,sort_keys=True,separators=(',',':'))+'\n')
    finally:
        if scratch.exists():shutil.rmtree(scratch)
