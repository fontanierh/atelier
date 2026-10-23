"""Select only the city data consumed by one logical constructor."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import yori  # noqa: E402,F401
from atelier.atomic_files import atomic_json  # noqa: E402
from atelier.export_manifest import real_directory  # noqa: E402

FIELDS = {
    'HD_CivicGardens': ('roads',),
    'HD_Streets': ('roads', 'road_widths'),
    'HD_PlazaShopApproaches': ('buildings',),
    'HD_Wires': ('poles',),
    'HD_LaneEdges': ('buildings',),
}


def project(city, asset):
    """@cc [owner:fontanierh,label:correctness;performance] logical-city-data-projection
    Publish exactly the current fields consumed by the selected logical constructor.
    Missing required fields MUST refuse. Unread city metadata and sibling placement
    changes outside those fields MUST stop here, without regenerating mesh exports.
    This data selection MUST NOT read or generate an FBX/GLB or import a sibling builder.
    """
    if asset not in FIELDS or any(field not in city or type(city[field]) is not list for field in FIELDS[asset]):
        raise ValueError('Incomplete selected city data')
    return dict(schema=1, asset=asset, city={field: city[field] for field in FIELDS[asset]})


def read(value, asset):
    if (set(value) != {'schema', 'asset', 'city'} or type(value['schema']) is not int
            or value['schema'] != 1 or value['asset'] != asset or type(value['city']) is not dict):
        raise ValueError('Foreign or malformed city projection')
    if project(value['city'], asset) != value:
        raise ValueError('Unexpected city projection fields')
    return value['city']


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--asset', required=True, choices=tuple(FIELDS))
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    real_directory(args.source.parent)
    if args.source.is_symlink() or not args.source.is_file():
        raise ValueError('City projection requires a regular source product')
    value = project(json.loads(args.source.read_text()), args.asset)
    real_directory(args.output.parent)
    atomic_json(args.output, value)


if __name__ == '__main__':
    main()
