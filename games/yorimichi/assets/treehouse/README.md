# Tree house art

The paintings and models behind the hidden tree house on the west hillside. Every image here is a compact JPEG copy
of the PNG the image model returned, and every model has its texture made smaller, so the folder stays small enough
for git. The full-size originals are kept outside the repository.

| Folder | What it holds | Made with |
| --- | --- | --- |
| `concepts/` | Ten concept paintings: five views (glimpse, reveal, lookout, overview, room), each by day and at dusk. JPEG, 1536 x 1024. | `gpt-image-2.5-sunburst`, quality high, steered by stills of the game |
| `refs/` | One reference painting per view of the tree house (22 views), plus `master.jpg`, the aerial overview that set the look of every place. `cameras.json` and `places.json` give the camera of each view and the position of each place. JPEG, 1536 x 1024. | `gpt-image-2.5-sunburst`, quality high, painted over the in-game blockout |
| `textures/` | 15 tileable surfaces (planks, bark, shingles, plaster, cloth...) and 11 pictures (noren, map, quilt, rugs, flag...). JPEG, 1024 x 1024, full colour resolution. | `gpt-image-2.5-sunburst`, quality high |
| `props/<slug>/` | 13 hero props (backpack, barrel, basket, bell, bookshelf, crate desk, futon, globe, kamado, log table, planter, stump kettle, telescope): `<slug>.glb` with a 1024 JPEG texture, `concept.jpg`, `asset.toml` and the Tripo `job.json`. | concept by `gpt-image-2.5-sunburst`, quality high; model by Tripo P2 image-to-model |

Each painting has its prompt (`*.prompt.txt`, or `prompt.txt` for a prop) and its provenance (`*.provenance.json`):
the model, quality, size, the context images it was given, token usage and hashes. `compact_copy` in the provenance
says how the JPEG was made. For the paintings made before this folder existed, the hashes are of the full-size files
the API saw and returned, not of the JPEGs here. The models keep their geometry exactly as Tripo made it; only the
embedded texture was re-encoded.

## Making them again

The tools are in `games/yorimichi/tools/`. They read and write this folder, skip what is already here and keep API
keys in the environment (`OPENAI_API_KEY`, `TRIPO_API_KEY`, or the ignored `.env`).

    uv run python games/yorimichi/tools/treehouse_concepts.py [--only room-day] [--dry-run]
    uv run python games/yorimichi/tools/treehouse_refs.py [--only master] [--dry-run]
    uv run python games/yorimichi/tools/treehouse_textures.py paint [--only bark] [--dry-run]
    uv run python games/yorimichi/tools/treehouse_textures.py finish
    uv run python games/yorimichi/tools/treehouse_props.py concept|model|sheet [--only bell] [--dry-run]

- `treehouse_textures.py finish` needs no network: it turns the JPEGs in `textures/` into the game-ready textures and
  `textures.json` in `build/yorimichi/treehouse/textures/`.
- To repaint something, rename its JPEG to `<name>.rejected-1.jpg` (these stay out of git) and run the tool again.
  `treehouse_props.py concept` always repaints and sets the old concept aside itself.
- `treehouse_props.py model` only asks Tripo for a new model when the concept changed since `job.json` was made. Raw
  downloads and private API responses stay in `build/yorimichi/treehouse/tripo/`.
- The concept and reference tools also need pictures that are not in git: the plan views
  (`build/yorimichi/review/treehouse/plan/`, from `world/regions/treehouse/plan_views.py`), the blockout captures
  (`build/yorimichi/treehouse/captures/blockout-r01/`) and the scouting stills (`build/yorimichi/treehouse/scout/`).
  The tools list whatever is missing before any call is made.
