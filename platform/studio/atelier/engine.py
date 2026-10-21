"""Where the tools are: the Unreal engine and Blender. `UE_ROOT` and `BLENDER` override the standard install paths."""
import os
import re
import shlex
import shutil
from pathlib import Path

DEFAULT_UE_ROOT = '/Users/Shared/Epic Games/UE_5.8'
DEFAULT_BLENDER = '/Applications/Blender.app/Contents/MacOS/Blender'


def unreal_root():
    return Path(os.environ.get('UE_ROOT') or DEFAULT_UE_ROOT)


def unreal_cmd(root=None):
    """@cc [owner:fontanierh,label:correctness] source-editor-discovery
    Prefer the command-line editor when present. A source build's actual editor
    app MAY serve imports/scripts/cooks when that command is absent. Discovery
    MUST remain inside the explicitly selected engine and MUST NOT execute it.
    """
    command = Path(root or unreal_root()) / 'Engine/Binaries/Mac/UnrealEditor-Cmd'
    app = unreal_app(root)
    return app if not command.is_file() and app.is_file() else command


def unreal_app(root=None):
    """The editor binary inside its app bundle, for running the game."""
    return Path(root or unreal_root()) / 'Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor'


def blender():
    # Resolved: Blender finds its bundled Python and data next to its real executable, not next to a PATH symlink.
    selected = os.path.realpath(os.environ.get('BLENDER') or shutil.which('blender') or DEFAULT_BLENDER)
    return _forwarded_blender(selected)


def _forwarded_blender(selected):
    """@cc [owner:fontanierh,label:correctness] transparent-blender-wrapper
    Discovery MUST NOT execute shell code. Only an unconditional, argument-preserving exec
    of an absolute Blender app executable MAY be unwrapped; other wrappers retain their identity.
    """
    try:
        if not Path(selected).is_file():
            return selected
        with open(selected, 'rb') as stream:
            content = stream.read(4097)
        if len(content) > 4096 or any(byte < 32 and byte not in (9, 10) or byte == 127 for byte in content):
            return selected
        lines = content.decode('utf-8').split('\n')
        if not lines or lines[0] not in ('#!/bin/sh', '#!/bin/bash'):
            return selected
        # Homebrew uses Bash for the same transparent exec shim. Startup files
        # and imported shell functions can change its meaning, so retain those
        # wrappers rather than skip any user-provided shell behavior.
        if lines[0] == '#!/bin/bash' and (os.environ.get('BASH_ENV') or os.environ.get('SHELLOPTS')
                or any(name.startswith('BASH_FUNC_') for name in os.environ)):
            return selected
        commands = [line.strip(' \t') for line in lines[1:]
                    if line.strip(' \t') and not line.lstrip(' \t').startswith('#')]
        if len(commands) != 1:
            return selected
        match = re.fullmatch(r'exec[ \t]+(.+?)[ \t]+"\$@"(?:[ \t]+#[^\n]*)?[ \t]*', commands[0])
        if not match:
            return selected
        target, = shlex.split(match[1])
        if any(char in target for char in '$`;|&<>(){}*?[]\r\n\x00'):
            return selected
        path = Path(target)
        if (not path.is_absolute() or path.name != 'Blender' or path.parent.name != 'MacOS'
                or path.parent.parent.name != 'Contents' or path.parent.parent.parent.suffix != '.app'
                or not path.is_file() or not os.access(path, os.X_OK)):
            return selected
        return os.path.realpath(path)
    except (OSError, UnicodeError, ValueError):
        return selected
