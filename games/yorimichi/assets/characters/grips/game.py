"""The grip poser's saved grips for the game: each hand's place on its prop and each finger bone's turn, in the game's frames.

    uv run python games/yorimichi/assets/characters/grips/game.py --character modori [--source DIR]

Reads build/yorimichi/grips/<character>/poses.json (the poser's saves), moments.json (each prop's mesh in its handle's
frame) and body.glb (the rest skeleton), or those in DIR (grips/<character>/ holds the committed copy), and writes
games/yorimichi/unreal/Content/Data/<character>/grips.json, which the move set reads (UAdventureMoveSet::ReadGrips) to hold
every grip exactly as posed, in every clip:

- `hand`: the hand bone's place in the prop's own frame (its mesh's, in the game's centimetres): `location`, and
  `rotation`, which the game turns onto its own bone frame: the bone's component rotation is `rotation` times its
  reference pose's;
- `bones`: each finger bone's turn on its parent, likewise: its local rotation is the parent's reference rotation
  inverted, times `rotation`, times its own reference rotation.

A glTF point (x, y, z) in metres is the game's (x, z, y) / 100 (export.py), a reflection G; a turn R in glTF's frame is
G R G in the game's. The props' meshes are ReferenceSword.glb and ReferenceGlider.glb in their game frames (centimetres) the same way.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent)); from moments import DIGITS, Glb, quaternion, rotation  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'world')); import yori  # noqa: E402

G = np.array([[1., 0., 0.], [0., 0., 1.], [0., 1., 0.]])


def turn(R):
    """A glTF turn in the game's frame, as a quaternion (x, y, z, w)."""
    return [round(float(v), 7) for v in quaternion(G @ R @ G)]


def unit(M):
    return M[:3, :3] / np.linalg.norm(M[:3, :3], axis=0)


def placed(p):
    """A {position, quaternion, scale} placement as a 4x4 matrix."""
    M = np.eye(4)
    M[:3, :3] = rotation(p['quaternion']) * p.get('scale', 1.)
    M[:3, 3] = p['position']
    return M


def main(args):
    source = args.source or yori.OUT / 'grips' / args.character
    poses = json.loads((source / 'poses.json').read_text())
    moments = {g['id']: g for g in json.loads((source / 'moments.json').read_text())['grips']}
    glb = Glb(source / 'body.glb')
    names = [n.get('name', '') for n in glb.json['nodes']]
    index = {n: i for i, n in enumerate(names)}
    parent = {c: i for i, n in enumerate(glb.json['nodes']) for c in n.get('children', [])}
    rest = {i: unit(M) for i, M in glb.worlds().items()}
    out = {}
    for gid, st in poses['grips'].items():
        d = st.get('derived')
        if gid not in moments or not d or not st.get('params'):
            continue
        g, side = moments[gid], moments[gid]['side']
        hand = index[f'hand_{side}']
        # The hand in the prop mesh's own frame: the mesh placed in the handle's frame by P (scale s).
        pm = g['prop_mesh']
        Rp, tp, s = rotation(pm['quaternion']), np.asarray(pm['position']), pm['scale']
        # The hand as the poser holds it (app.js holdOf): its moment's place, then the offset the user gave it.
        hold = placed(g['moments'][st['anchor']]['hand']) @ placed(st['offset']) if st.get('offset') else placed(g['moments'][st['anchor']]['hand'])
        Rh, ph = unit(hold), hold[:3, 3]
        location = G @ (Rp.T @ (ph - tp) / s) * 100.
        # Each digit bone's place from its parent's, the hand's as placed and every other bone at its rest turn.
        posed = {hand: Rh}

        def world(i):
            if i not in posed:
                p = parent[i]
                local = rotation(d['quaternions'][names[i]]) if names[i] in d['quaternions'] else rest[p].T @ rest[i]
                posed[i] = world(p) @ local
            return posed[i]
        bones = {}
        for digit in DIGITS:
            for name in (n.format(s=side) for n in digit):
                i, p = index[name], parent[index[name]]
                bones[name] = {'parent': names[p], 'rotation': turn(rest[p] @ (world(p).T @ world(i)) @ rest[i].T)}
        out[gid] = {'prop': g['prop'], 'side': side, 'status': st.get('status'), 'anchor': st.get('anchor'),
                    'hand': {'location': [round(float(v), 4) for v in location], 'rotation': turn(Rp.T @ Rh @ rest[hand].T)},
                    'bones': bones}
    target = yori.GAME / 'unreal' / 'Content' / 'Data' / args.character / 'grips.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    record = {'character': args.character, 'source': {'poses_sha256': hashlib.sha256((source / 'poses.json').read_bytes()).hexdigest(),
                                                       'saved': poses.get('saved')}, 'grips': out}
    # who saved it (a Tailscale login) stays out of the game's data
    if isinstance(record['source']['saved'], dict):
        record['source']['saved'] = {k: v for k, v in record['source']['saved'].items() if k != 'by'}
    target.write_text(json.dumps(record, indent=1) + '\n')
    print('GRIPS FOR THE GAME', target.relative_to(yori.REPO), sorted(out), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--character', default='modori')
    parser.add_argument('--source', type=Path, help="the poser's files (default build/yorimichi/grips/<character>/)")
    main(parser.parse_args())
