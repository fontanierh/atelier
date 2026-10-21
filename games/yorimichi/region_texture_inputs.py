"""Fresh membership and byte identity of only the report-selected regional textures."""
import json
from pathlib import Path

from region_products import file_record, source, texture_members


def members(folder):
    """Observe current selected membership, retaining absent paths for normal miss reporting."""
    folder = Path(folder)
    if folder.is_symlink():
        raise ValueError('Region texture root must not be linked')
    report = folder / 'build-report.json'
    if not report.exists():
        return [report]
    data = json.loads(source(folder, 'build-report.json').read_text())
    selected = [folder / name for name in texture_members(data)]
    for path in selected:
        if path.exists() or path.is_symlink():
            source(folder, path.relative_to(folder).as_posix())
    return [report, *selected]


def publish(folder, destination):
    """@cc [owner:fontanierh,label:correctness] selected-region-texture-bytes
    The snapshot MUST inventory exactly the texture/layer/normal files selected by the current
    report, binding actual regular file bytes. Unselected files MUST NOT enter this identity.
    Missing, linked or escaping selected sources MUST refuse before publishing a new snapshot.
    The ordinary action MUST observe selected membership afresh and bind its full helper code.
    """
    folder, destination = Path(folder), Path(destination)
    if folder.is_symlink():
        raise ValueError('Region texture root must not be linked')
    report = json.loads(source(folder, 'build-report.json').read_text())
    snapshot = dict(schema=1, files={name: file_record(folder, name) for name in texture_members(report)})
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(snapshot, sort_keys=True, separators=(',', ':')) + '\n')
    print(f'REGION TEXTURES COMPLETE: {len(snapshot["files"])} selected files', flush=True)


if __name__ == '__main__':
    import sys
    if len(sys.argv) != 3:
        raise ValueError('Expected REGION_FOLDER SNAPSHOT_PATH')
    publish(Path(sys.argv[1]), Path(sys.argv[2]))
