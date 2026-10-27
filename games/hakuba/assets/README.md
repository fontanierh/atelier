# Assets

Everything the game loads, each next to the sources it is exported from.

```text
assets/
  animations/               the move set, each clip on the rig, from a motion library
    idle/                   standing
    walk/, run/, sprint/    moving on foot, each a loop
    jump/, run-jump/        jumping from standing and from a run
    fall/                   falling
    land/, run-land/        landing on the spot and running on
    hard-land/, -up/        landing from high up, and standing up again
    hop-left/, -right/      the side hops that dodge, and their landings (`-land`)
    backflip/               the backflip that dodges, and its landing (`backflip-land/`)
    double-jump/            the double jump's tuck and forward somersault
    glide-open/             opening the paraglider, and `glide-open-falling/` while falling fast
    glide/                  hanging under the paraglider, and leaning `-forward`, `-back`, `-left` and `-right`
    glide-close/            closing it on landing
  characters/
    nox/                    Nox, the playable character, with every animation fitted to him
  equipment/
    glider/                 the paraglider, held in both hands above the head
  plants/                   trees, bushes and grass, each built from its settings alone
    maple-a/, maple-b/      maples
    broad-a/, broad-b/      broadleaf trees
    ginkgo-a/, ginkgo-b/    ginkgos
    pine-a/, pine-b/        pines
    cedar-a/, cedar-b/      cedars
    green-bush-a/, -b/      green bushes
    ochre-bush-a/, -b/      bushes of autumn leaves
    flower-bush-a/, -b/     flowering bushes
    grass-a/, grass-b/      tufts of grass
  props/                    made objects, each built from its settings alone
    utility-pole/           a concrete pole with insulators that cables fasten to
    street-lamp/            a lamp's arm and head, standing on a utility pole
  sounds/                   every sound the game plays (sounds/README.md)
    footstep-grass/, ...    a footstep on grass, on gravel (`-gravel`) and on stone (`-stone`)
    dash/                   a burst of cloth and air
    countryside/            birdsong, a breeze and a faint sea, a loop
    glide-wind/             rushing air at three speeds, loops
  textures/
    ground/                 the ground's grass and earth
    road/                   a road's asphalt and lines
    bark/                   tree bark
    painted-metal/          weathered white paint on sheet metal, for the guardrails
    maple-leaves/ ...       the leaves of each kind of plant: maple, ginkgo, ochre and small leaves, pine and
                            cedar needles, and flowers
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
  <asset-name>.glb          what the game loads, written by the exporter (`<asset-name>.ktx2` for a texture,
                            `<asset-name>.ogg` and `<asset-name>.takes.json` for a sound)
  src/                      everything the export is made from, if it is made from more than its settings
```

A plant or generated prop is made from its settings alone, so it has no `src/`; an imported prop keeps its source GLB
there. The game loads the export and what the export
writes beside it, such as the world's `tiles/`. The browser build copies the folder without `src/`, `asset.toml` and
the tile checksums (see `../Trunk.toml`).

`src/` holds every input of the export other than its settings, so a clone can export it again exactly. A source
made by hand, such as `characters/nox/src/model.glb`, is committed as it is. A `.rs` file in `src/` holds the
asset's own choices in code; the exporter compiles it in (`../tools/README.md` says what belongs in an asset and
what in the exporter).

`kind` in `asset.toml` picks the exporter, and the other keys are its settings (`../tools/README.md` lists them).
The exporter writes `inputs_sha256`; do not edit it.

The export does all the optimizing, such as shrinking textures and building their mipmaps, so the committed export
is the final file.

## Textures

A texture more than one asset shows is its own asset under `textures/`: an image in `src/`, exported as a `.ktx2`
with every mipmap level. Other assets name it by its folder name, and their exports point at its file rather than
holding a copy, so repainting a texture changes no other asset's export. A texture only one asset shows stays
inside that asset, such as Nox's skin in his model.

## Exporting

Each export is committed next to its sources, so a checkout runs the game without exporting anything. After
changing an asset's settings or sources, export it and commit both together:

```sh
cargo export assets/characters/nox     # from games/hakuba
cargo export assets                    # every asset, each after the assets it reads
cargo export --check assets            # lists every export whose inputs changed
```

## Storage

`.glb`, `.bin`, `.ktx2`, `.ogg` and `.wav` files are stored in Git LFS (`../.gitattributes`). `git push` uploads them.
