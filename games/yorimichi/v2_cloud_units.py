"""Two exact package owners for the original crater cap-cloud materials."""
from pathlib import Path

from v2_texture_units import SIDECARS, Unsupported, _code

SCRIPT = 'games/yorimichi/world/cloud_v2.py'
SCRIPTS = 'games/yorimichi/unreal/Scripts/'
ORIGINAL = SCRIPTS + 'crater_cloud_material.py'
SAVE = 'platform/studio/atelier/native_packages.py'
FOLDER = '/Game/CraterPark/Cloud'
NAMES = ('M_CraterCloud', 'M_CraterCloudVeil')


def author_units(rows, *, checkout, natives=None):
    """@cc [owner:fontanierh,label:correctness] crater-cloud-individual-owners
    The original unreal.crater_cloud declaration MUST own both exact Material
    packages before its alias is published. Each job MUST key the original graph,
    atmosphere/sea look closure and native save, with complete checkout sidecars.
    No original top-level/main, generated discovery or native asset fallback MAY run.
    """
    selected = [row for row in rows if row['id'] == 'unreal.crater_cloud']
    result = {'units': [], 'staged_inputs': {}, 'content_slots': {}, 'packages': {}, 'aliases': {}}
    if not selected:
        return result
    if len(selected) != 1:
        raise Unsupported('duplicate crater cloud producer')
    row = selected[0]
    expected = ['games/yorimichi/unreal/Content/CraterPark/Cloud/' + name + '.uasset' for name in NAMES]
    commands = row['commands']
    if (row['outputs'] != expected or len(commands) != 1 or commands[0].get('kind') != 'UnrealScript'
            or commands[0].get('script') != {'path': ORIGINAL}
            or commands[0].get('marker') != 'CRATER CLOUD MATERIAL COMPLETE'
            or commands[0].get('null_rhi') is not False or commands[0].get('env') not in ([], ())
            or commands[0].get('args') not in ([], ()) or commands[0].get('modules') not in ([], ())):
        raise Unsupported('crater cloud must match its exact original command and two packages')
    root = Path(checkout)
    code = sorted({*_code(root), SCRIPT, ORIGINAL, SAVE, SCRIPTS + 'atmosphere.py', SCRIPTS + 'sea_look.py'})
    for path in code:
        source = root / path
        if source.is_symlink() or not source.is_file():
            raise Unsupported('missing or linked crater cloud keyed code: ' + path)
    for name in NAMES:
        package = FOLDER + '/' + name
        stem = package.removeprefix('/Game/')
        unit_id = 'unreal.crater_cloud.material.' + name
        output = {'id': 'asset', 'logical_path': package, 'class': 'Material', 'destination': 'checkout',
                  'files': [{'path': 'content/Game/' + stem + suffix,
                             'install_path': 'games/yorimichi/unreal/Content/' + stem + suffix,
                             'required': suffix == '.uasset'} for suffix in SIDECARS]}
        result['units'].append({'id': unit_id, 'op': {'kind': 'unreal.author', 'version': '1'},
                                'script': SCRIPT, 'code': code, 'inputs': [],
                                'params': {'args': {'asset': name}, 'settings': []}, 'outputs': [output]})
        result['staged_inputs'][unit_id] = {}
        result['packages'][package] = {'unit': unit_id, 'item': 'asset', 'package': package}
    result['aliases']['unreal.crater_cloud'] = [unit['id'] for unit in result['units']]
    return result
