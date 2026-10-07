# Shared zeppelin implementation

The online service is under construction and is not enabled. The current native
multiplayer proof runs on the core branch; this work is stacked on the default-off
bike and sailboat change. The existing standalone zeppelin is unchanged.

`FJapanZeppelinManifest` owns bounded server passenger state. It has no actor,
replication, camera, collision or flight-path effects. Its native automation test
is part of the required network test list. Adding that test does not establish
that the actor adapter or a shared ride works.

## State contract

- Player identity comes from the requesting connection's server PlayerState.
  Admission observations (epoch, station, proximity, grounded state, readiness,
  menu, movement lock, pending contact and encounter ownership) come from the
  host. Clients never supply these observations.
- Accepting a passenger calls `EnterProtected` synchronously on the game thread.
  The adapter must recheck pending contacts and encounter ownership and then
  enter the scripted activity in the same call, returning its new epoch. A
  refusal returns zero without changing the pawn. Callbacks cannot yield or
  re-enter the manifest. Geometry must be validated before this final handoff.
  Any nonzero result is committed: an unchanged epoch emits an invariant error
  but still retains the passenger record so safe release remains possible.
- Accepted passengers are protected throughout scripted boarding, flight and
  disembark. There is no unprotected scripted reservation. Dock-call waiters
  remain ordinary on-foot players. The combat adapter must reject and count
  transport strikes at contact time, never queue them for disembark, and retarget
  enemies at the first protected frame. The current game has no projectiles; any
  future projectile must be consumed on its first protected contact too.
- The first reservation starts an eight-second boarding deadline. Later arrivals
  cannot extend it. At expiry an unready passenger stays protected at the dock
  until the adapter validates a safe return. Such a passenger prevents departure.
  A bystander on the hull or gangway also prevents departure. Safety can keep a
  ship docked with a visible explanation; it cannot leave a passenger behind.
  The host supplies a minimum walk duration from the validated boarding path;
  admission closes when that duration no longer fits before the deadline. The
  adapter retries unsafe expiries every host tick while boarding is overdue.
- Slots remain stable when someone leaves. The physical adapter chooses a deck
  capacity from one to eight after checking capsule dimensions and authored slot
  spacing; eight is a storage limit, not a demonstrated physical capacity.
- A personal release requires a successful safe-exit callback. Travel validates
  its final destination before removal; a failed travel leaves the ride intact.
  Disconnect is the only removal without a pawn exit. Neither kind of removal
  changes a flying ship's destination, even when the last passenger leaves.
- The first passenger receives route control. On removal the oldest ready
  passenger inherits it, or the oldest boarding passenger if none is ready yet.
  When somebody reaches their slot and the current controller is still walking,
  control passes to the oldest ready passenger immediately.
  Another ready passenger may request control after thirty seconds without a
  route/speed change. Every lease transfer changes its generation, so an old
  queued command cannot become valid again if control returns to the same player.
  Flight speed persists across trips, matching the standalone preference.
- Skip needs every current passenger's vote. Votes are revocable, expire after
  ten seconds, and clear on roster or trip changes. A skip only authorizes safe
  docking; it does not directly teleport or release a passenger. Requests include
  the roster revision so a queued vote cannot restore pre-disconnect consent.
- There are at most eight unserved calls, including the active pickup leg, and
  one per caller. Calls are ordered and idempotent. Dispatch requires an empty,
  clear dock; a call cannot move an occupied or reserved ship. Disconnect removes
  that caller's request but does not reset a leg already in progress. Personal
  travel and character replacement cancel the old epoch's call through
  `CancelCall`; a stale cancellation cannot remove a new epoch's request.
  A call uses epoch and station only: a route transition cannot stale a waiter's
  unrelated request.
- Trip revision changes on route selection, departure and arrival. Boarding
  changes a separate roster revision, so simultaneous valid admissions from the
  same trip snapshot do not invalidate each other.

## Remaining actor integration and evidence

Spawn one server service and attach clients to its replicated actor independently
of local world-data readiness. Replicate ship and passenger-relative transforms
from one timeline, with current state for late join. Keep cameras local and restore
each exactly once. Route interaction, phone travel, replacement, death and logout
through the owned-character RPC and personal release paths. Keep the online rule
off until native, rendered and packaged gates pass.

The adapter must prove real pending-contact ordering on both sides of admission,
an attack already in progress, a strike during the last scripted frame, no deferred
health loss after disembark, and enemy-clear safe exits. Manifest tests cover state
ordering only; they do not substitute for these world/health checks.

The full matrix includes listen and dedicated authority, simultaneous boarding,
capacity with different capsule sizes, boarding expiry, hull/gangway bystanders,
late join during boarding and flight, continuous relative passenger poses, menu
progress, lease/call/vote conflicts, individual travel/death/logout, empty and
occupied arrivals, camera restoration and resumed walking. Run 80 ms RTT/1% loss
and 60/15/2 emulation, then rendered and packaged rides. Same-machine receipts do
not establish two-machine play.
