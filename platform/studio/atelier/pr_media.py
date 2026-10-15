"""`atelier pr-media push <key> FILE...`: publish PR screenshots and films outside every default clone.

Each file goes into a commit under `refs/pr-media/<key>` (the PR number, or a branch-like slug before the PR exists).
Default clones and fetches take only branches and tags, so nobody downloads these commits; a `git clone --mirror` does.
GitHub serves a file of such a commit at `https://raw.githubusercontent.com/<owner>/<repo>/<commit>/<name>`, and its
Markdown shows images inline. The command prints one ready-to-paste Markdown line per file.

Only git plumbing runs (hash-object, mktree, commit-tree, fetch, push): the worktree, index, HEAD and branches are never
touched. When the remote already has the ref, the new commit starts from its tree (same-named files are replaced) and has
it as parent, so links to earlier commits keep working. The push is a fast-forward, never forced. The local
`refs/pr-media/<key>` caches the remote's ref. `--dry-run` builds the commit and prints its links without pushing.
"""
import re, subprocess, sys, urllib.parse
from pathlib import Path

PREFIX = 'refs/pr-media/'
IMAGES = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'}
VIDEOS = {'.mp4', '.mov', '.webm'}
MAX_BYTES = 50 * 1024 * 1024    # refused above this
WARN_BYTES = 10 * 1024 * 1024   # warned above this
KEY = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,99}')


def say(text):
    print(text, file=sys.stderr, flush=True)


def git(*args, repo=None, stdin=None):
    result = subprocess.run(['git', *args], cwd=repo, input=stdin, capture_output=True)
    if result.returncode:
        detail = result.stderr.decode(errors='replace').strip()
        raise SystemExit(f'git {args[0]} failed: {detail}')
    return result.stdout.decode(errors='replace').strip()


def check_key(key):
    if not KEY.fullmatch(key) or '..' in key or key.endswith(('.', '.lock')):
        raise SystemExit(f'pr-media key {key!r} must be a PR number or a slug of letters, digits, ".", "_" and "-" '
                         '(one ref component: no "/")')
    return PREFIX + key


def check_files(files):
    """The files as Paths, refusing missing, non-media, oversized and duplicate-named ones; warns about large ones."""
    checked, names = [], set()
    for name in files:
        path = Path(name)
        if not path.is_file():
            raise SystemExit(f'{name}: not a regular file')
        if path.suffix.lower() not in IMAGES | VIDEOS:
            raise SystemExit(f'{name}: not a media file ({", ".join(sorted(IMAGES | VIDEOS))})')
        if path.name in names:
            raise SystemExit(f'{name}: another file in this call is also named {path.name!r}')
        names.add(path.name)
        size = path.stat().st_size
        if size > MAX_BYTES:
            raise SystemExit(f'{name}: {size / 2**20:.1f} MiB is over the {MAX_BYTES // 2**20} MiB limit; '
                             'compress it (JPEG for stills, MP4 for films)')
        if size > WARN_BYTES:
            say(f'warning: {name} is {size / 2**20:.1f} MiB; a compressed JPEG or MP4 loads faster in the PR')
        checked.append(path)
    return checked


def github_repository(url):
    """(owner, repo) of a GitHub remote URL, https or ssh."""
    match = re.search(r'github\.com[:/]+([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+?)(?:\.git)?/?$', url)
    if not match:
        return None
    return match[1], match[2]


def remote_repository(remote, repo=None):
    """(owner, repo) from the remote's configured URL (before any insteadOf rewrite), or from `remote` given as a URL."""
    url = subprocess.run(['git', 'config', '--get', f'remote.{remote}.url'], cwd=repo, capture_output=True,
                         text=True).stdout.strip() or remote
    found = github_repository(url)
    if not found:
        raise SystemExit(f'remote {remote!r} is not a GitHub repository; links need github.com/<owner>/<repo>')
    return found


def markdown(owner, name, sha, filename):
    url = f'https://raw.githubusercontent.com/{owner}/{name}/{sha}/{urllib.parse.quote(filename)}'
    text = re.sub(r'([\\\[\]])', r'\\\1', filename)
    if Path(filename).suffix.lower() in VIDEOS:
        return f'[{text}]({url})'   # GitHub does not play raw videos inline
    return f'![{text}]({url})'


def remote_head(remote, ref, repo=None):
    """The remote's commit for `ref`, fetched into the local ref of the same name, or None when it has none."""
    listing = git('ls-remote', remote, ref, repo=repo)
    if not any(line.split('\t')[1:] == [ref] for line in listing.splitlines()):
        return None
    git('fetch', '--no-tags', '--no-write-fetch-head', remote, f'+{ref}:{ref}', repo=repo)
    return git('rev-parse', '--verify', f'{ref}^{{commit}}', repo=repo)


def build_commit(key, paths, parent, repo=None):
    """A commit whose flat tree is the parent's tree with `paths` added or replaced by basename."""
    entries = {}
    if parent:
        for entry in git('ls-tree', '-z', parent, repo=repo).split('\0'):
            if entry:
                entries[entry.split('\t', 1)[1]] = entry
    for path in paths:
        blob = git('hash-object', '-w', '--no-filters', '--', str(path.resolve()), repo=repo)
        entries[path.name] = f'100644 blob {blob}\t{path.name}'
    tree = git('mktree', '-z', repo=repo, stdin=''.join(e + '\0' for e in entries.values()).encode())
    message = f'PR media for {key}: {", ".join(p.name for p in paths)}\n'
    return git('commit-tree', tree, *(['-p', parent] if parent else []), repo=repo, stdin=message.encode())


def push(key, files, remote='origin', dry_run=False, repo=None):
    """@cc [owner:fontanierh,label:correctness] append-only-pr-media
    A pr-media push MUST NOT change the worktree, index, HEAD or branches, and MUST update the remote ref only as a
    fast-forward from the commit it fetched, so every link printed by an earlier push stays reachable.
    """
    ref = check_key(key)
    paths = check_files(files)
    owner, name = remote_repository(remote, repo)
    if subprocess.run(['git', 'check-ref-format', ref], cwd=repo).returncode:
        raise SystemExit(f'{ref} is not a valid ref name')
    parent = remote_head(remote, ref, repo)
    sha = build_commit(key, paths, parent, repo)
    if dry_run:
        say(f'dry run: built {sha} for {ref}' + (f' on {parent}' if parent else '') + '; nothing pushed')
    else:
        result = subprocess.run(['git', 'push', remote, f'{sha}:{ref}'], cwd=repo, capture_output=True,
                                text=True)
        if result.returncode:
            raise SystemExit(f'push to {ref} failed (someone may have pushed it meanwhile; rerun to add on top):\n'
                             f'{result.stderr.strip()}')
        git('update-ref', ref, sha, *([parent] if parent else []), repo=repo)
        say(f'pushed {ref} = {sha}' + (f' (parent {parent})' if parent else ' (new)'))
    for path in paths:
        print(markdown(owner, name, sha, path.name))
    return 0
