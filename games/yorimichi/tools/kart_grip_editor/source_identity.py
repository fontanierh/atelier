"""Portable identities for the prepared character model that an authored grip was inspected against."""
import hashlib
import json
from pathlib import Path
import tomllib

GAME = Path(__file__).resolve().parents[2]
ROOT = GAME.parents[1]
CHARACTERS = GAME / 'assets/characters'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def playable_ids():
    return tuple(sorted(p.parent.name for p in (GAME / 'assets/characters').glob('*/character.toml')
                        if (p.parent / 'adventure.toml').is_file() and
                        tomllib.loads(p.read_text()).get('role', 'player') == 'player'))


def profile_path(character, characters=CHARACTERS):
    """@cc [owner:fontanierh,label:architecture] character-owned-kart-grips
    Authored kart grips and prepared-model identities MUST live beside their character
    definition. Shared kart tooling MUST discover those files from the playable roster;
    a runtime aggregate MUST be generated, never a second authored source of truth.
    """
    return characters / character / 'kart-grip.json'


def model_path(character, characters=CHARACTERS):
    return characters / character / 'kart-grip-model.json'


def prepared_models(characters=CHARACTERS):
    """Collect character-owned identities for the generated runtime table."""
    models = {}
    for name in playable_ids():
        entry = json.loads(model_path(name, characters).read_text())
        if entry.get('schema') != 1 or entry.get('character') != name:
            raise ValueError(f'{name}: invalid prepared-model receipt')
        models[name] = {key: value for key, value in entry.items() if key not in ('schema', 'character')}
    return {'schema': 1, 'models': models}


def source_paths(character):
    folder = GAME / 'assets/characters' / character
    definition = tomllib.loads((folder / 'character.toml').read_text())
    # Only inputs that decide the prepared skeleton, skin and outfit. Animation builds
    # (combat-build.json, locomotion-build.json, adventure.toml) and authoring notes do
    # not invalidate an authored grip. The pipeline files here are the shared rig/skin
    # path, not the animation fitting and inspection tools.
    paths = {folder / definition['source'], folder / 'character.toml', folder / 'source-manifest.json'}
    paths.update(folder / name for name in ('export_hooks.py', 'outfit_correctives.py') if (folder / name).is_file())
    paths.update((folder / 'outfits').glob('*.toml'))
    pipeline = GAME / 'assets/characters' / 'pipeline'
    paths.update(pipeline / name for name in ('definition.py', 'export.py', 'rig.py'))
    paths.add(ROOT / 'platform/studio/atelier/character/names.py')
    paths.add(ROOT / 'platform/conventions/rigs/humanoid.toml')
    return tuple(p for p in sorted(paths) if '__pycache__' not in p.parts)


def source_identity(character):
    return digest({str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in source_paths(character)})


def register(models, characters=CHARACTERS):
    """@cc [owner:fontanierh,label:correctness] kart-prepared-model-identity
    A registered grip MUST identify the inspected model bytes and bind frames, with an
    independently verified current character-source identity. Production validation MUST
    reject stale receipts and MUST NOT derive its expected identity from the pose itself.
    """
    receipt = {}
    for path in sorted(characters.glob('*/kart-grip.json')):
        pose = json.loads(path.read_text())
        name = pose['character']
        if name != path.parent.name:
            raise ValueError(f'{path}: grip belongs to a different character')
        meta = json.loads((models / f'{name}.json').read_text())
        checksum = hashlib.sha256((models / f'{name}.glb').read_bytes()).hexdigest()
        if checksum != meta.get('model_sha256'):
            raise ValueError(f'{name}: prepared GLB does not match its export metadata; re-export it before registering')
        # A re-export whose bind is unchanged may carry the authored poses forward. The
        # receipt records the new model bytes; the save is updated below so the editor
        # no longer reports it as stale. A real bind or scale change still needs a save.
        if digest(pose['bind_world']) != digest(meta['bind_world']):
            raise ValueError(f'{name}: saved bind does not match the prepared model; re-author the grip')
        if abs(pose['scale'] - meta['scale']) > 1e-5:
            raise ValueError(f'{name}: prepared scale changed; re-author the grip')
        current = source_identity(name)
        if meta.get('source_sha256') != current:
            raise ValueError(f'{name}: character rig/skin sources changed; re-export and re-register the prepared model')
        bind = digest(meta['bind_world'])
        if digest(pose['bind_world']) != bind:
            raise ValueError(f'{name}: saved bind does not match the prepared model')
        receipt[name] = {'model_sha256': checksum, 'bind_sha256': bind, 'source_sha256': current,
                         'scale': meta['scale'], 'seated_world': {n: meta['seated_world'][n]
                         for n in ('pelvis', 'upperarm_L', 'upperarm_R')}}
        if pose.get('model_sha256') != checksum:
            pose['model_sha256'] = checksum
            path.write_text(json.dumps(pose, indent=2) + '\n')
        target = model_path(name, characters)
        temporary = target.with_name('.' + target.name + '.tmp')
        temporary.write_text(json.dumps({'schema': 1, 'character': name, **receipt[name]}, indent=2)+'\n')
        temporary.replace(target)
    return receipt


if __name__ == '__main__':
    print('Registered', ', '.join(register(ROOT / 'build/yorimichi/kart-grip-editor',
                                         CHARACTERS)))
