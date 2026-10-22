"""Render bounded listening examples from prepared candidates; no inference.

Run this offline batch under atelier.harness.safety.guarded. Footstep cadence is
an explicit audition stand-in for animation bone plants, not a recorded gameplay
trace. Runtime gain/pitch, skate envelopes and contact gain are pinned below.
"""
import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import tempfile
import wave

import numpy as np

from atelier.ai.stable_audio.review import digest, write_json
from atelier.ai.stable_audio import review

REPO = Path(__file__).resolve().parents[3]
RATE = 48000
SECONDS = 8
MAX_FILE = 160 * 1024
MAX_BANK = 10 * 1024 * 1024
RUNTIME = {
    'games/yorimichi/unreal/Source/Yorimichi/JapanFootsteps.cpp':
        '08df0472b8cac0db829b5e6602934321a2b10eceb4802ba6999b22c7c1cd512d',
    'platform/engine/Plugins/Activities/Skate/Source/AtelierSkate/Private/SkateComponent.cpp':
        '8a95e84663f16ae2df3ae2e1d57519a143c2603b7e095223d01562e89cc6ee45',
    'platform/engine/Plugins/Activities/Skate/Source/AtelierSkate/Private/SkateRuntime.cpp':
        '0121b2efb79092e036ef1455721cae7ebfe599dc86f8c699ff653a5735eba46c',
}


def runtime_identity():
    for name, expected in RUNTIME.items():
        if digest(REPO / name) != expected:
            raise ValueError('Revalidate sound profile against changed runtime: ' + name)
    return RUNTIME


def prepared_sources(root):
    """Validate every candidate before creating output or publishing a bank."""
    path = root / 'prepared.json'
    if path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError('Prepared manifest too large')
    data = json.loads(path.read_text())
    clips = data['clips']
    if not isinstance(clips, list) or not 1 <= len(clips) <= 512:
        raise ValueError('Invalid candidate count')
    pools, identities, ids = {}, [], set()
    for clip in clips:
        name = clip['file']
        if (clip['id'] in ids or clip['status'] != 'ready'
                or not re.fullmatch(r'samples/([0-9a-f]{64}/)?sample-\d+\.wav', name)
                or not re.fullmatch(r'(footstep|skate\.(roll|skid|land))\.[a-z_]+', clip['cue'])
                or not clip['cue'].endswith('.' + clip['surface'])
                or clip.get('loop') is not clip['cue'].startswith(('skate.roll.', 'skate.skid.'))):
            raise ValueError('Invalid or duplicate prepared candidate')
        ids.add(clip['id'])
        source = (root / name).resolve()
        if not source.is_relative_to(root) or digest(source) != clip['audio']['sha256']:
            raise ValueError('Prepared source checksum/path changed')
        with wave.open(str(source), 'rb') as handle:
            if (handle.getnchannels(), handle.getsampwidth(), handle.getframerate()) != (1, 2, RATE):
                raise ValueError('Expected mono48kHz16-bit candidate')
            frames = handle.getnframes()
            if not 1 <= frames <= 10 * RATE or frames != clip['audio']['frames']:
                raise ValueError('Invalid source frame count')
            if not clip['loop'] and frames > 2 * RATE:
                raise ValueError('Contact exceeds two-second event budget')
            raw = handle.readframes(frames)
            if len(raw) != frames * 2:
                raise ValueError('Truncated source')
        samples = np.frombuffer(raw, '<i2').astype(np.float64) / 32768
        if np.max(np.abs(samples)) < .001:
            raise ValueError('Silent prepared candidate')
        identities.append({'id': clip['id'], 'file': name, 'sha256': digest(source)})
        pools.setdefault(clip['cue'], []).append((clip['id'], samples))
    return pools, identities, digest(path)


def plans(pools):
    result = []
    skate = {cue.rsplit('.', 1)[1] for cue in pools if cue.startswith('skate.')}
    for surface in skate:
        if not all('skate.' + kind + '.' + surface in pools for kind in ('roll', 'skid', 'land')):
            raise ValueError('Incomplete skate surface: ' + surface)
    for cue in sorted(pools):
        if cue.startswith('footstep.'):
            surface = cue.removeprefix('footstep.')
            result.extend((kind, surface) for kind in ('walk', 'run'))
        elif cue.startswith('skate.roll.'):
            surface = cue.removeprefix('skate.roll.')
            if all('skate.' + kind + '.' + surface in pools for kind in ('skid', 'land')):
                result.extend((kind, surface) for kind in ('roll', 'slide', 'landing', 'transition'))
    if not result or len(result) > 80:
        raise ValueError('Invalid or excessive sequence count')
    return result


def foot_gain_pitch(speed_cm, rng):
    drive = np.clip((speed_cm - 60) / 260, 0, 1)
    return (.32 + .68 * drive) * rng.uniform(.88, 1), (.96 + .1 * drive) * rng.uniform(.94, 1.06)


def skate_gain_pitch(speed_m, slide=False):
    # USkateComponent::UpdateAudio, full82-degree powerslide, speed converted
    # from nativecm/s. Each playback frame uses runtime FInterpTo below.
    if slide:
        return .9 * np.clip(speed_m / 4, 0, 1), .9 + .3 * np.clip(speed_m / 8, 0, 1)
    return .85 * np.clip(speed_m / 4.5, 0, 1), .75 + .45 * np.clip(speed_m / 10, 0, 1)


def resample(samples, pitch):
    return np.interp(np.arange(0, len(samples), pitch), np.arange(len(samples)), samples)


def render(kind, surface, pools, seed):
    """@cc [owner:fontanierh,label:correctness] prepared-sequence-rendering
    Sequences MUST use verified prepared contacts/loops and the pinned runtime
    gain/pitch/envelope profile. Cadences MUST be labeled audition approximations
    to bone events. Missing surface cues MUST fail rather than substitute another
    material. Rendering MUST be deterministic, finite and reject clipped output.
    """
    rng = random.Random(seed)
    audio = np.zeros(SECONDS * RATE)
    events = []
    bags = {}

    def take(cue):
        if cue not in pools:
            raise ValueError('Missing surface cue: ' + cue)
        if not bags.get(cue):
            bags[cue] = list(pools[cue]); rng.shuffle(bags[cue])
        return bags[cue].pop()

    def contact(cue, at, gain, pitch, side=None, wrap=False):
        identity, samples = take(cue)
        shaped = resample(samples, pitch)
        start = round(at * RATE)
        count = min(len(shaped), len(audio) - start)
        audio[start:start + count] += shaped[:count] * gain
        if wrap and count < len(shaped):
            remainder = len(shaped) - count
            audio[:remainder] += shaped[count:] * gain
        events.append(dict(source=identity, time=round(at, 6), gain=float(gain), pitch=float(pitch), side=side))

    if kind in ('walk', 'run'):
        cadence, speed = (120, 180) if kind == 'walk' else (180, 500)
        interval = 60 / cadence
        for index, at in enumerate(np.arange(interval / 2, SECONDS, interval)):
            gain, pitch = foot_gain_pitch(speed, rng)
            contact('footstep.' + surface, at, gain, pitch, index % 2, wrap=True)
        description = f'{cadence} steps/min; alternating plant approximation'
    else:
        description = 'Runtime speed/pitch and60fps attack/release envelopes'
        tracks = {}
        for cue in ('roll', 'skid'):
            identity, samples = take('skate.' + cue + '.' + surface)
            tracks[cue] = dict(samples=samples, x=np.arange(len(samples) + 1),
                               cyclic=np.r_[samples, samples[0]], volume=0., phase=0., playing=False)
            events.append(dict(source=identity, role=cue))
        for frame in range(SECONDS * 60):
            at = frame / 60
            speed = float(np.interp(at, [0, 1, 3, 6.8, 7.6, 8], [0, 4.5, 8, 5, 0, 0]))
            skid = kind == 'slide' and 1 <= at < 6.5 or kind == 'transition' and 2.5 <= at < 4.5
            grounded = kind != 'landing' and not (kind == 'transition' and 4.5 <= at < 5.25)
            for cue, track in tracks.items():
                gain, pitch = skate_gain_pitch(speed, cue == 'skid')
                target = gain if grounded and (skid == (cue == 'skid')) else 0.
                volume = track['volume']
                distance = target - volume
                volume = target if distance * distance < 1.e-8 else volume + distance * min(
                    (30 if target > volume else 10) / 60, 1)
                track['volume'] = volume
                if volume <= .01:
                    track['playing'] = False
                    continue
                samples = track['samples']
                if not track['playing']:
                    track['phase'] = rng.uniform(0, 1.5) * RATE
                    track['playing'] = True
                indices = (track['phase'] + np.arange(RATE // 60) * pitch) % len(samples)
                segment = np.interp(indices, track['x'], track['cyclic'])
                start = frame * (RATE // 60)
                audio[start:start + len(segment)] += segment * volume
                track['phase'] = (indices[-1] + pitch) % len(samples)
        if kind == 'landing':
            for at in (.6, 2.5, 4.4, 6.3):
                contact('skate.land.' + surface, at, .8, 1.)
            description = 'Four air-to-ground contacts; runtime gain0.8/pitch1'
        elif kind == 'transition':
            contact('skate.land.' + surface, 5.25, .8, 1.)
            description = 'Accelerate → powerslide → airborne → land → roll to stop'
    # One common headroom scale preserves runtime walk/run/material balance.
    audio *= .75
    if kind not in ('walk', 'run'):
        audio[:960] *= np.linspace(0, 1, 960)
        audio[-3840:] *= np.linspace(1, 0, 3840)
    if not np.isfinite(audio).all() or np.max(np.abs(audio)) > .98:
        raise ValueError('Non-finite or clipped sequence')
    if math.sqrt(float(np.mean(audio * audio))) < .0001:
        raise ValueError('Silent sequence')
    return audio, events, description


def encode(samples, path):
    with tempfile.TemporaryDirectory() as folder:
        source = Path(folder) / 'source.wav'
        with wave.open(str(source), 'wb') as handle:
            handle.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
            handle.writeframes(np.round(samples * 32767).astype('<i2').tobytes())
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-threads', '1', '-i', str(source),
                        '-map_metadata', '-1', '-ac', '1', '-ar', str(RATE), '-c:a', 'aac',
                        '-b:a', '96k', '-threads', '1', '-fflags', '+bitexact', '-flags:a', '+bitexact',
                        '-movflags', '+faststart', str(path)], check=True, timeout=20)
    decoded = subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-threads', '1', '-i', str(path),
                              '-ac', '1', '-ar', str(RATE), '-f', 'f32le', '-'],
                             capture_output=True, check=True, timeout=20)
    signal = np.frombuffer(decoded.stdout, '<f4')
    if (abs(len(signal) - len(samples)) > 2048 or not np.isfinite(signal).all()
            or np.max(np.abs(signal)) > 1 or np.sqrt(np.mean(signal ** 2)) < .0001
            or not 1 <= path.stat().st_size <= MAX_FILE):
        raise ValueError('Encoded output exceeds duration/signal/size budget')
    return dict(sha256=digest(path), bytes=path.stat().st_size, seconds=SECONDS,
                decoded_frames=len(signal), decoded_rms=float(np.sqrt(np.mean(signal ** 2))))


def build(root):
    """@cc [owner:fontanierh,label:correctness] atomic-sequence-publication
    A complete verified encoded bank MUST publish before its manifest. Identity
    MUST include actual source hashes, renderer, pinned runtime and encoder.
    Existing media MUST never be overwritten. Interrupted builds MUST preserve
    the old manifest and every media byte it references. Sources MUST be rechecked
    before publication. Output and index size budgets MUST be enforced.
    """
    root = Path(root).resolve()
    with (root / '.writer.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        runtime = runtime_identity()
        pools, identities, manifest_hash = prepared_sources(root)
        encoder = shutil.which('ffmpeg')
        if not encoder:
            raise ValueError('ffmpeg is required')
        version = subprocess.check_output([encoder, '-version'], text=True, timeout=10)
        identity = dict(prepared_sha256=manifest_hash, sources=identities, runtime=runtime,
                        renderer_sha256=digest(Path(__file__)), encoder_sha256=digest(encoder),
                        review_helpers_sha256=digest(Path(review.__file__)),
                        encoder_version=version, codec='AAC96k-mono48k-faststart', duration=SECONDS)
        bank = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        folder = root / 'sequences' / bank
        folder.mkdir(parents=True, exist_ok=True)
        clips, provenance = [], []
        for number, (kind, surface) in enumerate(plans(pools), 1):
            name = f'sequence-{number:04d}.m4a'
            samples, events, description = render(kind, surface, pools, number)
            fd, temporary = tempfile.mkstemp(suffix='.m4a', dir=folder)
            os.close(fd); Path(temporary).unlink()
            try:
                audio = encode(samples, Path(temporary))
                output = folder / name
                if output.exists():
                    if digest(output) != audio['sha256']:
                        raise ValueError('Existing immutable sequence differs')
                else:
                    os.link(temporary, output)
            finally:
                Path(temporary).unlink(missing_ok=True)
            clips.append(dict(id=f'sequence-{number:04d}', activity=kind, surface=surface,
                              label=f'{kind.title()} · {surface.replace("_", " ")}',
                              file=f'sequences/{bank}/{name}', description=description, **audio))
            provenance.append(dict(id=clips[-1]['id'], events=events))
            print(f'Encoded {number}: {kind}/{surface}, {audio["bytes"]}bytes, decodedRMS{audio["decoded_rms"]:.4f}', flush=True)
        if sum(c['bytes'] for c in clips) > MAX_BANK:
            raise ValueError('Sequence bank exceeds10MiB')
        _, rechecked, source_hash = prepared_sources(root)
        if rechecked != identities or source_hash != manifest_hash or runtime_identity() != runtime:
            raise ValueError('Sequence inputs changed during rendering')
        if (digest(Path(__file__)) != identity['renderer_sha256']
                or digest(Path(review.__file__)) != identity['review_helpers_sha256']
                or digest(encoder) != identity['encoder_sha256']):
            raise ValueError('Renderer or encoder changed during rendering')
        if any(digest(root / c['file']) != c['sha256'] or (root / c['file']).stat().st_size != c['bytes'] for c in clips):
            raise ValueError('Encoded media changed before publication')
        document = dict(version=1, bank=bank, title='Sound previews', clips=clips)
        if len(json.dumps(document).encode()) > 64 * 1024:
            raise ValueError('Sequence index exceeds64KiB')
        write_json(root / f'.sequence-provenance-{bank}.json', dict(identity=identity, sequences=provenance))
        write_json(root / 'sequences.json', document)
        print(f'Published {len(clips)} sequences; {sum(c["bytes"] for c in clips)}bytes', flush=True)
        return document


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    build(parser.parse_args().root)
