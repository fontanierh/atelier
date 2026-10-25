# Tools

The Python that exports assets (`../assets/README.md` describes an asset folder). Run it from `games/hakuba`:

```sh
uv run --project tools export assets/characters/nox     # export one asset folder
uv run --project tools export --check assets            # list the exports whose inputs changed
```

```text
tools/
  pyproject.toml            the package, its dependencies and the `export` command
  uv.lock                   the exact dependency versions
  hakuba_tools/
    export.py               the `export` command: runs the exporter an asset's kind names, records its inputs
    character.py            the `character` exporter
    gltf.py                 reading, editing and writing .glb files
```

## Kinds

Each kind is one module with an `export(folder, settings)` function that writes `<folder name>.glb` and returns
the paths it wrote. `export.py` maps each `kind` to its module.

**`character`** exports a character's model: scaled to its height, textures resized, morph targets removed.

| Setting        | Meaning                                     |
|----------------|---------------------------------------------|
| `source`       | the model, relative to the asset folder     |
| `height_m`     | how tall the character stands in the game   |
| `texture_size` | the largest side of any texture, in pixels  |

## Inputs checksum

`inputs_sha256` in `asset.toml` covers the asset's settings, every file in its `src/` and every file in
`hakuba_tools/`. Changing any of them marks the export out of date until it is exported again.
