"""Select one original conifer LOD without adding LOD helpers to street-prop source inputs."""
from pathlib import Path
import sys
sys.path[:0]=[str(Path(__file__).resolve().parents[2]),str(Path(__file__).resolve().parents[1])]
import yori  # noqa: E402,F401
from hidamari.plan_prop import arguments,produce
from hidamari.prop_parameters import load
from hidamari.prop_lod_geometry import make_lod


def main(argv=None):
    args=arguments(argv);value=load(args.parameters)
    if not value['upright']:raise ValueError('Selected source is not a conifer')
    produce(args,value,make_lod=make_lod)


if __name__=='__main__':main()
