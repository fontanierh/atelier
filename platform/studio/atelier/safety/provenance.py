"""What the game reports about itself: the effective settings a capture actually ran with."""
import json, re
from pathlib import Path


def profile_from_log(path):
    """The `PROFILE` line the game's preferences print after applying, as a dict of effective values."""
    try:
        text = Path(path).read_text(errors='ignore')
    except OSError:
        return None
    found = None
    for match in re.finditer(r'PROFILE\s+(\{.*?\})\s*$', text, re.MULTILINE):
        try:
            found = json.loads(match.group(1))
        except ValueError:
            continue
    return found
