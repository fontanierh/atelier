"""Inspect UE snapshot task requests; no UAT, Zen or game build is started."""
import json
from pathlib import Path
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import pytest

from atelier import checkpoint_zen as zen
from atelier.checkpoint_store import CheckpointError


def test_export_uses_file_snapshot_with_embedded_cook_state_not_a_cook(tmp_path):
    ctx = SimpleNamespace(uproject=tmp_path / 'Fixture.uproject')
    xml = zen.graph(ctx, 'export', tmp_path / 'files', tmp_path / 'descriptor.json')
    root = ET.fromstring(xml)
    task, = root.findall('.//{*}ZenExportSnapshot')
    assert task.attrib['DestinationStorageType'] == 'File'
    assert task.attrib['DestinationFileName'] == 'cook'
    assert not root.findall('.//{*}Cook') and not root.findall('.//{*}Compile')


def test_import_relocates_only_descriptor_location_and_requires_receiver_store(tmp_path, monkeypatch):
    project = tmp_path / 'unreal/Fixture.uproject'
    ctx = SimpleNamespace(uproject=project, out=tmp_path / 'build', logs=tmp_path / 'build/logs')
    folder = ctx.out / '.state/checkpoint-zen'; folder.mkdir(parents=True)
    value = {'snapshots': [dict(type='file', targetplatform='Mac', filename='cook', directory='producer') ]}
    (folder / 'descriptor.json').write_text(json.dumps(value))
    requests = []
    def transfer(ctx, operation, output, descriptor):
        requests.append((operation, json.loads(descriptor.read_text())))
        store = project.parent / 'Saved/Cooked/Mac/ue.projectstore'
        store.parent.mkdir(parents=True)
        store.write_text('receiver Zen identity')
    monkeypatch.setattr(zen, 'run', transfer)
    assert set(zen.import_(ctx)) == {'cooked/Mac/ue.projectstore'}
    assert requests[0][0] == 'import'
    assert requests[0][1]['snapshots'][0]['directory'] == str(folder)
    assert json.loads((folder / 'descriptor.json').read_text()) == value


def test_import_refuses_foreign_snapshot_backends(tmp_path):
    ctx = SimpleNamespace(out=tmp_path)
    folder = tmp_path / '.state/checkpoint-zen'; folder.mkdir(parents=True)
    (folder / 'descriptor.json').write_text(json.dumps({'snapshots': [dict(type='cloud', targetplatform='Mac')]}))
    with pytest.raises(CheckpointError, match='Unsupported'):
        zen.import_(ctx)


def test_import_cli_keeps_paths_with_spaces_as_single_arguments(tmp_path, monkeypatch):
    ctx = SimpleNamespace(uproject=tmp_path / 'Game Space/Fixture.uproject', unreal_root=tmp_path / 'Epic Games/UE_5.8',
                          logs=tmp_path / 'logs')
    commands = []
    monkeypatch.setattr(zen, 'run_command', lambda ctx, operation, command: commands.append(command))
    zen.run(ctx, 'import', tmp_path / 'snapshot files', tmp_path / 'descriptor.json')
    assert len(commands) == 4
    assert commands[1][1:4] == ['project-create', '--force-update', commands[1][3]]
    assert str(ctx.unreal_root) in commands[1] and str(ctx.uproject) in commands[1]
    assert commands[-1][-4:] == ['--file', str(tmp_path / 'snapshot files'), '--name', 'cook']
