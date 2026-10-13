"""The isolated Nox import must load the helper and the type it persists on the mesh."""
import json

from atelier import build, unreal_modules


def test_nox_isolation_loads_contact_types_without_gameplay_plugins(tmp_path, monkeypatch):
    ctx = build.Context('yorimichi')
    steps = build.load_recipe('yorimichi').steps(ctx)
    nox = next(s for s in steps if s.name == 'unreal.nox')
    command, = nox.commands

    # Reproduce the native failure's linkage: neither small import library links
    # AtelierCore. The recipe must request it explicitly, while Skate stays out.
    project = tmp_path / 'Yorimichi.uproject'
    plugins = tmp_path / 'Plugins'
    for name in ('AtelierCore', 'Skate'):
        folder = plugins / name
        folder.mkdir(parents=True)
        (folder / (name + '.uplugin')).write_text(json.dumps({'Modules': [{'Name': name}]}))
    project.write_text(json.dumps({
        'Modules': [{'Name': name} for name in ('YorimichiImport', 'YorimichiAssets')],
        'Plugins': [{'Name': name, 'Enabled': True} for name in ('AtelierCore', 'Skate')],
    }))
    built = {name: name + '.dylib' for name in ('YorimichiImport', 'YorimichiAssets', 'AtelierCore', 'Skate')}
    monkeypatch.setattr(unreal_modules, 'project_modules', lambda folder: built)
    monkeypatch.setattr(unreal_modules, 'linked', lambda folder, name: set())
    with unreal_modules.descriptor(project, command.modules) as (isolated, excluded):
        enabled = {p['Name'] for p in json.loads(isolated.read_text())['Plugins'] if p.get('Enabled', True)}
        assert 'AtelierCore' in enabled
        assert 'Skate' not in enabled
        assert not any(path.endswith('AtelierCore.dylib') for path in excluded)
        assert any(path.endswith('Skate.dylib') for path in excluded)

    # The same helper's compiled digest must be built before import and must
    # invalidate a cached import when its capture format or saved type changes.
    ordered = [s.name for s in build.order(steps, ['unreal.nox'])]
    contact = 'unreal.module.AtelierCore'
    assert ordered.index('unreal.compile') < ordered.index(contact) < ordered.index('unreal.nox')
    first = build.fingerprint(nox, {contact: 'first contact type'})
    assert build.fingerprint(nox, {contact: 'changed contact type'}) != first
