# Independent native audio ownership
Normal world import preserves receiving packages for current validation instead of purging its
namespace upfront. The exact purge-removal transition and current mesh checks are owned by the
world importer. Audio does not add preservation branches to the shared geometry catalogue:
that would invalidate unrelated source generators. The sound importer depends on its six
source audio producers and saved-type module, rather than a world import.
All six producers publish complete WAV-folder products; the importer reads their actual byte
identities, including changed or missing generated waves, rather than only producer fingerprints.
Its native product inventories every wave directory, both fixed footstep packages and their
sidecars, and all six import reports; a missing required member cannot remain a complete product.
Each imported wave, attenuation and library must report a successful save and leave its regular
primary package on disk before the importer can report success. An in-memory registry entry is
insufficient, including on a first partial-directory publication.
JapanFootstepSet and JapanFootstepBank live in YorimichiAssets; the runtime component stays in
Yorimichi. Class/struct redirects retain previously saved package identities. The types' fields,
defaults and Find implementation are unchanged. Native compilation and an old-library redirect/load/runtime-consumer check are required at a
stopped receiver boundary. A headless sample-consumer test does not establish audible playback quality.
The initial type move and redirect configuration change require an ordinary compile and can
revalidate other configuration-bound imports once. No old fingerprints or producer evidence
are adopted to hide that transition. Later preparation-only library changes leave this audio
owner current when the actual saved-type module, configuration, audio and importer inputs match.

The offline sound profile follows an explicit asset-module revalidation witness: every runtime
component body and the moved lookup body is byte-identical, while the current source hashes
also bind the new saved-type implementation/header. This is source proof, not listening proof.
