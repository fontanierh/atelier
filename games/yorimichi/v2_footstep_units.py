"""Author the footstep attenuation and FootstepSet owners over the finished per-surface footstep waves.

Scripts/import_footsteps.py builds three things: the waves (owned by v2_audio_templates' raw_import/finish
followers), the shared A_Footstep attenuation and the DA_Footsteps UJapanFootstepSet over every surface's waves.
This module declares the last two as C3 author units. Each surface's wave roster is generated (sliced), so it
arrives as that surface's unresolved derived_items token from v2_audio_templates and is expanded before keying;
nothing here scans a generated folder.
"""
import json
from pathlib import Path

from v2_audio_templates import cue_settings
from v2_texture_units import SIDECARS, Unsupported, _code

GAME = 'games/yorimichi'
SCRIPT = GAME + '/world/footsteps_v2.py'
ORIGINAL = GAME + '/unreal/Scripts/import_footsteps.py'
SAVE = 'platform/studio/atelier/native_packages.py'
CONTENT = GAME + '/unreal/Content'
DEST = '/Game/Japan/Audio'
ATTENUATION = DEST + '/A_Footstep'
LIBRARY = DEST + '/DA_Footsteps'
ATTENUATION_UNIT = 'unreal.footsteps.attenuation'
LIBRARY_UNIT = 'unreal.footsteps.library'


def _token(surface):
    """The exact finished-wave token v2_audio_templates publishes for one footstep surface."""
    return {'derived_items': {'templates': [{'producer': 'audio.footsteps.files.' + surface, 'group': 'waves',
                                             'unit_prefix': 'unreal.sound.raw.footsteps.' + surface, 'follower': 0,
                                             'item': 'sound'}],
                              'root': 'build/v2-derived/audio/footsteps/' + surface}}


def _outputs(package, cls):
    relative = package.removeprefix('/Game/')
    files = [{'path': 'content/Game/' + relative + suffix, 'install_path': CONTENT + '/' + relative + suffix,
              'required': suffix == '.uasset'} for suffix in SIDECARS]
    return [{'id': 'asset', 'logical_path': package, 'class': cls, 'destination': 'checkout', 'files': files}]


def _yorimichi(checkout):
    project = json.loads((Path(checkout) / GAME / 'unreal/Yorimichi.uproject').read_text())
    module, = [m for m in project['Modules'] if m['Name'] == 'Yorimichi']
    return {'name': module['Name'], 'kind': module['Type'], 'loading_phase': module['LoadingPhase']}


def author_units(*, checkout, waves):
    """@cc [owner:fontanierh,label:correctness] footstep-native-owners
    A_Footstep MUST be authored by the original build_attenuation over the original
    settings. DA_Footsteps MUST bind each of the original's surfaces to exactly that
    surface's finished Sound Items, through the unresolved derived_items token the
    wave templates publish, plus the original MATERIAL_SURFACES, grass default and
    leaves canopy. Neither MAY scan generated waves, run the original top level, or
    claim the whole unreal.sounds target.
    """
    root = Path(checkout)
    surfaces = sorted(cue_settings('audio.footsteps', checkout=root))
    if not isinstance(waves, dict) or sorted(waves) != surfaces:
        raise Unsupported('footstep library needs exactly the surfaces ' + ', '.join(surfaces))
    if not {'grass', 'leaves'} <= set(surfaces):
        raise Unsupported('footstep library needs its default grass and canopy leaves surfaces')
    for surface in surfaces:
        if waves[surface] != _token(surface):
            raise Unsupported(f'footstep surface {surface} must be its finished wave derived_items token')
    from atelier.source_imports import ImportScanner
    found = ImportScanner().local_imports(root / SAVE, (root / 'platform/studio',))
    code = sorted({*_code(root), SCRIPT, ORIGINAL, *(p.relative_to(root).as_posix() for p in found)})
    attenuation = {'id': ATTENUATION_UNIT, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT,
                   'code': code, 'inputs': [],
                   'params': {'args': {'action': 'attenuation'}, 'settings': []},
                   'outputs': _outputs(ATTENUATION, 'SoundAttenuation')}
    library = {'id': LIBRARY_UNIT, 'op': {'kind': 'unreal.author', 'version': '1'}, 'script': SCRIPT, 'code': code,
               'inputs': [{'role': 'content', 'name': 'attenuation',
                           'source': {'kind': 'item', 'unit': ATTENUATION_UNIT, 'item': 'asset'}}],
               'params': {'args': {'action': 'library', 'attenuation': 'attenuation',
                                   'surfaces': {surface: _token(surface) for surface in surfaces}},
                          'settings': []},
               'outputs': _outputs(LIBRARY, 'DataAsset')}
    units = [attenuation, library]
    return {'units': units,
            'staged_inputs': {unit['id']: {row['name']: 'inputs/' + row['name'] for row in unit['inputs']} for unit in units},
            'content_slots': {'attenuation': False},
            'packages': {ATTENUATION: {'unit': ATTENUATION_UNIT, 'item': 'asset', 'package': ATTENUATION},
                         LIBRARY: {'unit': LIBRARY_UNIT, 'item': 'asset', 'package': LIBRARY,
                                   'dependencies': [{'unit': ATTENUATION_UNIT, 'item': 'asset', 'package': ATTENUATION}],
                                   'derived_dependencies': {surface: _token(surface) for surface in surfaces}}},
            'module_requirements': {LIBRARY_UNIT: [_yorimichi(root)]},
            'closes': [ATTENUATION, LIBRARY], 'aliases': {}}
