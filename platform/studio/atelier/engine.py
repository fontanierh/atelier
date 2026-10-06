"""Where the tools are: the Unreal engine and Blender. `UE_ROOT` and `BLENDER` override the standard install paths."""
import os
import shutil
from pathlib import Path

DEFAULT_UE_ROOT = '/Users/Shared/Epic Games/UE_5.8'
DEFAULT_BLENDER = '/Applications/Blender.app/Contents/MacOS/Blender'


def unreal_root():
    return Path(os.environ.get('UE_ROOT') or DEFAULT_UE_ROOT)


def unreal_cmd(root=None):
    """The command-line editor, for imports, scripts and cooks."""
    return Path(root or unreal_root()) / 'Engine/Binaries/Mac/UnrealEditor-Cmd'


def unreal_app(root=None):
    """The editor binary inside its app bundle, for running the game."""
    return Path(root or unreal_root()) / 'Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor'


def blender():
    # Resolved: Blender finds its bundled Python and data next to its real executable, not next to a PATH symlink.
    return os.path.realpath(os.environ.get('BLENDER') or shutil.which('blender') or DEFAULT_BLENDER)
