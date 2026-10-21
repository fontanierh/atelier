"""The transport sound bank (assets/audio/transport) against its runtime, its seams, its levels and its sources.

Runs from the source tree with numpy only: no Unreal. The loops and the pure-synthesis one-shots are built into a
temporary folder; the cues layered on Sonniss masters are built too when the masters are fetched on this machine.
"""
import ast
import importlib.util
from pathlib import Path
import re
import tomllib
import wave

import numpy as np
import pytest

GAME = Path(__file__).resolve().parents[1]
BANK = GAME / 'assets/audio/transport'
SOURCE = GAME / 'unreal/Source/Yorimichi'
spec = importlib.util.spec_from_file_location('transport_make', BANK / 'make.py')
make = importlib.util.module_from_spec(spec)
spec.loader.exec_module(make)

MASTERS = {name for spec_ in make.CUES.values() for name in spec_['sonniss']}
FETCHED = all((make.SONNISS / name).is_file() for name in MASTERS)
# The bike's and the skateboard's built banks, measured on 2026-10-20 (peak dBFS; loudest 400 ms RMS dBFS):
# loops peak -9.1..-4.4, loudest -30.7..-16.3; one-shots peak -9.1..-1.4, loudest -33.5..-11.1.
LOOP_PEAK, LOOP_LOUDEST = (-9.5, -4.0), (-31., -16.)
SHOT_PEAK, SHOT_LOUDEST = (-9.5, -1.0), (-34., -11.)


@pytest.fixture(scope='module')
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp('audio') / 'transport'
    manifest = make.build(out, make.SONNISS if FETCHED else None)
    return out, manifest


def samples(path):
    with wave.open(str(path)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 48000), path
        return np.frombuffer(w.readframes(w.getnframes()), np.int16) / 32768.


def runtime_cues():
    text = (SOURCE / 'TransportAudio.cpp').read_text()
    loops = set(re.findall(r'\{TEXT\("((?:ferry|gondola|zeppelin)_\w+)"\),[\d.]+f,[\d.]+f\}', text))
    every = set(re.findall(r'TEXT\("((?:ferry|gondola|zeppelin)_\w+)"\)', text))
    return loops, every - loops


def test_bank_has_exactly_the_cues_the_runtime_plays():
    loops, shots = runtime_cues()
    assert loops == set(make.LOOPS)
    assert shots == {cue for cue, spec_ in make.CUES.items() if not spec_['loop']}
    # The importer loads the manifest's loops into the folder the components load from.
    importer = (GAME / 'unreal/Scripts/import_transport_audio.py').read_text()
    assert "DEST = '/Game/Audio/Transport'" in importer and "['loops']" in importer
    assert 'TEXT("/Game/Audio/Transport/%s.%s")' in (SOURCE / 'TransportAudio.cpp').read_text()


def test_build_runs_the_bank_and_imports_it():
    build = (GAME / 'build.py').read_text()
    assert "Step('audio.transport', [Python(AUDIO / 'transport' / 'make.py')]" in build
    assert "UnrealScript(SCRIPTS / 'import_transport_audio.py', 'TRANSPORT AUDIO IMPORT COMPLETE', modules=SAVED_TYPES)" in build
    assert "'audio.bike', 'audio.transport'], heavy=True" in build
    bank = tomllib.loads((BANK / 'bank.toml').read_text())
    assert bank == {'id': 'transport', 'needs': ['combat'], 'build': 'make.py',
                    'licence': 'Sonniss GDC bundles and own synthesis: may ship inside the game; no AI use'}


def test_zeppelin_engine_pitch_follows_the_service_rpm():
    service = (SOURCE / 'ZeppelinService.cpp').read_text() + (SOURCE / 'ZeppelinNetwork.cpp').read_text()
    # Idle 55 moored, 480 cruising, 90 landing: the loops are made at 90 and 480 and pitched by RPM over those.
    assert service.count('IsFlying()?(Phase==5?90.f:480.f)*FMath::Sqrt(FlightSpeed):55.f') == 2
    assert (make.ZEPPELIN_IDLE_RPM, make.ZEPPELIN_CRUISE_RPM) == (90, 480)
    audio = (SOURCE / 'TransportAudio.cpp').read_text()
    assert 'RPM/90.f' in audio and 'RPM/480.f' in audio
    # The service feeds the same state on and offline, after it has moved the ship and its parts.
    assert service.count(' AdvanceParts(Dt);\n UpdateAudio();\n}') == 2
    assert 'Audio->SetState(Phase,RPM,GateOpen,Phase==5&&PhaseTime>=LandSeconds())' in service


def test_loops_are_seamless(built):
    out, manifest = built
    for cue in make.LOOPS:
        x = samples(out / cue / f'{cue}_01.wav')
        assert len(x) % 480 == 0, cue                                  # a whole number of 10 ms
        # The step across the seam is an ordinary step of the signal, not a click ...
        steps = np.abs(np.diff(x))
        assert abs(x[0] - x[-1]) <= np.quantile(steps, .999), cue
        # ... and no 5 ms window straddling the seam has more high-frequency energy than the loop's own windows.
        hf = np.diff(np.r_[x, x[:1]]) ** 2
        w = 240
        energy = np.convolve(np.r_[hf[-w:], hf, hf[:w]], np.ones(w), 'valid')[w // 2: w // 2 + len(hf)]
        seam = max(energy[-w // 2:].max(), energy[:w // 2].max())
        assert seam <= np.quantile(energy, .995) * 1.05, cue
    # Every loop is periodic by construction: building it again gives the same samples.
    again = make.loops()
    for cue, x in make.loops().items():
        assert np.array_equal(x, again[cue]), cue


def test_levels_sit_inside_the_existing_banks(built):
    out, manifest = built
    for cue, files in manifest['cues'].items():
        peak_range, loudest_range = (LOOP_PEAK, LOOP_LOUDEST) if make.CUES[cue]['loop'] else (SHOT_PEAK, SHOT_LOUDEST)
        assert len(files) == make.CUES[cue]['variants'], cue
        for entry in files:
            x = samples(out.parent.parent / entry['file'])
            levels = make.levels(x)
            assert peak_range[0] <= levels['peak_dbfs'] <= peak_range[1], (entry['file'], levels)
            assert loudest_range[0] <= levels['loudest_400ms_dbfs'] <= loudest_range[1], (entry['file'], levels)
            if not make.CUES[cue]['loop']:
                # One-shots start and end in silence (no click when they start or stop).
                assert abs(x[0]) < 1e-3 and abs(x[-1]) < 1e-3, entry['file']


def test_one_shots_are_built_or_need_only_fetched_masters(built):
    _, manifest = built
    expected = set(make.CUES) if FETCHED else {cue for cue, spec_ in make.CUES.items() if not spec_['sonniss']}
    assert set(manifest['cues']) == expected
    if not FETCHED:
        pytest.skip('Sonniss combat masters are not fetched here; their cues were left out')


def test_every_source_is_sonniss_or_synthesis(built):
    _, manifest = built
    picks = make.combat_picks()
    for cue, sources in manifest['sources'].items():
        assert sources[0] == {'kind': 'synthesis', 'script': 'assets/audio/transport/make.py'}, cue
        named = sources[1:]
        assert [source['kind'] for source in named] == ['sonniss'] * len(named), cue
        assert [Path(source['file']).name for source in named] == list(make.CUES[cue]['sonniss']), cue
        for source in named:
            item, path, md5 = picks[Path(source['file']).name]
            assert (source['source_item'], source['source_path'], source['md5']) == (item, path, md5)
            assert item.startswith('sonniss-gdc-'), item
    # make.py reads no audio but the declared masters: no music, no generated or downloaded sound.
    tree = ast.parse((BANK / 'make.py').read_text())
    docstrings = {id(node.body[0].value) for node in ast.walk(tree)
                  if isinstance(node, (ast.Module, ast.FunctionDef)) and ast.get_docstring(node) is not None}
    literals = [node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings]
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert {value for value in literals if re.fullmatch(r'[\w-]+\.wav', value)} == MASTERS
    assert MASTERS <= set(picks)
    forbidden = re.compile(r'music|suno|stable_audio|ledger|openai|elevenlabs|urlopen|requests|cache_dir', re.I)
    assert not [value for value in [*literals, *names] if forbidden.search(value)]


def test_build_declares_exactly_the_masters_make_reads():
    """audio.transport depends on the combat masters the cues layer, named one by one, not the whole cache."""
    build = ast.parse((GAME / 'build.py').read_text())
    declared = next(n.value for n in build.body if isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', '') == 'TRANSPORT_MASTERS')
    assert set(ast.literal_eval(declared)) == MASTERS
