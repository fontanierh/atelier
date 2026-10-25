# Assets

Everything the game loads, each next to the sources it is exported from.

```text
assets/
  characters/
    nox/                    Nox, the playable character
```

## An asset folder

Every asset is one folder, named in kebab case:

```text
<asset-name>/
  asset.toml                its kind, the settings its exporter reads, and the checksum of its inputs
  <asset-name>.glb          what the game loads, written by the exporter
  src/                      every source the .glb is exported from, and nothing else
```

The game loads only `<asset-name>.glb`. The browser build leaves out `asset.toml` and `src/` (see `../Trunk.toml`).

`src/` holds everything that goes into the export, so the `.glb` can be exported again exactly from a clone. A
source made by hand, such as `characters/nox/src/Nox.glb`, is committed as it is.

Assets have no scripts of their own. `kind` picks one exporter in `../tools/export/`, and the other settings in
`asset.toml` are what that exporter reads (`../tools/README.md` lists the kinds and their settings). The exporter
writes `inputs_sha256`; do not edit it.

Optimization, such as smaller textures, happens during export, so the committed `.glb` is the final file.

## Exporting

Exports are not part of the build: the exported `.glb` is committed next to its sources, so every checkout runs
the game straight away. After changing an asset's settings or sources, export it and commit both together:

```sh
cargo export assets/characters/nox     # from games/hakuba
cargo export --check assets            # lists every export whose inputs changed
```

## Storage

`.glb`, `.blend`, `.ktx2` and `.png` files are stored in Git LFS (`../.gitattributes`). The repository's pre-push
hook uploads them.
