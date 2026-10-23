"""Generate the north's material masks independently of every mesh export."""
from pathlib import Path
import sys

sys.path[:0] = [str(Path(__file__).resolve().parents[2]), str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402


def main():
    from hidamari import mountains
    from hidamari.layout import north_base_height
    output = yori.OUT/'hidamari'
    output.mkdir(parents=True,exist_ok=True)
    mountains.export_snow_mask(output,north_base_height)
    mountains.export_crater_mask(output)
    print('HIDAMARI NORTH MASKS COMPLETE',flush=True)


if __name__=='__main__': main()
