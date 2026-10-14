"""Run the upstream contract checker over source files, without traversing generated assets."""
import argparse
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

from . import paths


SUFFIXES = {'.py', '.pyi', '.ts', '.tsx', '.go', '.rs'}


def source_files(repo):
    names = subprocess.check_output(['git', '-C', str(repo), 'ls-files', '-z', '--cached',
                                     '--others', '--exclude-standard']).decode().split('\0')
    return sorted({Path(name) for name in names if name and
                   (Path(name).name == 'CONTRACTS' or Path(name).suffix in SUFFIXES) and
                   (repo / name).exists()})


def check(repo=paths.REPO):
    """@cc [owner:fontanierh,label:correctness] contract-check-scope
    Check tracked and nonignored source files, including new CONTRACTS files, without scanning
    generated output trees. Every directive MUST name only fontanierh as its owner. This command
    validates syntax and ownership, not whether the implementation satisfies the prose.
    """
    repo = Path(repo).resolve()
    checker = repo / 'platform/studio/contracts/node_modules/.bin/cc-check'
    if not checker.is_file():
        raise SystemExit('Install contract tools first: npm ci --prefix platform/studio/contracts')
    files = source_files(repo)
    errors = []
    with tempfile.TemporaryDirectory(prefix='atelier-contracts-') as directory:
        mirror = Path(directory)
        for relative in files:
            source = repo / relative
            if source.is_symlink():
                errors.append(f'{relative}: contract source must not be a symlink')
                continue
            content = source.read_text()
            for directive in re.finditer(r'@cc\s+\[([^\]]*)\]', content):
                owners = re.findall(r'(?:^|,)\s*owner:([^,]+)', directive[1])
                if owners != ['fontanierh']:
                    line = content.count('\n', 0, directive.start()) + 1
                    errors.append(f'{relative}:{line}: contract owner must be fontanierh')
            destination = mirror / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        # A single parser process is much faster than launching Node once per source file. The
        # source-only mirror preserves ancestor CONTRACTS discovery and excludes build outputs.
        (mirror / '.git').mkdir()
        print(f'Checking contract syntax and owners in {len(files)} source files...', flush=True)
        started = time.monotonic()
        with subprocess.Popen([str(checker), 'format'], cwd=mirror, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
            while True:
                try:
                    stdout, stderr = process.communicate(timeout=25)
                    break
                except subprocess.TimeoutExpired:
                    elapsed = int(time.monotonic() - started)
                    print(f'Contract parser still running after {elapsed}s; waiting for its result.', flush=True)
                    if elapsed >= 300:
                        process.kill()
                        process.communicate()
                        raise SystemExit('Contract parser exceeded five minutes; inspect the source scope before retrying')
            code = process.returncode
        if code:
            print(stderr or stdout)
    for error in errors:
        print(error)
    print(f'{len(files)} source files: contract syntax/owners ' +
          ('failed' if code or errors else 'passed (semantic review still required)'))
    return 1 if code or errors else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['check'])
    parser.parse_args(argv)
    return check()


if __name__ == '__main__':
    raise SystemExit(main())
