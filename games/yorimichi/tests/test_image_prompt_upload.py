"""The image helper sends the whole prompt: curl's -F would cut a field at its first ';' and read the rest as attributes."""
import importlib.util
import json
import subprocess
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / 'assets' / 'characters' / 'tools'


def test_a_prompt_with_semicolons_is_sent_whole(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(TOOLS))
    spec = importlib.util.spec_from_file_location('spirit_concepts_upload_test', TOOLS / 'spirit_concepts.py')
    sc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sc)
    monkeypatch.setenv('OPENAI_API_KEY', 'test')
    monkeypatch.setattr(sc, 'OUT', tmp_path)
    sent = {}

    def run(cmd, **kwargs):
        sent['cmd'] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({'data': []}), stderr='')
    monkeypatch.setattr(sc.subprocess, 'run', run)
    prompt = 'the style only; do not draw Cairo; a new character'
    sc.gpt_edit(prompt, [], 1)
    cmd = sent['cmd']
    field = f'prompt={prompt}'
    assert field in cmd and cmd[cmd.index(field) - 1] == '--form-string'
