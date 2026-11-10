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


def donor_named(names, blank_folder: str) -> list:
    """Pure: the absolute paths among the import-data names, other than the editor's working folder. A texture's import data
    keeps its repository-relative source (set by the portable-source step), which is not a donor path; an absolute one is."""
    blank = os.path.normpath(blank_folder)
    return [name for name in names if name and os.path.isabs(name) and os.path.normpath(name) != blank]


def donor_free(names, blank_folder: str) -> list:
    """Pure: the import-data file names that still name something. A blanked entry (empty) or the editor's working folder
    (where a blanked file reads back) does not count, so an empty result means no donor path is left."""
    blank = os.path.normpath(blank_folder)
    return [name for name in names if name and os.path.normpath(name) != blank]

