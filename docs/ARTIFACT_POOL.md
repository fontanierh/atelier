# Independent artifact pooling

Keep a complete playable canonical checkout warm. Feature worktrees keep independent generated
files; all share the installed engine and its local derived-data cache. Never share mutable Unreal
`Content`, `Binaries`, `Intermediate` or PCH trees. Cache hits must describe actual successful output,
not hide missing inputs or failed builds.

## Portable output pool

`atelier pool` is an initial, opt-in pool for independently generated Python outputs. The recipe
must declare exclusively owned `pool_roots`, no dependencies, and only Python commands. Yorimichi
currently opts in the Hidamari, tree-house and community-park texture finishing steps. All other
steps refuse pooling. Pool entries stay in the machine-local ignored cache; licensed/private output
must never be added to Git or uploaded to a public artifact store.

After a successful build records the new pool context, publish it at a render release:

```sh
uv run atelier pool publish yorimichi world.hidamari_textures
```

In another feature checkout, sync its locked Python environment, check the pool, then restore:

```sh
uv sync
uv run atelier pool status yorimichi world.hidamari_textures
uv run atelier pool restore yorimichi world.hidamari_textures
uv run atelier build yorimichi world.hidamari_textures
```

The key combines source/command fingerprint, declared output ownership, platform/architecture,
Python interpreter bytes/version, installed package versions, dependency lock and studio Python
support files. It deliberately excludes whole Git revision, so unrelated feature changes can hit.
All output files are inventoried and SHA-256 checked before publication and restoration. Entries
publish atomically; a repeated key with different bytes refuses to overwrite the first entry.
Restores are independent APFS clones where available, regular copies elsewhere. Symlinks refuse.
A failed/interrupted restore removes its stamp before replacing files and cannot certify completion.

Publish/restore take the normal render mutex for actual file transfer; they fail promptly when busy.
Read the machine ledger/telemetry and coordinate these useful short turns. `status` only reads cache
availability; restoration also verifies every file. Legacy and `--touch` stamps cannot publish: a real
successful build must have recorded the matching pool key. A miss leaves ordinary incremental build
as the fallback. This first pool is explicit, rather than silently changing every build's behavior.

## Full game and feature integration

| Artifact | Current safe workflow |
| --- | --- |
| Complete generated game plus compiled module | `atelier reuse` from a clean complete checkout at exactly the same revision and engine; then incremental build |
| Opted-in portable texture folders | Publish/restore matching pool key with full output hashes; independent copies |
| Other generated Blender/character/audio outputs | Keep them warm; extend recipe ownership and tool/dependency manifests before enabling cross-branch pooling |
| Unreal imported assets | Keep complete source/output proof; normal incremental import unless a targeted delta proves the full changed-content allowlist, collision/material contracts and unaffected asset hashes |
| C++ and PCH | Compile incrementally per worktree; no shared mutable Intermediate or cross-branch Binaries certification |
| Shaders/derived data | Reuse the engine's existing local per-user DDC; prewarm only the actual renderer/profile needed |

A geometry or texture pool does not certify an Unreal import, shader profile or compiled ABI. Main
must still rebuild/import each affected step and pass its validators after feature integration.
Community-park source changes affect terrain, vegetation and map inputs as well as park assets;
copying the park alone is insufficient. Do not blanket-touch stamps or clear generated assets/DDC.

Next candidates are isolated Blender outputs with verified Blender/runtime context and full consumed
dependency output manifests. Region-owned Unreal imports and a cheap map assembly step would address
the large broad-world import cost. Those require ownership and collision/layout proofs before reuse.
A future shared DDC or compiler cache is separate from portable asset pooling and must retain local
fallback and real toolchain/header/flag keys; it never means sharing mutable intermediate directories.
