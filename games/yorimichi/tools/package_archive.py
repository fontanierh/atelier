"""Turn the archived Yorimichi .app into release files: the download folder, a zip, parts and checksums.

    python games/yorimichi/tools/package_archive.py --out build/yorimichi/package

`atelier build yorimichi unreal.package` runs this as a guarded job after BuildCookRun has archived the .app
(games/yorimichi/docs/PACKAGING.md). The download is a folder: the .app, a launcher carrying the desktop profile, and a
README. It is zipped with ditto, which keeps the app's symlinks, signature and permissions, and split into parts when it
is too large for a GitHub release asset. Every phase is bounded and reports progress.
"""
import argparse, hashlib, importlib.util, json, plistlib, shutil, subprocess, sys, tempfile, time
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
REPO = TOOLS.parents[2]
# GitHub release assets must stay under 2 GiB each.
PART_BYTES = 1900 * 1024 * 1024


PACKAGE_PHASE_SECONDS = 45 * 60      # each of zip, split and checksum
PLAYTEST_README = """Yorimichi playtest build (macOS, Apple silicon).

Start the game by double-clicking "Play Yorimichi.command". It starts the game with the desktop profile: the forward
renderer, the native 1440 view and the optimized city. Starting Yorimichi.app directly skips that profile.

The first time: if macOS says the launcher or the app cannot be opened, right-click "Play Yorimichi.command", choose
Open, then Open again. The launcher removes the download quarantine itself.

Settings and logs are inside the app's macOS sandbox container:
~/Library/Containers/<bundle-id>/Data/Library/Application Support/Yorimichi/settings.txt
~/Library/Containers/<bundle-id>/Data/Library/Logs/Yorimichi/game.log
The launcher reads <bundle-id> from Yorimichi.app/Contents/Info.plist.
This build always uses the forward renderer: choosing Lumen in the menu has no effect here.
"""


def desktop_preview():
    spec = importlib.util.spec_from_file_location('yorimichi_desktop_preview', TOOLS / 'desktop_preview.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module
PACKAGE_PROGRESS_SECONDS = 25
# Loose runtime files the game cannot start without (unreal/Content/Data, written by data.stage).
STAGED_DATA = ('world.json', 'heightmap.bin', 'map/map.json')


def bounded(argv, log, label, watch):
    """Run one packaging tool to completion within its deadline, saying how far it has got at least every 25 s."""
    process = subprocess.Popen(argv)
    started = time.monotonic()
    try:
        while True:
            try:
                process.wait(timeout=PACKAGE_PROGRESS_SECONDS)
                break
            except subprocess.TimeoutExpired:
                elapsed = time.monotonic() - started
                if elapsed > PACKAGE_PHASE_SECONDS:
                    raise RuntimeError(f'{label} exceeded {PACKAGE_PHASE_SECONDS} s')
                written = sum(p.stat().st_size for p in watch() if p.exists())
                line = f'{label}: {elapsed / 60:.1f} min, {written / 2**30:.2f} GiB written'
                log.write(line + '\n'); log.flush()
    finally:
        if process.poll() is None:
            process.kill(); process.wait()
    if process.returncode:
        raise RuntimeError(f'{label} exited {process.returncode}')


def staged_data(app):
    """Content/Data is staged as loose files beside the paks (DirectoriesToAlwaysStageAsNonUFS): the game reads it with
    AtelierDataPath at run time, so a package without it would start into an empty world."""
    data = [d for d in app.glob('Contents/UE/*/Content/Data') if d.is_dir()]
    missing = [rel for rel in STAGED_DATA if not data or not (data[0] / rel).exists()]
    if missing:
        raise RuntimeError(f'the packaged app lacks staged runtime data: {missing}')


# CoreAudio's first HAL call on macOS 26 looks up this service even for output-only audio. Without this exact
# allowance the standard UE App Sandbox signature can hang before the game starts. Keep the sandbox and its
# other entitlements; the local Development download is ad-hoc signed, never a Developer ID/notarized product.
AUDIO_SERVICE = 'com.apple.cmio.registerassistantservice.system-extensions'
MACH_LOOKUP = 'com.apple.security.temporary-exception.mach-lookup.global-name'


def audio_compatibility(app, log):
    def codesign(*args):
        return subprocess.run(['codesign', *args, str(app)], capture_output=True, check=True, timeout=120)
    raw = codesign('-d', '--entitlements', '-', '--xml').stdout
    entitlements = plistlib.loads(raw) if raw.strip() else {}
    if entitlements.get('com.apple.security.app-sandbox'):
        services = entitlements.get(MACH_LOOKUP, [])
        if not isinstance(services, list) or not all(isinstance(name, str) for name in services):
            raise RuntimeError('invalid existing Mach lookup entitlements')
        if AUDIO_SERVICE not in services:
            details = codesign('-d', '--verbose=4').stderr.decode(errors='replace')
            if 'Signature=adhoc' not in details:
                raise RuntimeError('audio compatibility signing requires an ad-hoc playtest app')
            entitlements[MACH_LOOKUP] = [*services, AUDIO_SERVICE]
            log.write('signing sandbox CoreAudio service allowance; existing entitlements preserved\n'); log.flush()
            with tempfile.TemporaryDirectory(prefix='yorimichi-signing-') as scratch:
                path = Path(scratch) / 'audio.entitlements'
                path.write_bytes(plistlib.dumps(entitlements))
                codesign('--force', '--sign', '-', '--preserve-metadata=identifier,requirements,flags',
                         '--entitlements', str(path))
            applied = plistlib.loads(codesign('-d', '--entitlements', '-', '--xml').stdout)
            if applied != entitlements:
                raise RuntimeError('signed app entitlements do not match the preserved audio allowance')
    codesign('--verify', '--deep', '--strict')


def package_zip(root, log):
    """Zip the archived .app for download (ditto keeps its symlinks, signature and permissions), split it into parts
    when it is too large for a GitHub release asset, and record sizes and SHA-256 checksums. Every phase is bounded and
    reports progress."""
    # The download is a folder: the .app, a launcher carrying the desktop profile, and how to start it. A fresh
    # archive moves in; a retry after a failed zip reuses the app already moved.
    folder = root / 'Yorimichi'
    archived = sorted((root / 'archive').glob('*/*.app'))
    if len(archived) > 1:
        raise RuntimeError(f'expected one archived .app under {root / "archive"}, found {len(archived)}')
    for candidate in archived or folder.glob('*.app'):
        staged_data(candidate)   # before anything moves, so a refused package leaves the archive as it was
    if archived:
        shutil.rmtree(folder, ignore_errors=True); folder.mkdir()
        archived[0].rename(folder / archived[0].name)
    apps = sorted(folder.glob('*.app'))
    if len(apps) != 1:
        raise RuntimeError(f'no packaged .app under {root / "archive"} or {folder}')
    app = apps[0]
    audio_compatibility(app, log)
    launcher = folder / 'Play Yorimichi.command'
    launcher.write_text(desktop_preview().packaged_launcher()); launcher.chmod(0o755)
    (folder / 'README.txt').write_text(PLAYTEST_README)
    revision = subprocess.run(['git', 'rev-parse', '--short=8', 'HEAD'], cwd=REPO, capture_output=True, text=True).stdout.strip()
    name = f'Yorimichi-macOS-{revision or "local"}'
    for old in [*root.glob('Yorimichi-macOS-*'), root / 'manifest.json', root / 'SHA256SUMS']:
        old.unlink(missing_ok=True)
    archive = root / f'{name}.zip'
    bounded(['ditto', '-c', '-k', '--sequesterRsrc', '--keepParent', str(folder), str(archive)], log, 'zip', lambda: [archive])
    files = [archive]
    if archive.stat().st_size > PART_BYTES:
        prefix = root / f'{name}.zip.part-'
        bounded(['split', '-b', str(PART_BYTES), '-a', '2', str(archive), str(prefix)], log, 'split',
                lambda: list(root.glob(f'{name}.zip.part-*')))
        archive.unlink()
        files = sorted(root.glob(f'{name}.zip.part-*'))
    entries, started, spoken = [], time.monotonic(), time.monotonic()
    for f in files:
        digest = hashlib.sha256()
        with f.open('rb') as handle:
            for block in iter(lambda: handle.read(1 << 20), b''):
                digest.update(block)
                now = time.monotonic()
                if now - started > PACKAGE_PHASE_SECONDS:
                    raise RuntimeError(f'checksums exceeded {PACKAGE_PHASE_SECONDS} s')
                if now - spoken >= PACKAGE_PROGRESS_SECONDS:
                    spoken = now; line = f'checksum: {f.name}, {(now - started) / 60:.1f} min'
                    log.write(line + '\n'); log.flush()
        entries.append({'file': f.name, 'bytes': f.stat().st_size, 'sha256': digest.hexdigest()})
    (root / 'SHA256SUMS').write_text(''.join(f"{e['sha256']}  {e['file']}\n" for e in entries))
    manifest = {'app': app.name, 'launcher': launcher.name, 'revision': revision, 'zip': f'{name}.zip', 'split': len(files) > 1, 'files': entries}
    (root / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    for e in entries:
        log.write(f"packaged {e['file']} {e['bytes'] / 2**30:.2f} GiB sha256 {e['sha256']}\n")



def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--out', type=Path, required=True, help='the package folder: archive/ in, release files out')
    args = parser.parse_args(argv)
    package_zip(args.out, sys.stdout)
    print('PACKAGE ARCHIVE COMPLETE', flush=True)


if __name__ == '__main__':
    main()
