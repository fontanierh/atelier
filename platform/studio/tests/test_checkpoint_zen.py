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
