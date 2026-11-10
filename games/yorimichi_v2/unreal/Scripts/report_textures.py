"""Report texture settings as JSON: sRGB flag, compression, LOD group and address modes (read-only `editor.run`).

Run with V2_EDITOR_READ_ONLY=1 through `atelier build yorimichi_v2 editor.run`: no claim is needed, every save is refused
and build.py fails if any file changes. V2_REPORT_PACKAGES names the textures, whitespace separated
("/Game/BelmonteTrain/Source/SM_BT_Tender/LOD0/T_BT_Crest ..."); V2_REPORT_OUT names the JSON file, which must lie outside
games/yorimichi_v2.

Each row is keyed by the texture's package path:
  srgb              the sRGB flag (true or false)
  compression       the compression setting's name, e.g. TC_Default
  lod_group         the LOD group's name, e.g. TEXTUREGROUP_World
  address_x         the X address mode's name, e.g. TA_Wrap
  address_y         the Y address mode's name
  error             present only when that texture could not be read; the other rows are still written
"""
import json
import os

import unreal as U

MARKER = 'V2 TEXTURES REPORTED'
EAL = U.EditorAssetLibrary


def split_packages(text):
    """Pure: V2_REPORT_PACKAGES is a whitespace-separated list of package paths."""
    return text.split()


GAME = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))


def report_target(target, game=GAME):
    """Pure: the resolved output path, refused inside the game tree (a claim-free read must not write a tracked file or a
    Content package; yorimichi-v2-single-writer). Symlinks are resolved first, so a link that points into the tree is
    refused too."""
    resolved = os.path.realpath(os.path.abspath(target))
    root = os.path.realpath(game)
    if resolved == root or resolved.startswith(root + os.sep):
        raise ValueError(f'V2_REPORT_OUT {target!r} lies inside {root}; write the report outside the game tree')
    return resolved


def check_coverage(report, expected):
    """Pure: the expected packages that have no row, and the rows that carry an error. Nothing else is judged."""
    missing = sorted(p for p in expected if p not in report)
    failed = sorted(p for p, row in report.items() if 'error' in row)
    return missing, failed


def enum_name(value):
    """Pure: an enum's bare name. The editor's text is "<Type.NAME: index>" (or "Type.NAME", or "Type::NAME"), and the
    name is what remains once the type, the index and the brackets are dropped."""
    return str(value).lstrip('<').split(':')[0].split('.')[-1].split('::')[-1].strip(' >')


def row(texture):
    """The settings of one texture (sRGB, max size, compression, LOD group, address modes), read through its accessors."""
    return dict(srgb=bool(texture.get_editor_property('srgb')),
                max_texture_size=int(texture.get_editor_property('max_texture_size')),
                compression=enum_name(texture.get_editor_property('compression_settings')),
                lod_group=enum_name(texture.get_editor_property('lod_group')),
                address_x=enum_name(texture.get_editor_property('address_x')),
                address_y=enum_name(texture.get_editor_property('address_y')))


def report(path):
    texture = EAL.load_asset(path)
    if not isinstance(texture, U.Texture2D):
        return {'error': f'not a Texture2D: {path}'}
    return row(texture)


def main():
    target = report_target(os.environ['V2_REPORT_OUT'])   # refused before anything is read or opened
    packages = split_packages(os.environ['V2_REPORT_PACKAGES'])
    out = {}
    for path in packages:
        try:   # one unreadable texture is reported, not fatal to the rest
            out[path] = report(path)
        except Exception as exc:
            out[path] = {'error': repr(exc)}
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, 'w') as f:
        json.dump(out, f, indent=1, sort_keys=True)
    missing, failed = check_coverage(out, packages)
    U.log(f'{MARKER} {len(out)} rows missing={len(missing)} errors={len(failed)}')


if __name__ == '__main__':
    main()
