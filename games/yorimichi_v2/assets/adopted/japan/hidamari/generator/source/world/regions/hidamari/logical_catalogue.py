"""Shared city ownership data; individual constructors do not consume this roster."""
from pathlib import Path
import re

ROSTER = Path(__file__).resolve().parents[3] / 'unreal/Source/Yorimichi/CitySurfaceParents.h'
PREFIX = ('// Shared logical city ownership, read by the recipe and runtime.\n'
          '#pragma once\n#define YORIMICHI_CITY_PARENTS(ITEM) ' + '\\' + '\n')


def read(path=ROSTER):
    """@cc [owner:fontanierh,label:correctness] shared-logical-city-roster
    Build admission and native runtime MUST use the same explicit ordered parent
    inventory. Adding a parent MUST NOT add this roster to existing constructors'
    inputs: each selected constructor still reads only its own code/data. Reject
    unsafe, duplicate or case-fold aliased parent names before graph construction.
    """
    text = Path(path).read_text()
    if not text.startswith(PREFIX) or not text.endswith('\n'):
        raise ValueError('Invalid shared city ownership header')
    rows = text[len(PREFIX):].splitlines()
    result = []
    for index, row in enumerate(rows):
        match = re.fullmatch(r'    ITEM\("([A-Za-z][A-Za-z0-9_]*)"\)' + (r' \\' if index+1<len(rows) else ''), row)
        if match is None:
            raise ValueError('Invalid shared city parent entry')
        result.append(match[1])
    if not result or len({key.casefold() for key in result}) != len(result):
        raise ValueError('Shared city ownership must be complete and unique')
    return tuple(result)


ASSETS = read()
