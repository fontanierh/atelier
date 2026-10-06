"""The curl image clients send the whole prompt and keep the API key out of argv.

curl's -F would cut a field at its first ';' and read the rest as attributes, and any argument is visible to ps.
"""
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

GAME = Path(__file__).resolve().parents[1]
CLIENTS = {'spirit_concepts': GAME / 'assets' / 'characters' / 'tools' / 'spirit_concepts.py',
           'hidamari_lab': GAME / 'world' / 'regions' / 'hidamari' / 'kit' / 'lab.py'}
KEY = 'sk-test-not-a-real-key'


@pytest.mark.parametrize('client', sorted(CLIENTS))
def test_the_prompt_is_sent_whole_and_the_key_stays_off_argv(client, monkeypatch, tmp_path):
    path = CLIENTS[client]
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location(f'{client}_upload_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv('OPENAI_API_KEY', KEY)
    sent = {}

    def run(cmd, **kwargs):
        sent['cmd'], sent['input'] = cmd, kwargs.get('input')
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({'data': []}), stderr='')
    monkeypatch.setattr(module.subprocess, 'run', run)
    prompt = 'the style only; do not draw Cairo; a new character'
    module.gpt_edit(prompt, [], 1)
    cmd = sent['cmd']
    field = f'prompt={prompt}'
    assert field in cmd and cmd[cmd.index(field) - 1] == '--form-string'
    assert not any(KEY in arg for arg in cmd)
    assert cmd[cmd.index('@-') - 1] == '-H' and sent['input'] == f'Authorization: Bearer {KEY}\n'
