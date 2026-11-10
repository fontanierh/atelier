"""@cc [owner:fontanierh,label:correctness] yorimichi-v2-single-writer
The material instances of the small families, planned on main's per-package instance form (material-instance v2, as
belmontetrain_materials.py writes it): for each instance, what its generator script sets, compared with the committed
editor read (docs/inventory/small-families-reads/instances/<family>.json). Only an instance whose stated values agree is
planned; a stated value the read does not show, or a differing one, holds the instance.

    expected(family, donor)   what the generator writes, from the donor (script and build data, read only)
    agreement(...)            per package: agree, or the reasons it is held
    records(...)              the material-instance records for the agreeing packages (plan; nothing is written here)

Switches are stated only where a parent's switch differs from the read; none of these instances' reads shows one, so no
row states a switch. The two Mega Park natural instances keep their two-sided base-property override, which recipe v2
cannot state, so they are held and stay in their adopted record.
"""
from __future__ import annotations

import json
from pathlib import Path

GAME = Path(__file__).resolve().parents[2]
READS = GAME / 'docs/inventory/small-families-reads/instances'
MEGA_PARENTS = ['M_RetailOpaque', 'M_RetailMasked', 'M_RetailTranslucent']   # import_megapark.py:76
MEGA_ALIAS = {'diffuse': 'Diffuse', 'decal': 'Decal', 'macrooverlay': 'Macro', 'lightmap': 'Lightmap',
              'normal': 'Normal', 'detail': 'Detail', 'specular': 'Specular', 'transparent': 'Transparent'}   # :182-183
MEGA_DEFAULTS = {'Diffuse': 'T_DefaultWhite', 'Decal': 'T_DefaultWhite', 'Macro': 'T_DefaultWhite',
                 'Lightmap': 'T_DefaultLinear', 'Normal': 'T_DefaultNormal', 'Detail': 'T_DefaultNormal',
                 'Specular': 'T_DefaultBlack', 'Transparent': 'T_DefaultWhite'}                                   # :184-186
MEGA_MOSSY = {'0x2c70170a001d0133', '0x2c70170a001d0135', '0x2c70170a001d014f'}                                  # :23
MEGA_NATURAL = MEGA_MOSSY | {'0x2c70170a001d00aa', '0x2c70170a00040094'}                                         # :28-29
TREE_GLOW = {'glass': .3}     # import_treehouse.py:32 (the other GLOW entries are for slugs this family does not use)
HID_STRENGTH = {'flat': 0.}   # city_material.py:23
HID_MACRO = {'flat': 0.}      # city_material.py:25-26

class InstanceError(RuntimeError):
    pass


def _load(path: Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as error:
        raise InstanceError(f'{path}: {error}') from None


def _tex(tid: str) -> str:
    return f'/Game/MegaPark/Textures/T_{tid[2:]}'


def expected_megapark(donor: Path) -> dict:
    """The Mega Park instance rows import_megapark.py:166-221 writes, from the donor's build report and restyle data."""
    build = _load(donor / 'build/yorimichi/megapark/build.json')['materials']
    restyle = _load(donor / 'build/yorimichi/megapark/textures/textures.json')['lightmaps']
    out = {}
    for key, p in build.items():
        name = 'MI_' + key[2:]
        channels = p.get('retail_texture_ids', {})
        params = p.get('retail_parameters', {})

        def number(param, default):
            try:
                return float(params[param][0])
            except (KeyError, ValueError, TypeError, IndexError):
                return default
        textures = {}
        for role, param in MEGA_ALIAS.items():
            textures[param] = _tex(channels[role]) if role in channels else f'/Game/MegaPark/Textures/{MEGA_DEFAULTS[param]}'
        scalars = {'MacroScale': number('macroOverlayUVScale', 1.), 'DetailScale': number('detailNormalUVScale', 1.),
                   'MacroOpacity': number('macroOverlayOpacity', 0.) if 'macrooverlay' in channels else 0.,
                   'UseDecal': float('decal' in channels), 'HasLightmap': float('lightmap' in channels),
                   'HasTransparent': float('transparent' in channels),
                   'LightmapNorm': restyle.get(channels.get('lightmap'), 3.),
                   'Moss': float(channels.get('diffuse') in MEGA_MOSSY)}
        if p.get('seam'):
            scalars.update(SpecularScale=0., Gloss=0., LightmapOcclusion=.25)
        natural = p.get('alpha_mode', 0) == 0 and channels.get('diffuse') in MEGA_NATURAL
        out[f'/Game/MegaPark/Materials/{name}'] = {
            'parent': f'/Game/MegaPark/Materials/{MEGA_PARENTS[int(p.get("alpha_mode", 0))]}',
            'textures': textures, 'scalars': scalars, 'vectors': {}, 'natural': natural, 'seam': bool(p.get('seam'))}
    return out


def expected_belmonte(donor: Path) -> dict:
    """The Belmonte rows import_belmonte.py:160-182 writes, from the donor's material report (by instance name)."""
    entries = _load(donor / 'build/yorimichi/belmonte-materials/materials.json')
    entries = entries.get('materials', entries)
    rows = entries.values() if isinstance(entries, dict) else entries
    out = {}
    for e in rows:
        if not e.get('name', '').startswith('MI_BM_'):
            continue
        out[f'/Game/Belmonte/Materials/{e["name"]}'] = {
            'parent': '/Game/Belmonte/Materials/M_Belmonte',
            'textures': {} if e['texture'] is None else {'Tex': None},   # a textured row is held below
            'scalars': {'Tile': float(e['tile_m']), 'WhiteVertex': float(bool(e['white_vertex'])),
                        'Terrain': float(bool(e['terrain'])), 'Brightness': float(e['brightness']),
                        'Atlas': float(bool(e['atlas'])), 'Strength': float(e['texture'] is not None),
                        'Roughness': .25 if e['water'] else .87},
            'vectors': {'Colour': list(e['colour']), 'Tint': list(e['tint'])}, 'natural': False, 'seam': False}
    return out


def expected_treehouse(donor: Path) -> dict:
    """The tree house rows import_treehouse.py:254-260 writes: Tex, Gain (the texture's gain), Glow, and RoomCut 0 on the
    trunk. The pane has no texture and its script is not compared here."""
    info = _load(donor / 'build/yorimichi/treehouse/textures/textures.json')
    parent = '/Game/Japan/Treehouse/Materials/M_TreeHouse'
    out = {}
    for slug in ('flat', 'glass', 'rope'):
        out[f'/Game/Japan/Treehouse/Materials/MI_TH_{slug}'] = {
            'parent': parent, 'textures': {'Tex': f'/Game/Japan/Treehouse/Textures/T_TH_{slug}'},
            'scalars': {'Gain': float(info[slug]['gain']), 'Glow': float(TREE_GLOW.get(slug, 0.))}, 'vectors': {},
            'natural': False, 'seam': False}
    out['/Game/Japan/Treehouse/Materials/MI_TH_trunk'] = {
        'parent': parent, 'textures': {'Tex': '/Game/Japan/Treehouse/Textures/T_TH_bark'},
        'scalars': {'Gain': float(info['bark']['gain']), 'Glow': 0., 'RoomCut': 0.}, 'vectors': {},
        'natural': False, 'seam': False}
    return out


def expected_hidamari(donor: Path) -> dict:
    """city_material.py:116-117: MI_HD_flat, Tex the plaster, Tile 1, Gain 1, Strength and Macro from the flat tables."""
    return {'/Game/Japan/Hidamari/Materials/MI_HD_flat': {
        'parent': '/Game/Japan/Hidamari/Materials/M_HDCity', 'textures': {'Tex': '/Game/Japan/Hidamari/Textures/T_HD_plaster'},
        'scalars': {'Tile': 1., 'Gain': 1., 'Strength': HID_STRENGTH['flat'], 'Macro': HID_MACRO['flat']},
        'vectors': {}, 'natural': False, 'seam': False}}


FX_PARENTS = {'MI_FX_Glow': ('M_FX_Additive', 'Glow'), 'MI_FX_Spark': ('M_FX_Additive', 'Spark'),
              'MI_FX_Ring': ('M_FX_Additive', 'Ring'), 'MI_FX_Dust': ('M_FX_Dust', 'Dust')}   # import_combat_fx.py:84-85


def expected_fx(donor: Path) -> dict:
    return {f'/Game/FX/{name}': {'parent': f'/Game/FX/{parent}', 'textures': {'Sprite': f'/Game/FX/Textures/T_FX_{tex}'},
                                 'scalars': {}, 'vectors': {}, 'natural': False, 'seam': False}
            for name, (parent, tex) in FX_PARENTS.items()}


EXPECTED = {'megapark': expected_megapark, 'belmonte': expected_belmonte, 'treehouse': expected_treehouse,
            'hidamari': expected_hidamari, 'fx': expected_fx}
READ_FILE = {'megapark': 'megapark', 'belmonte': 'belmonte', 'treehouse': 'treehouse', 'hidamari': 'hidamari', 'fx': 'fx'}


def _package(path: str) -> str:
    """An object path's package (the path up to its first '.'), compared whole."""
    return path.split('.')[0]


def _close(a, b, tol=1e-2):
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def agreement(family: str, donor: Path) -> dict:
    """package -> {'agree': bool, 'held': [reasons]} for every instance the generator names in this family."""
    read = _load(READS / f'{READ_FILE[family]}.json')
    expected = EXPECTED[family](donor)
    out = {}
    for package, row in read.items():   # the family's own instances: the rows of the read, not the whole donor report
        if 'error' in row:
            out[package] = {'agree': False, 'held': ['the read could not read this instance']}
            continue
        if package not in expected:
            out[package] = {'agree': False, 'held': ['the generator does not name this instance']}
            continue
        want = expected[package]
        held = []
        eff = row.get('effective', {})
        if _package(row['parent']) != _package(want['parent']):   # the full package path, not just its name
            held.append(f'parent {row["parent"]} is not {want["parent"]}')
        # Every stated value needs read evidence: the effective value, or the package's own stored override (an
        # opaque Mega Park instance stores HasTransparent although its parent declares no such parameter).
        own = row.get('overrides', {})
        for name, value in want['scalars'].items():
            got = eff.get('scalar', {}).get(name, own.get('scalar', {}).get(name))
            if got is None:
                held.append(f'scalar {name} is stated but the read does not show it')
            elif not _close(got, value):
                held.append(f'scalar {name} reads {got}, not {round(value, 4)}')
        for name, value in want['vectors'].items():
            got = eff.get('vector', {}).get(name, own.get('vector', {}).get(name))
            if got is None:
                held.append(f'vector {name} is stated but the read does not show it')
            elif len(got) != len(value) or any(not _close(g, v, 1e-3) for g, v in zip(got, value)):   # alpha too
                held.append(f'vector {name} reads {got}, not {value}')
        for name, package_path in want['textures'].items():
            if package_path is None:
                continue
            got = eff.get('texture', {}).get(name)
            if got is None or _package(got) != _package(package_path):
                held.append(f'texture {name} reads {got}, not {package_path}')
        if family == 'belmonte' and want['textures'] and any(v is None for v in want['textures'].values()):
            held.append('a textured Belmonte row: its texture is not yet mapped to a package')
        if family == 'megapark' and want['natural']:
            held.append('a two-sided base-property override (recipe v2 cannot state it)')
        out[package] = {'agree': not held, 'held': held}
    return out
