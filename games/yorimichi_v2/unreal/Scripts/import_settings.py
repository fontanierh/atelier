"""Pure parsing of the optional recipe settings of import_asset.py (no Unreal import, so tests/test_import_settings.py runs them).

Every setting defaults to what the importer did before it existed, so a record that omits it imports identically:
- mesh `allow_cpu_access` (bool): absent leaves the flag as imported; `double_sided` (bool): absent keeps complex collision
  double-sided (the original behaviour);
- mesh `legacy_fbx` (bool): absent keeps the Interchange FBX import unless the record imports UCX hulls;
- mesh `collision_trace` (a CTF_USE_* name): absent leaves the flag the collision mode sets;
- texture `max_texture_size` (int, 0 = engine default) and `lod_group` (a TEXTUREGROUP_* name): absent leaves them as imported.
"""
import os

TEXTURE_GROUPS = {'TEXTUREGROUP_WORLD', 'TEXTUREGROUP_EFFECTS', 'TEXTUREGROUP_CHARACTER', 'TEXTUREGROUP_UI',
                  'TEXTUREGROUP_WORLD_NORMAL_MAP', 'TEXTUREGROUP_WORLD_SPECULAR'}


TRACE_FLAGS = {'CTF_USE_DEFAULT', 'CTF_USE_SIMPLE_AND_COMPLEX', 'CTF_USE_SIMPLE_AS_COMPLEX', 'CTF_USE_COMPLEX_AS_SIMPLE'}


class SettingError(RuntimeError):
    pass


def _flag(settings: dict, key: str):
    if key not in settings:
        return None
    if not isinstance(settings[key], bool):
        raise SettingError(f'{key} must be true or false, not {settings[key]!r}')
    return settings[key]


def allow_cpu_access(settings: dict):
    """True/False to set the mesh flag, None to leave it as imported."""
    return _flag(settings, 'allow_cpu_access')


def double_sided(settings: dict) -> bool:
    """Complex collision's double-sided geometry: True unless the record says false."""
    value = _flag(settings, 'double_sided')
    return True if value is None else value


def max_texture_size(settings: dict):
    """A positive size to set, or None to leave the texture as imported."""
    if 'max_texture_size' not in settings:
        return None
    value = settings['max_texture_size']
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0 or value & (value - 1):
        raise SettingError(f'max_texture_size must be a positive power of two, not {value!r}')
    return value


def lod_group(settings: dict):
    """The TEXTUREGROUP_* name to set, or None."""
    if 'lod_group' not in settings:
        return None
    value = settings['lod_group']
    if value not in TEXTURE_GROUPS:
        raise SettingError(f'unknown lod_group {value!r}')
    return value


def legacy_fbx(settings: dict) -> bool:
    """True to import an FBX through the legacy importer (the donor's, with Interchange off), which drops degenerate
    triangles that the Interchange importer keeps. UCX-hull records always use it; False when absent."""
    return bool(_flag(settings, 'legacy_fbx'))


def collision_trace(settings: dict):
    """The CTF_USE_* trace flag to set after the collision mode's own, or None."""
    if 'collision_trace' not in settings:
        return None
    value = settings['collision_trace']
    if value not in TRACE_FLAGS:
        raise SettingError(f'unknown collision_trace {value!r}')
    return value


def material_instances(settings: dict, packages: list) -> list:
    """Pure: one row {package, parent, textures, scalars, vectors} per planned package, from either recipe form. The single
    form gives every package the same values; the instances form gives each package its own row, and a package it does not
    name (or a row for a package not planned) is refused, so nothing is written from a guess."""
    if 'instances' in settings:
        rows = {row.get('package'): row for row in settings['instances']}
        missing = [p for p in packages if p not in rows]
        extra = sorted(set(rows) - set(packages))
        if missing or extra:
            raise SettingError(f'instances do not match the planned packages (missing {missing}, extra {extra})')
        source = rows
    else:
        source = {p: settings for p in packages}
    out = []
    for package in packages:
        values = source[package]
        if 'parent' not in values:
            raise SettingError(f'{package} names no parent')
        out.append(dict(package=package, parent=values['parent'], textures=dict(values.get('textures', {})),
                        scalars=dict(values.get('scalars', {})), vectors=dict(values.get('vectors', {})),
                        switches=dict(values.get('switches', {}))))
    return out


def donor_named(names, blank_folder: str, portable: str = '') -> list:
    """Pure: the absolute paths among the import-data names, other than the editor's working folder. A texture's import data
    keeps its repository-relative source (set by the portable-source step), which is not a donor path; an absolute one is.
    The editor reports that relative source resolved against its working folder, so that exact path is the portable source
    too, not a donor path."""
    blank = os.path.normpath(blank_folder)
    allowed = {blank} | ({os.path.normpath(os.path.join(blank_folder, portable))} if portable else set())
    return [name for name in names if name and os.path.isabs(name) and os.path.normpath(name) not in allowed]


def donor_free(names, blank_folder: str) -> list:
    """Pure: the import-data file names that still name something. A blanked entry (empty) or the editor's working folder
    (where a blanked file reads back) does not count, so an empty result means no donor path is left."""
    blank = os.path.normpath(blank_folder)
    return [name for name in names if name and os.path.normpath(name) != blank]


def reduction_plan(settings: dict):
    """Pure: the recipe's LOD reduction plan as [[percent, screen], ...] (LOD0 first), or None when the record names none.
    LOD0 keeps every triangle and screen 1; the rest are a fraction of the triangles at a smaller screen size, as the donor's
    generate_lods writes them. Anything else is refused, so a fresh import never takes an unknown plan."""
    plan = settings.get('lods')
    if plan is None:
        return None
    if not isinstance(plan, list) or not plan or any(not isinstance(row, list) or len(row) != 2 for row in plan):
        raise SettingError('lods must be a non-empty list of [percent, screen] pairs, LOD0 first')
    percents = [row[0] for row in plan]
    screens = [row[1] for row in plan]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in percents + screens):
        raise SettingError('lods values must be numbers')
    if percents[0] != 1 or screens[0] != 1 or any(not 0 < p <= 1 for p in percents):
        raise SettingError('lods LOD0 must be 100% at screen 1, and every level a fraction of the triangles')
    if any(b >= a for a, b in zip(screens, screens[1:])):
        raise SettingError('lods screen sizes must fall with each level')
    return [[float(p), float(q)] for p, q in plan]


def level_kind(source: str) -> str:
    """Pure: which importer a chain level or LOD0 file goes through: 'fbx' for an FBX, 'gltf' for a glTF or GLB."""
    lower = source.lower()
    if lower.endswith('.fbx'):
        return 'fbx'
    if lower.endswith(('.glb', '.gltf')):
        return 'gltf'
    raise SettingError(f'{source}: a chain level must be an FBX, a GLB or a glTF file')

