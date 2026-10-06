"""The art tools' image helpers all go through atelier.ai.images, with the same model, size and key as before."""
import importlib.util
from pathlib import Path

import pytest

from atelier.ai import images

GAME = Path(__file__).resolve().parents[1]
TOOLS = GAME / 'assets' / 'characters' / 'tools'
CLIENTS = {'spirit_concepts': TOOLS / 'spirit_concepts.py', 'cairo_back_concepts': TOOLS / 'cairo_back_concepts.py',
           'hidamari_lab': GAME / 'world' / 'regions' / 'hidamari' / 'kit' / 'lab.py'}


def load(name, monkeypatch):
    path = CLIENTS[name]
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location(f'{name}_client_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('name', sorted(CLIENTS))
def test_gpt_edit_delegates_to_the_shared_client(name, monkeypatch):
    module = load(name, monkeypatch)
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')
    calls = []

    def sunburst(prompt, size, refs, n, **options):
        calls.append((prompt, size, refs, n, options))
        return [b'png'] * n, {'data': [{}] * n}, 1.5
    monkeypatch.setattr(images, 'sunburst', sunburst)
    prompt = 'the style only; do not draw Cairo; a new character'
    result = module.gpt_edit(prompt, ['ref.png'], 2)
    assert result[0] == [b'png', b'png']
    (sent, size, refs, n, options), = calls
    assert (sent, refs, n) == (prompt, ['ref.png'], 2)
    assert options == {'model': 'gpt-image-2.5-sunburst', 'quality': 'high', 'key': 'sk-test'}
    assert size == getattr(module, 'SIZE', '1536x1024')


def test_the_lab_ends_cleanly_when_the_request_fails(monkeypatch):
    lab = load('hidamari_lab', monkeypatch)
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test')

    def timeout(*args, **kwargs):
        raise TimeoutError('read timed out')
    monkeypatch.setattr(images, 'sunburst', timeout)
    with pytest.raises(SystemExit, match='gpt-image error: TimeoutError'):
        lab.gpt_edit('p', [], 1)
