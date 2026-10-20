# Selectable soundbank sources

`catalog.json` contains four complete, stable choices. Original remains the default
and delegates to the existing footstep and skate assets without copying,
regenerating or replacing them. The existing in-game selector consumes the native
registry produced from this catalog; preparation alone does not select a bank.

| Selection | Bank | Committed replacement samples | Source WAV bytes |
| --- | --- | ---: | ---: |
| 0 (default) | Original | Existing assets | Unchanged |
| 1 | Soft Contact | 53 | 2,924,572 |
| 2 | Dry Street | 53 | 2,985,244 |
| 3 | Warm Motion | 53 | 3,328,636 |

Soft Contact's prompt brief emphasizes muted rounded contacts and fine surface
texture. Warm Motion asks for warmer body and wooden resonance. Each retains the
actual material and recognizable skateboard wheels/deck. Every consumed WAV is
distinct across all three generated banks; none is an inherited duplicate choice.

`atelier build yorimichi audio.soundbanks` validates committed definitions and
prepares an independently inventoried product under `build/yorimichi/audio/soundbanks`.
It performs no inference and requires no model weights or private cache. Normal
Unreal consumers declare the `audio.soundbanks` product as an actual read.

Each generated entry names `<bank-id>/bank.json` with its SHA-256. That manifest
must provide all seven existing footstep pools, all eight skate surface rolls and
landings, and powerslide friction. Other families explicitly inherit Original,
including horse hoof stand-ins, bikes, combat, ambience/voices, UI and other skate
cues. A source cannot be silently reused for another material or cue.

Each source is `samples/<source-id>.wav`, canonical mono 48 kHz PCM16, with its
actual checksum and generation/processing provenance. Footstep pools contain
4–12 contacts; landing pools 2–4 contacts; each continuous cue has 1–2 loops.
Contacts last 70–1200 ms and loops 0.5–4 seconds. Each bank is limited to 16 MiB.
Provenance retains prompt, seed, model/source/weight identity, sampler settings,
raw checksum, processing-code checksum, source interval and loop crossfade.

Preparation validates all inputs before writing media, uses a writer lock,
publishes immutable media without replacement, rechecks inputs and products,
and publishes its index last. The build product inventories the complete output
directory. Corrupt or incomplete banks fail; they do not silently select Original.
Passing these checks establishes structural readiness, not listening acceptance.

This publication step uses normal incremental fingerprints and complete product
inventories, but deliberately does not opt into portable caching or action input
auditing: those mechanisms clear or replace product roots, conflicting with
preserving a published bank on failure. The source checks remain mandatory.

The three alternatives each supply four contacts per footstep pool, one roll per
skate surface, two landings per surface and one powerslide loop. Every footstep
and landing pool spans at least two actual raw takes. Sources use the unchanged
production extractor and preserve its PCM, normalization, gates and crossfades.
Rejected takes remain rejected; complete source coverage does not imply listening
acceptance. Original remains the fresh/default choice throughout.

`audio.soundbank_previews` builds one 16-second mono 48 kHz PCM16 audition per
catalog entry (about 1.5 MiB each). Every example uses the same seeds and timeline:
four seconds walking on stone, four running on stone, then eight seconds of
concrete skateboard acceleration, powerslide, air, landing and stopping. These
are approximate foot-plant cadences, with the pinned runtime gain, pitch and
skate envelopes. No per-click synthesis or batch decoding is needed by a future
menu player. Original uses actual legacy footstep and skate outputs without
changing their bytes or levels; alternatives use their own verified media.

Auditions are separate, replaceable derived products. Their normal build reads
the complete `audio.soundbanks`, `audio.footsteps` and `audio.skate` products and
fails on missing media, stale indices or a changed runtime profile. The report
records actual source hashes, renderer/producer identities and runtime pins.
This does not select a bank or establish subjective listening acceptance.

The menu's **Soften footsteps** switch defaults on (the release defaults, JapanPreferences.cpp). It applies a 3 kHz low-pass
to human footsteps and foot landings. **Footstep volume** defaults to 1 and ranges
from 0 to 1. Both save locally and update existing and future footstep voices
across all four banks, including other players heard on this device. Horse
hooves, skateboard audio, music and overall volume keep their own controls.
The menu auditions retain their default, unfiltered comparison mix; these
controls tune actual in-game footsteps rather than the mixed audition files.
The default audition profile's source lineage is recorded in
`../profile/footstep-preferences-revalidation.json`; this records unchanged
contact timing and the reviewed playback change, without claiming a new native
listening or compilation check.

**Soften skate sounds** works the same way for the skateboard and also defaults
on. It applies a 3 kHz low-pass to board rolls, grinds, slides, skids, foot
brakes, pops and landings. **Skate volume** defaults to 0.5 and ranges from 0 to 1.
Both save locally. They update loops and one-shots that are already playing as
well as future ones, for every bank and for other riders heard on this device.
Footsteps, hooves, music and overall volume are unaffected. Envelopes, pitch,
attenuation and timing are unchanged; see
`../profile/skate-preferences-revalidation.json`.

`audio.soundbank_import_plan` validates the current committed catalog, every
prepared WAV (including surfaces omitted from the audition), the audition PCM,
and the current profile/producer bindings. It emits a portable plan for the normal
native import under `/Game/AudioBanks`, with stable selections, exact source
identities and explicit footstep/Skate slot mappings. Original has an audition
entry only, and no replacement cue library. The existing generic Skate API has
one continuous wave per loop slot, so this boundary rejects multiple loop
variants instead of silently discarding one. The source catalog's broader loop
range does not imply that every native consumer supports it.

Signal validation runs in normal Python because Unreal's embedded Python has no
NumPy. A native consumer must recheck the plan and actual media, require current
build certification, import bounded inline PCM assets, and publish a verified
runtime registry. The plan itself neither imports packages nor installs or
selects a bank.

The normal `unreal.soundbanks` step consumes the checked import plan in two bounded
editor invocations. The first preflights all media before rebuilding only
`/Game/AudioBanks`, saves mono 48 kHz PCM/ForceInline waves and hard-reference data
assets, and records a candidate with actual saved-package checksums. The second
starts a fresh editor, repeats admission, verifies those unchanged packages and
all loaded references, then publishes the registry. `data.soundbanks` carries that
registry into `Data/Soundbanks`; general `data.stage` reads the staged product so
packaging retains the complete dependency. Audio-only fixture staging therefore
does not depend on world generation. The owned packages are included in cooking and
preserved by content cleanup. A candidate receipt is never runtime metadata.

The Soft Contact/Warm Motion source completion uses this existing import,
registry, staging and menu mechanism without runtime changes. Its focused source,
PCM, fingerprint and portable preflight checks do not claim a new Unreal import,
gameplay session or cooked-package acceptance. Subjective listening remains a
separate acceptance decision.

The menu selector uses only entries in the installed registry, so stable selection
numbers need not be contiguous. A local-world subsystem loads an alternative,
checks the saved identity and all wave/pool/loop coverage, preflights every ready
foot/skate emitter, saves the preference and commits on the game thread. Failed
loads or saves keep the prior bank. New emitters subscribe at audio readiness;
remote emitters use this client's choice. Nothing about that choice is replicated.
Fresh Original performs no replacement or audition load. Its existing references,
shuffle state, timing and mix remain the default.

The explicit 16-second menu preview uses one owned nonspatial player. Changing the
selection, closing or changing menu pages, backgrounding and world teardown stop
both the player and any pending preview load. Selection and preview each have a
generation token so an obsolete completion cannot take over the current session.
Selection commits, preview completions and late emitters re-read the bounded staged
registry and require its exact admitted snapshot; a change or removal refuses the
new activation and asks for a restart. Cached entries are not activation authority.
These source guarantees alone do not establish subjective listening,
host/guest presentation or cooked-package acceptance for a newly added bank.
