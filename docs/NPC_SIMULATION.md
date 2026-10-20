# AI NPCs and the simulation layer

Status: design proposal. Nothing here is implemented yet.

Last updated: 2026-10-20.

Atelier should own the generic simulation and cognition layer for AI-driven inhabitants. Yorimichi is the first consumer and the reference implementation, not the home of the system.

The runtime is C++ inside an Unreal plugin. Python stays for build tooling, data validation, and offline evaluation, never in the live loop.

## Platform and game boundary

| Concern | Platform | Game |
| --- | --- | --- |
| Snapshot, event, action, option schema | owns | fills in |
| Affordance registry, schema, and queries | owns | defines actions, effects, and handlers |
| Brain, scheduler, decision loop | owns | attaches to its pawns |
| Identity, goals, needs, memory | behavior and schema | authors content |
| Accounts, reservations, transfers | mechanisms | wages, rent, eviction, happiness rules |
| Event urgency | scheduling hooks | classifies urgency |
| Model client, routing, caching, ledger | owns | configures keys and prices |
| Navigation, animation, physics | none | owns |
| Persistence | versioned inhabitant state | save envelope and game fields |
| World query, action executor | interfaces | implementations |

Policy stays in the game: the platform provides accounts and transfers, not a rent rule. It provides urgency hooks, not a definition of what is urgent. Three interfaces carry that policy: world query, action executor, and persistence.

Platform modules never name a game. Games configure the platform; they do not reimplement it.

Proposed locations:

- platform/engine/Plugins/AtelierNPC/: runtime C++ plugin.
- platform/conventions/npc_protocol.schema.json: machine-readable and versioned. C++ and Python validators read the same file; the Markdown explains it.
- platform/studio/atelier/npc/: build-time validation, prompt evals, cost reports. Not the runtime.
- games/<game>/: NPC content, world bindings, actor classes, nav, save data.

## Runtime shape

    UWorld
      └─ UNPCSimulationSubsystem        fixed social tick, scheduler, ledger
           ├─ UNPCBrainComponent         one per inhabitant
           ├─ UNPCSensorComponent        range and line-of-sight queries
           ├─ UAffordanceRegistry        world subsystem
           ├─ UNPCModelClient            async HTTP, one interface
           └─ UNPCEconomySubsystem       jobs, wages, rent, homes

The brain is a component, so any pawn can be an inhabitant. One subsystem owns the clock and the frame budget; there are no per-NPC timers. HTTP completions arrive on a worker callback; world access and action commits happen on the game thread. Worker inputs are immutable, object references are weak, and every request is cancelled on world teardown or load.

## Four layers

| Layer | Does | Cadence | Model |
| --- | --- | --- | --- |
| Unreal | movement, animation, collision, schedules, shared clock | every frame | none |
| Reaction | answers speech, a block, or a sudden event | event-driven, under 1 s | JEV |
| Tick | picks one concrete action from what is in range | 1 min hot, 5 min cold | Luna hot, Qwen cold |
| Reflection | planning, memory summaries, goal checkpoints | every 10 in-game minutes | Luna hot, Qwen cold |

Unreal is the reflex layer. JEV is fast cognition for events where a second of delay is visible. The tick model is deliberate cognition, and its mostly stable prompt is what makes cached input cheap. Reflection is slow enough to think.

Chatter is a call lane, not a cognitive layer: hot and player-facing speech uses Luna, ambient cold-tier chatter uses a cheap model.

## Identity and goals

Each inhabitant has a fixed sheet and a changing state.

Fixed: name, age, origin, home city, personality, values, fears, secrets, voice, skills, work history, one life goal, and dispositions such as whether they would steal when starving.

Changing: mood, energy, hunger, money, job, home, relationships, reputation, beliefs, current intention, recent memories, happiness.

Identity is authored as data. Tools may draft prose; the runtime never generates identity.

Goals are state machines with stages, progress, priority, and secrecy:

    Goal: open a bakery.
    Stage 1: save 300 coins. Progress: 120.
    Stage 2: find a vacant shop.
    Stage 3: get a permit.
    Stage 4: open and hire one clerk.

The platform owns the goal state-machine runtime. The goal definitions and stage predicates are game data. The model chooses the next action inside the current stage; it does not invent the plan.

## Knowledge and memory

The platform keeps a shared gazetteer: places, routes, prices, schedules, public facts. A game supplies its content.

Each inhabitant has a personal knowledge graph. A fact has a source, confidence, and possibly a false belief. Inhabitants know their hometown, workplace, routes, and a few rumors. The mind sees beliefs, not ground truth. The player can teach, lie, and spread rumors.

Memory has four parts: recent events verbatim, older events summarized, conversations and overheard speech, and important facts and relationships retrieved when relevant. Each memory stores who, what, where, when, and whether it was direct or overheard.

Reflection writes summaries. The tick prompt gets a compact working set: situation, plan checkpoint, and a few relevant memories. Keep bounded buffers per inhabitant.

## Talking and hearing

Every inhabitant who speaks uses a language model, including NPC-to-NPC talk.

1. The decision model picks a target and an intent.
2. The language model writes the line from persona, relationship, memories, and intent.
3. The line goes to the direct listener and everyone in hearing range.
4. Every listener stores it in memory. Listening is free.
5. A listener calls the model only if it decides to respond.

A conversation is a short turn-taking session with a lock on both sides. Overhearers can join later. Start with a radius plus a same-area check; walls refine it.

Add consent, a turn limit, an expiry, and an interruption rule. Two inhabitants who both want the last word must not loop.

## Affordances and perception

The model does not choose from a fixed verb list. It chooses from the interactions available at that moment.

Each interactable carries an affordance component: actions, preconditions, state, and radius. Examples: door, food, bed, job board, shop counter, workstation, train, zeppelin, bench, home, person.

The platform defines the shape of an action, not its vocabulary. Train, zeppelin, bread, and job board are game content. A game can add a new verb without touching the platform.

An action descriptor carries:

- an id and label, namespaced by the game, such as train.board
- target kind and interaction radius
- preconditions: money, item, skill, time window, state tag, or a game predicate
- expected effects: time, money, hunger, energy, happiness, relationship
- an execution handler that starts the action and reports progress

The game returns a descriptor valid for the current actor and state, not a static list. The platform filters, ranks, validates, and dispatches. The game decides what the action means and how it looks.

Hunger and sleep are needs, not actions. The inhabitant eats by interacting with food and sleeps by interacting with a bed. A bench or the ground offers sleep rough.

The action list is built at decision time: find what is in range, ask what it offers, filter by preconditions, add wait and talk, add reachable destinations, then rank and cap. Above about 16 candidates, use a two-stage choice: category, then target.

No object in range means no interact action. Context can remove actions: an in-transit zeppelin offers talk, stay, and look; a conversation offers talk or end; a shift offers work actions.

Each option carries an id, label, target, preconditions, expected effects, and risk. The model picks an id; the simulation validates it against the current option set. The model cannot invent an action.

Starting an action is a transaction: take the reservation, apply the effects once, and release on completion, cancellation, or timeout. A late or retried answer must never apply the same effect twice.

Unreal reports facts, the game tags their urgency, and the platform decides whether a fact enters the event queue or only the option set:

- Events are pushed immediately: spoken to, bumped, attacked, path blocked, vehicle docked, shift started. JEV handles them.
- Snapshots are pulled at decision time: position, movement, path status, inventory, time, and nearby actors and objects with distance, state, and visibility.
- Diffs are pushed at low frequency: a new actor in range or an interactable changing state, coalesced to at most one per inhabitant every few seconds.

A new person walking past is not an event; it is an option at the next tick. Being addressed by that person is an event. The game supplies urgency policy; the platform applies it and keeps the queues.

Use reliable, ordered events for speech and action outcomes, coalesced diffs for reconstructible state, and snapshots for reconciliation. Carry timestamps, sequence numbers, and removal tombstones. Absence from a capped snapshot must never mean the object is gone; it means only that it was not among the closest candidates.

Sampling follows the tiers: 1 Hz hot, 0.2 Hz cold. That is about 72 passes per second at 200 inhabitants, before off-screen reductions. Stagger them across frames by inhabitant id with a per-frame budget; idle inhabitants sample slower.

Budget in game-thread milliseconds, not kilobytes. Measure overlaps, visibility traces, path queries, and allocations. Share one spatial index, bound the number of visibility traces, and never pathfind for every candidate. Reserve snapshot slots for the current target and goal destination so a cap cannot hide what the plan needs.

Off-screen inhabitants need an authoritative persistent record independent of the pawn. Visibility, cognition tier, and simulation fidelity are separate switches. Promotion reconciles travel, occupancy, schedules, and reservations before the pawn takes over.

Ranges: interact at 2 to 3 m, notice people at 15 to 25 m, hear speech at 8 to 10 m. Cap a snapshot at about 12 objects and 8 actors, sorted by distance and importance. Destinations are gazetteer ids; the game owns pathfinding.

A snapshot is about 1 KB. Two hundred inhabitants at 1 Hz is roughly 200 KB/s, in-process. No bridge is involved.

## Decision loop

The simulation runs a fixed social tick, for example 1 Hz, independent of frame rate. All inhabitants see the same tick and events in the same order. Movement and animation run in Unreal at frame rate.

Each brain has a next decision time. When it arrives, or when an event interrupts, the subsystem builds the compact state and asks how urgent this is and which option to pick. Treat self-reported confidence as a weak hint, not a gate: validate the chosen option and use a deterministic fallback when it fails.

Walk, path, and collision belong to the game's controller. The action executor owns start, progress, cancellation, completion, and timeout, and takes atomic reservations for resources such as a seat, a bed, or a shop counter. The brain receives progress events: arrived, blocked, interrupted, path failed. A failed path triggers a new decision. A new observation is injected as an interruption with a cooldown and a novelty check.

Model calls are async and carry a decision generation plus versions for the relevant targets and preconditions. Apply the answer only if those still match at commit; otherwise discard or re-decide. A whole-world version is too coarse: movement alone would expire every answer. Reflection updates memory independently of ticks. A reaction supersedes a pending tick for the same inhabitant.

Urgent admission is separate from the social tick. A 1 Hz tick boundary must not consume the sub-second reaction budget, so reactions get reserved capacity and their own queue. Stagger model deadlines as well as sensing; long reflections must not occupy every request slot.

When two inhabitants meet, create one encounter event with a deterministic initiator, not two independent decisions. Lock both for the conversation.

Fixed seeds and sorted events do not make Unreal itself deterministic. Promise deterministic cognition replay against recorded observations, model completions, and action outcomes, with the tick each was applied. Save stable ids, logical travel and action state, RNG state, deadlines, and reservations. Cancel outstanding HTTP work on load.

## Tiers and models

| Tier | Share | Tick | State | Model |
| --- | ---: | --- | --- | --- |
| Hot | 20% | every 60 s | full observations and conversations | Luna |
| Cold | 80% | every 5 min | compressed state and schedule | Qwen 3.7 Flash |

Reactions are event-driven in both tiers. Promotion and demotion happen at tick boundaries so no inhabitant has two pending decisions. Cold inhabitants lean on their schedule between ticks. Fully off-screen inhabitants can drop to schedule-only execution.

Four call lanes:

| Lane | Trigger | Budget | Latency | Model |
| --- | --- | ---: | --- | --- |
| Reaction | speech, blocked path, sudden event | 2K | under 1 s | JEV |
| Tick | regular deadline | 8K | a few seconds | Luna or Qwen |
| Reflection | every 10 in-game minutes | 32K | tens of seconds | Luna or Qwen |
| Chatter | an inhabitant says a line | 2K | under 2 s | cheap model |

JEV is $0.042 per 1M input with free output and answers in about 0.3 s; a 2K reaction costs $0.000084.

Luna is $0.10 per 1M input, $0.01 cached, $0.50 output, about 1.9 s for structured output.

Qwen 3.7 Flash on Alibaba us-east-1 is $0.0345 input, $0.0069 cached, $0.1495 output. OpenRouter measures p50 728 ms, p90 1.84 s, p99 4.56 s on short probes; an 8K tick lands around 1.5 to 2 s at p50.

Cheaper endpoints, at 90% cache for an 8K tick with 100 output tokens:

| Model | Provider | In/M | Cache/M | Out/M | Per tick |
| --- | --- | ---: | ---: | ---: | ---: |
| gpt-oss-20b | Darkbloom fp8 | $0.018 | $0.009 | $0.09 | $0.000088 |
| qwen3.7-flash | Alibaba us-east-1 | $0.0345 | $0.0069 | $0.1495 | $0.000092 |
| gemma-3-4b | Parasail bf16 | $0.04 | $0.02 | $0.05 | $0.000181 |
| Luna | OpenAI | $0.10 | $0.01 | $0.50 | $0.000210 |

Pin the provider. The model-level OpenRouter price is the cheapest endpoint, not the one you get, and the same model varies in quantization, cache support, and uptime. Check implicit caching per endpoint. Gemma 3 has structured output but usually no tool calls.

Official DeepSeek deepseek-flash is $0.15 input, $0.003 cached, $0.60 output off-peak, double at peak. At 90% cache it is a wash with Luna and worse at peak, so it is not worth switching for price.

Avoid 1B to 4B models for action choice. They work as narrow classifiers, not for picking from sixteen affordances.

## Cost

Assumptions: 200 inhabitants; 20% hot at 1/min on Luna, 80% cold at 1/5min on Qwen; 8K tick with 100 output; 32K reflection with 800 output every 10 min; 12 chat lines per hour; one 2K JEV reaction every 3 min; 90% cache.

| Lane | Hot (Luna) | Cold (Qwen) |
| --- | ---: | ---: |
| Reactions, 20/hour | $0.0017 | $0.0017 |
| Tick | $0.0126 | $0.0011 |
| Reflection, 6/hour | $0.0060 | $0.0026 |
| Chatter, 12 lines/hour | $0.0008 | $0.0003 |
| **Total per inhabitant-hour** | **$0.0211** | **$0.0057** |

Blended: **$0.0088 per inhabitant-hour**, or **$1.76 per hour for 200**. A two-hour session is $3.51; a 40-hour month is $70.

Same cadence, all-Qwen: $0.0066 ($1.32/hour). All-Luna: $0.0131 ($2.62/hour).

One god agent on Luna high reasoning, reading 128K per minute with 90% cache, adds $0.0010 to $0.0013 per inhabitant-hour. With 2K output per pass the total is **$0.0098 per inhabitant-hour**, or **$1.97 per hour for 200**.

The god agent sees a stable roster plus a fresh snapshot, writes short thoughts with a reason and expiry, and cannot command. Cap inserts per pass, cooldown per inhabitant, log every thought.

The largest levers, in order: cache hit rate, reflection cadence and size, tick cadence, then the tick model. Tiering cuts the tick line by about 64%.

This is a scenario, not a measured budget. It assumes six reflection calls per real hour, which requires a defined in-game clock, and it ignores cache expiry, reasoning-token variance, retries, and provider drift. Measure the cached share and set a hard session cap before trusting it.

## Model runtime

The plugin talks to OpenAI-compatible APIs directly from C++ with UE's HTTP and JSON modules.

- INPCModelClient interface: HTTP client, fake client, and a future gateway client.
- Request pool with a max in flight, and a priority queue: reactions, hot ticks, cold ticks, reflection, god (later).
- Per-lane timeouts: reaction 1.5 s, tick 8 s, reflection 60 s, god 90 s.
- Ledger contract: an exclusive record before submission, then terminal or uncertain. A 429 is a non-execution and may be retried with jitter. A 5xx after submission is uncertain and must not be retried automatically; reconcile it first.
- Hard per-session spend cap, enforced before the request leaves the process.
- Circuit breaker: above a 20% error rate over a minute, fall back to schedule-only and log.
- Stable prompt prefix first (system, identity, rules, goal), volatile state last. That is what makes caching work.
- Estimate tokens before sending and reject over-budget prompts.
- Append-only ledger: request id, lane, model, tokens from usage, cost, latency, outcome.

Keys never ship in a client build. The prototype reads the local environment; a release goes through a backend proxy that holds the key and enforces spend limits.

## Headless simulation and tests

The same brain runs against a synthetic world, with no map, no rendering, and no network:

- FNPCSyntheticWorld implements the snapshot and event source over a graph of places, travel times, jobs, homes, and shops.
- FFakeNPCModelClient returns scripted decisions with configurable latency and error rate.
- Run 200 inhabitants for 30 in-game days in a commandlet or automation test.

Invariants: every transfer has a source and a sink, the treasury balances, every inhabitant has at most one home and one job, no double-booked shifts, no inhabitant has two pending decisions, queues are bounded, and a replay reproduces the same day.

Live validation then uses five inhabitants in one region and the real model client.

## Implementation plan

1. Define the machine-readable protocol and the action transaction model: reservations, cancellation, stale replies, and exactly-once effects.
2. Separate persistent inhabitant records from pawns: save and load, streaming, and promotion.
3. Split clocks and budgets: urgent admission, the social tick, request caps, the ledger contract, and a session spend cap.
4. Build the synthetic world, fake client, scheduler, and option builder in the C++ plugin. Get headless tests green.
5. Add identity, goals, needs, memory, and the economy mechanisms.
6. Add the Unreal sensor and affordance components, plus a debug view.
7. Bind five real inhabitants in one game region. Test contention, model outages, save and reload, and off-screen transitions.
8. Scale to 200 and measure cache hit rate, queue depth, staleness, and cost per day. Add the god agent after the five behave convincingly.

## Open questions

- One C++ HTTP client, or a local gateway sidecar for keys, rate limits, and spend caps?
- DataAssets or JSON for identity sheets and affordance catalogs?
- How much of the economy belongs to the platform, and how much is game balance?
- What is the save format for memories, goals, and scheduler state?
- How do we keep determinism across engine versions?

## References

- JEV: https://docs.typesafe.ai/introduction
- OpenAI pricing: https://developers.openai.com/api/docs/pricing?tab=suite
- OpenRouter models and prices: https://openrouter.ai/models
- JevTown: https://github.com/NevaMind-AI/JevTown
