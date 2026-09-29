"""Where the character authoring tools find the revision history.

The tools here author new revisions of Yorimichi's characters (poses, clips, outfits, rigs) the way the prototype did:
each reads earlier revision folders (output/imagegen/<character>/<stage>-rNN/) and writes the next one. Only the current
revision of each character is in this repository (assets/characters/<id>/); the history stays in the prototype
repository, the archive. Point YORIMICHI_ARCHIVE at a checkout of it:

    export YORIMICHI_ARCHIVE=/path/to/the/prototype/checkout      # contains output/imagegen/...

After a new revision is approved, `promote.py` copies it into assets/characters/<id>/ and updates character.toml.
"""
import os
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
_archive = os.environ.get('YORIMICHI_ARCHIVE')
ROOT = Path(_archive).expanduser().resolve() if _archive else TOOLS / '_archive_not_set'
if not _archive:
    import warnings
    warnings.warn('YORIMICHI_ARCHIVE is not set: tools that read earlier character revisions will not find them', stacklevel=2)
