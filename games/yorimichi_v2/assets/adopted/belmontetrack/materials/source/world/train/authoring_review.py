"""Complete coach scenes for diagnostics, without combined mesh exports."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import yori  # noqa: E402
from train import build as builder  # noqa: E402


def save_scene(coach, *, mesh, lod_sets, placements, info):
    """Save the actual pre-export scene with the original authoring visibility policy."""
    if set(lod_sets) != {0, 1, 2} or info['mesh'] != mesh:
        raise ValueError('Authoring diagnostics require the complete coach source')
    output = builder.OUT / coach.name
    output.mkdir(parents=True, exist_ok=True)
    placement_path = output / f'{coach.name}-placements.json'
    placement_path.write_text(json.dumps(placements, indent=1))
    title = ''.join(part.title() for part in coach.name.split('-'))
    for obj in builder.bpy.data.collections[f'{title}_Reservations'].objects:
        obj.hide_render = False
    for obj in builder.bpy.data.collections[f'{title}_LOD2'].objects:
        obj.hide_set(True)
    scene_path = output / f'{coach.name}.blend'
    if builder.bpy.ops.wm.save_as_mainfile(filepath=str(scene_path), compress=True, relative_remap=True) != {'FINISHED'}:
        raise RuntimeError('Coach authoring scene save did not finish')
    return dict(info, files={path.name: dict(bytes=path.stat().st_size, sha256=builder.sha(path))
                            for path in (placement_path, scene_path)})


def refuse_export(*args, **kwargs):
    raise RuntimeError('Coach authoring diagnostics must not export combined meshes')


def main(argv=None):
    """@cc [owner:fontanierh,label:correctness] isolated-coach-authoring-diagnostics
    Diagnostics MUST save complete genuine pre-export blend scenes, placements and
    original source/manifest metadata in the isolated authoring root. They MUST NOT
    export combined meshes or overwrite/satisfy the production train library. Keep
    original reservation render visibility and hidden LOD2 objects. Restore every
    temporary builder override even when construction, saving or export refusal fails.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.output.resolve()
    if output != (yori.OUT / 'belmonte-train-authoring').resolve():
        raise ValueError('Legacy coach diagnostics require the isolated authoring root')
    original_build, original_export = builder.build, builder.export_glb
    original_output, original_textures = builder.OUT, builder.TEX
    def scene_only(coach, images):
        return original_build(coach, images, source_sink=save_scene)
    try:
        builder.OUT = output
        builder.TEX = output / 'textures'
        builder.build = scene_only
        builder.export_glb = refuse_export
        builder.main()
    finally:
        builder.build, builder.export_glb = original_build, original_export
        builder.OUT, builder.TEX = original_output, original_textures


if __name__ == '__main__':
    main(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else [])
