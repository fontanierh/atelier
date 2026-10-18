"""Pinned audio admission must reject source/tool mutation and arbitrary commands."""
from dataclasses import asdict, FrozenInstanceError, replace
import json
from pathlib import Path
import sys
import wave

import pytest

from atelier.harness import ffmpeg_audio as audio


@pytest.fixture
def command(tmp_path,monkeypatch):
    tool=tmp_path/'ffmpeg';tool.write_text('fixture executable');tool.chmod(0o700)
    monkeypatch.setattr(audio,'REVIEWED_EXECUTABLES',frozenset({audio.digest(tool)}))
    source=tmp_path/'input.wav'
    with wave.open(str(source),'wb') as handle:
        handle.setparams((1,2,48000,0,'NONE','not compressed'));handle.writeframes(b'\1\0'*4800)
    return audio.Command.create(tool,source,tmp_path/'output.m4a',mode='encode',output_dir=tmp_path)


def test_only_fixed_pinned_literal_audio_can_select_workers(command):
    assert audio.workers(command)==4
    assert audio.workers(list(command)) is None
    assert audio.workers([sys.executable,'arbitrary.py']) is None
    with pytest.raises(FrozenInstanceError):command.mode='arbitrary'
    assert '-hwaccel' not in command and command.argv.count('-i')==1
    assert command[command.argv.index('-protocol_whitelist')+1]=='file'


@pytest.mark.parametrize('change',['tool','input','output','format'])
def test_pins_and_new_output_are_rechecked(command,change):
    if change=='tool':Path(command.executable).write_text('changed executable')
    if change=='input':Path(command.source).write_bytes(b'changed')
    if change=='output':Path(command.output).write_bytes(b'occupied')
    if change=='format':command=replace(command,mode='hardware')
    with pytest.raises(ValueError):audio.workers(command)


def test_exec_rechecks_original_pins_before_any_tool_execution(command,monkeypatch):
    from atelier.harness import ffmpeg_audio_exec as entry
    monkeypatch.setattr(sys,'argv',['entry',json.dumps(asdict(command))])
    called=[];monkeypatch.setattr(entry.os,'execve',lambda *args:called.append(args))
    Path(command.source).write_bytes(b'replaced before GO')
    with pytest.raises(ValueError):entry.main()
    assert called==[]


def test_exec_uses_exact_args_and_bounded_environment(command,monkeypatch):
    from atelier.harness import ffmpeg_audio_exec as entry
    monkeypatch.setattr(sys,'argv',['entry',json.dumps(asdict(command))])
    monkeypatch.setenv('OMP_NUM_THREADS','8')
    monkeypatch.setenv('DYLD_INSERT_LIBRARIES','unreviewed.dylib')
    monkeypatch.setenv('LD_PRELOAD','unreviewed.so')
    called=[];monkeypatch.setattr(entry.os,'execve',lambda *args:called.append(args))
    entry.main()
    tool,argv,env=called[0]
    assert tool==command.executable and argv==list(command)
    assert 'DYLD_INSERT_LIBRARIES' not in env and 'LD_PRELOAD' not in env
    assert all(env[name]=='1' for name in audio.WORKER_ENV)


def test_oversized_input_fails_before_hashing(tmp_path,monkeypatch):
    tool=tmp_path/'ffmpeg';tool.write_bytes(b'fixture');source=tmp_path/'input.wav'
    with source.open('wb') as handle:handle.truncate(2*1024**2)
    monkeypatch.setattr(audio,'digest',lambda path:pytest.fail('Oversized input must not be hashed'))
    with pytest.raises(ValueError,match='byte budget'):
        audio.Command.create(tool,source,tmp_path/'out.m4a',mode='encode',output_dir=tmp_path)


def test_unreviewed_binary_keeps_unknown_profile(command, monkeypatch):
    monkeypatch.setattr(audio, 'REVIEWED_EXECUTABLES', frozenset())
    assert audio.workers(command) is None
    command.verify()  # Still usable through full exclusive admission.


def test_output_directory_cannot_be_rebound_or_escaped(command, tmp_path):
    other = tmp_path / 'other'
    other.mkdir()
    with pytest.raises(ValueError, match='declared directory'):
        replace(command, output=str(other / 'out.m4a')).verify()
    with pytest.raises(ValueError, match='declared directory'):
        replace(command, output_dir_identity=(0, 0)).verify()


def test_playlist_bytes_are_never_demuxed_by_auto_detection(command, tmp_path):
    playlist = tmp_path / 'playlist.m4a'
    playlist.write_text('ffconcat version 1.0\nfile secret.wav\n')
    decode = audio.Command.create(command.executable, playlist, tmp_path / 'decoded.f32',
                                  mode='decode', output_dir=tmp_path)
    args = decode.argv
    assert args[args.index('-f') + 1] == 'mov'
    assert args.index('-f') < args.index('-i')
    assert args[args.index('-t') + 1] == '8'
    assert command.argv[command.argv.index('-f') + 1] == 'wav'
