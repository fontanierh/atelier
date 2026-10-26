# Assets

Everything the game loads, each next to the sources it is exported from.

```text
assets/
  animations/
    idle/                   the idle, on the rig
  characters/
    nox/                    Nox, the playable character, with every animation fitted to him
  world/                    the world, in tiles
    src/ground/             the ground's heights, in pages 512 m wide
    src/regions/            one folder per region, with its layout
    tiles/                  each tile in full and middle detail, and `checksums.toml`: what each was made from
```

## An asset folder

Every asset is one folder, named in kebab case:

```text
<asset-name>/
  asset.toml                its kind, its settings, and the checksum of its inputs
  <asset-name>.glb          what the game loads, written by the exporter
  src/                      everything the .glb is exported from
```

The game loads `<asset-name>.glb` and what the export writes beside it, such as the world's `tiles/`. The browser
build copies the folder without `src/`, `asset.toml` and the tile checksums (see `../Trunk.toml`).

`src/` holds every input of the export, so a clone can export the `.glb` again exactly. A source made by hand, such
as `characters/nox/src/model.glb`, is committed as it is. A `.rs` file in `src/` holds the asset's own choices
in code; the exporter compiles it in (`../tools/README.md` says what belongs in an asset and what in the exporter).

`kind` in `asset.toml` picks the exporter, and the other keys are its settings (`../tools/README.md` lists them).
The exporter writes `inputs_sha256`; do not edit it.

The export does all the optimizing, such as shrinking textures, so the committed `.glb` is the final file.

## Exporting

Each `.glb` is committed next to its sources, so a checkout runs the game without exporting anything. After
changing an asset's settings or sources, export it and commit both together:

```sh
cargo export assets/characters/nox     # from games/hakuba
cargo export --check assets            # lists every export whose inputs changed
```

## Storage

`.glb` and `.bin` files are stored in Git LFS (`../.gitattributes`). `git push` uploads them.
