# Multiplayer: implementation and test handoff

The host owns shared combat outcomes and activity changes. The guest predicts
movement and replays saved moves against host checkpoints. Local two-process
tests cover session admission, walking, jumping, skating, combat reactions and
disconnect back to Solo. This is development evidence, not a completed
two-machine or packaged release certification.

## Current scope

- Ordinary Solo play retains its immediate combat path. A remote autonomous
  player's on-foot reaction uses the scheduled path described below.
- Bike and sail support uses `AJapanGameState::bPredictedVehicles`, enabled by
  default. A host can still disable vehicles; the vehicle regression explicitly
  tests that opt-out before restoring normal availability.
- The zeppelin is one replicated host-owned service with separate passenger
  seats. Boarding, destination and speed controls use the owning player's RPCs.
- Character selection is available during a session. The persistent controller
  replaces its pawn, preserving health, player identity and activity, and advances
  the activity epoch. Pending combat resolves before replacement. Bike and sail
  checkpoints resume; skating carries the existing simulation, stance and trick
  state into the replacement rig. Requests during physical bail/get-up or a
  transition clip stay queued until that recovery finishes.
- Source changes require native and rendered checks at the final revision.
  Same-machine tests do not establish packaged or two-machine acceptance.

## Required multiplayer checks before release

Run the final clean revision's compile and `data.network` staging, then the native
wire suite. All 18 named fixtures must pass, including encounter replacement;
an engine exit code alone is insufficient.
Run a listen pair at zero lag and at 60 ms delay / 15 ms variance / 2% loss. Both
observers must receive sustained skate poses and evaluate the expected skeleton.
Skate replacement receipts also require the finalized mesh world frame to match
the applied stream frame. Matching local bones alone can miss a misplaced body.

The session runner supports `--feature-case equipment|switch-foot|switch-bike|
switch-sail|switch-skate|switch-skate-air|switch-skate-bail|zeppelin` and
`--render-view host|guest`. Run both observer
views; one process renders while its peer uses NullRHI. The aggregate guard defaults
to 10 GiB. A rendered observer can use `--aggregate-memory-gib 14`, `16` or `18`
only with explicit authorization for that session. Individual guards default to
10 GiB; `--rendered-memory-gib 12` also requires explicit session authorization
and applies only to the process that renders. Its NullRHI peer stays at 10 GiB.
Startup requires the selected aggregate ceiling plus 2 GiB available, and receipts
check and record the actual individual and aggregate ceilings and peaks.
Inspect the captures as well as the receipts. Rerun bike, sail,
pending mount, parking, crash and combat routes before enabling a release build.
Use matching packaged identities for a two-device Tailscale playtest before claiming
that a release's multiplayer has been verified on separate machines.

## Scheduled combat reactions

Damage, the confirmed outcome and feedback are immediate. For a remote on-foot
player, the host freezes movement reaction data into a bounded immutable payload
and sends it reliably. The owner applies it on its next saved move. That move
carries the reaction sequence and its original movement/input boundaries; the
host applies the same payload at the same boundary. Lost combined moves are
split at that boundary, and correction replay reuses the retained payload.

Payloads use a fixed action index rather than network-provided names. The journal
is bounded, activity epochs increase monotonically, and overflow, invalid
origins, failed restore/application and forced recovery are counted. A pending
event has a bounded deadline of at most half a second. A good ACK drains pending
replay before Unreal frees saved moves. A checkpoint is retired only after the
host's accepted prefix and the owner's saved-move disposal permit it.

Damage eligibility uses contact-time history. Hit immunity lasts 0.7 seconds
from resolution; delaying the movement reaction does not extend that deadline.
Attacks pressed inside an unresolved reaction window retain their ineligible
origin even if buffered. A continuous held guard becomes eligible after all
overlapping windows close, without inventing a new parry. Physical knockdown
and a separate get-up deadline preserve their protection.

A lethal hit commits health immediately and replaces the movement epoch at the
next safe movement boundary. Pending reactions are applied before that handoff;
old movement cannot run while the lethal replacement is queued. The new epoch
carries the knockdown state and pending launch. Old-epoch reaction deliveries
are discarded. Health and activity replicate separately, so health observed
inside the activity callback is reported but is not assumed to be current.

## Evidence retained before integration

Raw receipts identify the clean source revision, executable/module hashes,
build fingerprints and individual check results. Full logs and captures live in
the ignored build archive and the corresponding agent-board review threads.

| Revision | Accepted native evidence |
| --- | --- |
| `39f9e8ea` | Compile and all 17 network automation fixtures; eight stationary delivery cases at zero lag, and moving cases 0/5 both at zero lag and 60 ms lag / 15 ms variance / 2% loss. All 12 pairs passed and were independently reviewed. |
| `7e5bf9ac` | Compile and all 17 fixtures; moving lethal cases 8/9 both at zero lag and 60/15/2. All four passed independent raw-receipt review. Both orderings of old payload versus activity reset were observed. Combat with a 20 fps host and 30 fps owner at 60/15/2 passed 106 checks. |
| Earlier vehicle revisions | Bike, sail, outage recovery, parking and crash receipts are historical only. Pending-mount bike/sail have not been rerun with the scheduled reaction fix. |

The reaction/death checker keeps zero corrections above 1 cm, maximum error
strictly below 1 cm, and zero rejected checkpoints. The maximum in the accepted
pairs was 0.0594 cm at the initial spawn checkpoint. There is no hit-recoil
exemption. Observed packet loss is incidental, not targeted loss coverage.

Wire17 has deterministic real-code tests for immunity boundaries at 0.69/0.71 s,
buffered attack origins, held guard and overlapping windows, dropped marked
moves, late moves, forged stamps, timestamp wrap and journal bounds. Dedicated
end-to-end immunity/eligibility pair cases 10–12 were proposed but **not
implemented or run**. Combat at 30/60 host fps, pending-mount bike/sail and all
native checks on the final integrated revision remain open.

## Development checks

These are instructions for the next testing session, not steps run during the
October 8 wrap-up. Follow the machine render ledger, live locks and normal
memory guards. Build assets and identity before accepting a native receipt:

```sh
nice -n 10 uv run atelier build yorimichi unreal.compile data.network
nice -n 10 uv run python games/yorimichi/tools/review_network_wire.py
nice -n 10 uv run python games/yorimichi/tools/review_network_session.py \
  --reaction-delivery-case 0 --reaction-delivery-moving \
  --lag-ms 60 --variance-ms 15 --loss-percent 2
```

`review_network_session.py --reaction-delivery-case N` supports:

| Case | Purpose |
| --- | --- |
| 0 | Hit after a correction; optional moving victim |
| 1 | Zero-impulse guard reaction |
| 2 | Labelled CMC response-send hold across captures |
| 3 | Previously prepared good ACK |
| 4 | Second hit after capture |
| 5 | Stale correction followed by real throttling; optional moving victim |
| 6 | Epoch cancellation |
| 7 | Host-owned pawn's immediate hit |
| 8 | Moving lethal hit |
| 9 | Moving lethal hit with one earlier hit pending |

Cases 8/9 require `--reaction-delivery-moving`. Pairs run either without lag or
with `--lag-ms 60 --variance-ms 15 --loss-percent 2`. The deliberate holds and
stale deliveries are Development-only and labelled in the receipts. Case 2
holds CMC responses; it does not hold the reliable reaction RPC.

## Two-device playtest

Use the same reviewed revision and network identity on both machines. Verify Solo
startup first, then host and join over Tailscale. Check sword draw, attack, held
guard and sheath; observe both players' skating, walking and jumps. Ride bikes,
sailboats and the shared zeppelin, and change character during each activity.
Exercise hits, guard/parry/dodge, knockdown/death and recovery, then verify that a
guest disconnect returns to Solo and that leaving as host ends the shared session.
Record both logs and build identities with any failure.
