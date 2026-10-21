# Build reuse contracts and review boundaries

When changing reuse, preparation or regional layering, read the ancestor `CONTRACTS` files
and the local `@cc` declarations before editing. The syntax/owner checker does not prove
these rules: review the real callers and test evidence. `owner:fontanierh` is the contract
owner; a source approval is not native or performance acceptance.

The 21 October build work relies on these boundaries:

| Mechanism | Contract location and invariant | Relevant checks |
| --- | --- | --- |
| Action reuse across revisions | `platform/studio/atelier/CONTRACTS`, `checkpoint_actions.publish`: complete inputs/products/tools and output ownership; old state cannot become a produced action certificate | `test_checkpoint_actions.py`, candidate/restore tests |
| Retained checkpoint capture and history | `checkpoint_store.capture`, `native_protocol.validate`, platform `historical-inputs-are-not-capture-head`: immutable complete bytes, bounded paths and original task evidence | Store/history/candidate tests |
| Native runtime isolation | `native_protocol.native_context` and `runtime_files`: standard-library protocol with an explicit complete runtime closure, excluding build/release/playtest controllers | `test_native_protocol.py`, game controller-cascade checks |
| Current mesh admission | `unreal_mesh_reuse.MeshReuse`, `mesh_reuse.Receipts`, platform policy/history contracts: current engine/source/owner/options/validation proof; dirty packages miss; unsupported evidence imports normally | `test_mesh_reuse.py`, `test_unreal_mesh_reuse.py`, GLB adapter tests |
| Real source tag and count reporting | Script `CONTRACTS`, `finalized-reuse-is-the-success-metric`, `MeshReuse.miss`: actual loaded `AssetImportData`, observed refusal reasons, no pending/staged counts advertised as final hits | Source-tag/validator rejection and successful host-finalization regressions |
| Post-host receipt publication | `mesh_reuse.finalize_pending`: exact invocation/context/source/package sidecars, after marker and positive guard cleanup | Host receipt, fake-context and module/preflight tests |
| Partial preparation resume | `mesh_geometry.expected_digest`, `save_unit` and native snapshot/unit contracts: exact float32 triangle/corner/slot stream; complete package-byte hints; current native snapshot/settings/material proof remains the caller's responsibility | `test_mesh_geometry.py`; native snapshot and saved-variant validation in the feature |
| JSON allocation lifetime | Native-source `foliage-json-allocation-lifetimes`: transfer owned text without a full copy and release parsed DOM before mesh construction, preserving description lifetime | Feature preparation source/native acceptance; memory remains guarded |
| Clean LOD package continuity | Script `CONTRACTS` and the source binding implementation: equal bindings skip dirtying setters, clean source saves stay dirty-only, current target assembly remains required | Real owner-body package-continuity regressions |
| Explicit script memory | `build.UnrealScript.memory_limit`, `build.fingerprint`: finite supported ceiling, actual aggregate guard and full reservation, honest batch refusal, unchanged default representation | Memory/admission/batch and default fingerprint tests |
| Membership scan optimization | `checkpoint_actions.source_scopes`: identical lexical containment and fresh tracked sources per check, without stale cross-check caching | Nested/sibling/absolute/new-source cases |
| Public-first private backup | Platform publication/lifetime contracts and `checkpoint_backup.queue`: public success precedes scheduling; durable frozen-runtime work can resume without the producer | `test_checkpoint_backup.py`, lifecycle/recovery tests |
| Parallel transport | `checkpoint_packs.Spool`: bounded workers/prepared parts, verified immutable pack bytes, cancellation cleanup before spool retirement | `test_checkpoint_github.py`, spool overlap and cleanup cases |
| Remote private retention | `checkpoint_gc.collect`, `checkpoint_coordination.owned`, platform pin/exclusion contracts: newest index plus live transitive references, bounded pins/tombstones, no deletion on uncertainty | Shared-pack draft retry, pin expiry and cross-machine exclusion cases |
| Regional projections and selected textures | `region_products` contracts and platform complete-build-inputs: consumed fields, exact real model/texture membership, fresh selected bytes and complete support closure | Region/product/selected-texture propagation tests |
| Independent model producers | Regional `CONTRACTS`, `brinecove.foliage_library.load`: assembly requires the complete current model library; no hidden inline regeneration | All-model catalogue/serialization/startup and helper-edit cases |
| Bounded geometry pieces | Regional `CONTRACTS`, `mesh_partition.face_groups`, `mesh_cells.cell_face_groups`: exact face coverage/corner attributes, declared budget/frame, stable ownership and inherited parent policies | Partition/city/clearance checks; native culling, collision and draw-call acceptance remains separate |
| Generated membership retirement | `model_files.retain_files`, `native_membership.retire`, regional `CONTRACTS`: current complete membership before deletion, explicit exclusive owner, no source/foreign deletion, all native references checked first | Source removal/rename/hull and native preflight/failure cases |
| Native preparation module boundary | Native-source `CONTRACTS`: preparation helpers and raw role certification bind their own actual compiled modules | Feature module-graph/digest tests; adoption and native acceptance remain separate |
| Serialized saved-type moves | Native-source `CONTRACTS`: unchanged intended fields/defaults and explicit redirects; compile/source parity cannot prove old-library loading/playback | Draft world/audio boundary source/save/product/profile tests; native gate remains open |

Keep these distinctions when reporting results:

- A compatible workspace is not a new produced action certificate.
- A package selected or staged as a candidate has not yet passed native admission.
- A saved per-mesh unit is a hint, not successful completion of its failed parent task.
- Geometry reuse does not prove identical package bytes, an avoided cook or an end-to-end speedup.
- A merged source mechanism does not prove every region is integrated or every native path is effective.

Known remaining work must stay explicit. Bounded Brinecove and city source pieces are landed;
the Belmonte static-model integration has its own review/CI, and oversized generated ground and
remaining regions still need actual producer/consumer integration. Local global-store/workspace
garbage collection is not implemented by the remote collection rule. Native audio type-move and
preparation-module adoption gates must not be inferred from this documentation or source approval.

Directory contracts are used where the rule spans several runtime files. This adds review obligations
without editing native Python/C++ bodies solely to attach annotations. Put future narrower contracts
next to the responsible declaration when it improves precision, and retain the actual dependency
boundary: do not exempt changed executable inputs from fingerprints to conceal a rebuild.
