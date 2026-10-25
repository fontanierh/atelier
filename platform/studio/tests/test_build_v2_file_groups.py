"""Ordinary file groups copy exact completed payloads; no native execution."""
import hashlib
import json

import pytest
from atelier.build_v2.file_groups import write_file_set


def test_actual_temp_wav_fbx_png_set_has_exact_selected_bytes_and_metadata(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    files = {'Sound.wav': b'RIFF\x00\x00\x00\x00WAVE', 'Walk.fbx': b'Kaydara FBX Binary  \x00',
             'Picture.png': b'\x89PNG\r\n\x1a\n'}
    for name, data in files.items(): (source / name).write_bytes(data)
    (source / 'producer.json').write_text('{}')
    output = tmp_path / 'output'
    value = write_file_set(source, output, parent='Media', selectors=['*.wav', '*.fbx', '*.png'],
                           metadata={name.rsplit('.', 1)[0]: {'role': name.rsplit('.', 1)[1]} for name in files})
    assert value == json.loads((output / 'plan.json').read_bytes())
    assert set(p.name for p in output.iterdir()) == {'plan.json', *files}
    assert 'source_triangles' not in value
    for row in value['pieces']:
        assert (output / row['payload']).read_bytes() == files[row['payload']]
        assert row['sha256'] == hashlib.sha256(files[row['payload']]).hexdigest()
    assert (source / 'producer.json').read_text() == '{}'


def test_selected_file_projection_stays_independent_of_siblings(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    (source / 'A.wav').write_bytes(b'A'); (source / 'B.wav').write_bytes(b'B')
    def emit(name):
        value = write_file_set(source, tmp_path / name, parent='Audio', selectors=['*.wav'])
        return {row['name']: row for row in value['pieces']}
    first = emit('first'); (source / 'B.wav').write_bytes(b'B2'); second = emit('second')
    assert first['A'] == second['A'] and first['B'] != second['B']
    (source / 'A.wav').write_bytes(b'A2'); third = emit('third')
    assert second['A'] != third['A'] and second['B'] == third['B']


@pytest.mark.parametrize('damage', ['alias', 'link', 'directory_alias', 'metadata', 'selector', 'budget'])
def test_unknown_alias_link_and_budget_refusals(tmp_path, damage):
    source = tmp_path / 'source'; source.mkdir(); (source / 'A.wav').write_bytes(b'WAVE')
    kwargs = {'selectors': ['*.wav']}
    if damage == 'alias':
        (source / 'other').mkdir(); (source / 'other/a.wav').write_bytes(b'other')
    elif damage == 'link': (source / 'link').symlink_to(source / 'A.wav')
    elif damage == 'directory_alias':
        (source / 'folder').mkdir(); (source / 'folder/A.wav').write_bytes(b'duplicate')
    elif damage == 'metadata': kwargs['metadata'] = {'A': []}
    elif damage == 'selector': kwargs['selectors'] = ['../*.wav']
    else: kwargs['limits'] = {'max_pieces': 10, 'max_manifest_bytes': 1, 'max_member_bytes': 2, 'max_total_bytes': 3}
    with pytest.raises(ValueError): write_file_set(source, tmp_path / 'output', parent='Audio', **kwargs)


def test_recipe_emit_suffix_abi_is_recursive_and_closed(tmp_path):
    from atelier.build_v2.file_groups import emit
    source = tmp_path / 'source'; (source / 'nested').mkdir(parents=True)
    (source / 'nested/Clip.wav').write_bytes(b'RIFF-WAVE')
    (source / 'metadata.json').write_text('{}')
    value = emit(source, tmp_path / 'output', parent='Audio', extensions=['.wav'])
    assert value['pieces'][0]['payload'] == 'Clip.wav'
    with pytest.raises(ValueError): emit(source, tmp_path / 'bad', parent='Audio', extensions=['../.wav'])
