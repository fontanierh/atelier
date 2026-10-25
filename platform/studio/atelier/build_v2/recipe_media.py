"""Closed audio decoding roles inside the existing guarded recipe worker.

SDK paths and their installed read permissions are execution context, never new
item-key ingredients. Source WAVs already belong to the frozen private view.
"""
from contextlib import contextmanager
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import threading

INSTALL_ROOT = Path('/opt/homebrew')
SDK_FIELDS = {'version', 'executable', 'image', 'read_literals', 'openssl_config'}


def _file(value):
    path = Path(value)
    if (not path.is_absolute() or path != Path(os.path.abspath(path)) or path.resolve() != path
            or not path.is_file() or path.is_symlink() or path.stat().st_nlink != 1):
        raise ValueError('audio role requires an independent canonical regular file')
    return path


def _root(value):
    path = Path(value)
    if (not path.is_absolute() or path.resolve() != path or not path.is_dir()
            or path.stat().st_uid != os.getuid()):
        raise ValueError('audio execution requires existing owned absolute roots')
    return path


def discover_media(ffmpeg_abs=None, ffprobe_abs=None):
    """Reuse the installed Node SDK's complete dylib/link/config discovery."""
    if globals().get('__package__'):
        from . import recipe_node
    else:
        spec = importlib.util.spec_from_file_location('atelier_media_node_sdk', Path(__file__).with_name('recipe_node.py'))
        recipe_node = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = recipe_node
        spec.loader.exec_module(recipe_node)
    tools = {}
    for name, locator in (('ffmpeg', ffmpeg_abs), ('ffprobe', ffprobe_abs)):
        role = os.fspath(locator) if locator is not None else str(INSTALL_ROOT / 'bin' / name)
        if not role or not Path(role).is_absolute():
            raise ValueError('audio producer requires an installed absolute ' + name)
        tools[name] = recipe_node.discover_node(role)
    sdk = {'version': 1, **tools}
    permissions(sdk)
    return sdk


def _configuration(tool):
    """Retain only the selected crypto image's exact ordinary compiled default."""
    crypto = {Path(name).resolve(strict=True) for name in tool['read_literals']
              if Path(name).name == 'libcrypto.3.dylib'}
    if not crypto:
        if tool['openssl_config'] is not None:
            raise ValueError('audio SDK has an unrelated OpenSSL configuration')
        return
    if len(crypto) != 1:
        raise ValueError('ambiguous audio SDK crypto context')
    image = _file(next(iter(crypto)))
    if image.stat().st_size > 64 * 1024 * 1024:
        raise ValueError('audio SDK crypto metadata exceeds bound')
    matches = re.findall(rb'OPENSSLDIR: "([^"\x00\r\n]+)"', image.read_bytes())
    if len(matches) != 1:
        raise ValueError('audio SDK crypto default is not exact')
    config = _file(Path(matches[0].decode('utf-8')) / 'openssl.cnf')
    if str(config) != tool['openssl_config'] or str(config) not in tool['read_literals']:
        raise ValueError('audio SDK OpenSSL configuration changed')
    if config.stat().st_size > 1024 * 1024:
        raise ValueError('audio SDK configuration exceeds bound')
    active = [line.split('#', 1)[0].strip() for line in config.read_text().splitlines()]
    if any(line.startswith('.include') or re.search(r'^(?:module|dynamic_path|engines)\s*=', line)
           or '$ENV::' in line for line in active):
        raise ValueError('unsupported audio SDK OpenSSL include/provider configuration')


def permissions(sdk):
    """Installed-platform additions for the worker's existing deny-default sandbox."""
    if not isinstance(sdk, dict) or set(sdk) != {'version', 'ffmpeg', 'ffprobe'} or sdk['version'] != 1:
        raise ValueError('unknown installed audio SDK context')
    if any(name in os.environ for name in ('OPENSSL_CONF', 'OPENSSL_CONF_INCLUDE', 'OPENSSL_MODULES')):
        raise ValueError('unsupported ambient OpenSSL override')
    reads, executables, roots = set(), [], set()
    for name in ('ffmpeg', 'ffprobe'):
        tool = sdk[name]
        if not isinstance(tool, dict) or set(tool) != SDK_FIELDS or tool['version'] != 1:
            raise ValueError('unknown installed audio tool context')
        image, role = Path(tool['image']), Path(tool['executable'])
        if (not role.is_absolute() or not image.is_relative_to(INSTALL_ROOT) or image.name != name
                or not image.is_file() or image.resolve() != image or image.parent.name != 'bin'
                or image.parent.parent == INSTALL_ROOT or role.resolve(strict=True) != image
                or not {str(role), str(image)}.issubset(tool['read_literals'])):
            raise ValueError('installed audio executable role changed')
        for literal in tool['read_literals']:
            if (not Path(literal).is_absolute() or not Path(literal).is_relative_to(INSTALL_ROOT)
                    or '..' in Path(literal).parts or not Path(literal).resolve(strict=True).is_relative_to(INSTALL_ROOT)):
                raise ValueError('audio SDK read escapes the installed platform')
        _configuration(tool)
        reads.update(tool['read_literals'])
        executables.append(str(image))
        roots.add(str(image.parent.parent))
    configs = {sdk[name]['openssl_config'] for name in ('ffmpeg', 'ffprobe')} - {None}
    if len(configs) > 1:
        raise ValueError('audio SDK images require incompatible crypto defaults')
    return {'executables': executables, 'read_literals': sorted(reads), 'read_subpaths': sorted(roots),
            'extra_rules': ['(allow process-fork)', '(allow file-read* (literal "/dev/fd"))',
                *['(allow file-read-metadata (subpath ' + json.dumps(root) + '))' for root in sorted(roots)]]}


def _stamp(path):
    info = path.stat()
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_mode)


class MediaExecution:
    """@cc [owner:fontanierh,label:safety;correctness] recipe-closed-media-audio
    Only the three original WAV decode/channel-probe shapes MAY execute. Inputs
    MUST be existing keyed view files pinned before producer execution; native WAV
    outputs MUST stay in owned scratch or explicit disjoint view write roots.
    Executables MUST be exact installed images, with fixed three-worker ffmpeg
    settings and no shell, network protocols, caller environment or descriptors.
    Only a one-use matching Popen event on its launching thread MAY receive the
    existing PathGuard grant. No second admission, audit disable or result authority
    is supplied. See test_build_v2_recipe_media.py.
    """
    def __init__(self, sdk, view, scratch, *, inputs=None, writes=()):
        permissions(sdk)
        self.sdk = sdk
        self.view, self.scratch = _root(view), _root(scratch)
        if self.scratch == self.view or self.scratch.is_relative_to(self.view) or self.view.is_relative_to(self.scratch):
            raise ValueError('audio scratch must be separate from the frozen view')
        self.sources = {}
        for root in ([self.view] if inputs is None else inputs):
            root = Path(root)
            if not root.is_relative_to(self.view) or root.resolve() != root:
                raise ValueError('audio input is outside the frozen view')
            paths = root.rglob('*') if root.is_dir() else [root]
            for path in paths:
                if path.suffix.lower() == '.wav':
                    path = _file(path)
                    self.sources[path] = _stamp(path)
        self.writes = [self.scratch]
        for value in writes:
            root = Path(value)
            if (not root.is_absolute() or root.resolve() != root or root == self.view
                    or not root.is_relative_to(self.view)
                    or any(path == root or path.is_relative_to(root) for path in self.sources)):
                raise ValueError('audio write role overlaps frozen inputs or escapes the private view')
            self.writes.append(root)
        self.environment = {'LC_ALL': 'C', 'TZ': 'UTC', 'HOME': str(self.scratch),
                            'TMPDIR': str(self.scratch), 'PATH': ''}
        config = sdk['ffmpeg']['openssl_config'] or sdk['ffprobe']['openssl_config']
        if config:
            self.environment['OPENSSL_CONF'] = config
        self._grant = None
        self._failed = None

    def _source(self, name):
        path = _file(name)
        if path not in self.sources or _stamp(path) != self.sources[path]:
            raise ValueError('audio input is not an unchanged declared frozen WAV')
        return path

    def _output(self, name):
        path = Path(name)
        if (not path.is_absolute() or path != Path(os.path.abspath(path)) or path.resolve() != path
                or path.suffix.lower() != '.wav' or path in self.sources
                or not any(path.is_relative_to(root) and path != root for root in self.writes)):
            raise ValueError('audio output is outside its declared owned write role')
        if path.exists():
            _file(path)  # Reject existing links/hardlinks before ffmpeg's overwrite.
        return path

    def validate(self, argv, args, kwargs):
        if args or type(argv) is not list or any(type(value) is not str for value in argv) or not argv:
            raise ValueError('unsupported audio subprocess request')
        name = next((name for name in ('ffmpeg', 'ffprobe') if argv[0] in
                    (name, self.sdk[name]['executable'], self.sdk[name]['image'])), None)
        if name == 'ffmpeg' and len(argv) == 13 and argv[1:5] == ['-v', 'error', '-y', '-i'] and argv[6:12] == [
                '-ac', '1', '-ar', '48000', '-sample_fmt', 's16'] and not kwargs:
            self._source(argv[5]); self._output(argv[12])
        elif name == 'ffprobe' and len(argv) == 10 and argv[1:9] == [
                '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=channels', '-of', 'csv=p=0'] and kwargs == {
                    'stdout': subprocess.PIPE, 'stderr': subprocess.PIPE, 'text': True}:
            self._source(argv[9])
        elif name == 'ffmpeg' and len(argv) == 12 and argv[1:4] == ['-v', 'error', '-i'] and argv[5:] == [
                '-map', '0:a:0', '-ar', '48000', '-f', 'f32le', '-'] and kwargs == {
                    'stdout': subprocess.PIPE, 'stderr': subprocess.PIPE}:
            self._source(argv[4])
        else:
            raise ValueError('unsupported audio decode/probe command or Popen arguments')
        command = [self.sdk[name]['image']]
        if name == 'ffmpeg':
            command += ['-threads', '3', '-filter_threads', '3', '-nostdin']
        command += ['-protocol_whitelist', 'file,pipe']
        return command + argv[1:]

    def allow_subprocess(self, audit_args):
        if self._grant is None or len(audit_args) != 4:
            return False
        executable, argv, cwd, env = audit_args
        command, thread = self._grant
        if (executable != command[0] or argv != command or cwd != str(self.view)
                or env != self.environment or threading.get_ident() != thread):
            return False
        self._grant = None
        return True

    @contextmanager
    def install(self):
        """Scope Popen rewriting while the original subprocess.run keeps pipe/check handling."""
        original = subprocess.Popen
        def popen(argv, *args, **kwargs):
            try:
                command = self.validate(argv, args, kwargs)
            except (ValueError, OSError) as error:
                self._failed = str(error)
                raise
            self._grant = (command, threading.get_ident())
            try:
                return original(command, cwd=str(self.view), env=dict(self.environment),
                                close_fds=True, **kwargs)
            finally:
                self._grant = None
        subprocess.Popen = popen
        try:
            yield self
            if self._failed:
                raise ValueError('refused audio subprocess attempt: ' + self._failed)
        finally:
            subprocess.Popen = original
            self._grant = None
