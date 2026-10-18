"""Pinned local mono audio commands, with explicit codec and filter worker limits."""
from collections.abc import Sequence
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import stat
import wave

RATE = 48000
MAX_FRAMES = 8 * RATE
MAX_AAC_BYTES = 160 * 1024
CEILING_GIB = 4
# Reviewed Homebrew FFmpeg binary; other builds retain full exclusive admission.
REVIEWED_EXECUTABLES = frozenset({
    '8aabed5b0398745fe876d557a43cb9de2e391996b332d94a19bca55fd520ee62',
})
CPU_WORKERS = 4  # Decoder, encoder, simple filter and mux/orchestration stages.
WORKER_ENV = {name: '1' for name in (
    'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS',
    'NUMEXPR_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'BLIS_NUM_THREADS')}


def worker_environment():
    inherited = {name: value for name, value in os.environ.items()
                 if not name.startswith('DYLD_') and name not in ('LD_PRELOAD', 'LD_LIBRARY_PATH')}
    return {**inherited, **WORKER_ENV}


def digest(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def identity(path):
    value = Path(path).stat()
    if not stat.S_ISREG(value.st_mode):
        raise ValueError('Audio input/tool must be a regular file')
    return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


@dataclass(frozen=True)
class Command(Sequence):
    """@cc [owner:fontanierh,label:safety] bounded-local-audio-command
    Only the fixed local mono PCM-to-AAC and AAC-to-PCM commands MAY select this profile.
    The absolute executable and bounded input MUST match their original file identity and SHA
    before admission and again before exec. Codec and filter workers MUST all remain one,
    Input demuxers MUST be fixed WAV/MOV, decode duration MUST be at most eight seconds,
    and output MUST be a new file inside its identity-bound declared directory.
    Only reviewed executable SHAs MAY select shared admission; unreviewed builds MUST retain
    full exclusive admission. Network/hardware inputs MUST NOT be accepted.
    This profile MUST NOT classify Python launchers, arbitrary FFmpeg arguments or other tools.
    """
    executable: str
    source: str
    output: str
    mode: str
    output_dir: str
    output_dir_identity: tuple
    executable_sha256: str
    source_sha256: str
    executable_identity: tuple
    source_identity: tuple

    @classmethod
    def create(cls, executable, source, output, *, mode, output_dir):
        executable, source, output = (str(Path(p).resolve()) for p in (executable, source, output))
        output_dir = str(Path(output_dir).resolve(strict=True))
        directory = Path(output_dir).stat()
        if not stat.S_ISDIR(directory.st_mode):
            raise ValueError('Audio output directory must exist')
        maximum = MAX_FRAMES * 2 + 65536 if mode == 'encode' else MAX_AAC_BYTES
        if mode not in ('encode', 'decode') or not 1 <= Path(source).stat().st_size <= maximum:
            raise ValueError('Audio input exceeds its byte budget')
        if Path(executable).stat().st_size > 32 * 1024 * 1024:
            raise ValueError('Audio tool exceeds its executable byte budget')
        value = cls(executable, source, output, mode, output_dir, (directory.st_dev, directory.st_ino),
                    digest(executable), digest(source),
                    identity(executable), identity(source))
        value.verify()
        return value

    def verify(self):
        if (self.mode not in ('encode', 'decode') or Path(self.executable).name != 'ffmpeg'
                or any(not Path(p).is_absolute() for p in (self.executable, self.source, self.output))
                or any(not re.fullmatch('[0-9a-f]{64}', value) for value in
                       (self.executable_sha256, self.source_sha256))
                or Path(self.output).exists() or Path(self.output).is_symlink()):
            raise ValueError('Invalid bounded audio command or occupied output')
        directory = Path(self.output_dir).stat()
        if (not Path(self.output_dir).is_absolute() or not stat.S_ISDIR(directory.st_mode)
                or (directory.st_dev, directory.st_ino) != tuple(self.output_dir_identity)
                or Path(self.output_dir).resolve() != Path(self.output_dir)
                or Path(self.output).parent != Path(self.output_dir)):
            raise ValueError('Audio output escaped its declared directory')
        maximum = MAX_FRAMES * 2 + 65536 if self.mode == 'encode' else MAX_AAC_BYTES
        if not 1 <= Path(self.source).stat().st_size <= maximum or Path(self.executable).stat().st_size > 32 * 1024 * 1024:
            raise ValueError('Audio input/tool exceeds its byte budget')
        for path, pin, expected in ((self.executable, self.executable_identity, self.executable_sha256),
                                    (self.source, self.source_identity, self.source_sha256)):
            before = identity(path)
            if before != tuple(pin) or digest(path) != expected or identity(path) != before:
                raise ValueError('Pinned audio executable/input changed')
        if not os.access(self.executable, os.X_OK):
            raise ValueError('Audio tool is not executable')
        if self.mode == 'encode':
            if Path(self.source).stat().st_size > MAX_FRAMES * 2 + 65536:
                raise ValueError('Audio PCM input exceeds its byte budget')
            with wave.open(self.source, 'rb') as handle:
                if ((handle.getnchannels(), handle.getsampwidth(), handle.getframerate()) != (1, 2, RATE)
                        or not 1 <= handle.getnframes() <= MAX_FRAMES):
                    raise ValueError('Audio PCM format/duration exceeds its budget')
        elif not 1 <= Path(self.source).stat().st_size <= MAX_AAC_BYTES:
            raise ValueError('Encoded audio input exceeds its byte budget')

    @property
    def argv(self):
        prefix = (self.executable, '-v', 'error', '-nostdin', '-n', '-filter_threads', '1',
                  '-filter_complex_threads', '1', '-protocol_whitelist', 'file', '-threads', '1')
        if self.mode == 'decode':
            prefix += ('-c:a', 'aac')
        prefix += ('-f', 'wav' if self.mode == 'encode' else 'mov')
        common = ('-i', self.source, '-t', '8', '-map', '0:a:0', '-vn', '-sn', '-dn', '-ac', '1',
                  '-ar', str(RATE), '-threads', '1')
        suffix = (('-map_metadata', '-1', '-c:a', 'aac', '-b:a', '96k', '-fflags', '+bitexact',
                   '-flags:a', '+bitexact', '-movflags', '+faststart') if self.mode == 'encode'
                  else ('-f', 'f32le'))
        return prefix + common + suffix + (self.output,)

    def __len__(self):
        return len(self.argv)

    def __getitem__(self, index):
        return self.argv[index]

    def prepared_argv(self):
        import json
        import sys
        from dataclasses import asdict
        return [sys.executable, str(Path(__file__).with_name('ffmpeg_audio_exec.py')),
                json.dumps(asdict(self), separators=(',', ':'))]


def workers(command):
    if type(command) is not Command:
        return None
    command.verify()
    return CPU_WORKERS if command.executable_sha256 in REVIEWED_EXECUTABLES else None


def run(command, report, *, purpose):
    """Use the ordinary guard, admission and aggregate lifecycle for the actual FFmpeg process."""
    import subprocess
    from atelier.harness.safety import guarded
    if type(command) is not Command:
        raise ValueError('A pinned local audio command is required')
    code = guarded.run(command, report, kind='job', timeout=20, purpose=purpose,
                       aggregate_tree=True, env=worker_environment())
    if code:
        raise subprocess.CalledProcessError(code, list(command))
