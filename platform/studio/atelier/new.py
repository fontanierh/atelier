"""Start a new game: `atelier new <id> [--title "My Game"]`.

Copies the sandbox (games/sandbox: a capsule character on a flat test ground, the live bridge, streaming) into
games/<id>, renaming the Unreal module, its classes, the project, config and content paths, and giving the project its
own ID. `atelier build <id>` then compiles it and makes its level; `atelier play <id>` runs it.
"""
import re, subprocess, uuid
from pathlib import Path

from . import paths

TEMPLATE = 'sandbox'


def module_name(game_id):
    """my_game -> MyGame: the Unreal module, target and class prefix."""
    return ''.join(part[:1].upper() + part[1:] for part in re.split(r'[_-]+', game_id) if part)


def main(game_id, title=None):
    if not re.fullmatch(r'[a-z][a-z0-9_]{1,31}', game_id):
        raise SystemExit('a game id is lowercase letters, digits and underscores, starting with a letter (my_game)')
    target = paths.GAMES / game_id
    if target.exists():
        raise SystemExit(f'{target} already exists')
    module = module_name(game_id)
    title = title or ' '.join(part.capitalize() for part in game_id.split('_'))
    source = paths.GAMES / TEMPLATE
    files = subprocess.run(['git', 'ls-files', '--', str(source)], cwd=paths.REPO, capture_output=True, text=True,
                           check=True).stdout.split()
    if not files:
        raise SystemExit(f'the template {source} is not in git')

    def rename(text):
        text = text.replace('SANDBOX_API', module.upper() + '_API')
        text = text.replace('Sandbox', module).replace('sandbox', game_id)
        return text

    for rel in files:
        src = paths.REPO / rel
        dst = target / rename(str(src.relative_to(source)))
        dst.parent.mkdir(parents=True, exist_ok=True)
        data = src.read_bytes()
        try:
            text = rename(data.decode())
            if src.name == 'game.toml':
                text = re.sub(r'^title = "[^"]*"', f'title = "{title}"', text, flags=re.M)
                text = re.sub(r'^# .*\n(# .*\n)*', f'# {title}: a new game on Atelier, started from the sandbox.\n', text, count=1)
            if src.name == 'DefaultEngine.ini':
                text = re.sub(r'ProjectID=[0-9A-F]+', 'ProjectID=' + uuid.uuid4().hex.upper(), text)
            if src.name == 'README.md' and src.parent == source:
                text = README.format(title=title, id=game_id, module=module)
            dst.write_text(text)
        except UnicodeDecodeError:
            dst.write_bytes(data)
    print(f'{title}: games/{game_id} (module {module}). Next:\n'
          f'  atelier build {game_id}      # compile and make the level (about a minute)\n'
          f'  atelier play {game_id}\n'
          f'  atelier live state          # while it runs: the live bridge answers')
    return 0


README = """# {title}

A game on Atelier, started with `atelier new {id}` from the sandbox: a capsule character on a flat test ground with
the live bridge on. The Unreal project is `unreal/{module}.uproject`; the C++ module is `{module}`.

```sh
atelier build {id}          # compile the module and make the level (unreal/Scripts/make_level.py)
atelier play {id}           # WASD / left stick, mouse / right stick, Space / A
atelier live state          # while it runs
```

Where to go from here: enable more platform plugins in `unreal/{module}.uproject` (Skate, AtelierFX, AtelierStream)
and set their sections in `unreal/Config/DefaultGame.ini`; add build steps to `build.py` for your own generators and
imports; put characters under `assets/characters/<name>/` with a `character.toml`. The repository README walks through
each.
"""
