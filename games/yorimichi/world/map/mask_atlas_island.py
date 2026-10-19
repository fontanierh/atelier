"""Give the world overview an island-shaped feathered alpha edge.

The RGB painting is never changed: its coastline still comes from the signed
terrain mask and atlas.verify_coast still checks it. The alpha channel only
controls where the UI reveals that painting, so the World view becomes the
island silhouette instead of a rectangular ocean tile.

The source receipt must already bind its painting to the authoritative signed
World mask, or carry an explicit terrain-reference-revalidation witness. The
original paid-call receipt is nested unchanged; this tool never mints a new
geography claim for an unverified painting.
"""
import argparse
import hashlib
import json
import os
import tempfile
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

import atlas


def island_alpha(mask, dilation, feather, threshold):
    land = np.asarray(mask.convert('L')) > 127
    keep = mask.convert('L').filter(ImageFilter.MaxFilter(dilation * 2 + 1))
    alpha = np.asarray(keep.filter(ImageFilter.GaussianBlur(feather))).copy()
    alpha[land] = 255
    return np.where(alpha < threshold, 0, alpha).astype('uint8')


def validate_source(original, source_sha, mask_path, witness_path=None, assets=None,
                    mask_bytes=None, manifest_bytes=None, current=None, witness_bytes=None):
    """Return the validated revalidation witness, or None when the receipt has current geography."""
    assets = Path(assets) if assets is not None else atlas.ASSETS
    if original.get('output_sha256') != source_sha:
        raise ValueError('Source painting bytes differ from their receipt')
    if original.get('labels_baked', True):
        raise ValueError('Source painting contains baked labels')
    if original.get('bounds') != atlas.WORLD_BOUNDS:
        raise ValueError('Source painting is not the production World frame')
    mask_path = Path(mask_path).resolve()
    canonical = (Path(assets) / 'coasts' / 'world.png').resolve()
    if mask_path != canonical:
        raise ValueError('Use the authoritative signed World coast mask')
    mask_bytes = mask_path.read_bytes() if mask_bytes is None else mask_bytes
    mask_sha = hashlib.sha256(mask_bytes).hexdigest()
    manifest_path = Path(assets) / 'coasts' / 'source.json'
    manifest = json.loads(manifest_path.read_text() if manifest_bytes is None else manifest_bytes)
    current = atlas.geography_signature() if current is None else current
    if manifest.get('geography') != current:
        raise ValueError('Authoritative World coast reference is stale')
    frame = (manifest.get('frames') or {}).get('world') or {}
    if frame.get('bounds') != atlas.WORLD_BOUNDS or frame.get('sha256') != mask_sha:
        raise ValueError('Coast mask is not the signed World reference')
    reference_sha = frame.get('reference_sha256')
    if not isinstance(reference_sha, str) or len(reference_sha) != 64 or any(
            c not in '0123456789abcdef' for c in reference_sha.lower()):
        raise ValueError('Signed World coast reference has no reference witness')
    inputs = original.get('inputs') or []
    roles = {}
    for item in inputs:
        if not isinstance(item, dict):
            continue
        role, sha = item.get('role'), item.get('sha256')
        if not role or not sha:
            continue
        if role in roles:
            raise ValueError(f'Generation receipt has duplicate {role} inputs')
        roles[role] = sha
    original_mask_sha = roles.get('exact coast mask')
    original_reference_sha = roles.get('exact geography')
    if not original_mask_sha:
        raise ValueError('Generation receipt did not record its exact coast mask')
    if not original_reference_sha:
        raise ValueError('Generation receipt did not record its exact geography reference')
    witness = None
    if (original.get('geography') != current or original_mask_sha != mask_sha
            or original_reference_sha != reference_sha):
        if witness_path is None:
            if original_mask_sha != mask_sha:
                raise ValueError('Generation receipt did not use this signed World coast mask; supply a revalidation witness')
            if original_reference_sha != reference_sha:
                raise ValueError('Generation receipt did not use the signed World reference; supply a revalidation witness')
            raise ValueError('Source receipt has no current geography and no revalidation witness')
        witness = json.loads(Path(witness_path).read_text() if witness_bytes is None else witness_bytes)
        if (original_mask_sha != mask_sha or original_reference_sha != reference_sha
                or 'original_coast_sha256' in witness or 'current_coast_sha256' in witness
                or 'original_reference_sha256' in witness):
            expected = dict(kind='terrain-reference-revalidation', geography=current,
                            painting_sha256=source_sha, original_coast_sha256=original_mask_sha,
                            current_coast_sha256=mask_sha, original_reference_sha256=original_reference_sha,
                            reference_sha256=reference_sha)
        else:
            expected = dict(kind='terrain-reference-revalidation', geography=current,
                            painting_sha256=source_sha, coast_sha256=mask_sha,
                            reference_sha256=reference_sha)
        if witness != expected:
            raise ValueError('Revalidation witness does not bind this painting, original/current mask and reference')
    return witness


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--record', type=Path, required=True)
    parser.add_argument('--mask', type=Path, required=True)
    parser.add_argument('--witness', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--out-record', type=Path, required=True)
    parser.add_argument('--dilation', type=int, default=9)
    parser.add_argument('--feather', type=int, default=24)
    parser.add_argument('--threshold', type=int, default=6)
    args = parser.parse_args()

    source_bytes = args.source.read_bytes()
    record_bytes = args.record.read_bytes()
    mask_bytes = args.mask.read_bytes()
    witness_bytes = args.witness.read_bytes() if args.witness is not None else None
    manifest_path = Path(atlas.ASSETS) / 'coasts' / 'source.json'
    manifest_bytes = manifest_path.read_bytes()
    current = atlas.geography_signature()
    original = json.loads(record_bytes)
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    witness = validate_source(original, source_sha, args.mask, args.witness,
                              mask_bytes=mask_bytes, manifest_bytes=manifest_bytes, current=current,
                              witness_bytes=witness_bytes)
    if args.out.exists() or args.out_record.exists():
        raise FileExistsError('Preserve the existing World alpha and receipt')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=args.out.name + '.', suffix='.tmp', dir=args.out.parent)
    os.close(fd)
    tmp_out = Path(tmp_name)
    fd, tmp_name = tempfile.mkstemp(prefix=args.out_record.name + '.', suffix='.tmp', dir=args.out.parent)
    os.close(fd)
    tmp_record = Path(tmp_name)

    try:
        with Image.open(BytesIO(source_bytes)) as raw, Image.open(BytesIO(mask_bytes)) as mask:
            image = raw.convert('RGBA')
            mask = mask.convert('L')
            if image.size != mask.size:
                raise ValueError('Source painting and coast mask dimensions differ')
            alpha = island_alpha(mask, args.dilation, args.feather, args.threshold)
            image.putalpha(Image.fromarray(alpha))
            land = np.asarray(mask) > 127
            far = [(0, 0), (image.width - 1, 0), (0, image.height - 1),
                   (image.width - 1, image.height - 1), (image.width - 1, image.height // 2)]
            far = [(x, y) for x, y in far if mask.getpixel((x, y)) < 128]
            if alpha[land].min() < 250 or not far or max(alpha[y, x] for x, y in far) != 0:
                raise ValueError('World alpha does not keep land opaque and far sea clear')
            error = atlas.verify_coast(image, mask, 'world')
            if error > .0035:
                raise ValueError(f'World painting no longer matches its coast mask: {error:.2%}')
            image.save(tmp_out, format='PNG', optimize=True)
            record = dict(kind='island-alpha-atlas-painting', bounds=original['bounds'], labels_baked=False,
                          geography=current, prompt=original['prompt'],
                          requested_model=original.get('requested_model'), quality=original.get('quality'),
                          output_sha256=hashlib.sha256(tmp_out.read_bytes()).hexdigest(),
                          generation=original, generation_witness=witness,
                          display=dict(kind='island-alpha-from-signed-coast',
                                       mask_sha256=hashlib.sha256(mask_bytes).hexdigest(),
                                       alpha_sha256=hashlib.sha256(alpha.tobytes()).hexdigest(),
                                       dilation_pixels=args.dilation, feather_pixels=args.feather,
                                       alpha_threshold=args.threshold, coast_error=error,
                                       land_alpha_min=int(alpha[land].min()),
                                       far_sea_sample_alpha_max=int(max(alpha[y, x] for x, y in far)),
                                       changed_rgb=False))
            tmp_record.write_text(json.dumps(record, indent=2) + '\n')
        if args.source.read_bytes() != source_bytes:
            raise ValueError('Source painting changed during alpha generation')
        if args.record.read_bytes() != record_bytes:
            raise ValueError('Generation receipt changed during alpha generation')
        if args.mask.read_bytes() != mask_bytes:
            raise ValueError('Coast mask changed during alpha generation')
        if args.witness is not None and args.witness.read_bytes() != witness_bytes:
            raise ValueError('Revalidation witness changed during alpha generation')
        if manifest_path.read_bytes() != manifest_bytes:
            raise ValueError('Coast manifest changed during alpha generation')
        if atlas.geography_signature() != current:
            raise ValueError('Current geography changed during alpha generation')
        try:
            os.link(tmp_out, args.out)
        except FileExistsError:
            raise FileExistsError('Refusing to overwrite an existing World alpha') from None
        try:
            os.link(tmp_record, args.out_record)
        except FileExistsError:
            if os.path.samefile(args.out, tmp_out):
                os.unlink(args.out)
            raise FileExistsError('Refusing to overwrite an existing World receipt') from None
    finally:
        for path in (tmp_out, tmp_record):
            if path.exists():
                path.unlink()
    print(f'World alpha: {args.out}; coast error {error:.3%}; land opaque; far sea clear', flush=True)


if __name__ == '__main__':
    main()
