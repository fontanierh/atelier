# Autonomous NPCs in Yorimichi

Status: design proposal. Nothing here is implemented yet.

Last updated: 2026-10-20.

Summary: NPCs choose from context-built affordances on a shared tick, remember and gossip, and live inside a job, rent, and housing economy. Hot NPCs run on Luna; the rest run on Qwen 3.7 Flash. Blended cost is about $0.0098 per agent-hour including one god agent.

## Goal

Yorimichi should have a town of NPCs with their own identity, jobs, homes, goals, needs, and social life. They keep living when the player is away. The player can watch them, talk to them, and change their circumstances.

Hosted inference only. Target: 200 NPCs, one instance per NPC.

## Three layers

| Layer | Does | Cadence |
| --- | --- | --- |
| Unreal | movement, animation, collision, schedules, shared clock | every frame |
| Decision model | picks one concrete action from what is in range | decision deadline or event |
| Language model | speech, reflection, planning | when someone speaks or reflection is due |

Unreal is the reflex layer. The decision model is fast cognition. The language model is slow cognition.

## Identity

Each NPC has a fixed sheet and a changing state.

Fixed: name, age, origin, home city, personality, values, fears, secrets, voice, skills, work history, one life goal, and dispositions such as whether they would steal when starving or betray someone for money.

Changing: mood, energy, hunger, money, job, home, relationships, reputation, beliefs, current intention, recent memories, happiness.

Identity is authored as data, not generated at runtime. Authoring tools can draft the prose.

### Life goals

Goals are structured state machines, not free text. Each has stages, progress, priority, and secrecy.

    Goal: open a bakery in Hidamari.
    Stage 1: save 300 coins. Progress: 120.
    Stage 2: find a vacant shop.
    Stage 3: get a permit.
    Stage 4: open and hire one clerk.

The deterministic goal machine owns the stages. The model chooses the next action inside the current stage. It does not invent the plan.

## Knowledge and memory

The world has a shared gazetteer: places, routes, prices, the job board, train schedules, shops, public facts.

Each NPC has a personal knowledge graph. A fact has a source, confidence, and possibly a false belief. NPCs know their hometown, workplace, routes, and a few rumors. The mind sees beliefs, not ground truth. The player can teach, lie, and spread rumors.

Memory has four parts: recent events verbatim, older events summarized, conversations and overheard speech, and important facts and relationships retrieved when relevant. Each memory stores who, what, where, when, and whether it was direct or overheard.

Reflection writes the summaries. The decision prompt gets a compact working set: situation, plan checkpoint, and the few relevant memories.

## Talking and hearing

Every NPC who speaks uses a language model, including NPC-to-NPC talk.

1. The decision model picks a target and an intent.
2. The language model writes the line from persona, relationship, memories, and intent.
3. The line goes to the direct listener and everyone in hearing range.
4. Every listener stores it in memory. Listening is free.
5. A listener calls the model only if it decides to respond.

A conversation is a short turn-taking session with a lock on both NPCs. Overhearers can join later. Start with a radius plus a same-area check; walls can refine it.

## Actions and affordances

The model does not choose from a fixed verb list. It chooses from the interactions available at that moment.

Each object, actor, vehicle, or place exposes actions:

- Door: open, close, enter, leave, lock, knock.
- Food or carried item: eat, drink, read, use, give, drop.
- Bed: sleep, rest.
- Job board: browse, apply.
- Shop counter: buy, sell, work a shift.
- Workstation: work.
- Train or zeppelin: board, ride, disembark.
- NPC: talk, ask, help, trade.
- Bench: sit, rest, sleep rough.
- Home: enter, leave, sleep, store.

Hunger and sleep are needs, not actions. The NPC eats by interacting with food and sleeps by interacting with a bed. If no bed is available, the ground or a bench offers sleep rough.

The action list is built from context: find what is in range, ask what it offers, filter by preconditions, add wait and talk, add reachable destinations, then rank and cap. Above about 16 candidates, use a two-stage choice: category first, then target.

No object in range means no interact action. Three objects mean three options. Context can remove actions: an in-transit zeppelin offers only talk, stay, and look; a conversation offers talk or end; a shift offers work actions.

Each option carries an id, label, target, preconditions, expected effects, and risk. The model picks one; the simulation validates and executes it. The model cannot invent an action that was not offered.

### Decision state

A tick state of about 750 tokens is enough: 608 for state plus 137 for options. Fields: name, day, time, location, current action, ETA, shift, needs, money, rent, wage, job, home, goal, traits, relationships, known facts, nearby actors, inventory, memories, plan, observation.

Example options: work the counter, buy bread, talk to Bob, read the job board, walk to the station, go home and sleep, wait.

## Needs and happiness

NPCs get tired and hungry. Sleeping at home restores energy. Sleeping rough gives poor rest and a penalty.

Happiness is an unbounded unsigned integer, clamped at zero. It is the lifetime record. Decisions use expected change plus a bounded recent mood, so a rich NPC still cares about a bad night.

| Event | Change | Limit |
| --- | ---: | --- |
| Sleep at home | +6 | once per day |
| Sleep on the street | -12 | once per day |
| Pay rent | +2 | per rent period |
| Miss rent | -25 | per period |
| Get evicted | -60 | once |
| Complete a shift | +4 | per shift |
| Complete a goal stage | +40 | per stage |
| Complete a life goal | +250 | once |
| Go hungry | -2 | per hour |
| Good conversation | +1 | per pair per hour |
| Help someone | +5 | per act |

The NPC knows the goal and the next step, not the formula. It knows simple consequences: home sleep beats the street, missing rent risks eviction.

Each option carries a precomputed expected change and a short label: "Sleep in your bed: +6, safe" or "Sleep rough here: -12, cold". The model chooses; the simulation does the arithmetic. Use cooldowns, diminishing returns, and daily caps so nothing can be farmed.

## Economy and housing

The world starts with fixed base jobs: shop clerk, cafe worker, station attendant, dock worker, groundskeeper. Each job has a title, employer, location, shift, wage, requirements, capacity, and status.

The job board lists vacancies. NPCs apply when they need money or want a better job. A vacant job goes to an applicant who meets the requirements; if several apply, pick by skill, reliability, or first come. Add an application cooldown and a rejection memory.

The world pays wages. Rent, food, taxes, and purchases at world-owned stores take money back. Log every source and sink so the money supply can be audited.

Stores need a clerk to open. No clerk means closed and no revenue. Do not tie critical transport to staffing at first; a missing conductor can break the player's travel.

Every NPC has a canonical home. Rent is due regularly. Failure to pay means eviction; the home becomes available and another NPC can take it. The evicted NPC is homeless until they recover.

Later, NPCs can start businesses: save capital, find a storefront, open, hire. That falls out of the goal system.

### Housing audit

| Region | Strict houses | Other residential | Notes |
| --- | ---: | --- | --- |
| Hidamari | 177 `HD_House_*` | 24 apartments, 22 machiya | 437 building instances total |
| Momiji | 2 cottages | 1 tea house | possibly living quarters |
| Belmonte | 11 (7 villas, 4 farmhouses) | 39 town blocks | plus civic and hippodrome meshes |
| Brinecove | 131 townhouses | 39 shacks, 43 taverns | 170 dwellings with shacks, 213 with taverns |

Strict total across the four regions: 321 houses. That is enough for 200 NPCs if apartments, machiya, and shacks are used, with room for vacancies and eviction.

## Decision loop

The world runs on a shared clock. A social tick runs at a fixed rate, for example 1 Hz. All NPCs see the same tick and events in the same order. Movement and animation run in Unreal at frame rate.

Each NPC has a next_decision_at. When it arrives, or when an event interrupts, the simulation builds the compact state and asks a few narrow questions: how urgent is this, and which option do I pick? Use confidence: above the threshold, act; below, continue or idle.

Walk, path, and collision belong to Unreal. The mind gets progress events: arrived, blocked, interrupted, path failed. A failed path triggers a new decision. A new observation is injected as an interruption: "You are still heading to the mill. You see Bob on the road. You are not in a hurry."

Observation injection needs a cooldown and a novelty check, or NPCs stop every few meters to talk.

Decisions run asynchronously with a state version. Apply the answer only if the state is still current; otherwise discard or re-decide.

When two NPCs meet, create one encounter event with a deterministic initiator, not two independent decisions. Lock both for the conversation.

For determinism: fixed seed, fixed event order, and a log of every request and response. That lets you replay a day.

## Tiers and models

Two tiers keep the bill and the latency budget predictable:

| Tier | Share | Tick | State | Model |
| --- | ---: | --- | --- | --- |
| Hot | 20% | every 60 s | full observations and conversations | Luna |
| Cold | 80% | every 5 min | compressed state and schedule | Qwen 3.7 Flash |

Reactions are event-driven in both tiers. An NPC who is spoken to, blocked, or robbed answers on the next social tick regardless of cadence. Promotion and demotion happen at tick boundaries so no NPC has two pending decisions. Cold NPCs lean on their schedule between ticks.

Fully off-screen NPCs can drop to schedule-only execution, with no call until something changes.

## God agent

One Luna agent with high reasoning runs once a minute and watches the whole town. It reads a 128K prompt: about 115K of stable material (rules, all 200 identity sheets, standing arcs) and 13K of fresh state (location, current action, goal stage, happiness trend, and flags for stuck, starving, homeless, or unpaid rent). The stable part is what makes a 90% cache rate plausible. The snapshot itself changes every minute and cannot be cached, so the prompt has to be laid out with the static roster first.

It does not command. It writes a short "god thought" into an NPC's context as an observation, with a reason and an expiry, and the NPC can ignore it. Cap inserts at a few per pass, use a per-NPC cooldown, and log every thought. The job is to catch an NPC who is stuck, looping, or about to do something destructive, not to play the town for them.

At 128K input per minute and 90% cache, input costs $0.146 per hour. With 2K output per pass the god agent costs about $0.21 per hour; with 4K, about $0.27. That adds $0.0010 to $0.0013 per agent-hour. Without cache it would be $0.77 per hour for input alone.

A high-reasoning pass may not finish in 60 seconds. Run it asynchronously and skip a minute rather than queue; the town can wait one pass for a nudge.

## Hosted models

All inference is hosted. Four lanes:

| Lane | Trigger | Budget | Latency | Model |
| --- | --- | ---: | --- | --- |
| Reaction | speech, blocked path, sudden event | 2K | under 1 s | JEV |
| Tick | regular deadline | 8K | a few seconds | Luna or Qwen |
| Reflection | every 10 in-game minutes | 32K | tens of seconds | Luna or Qwen |
| Chatter | an NPC says a line | 2K | under 2 s | cheap model |

JEV is $0.042 per 1M input with free output and answers in about 0.3 s. A 2K reaction costs $0.000084.

Luna is $0.10 per 1M input, $0.01 cached, $0.50 output, and about 1.9 s for structured output.

Qwen 3.7 Flash on Alibaba us-east-1 is $0.0345 input, $0.0069 cached, $0.1495 output. OpenRouter measures p50 728 ms, p90 1.84 s, p99 4.56 s on short probes; an 8K tick lands around 1.5 to 2 s at p50. It is not in EU in-region routing, so calls from Paris cross regions.

Hot-tier and player-facing speech uses Luna. Ambient cold-tier chatter uses the cheap model.

### Cheaper alternatives

| Model | Provider | In/M | Cache/M | Out/M | 8K tick, 90% cache |
| --- | --- | ---: | ---: | ---: | ---: |
| gpt-oss-20b | Darkbloom fp8 | $0.018 | $0.009 | $0.09 | $0.000088 |
| qwen3.7-flash | Alibaba us-east-1 | $0.0345 | $0.0069 | $0.1495 | $0.000092 |
| gemma-3-4b | Parasail bf16 | $0.04 | $0.02 | $0.05 | $0.000181 |
| Luna | OpenAI | $0.10 | $0.01 | $0.50 | $0.000210 |
| gemma-3-12b | DeepInfra bf16 | $0.05 | none | $0.15 | $0.000415 |

Pin the provider. The model-level OpenRouter price is the cheapest endpoint, not the one you get, and the same model varies in quantization, cache support, and uptime. Check implicit caching per endpoint. Gemma 3 has structured output but usually no tool calls; GPT-OSS-20B, Qwen 3.7, Qwen 3.5 9B, and Gemma 4 26B do.

Official DeepSeek deepseek-flash is $0.15 input, $0.003 cached, $0.60 output off-peak, double at peak (01:00-04:00 and 06:00-10:00 UTC on weekdays). At 90% cache that is $0.00020 per tick, a wash with Luna, and worse at peak. It is not worth switching for price.

Avoid 1B to 4B models for action choice. They work as narrow classifiers, not for picking from sixteen affordances. Batch and free variants are not production options.

Nothing is verified against Yorimichi states yet. Test 1,000 decisions and 500 lines, and score JSON validity, action validity, and latency, not just price.

## Cost

Assumptions: 200 NPCs; 20% hot at 1/min on Luna, 80% cold at 1/5min on Qwen; 8K tick with 100 output; 32K reflection with 800 output every 10 min; 12 chat lines per hour; one 2K JEV reaction every 3 min; 90% cache.

| Lane | Hot (Luna) | Cold (Qwen) |
| --- | ---: | ---: |
| Reactions, 20/hour | $0.0017 | $0.0017 |
| Tick | $0.0126 | $0.0011 |
| Reflection, 6/hour | $0.0060 | $0.0026 |
| Chatter, 12 lines/hour | $0.0008 | $0.0003 |
| **Total per agent-hour** | **$0.0211** | **$0.0057** |

Blended: **$0.0088 per agent-hour**, or **$1.76 per hour for 200 NPCs**. A two-hour session is $3.51; a 40-hour month is $70.

Same cadence, all-Qwen: $0.0066 per agent-hour ($1.32/hour). All-Luna: $0.0131 ($2.62/hour).

Adding the god agent at 2K output per pass: **$0.0098 per agent-hour**, or **$1.97 per hour for 200 NPCs**. At 4K output it is $0.0101 and $2.03.

The largest levers, in order: cache hit rate, reflection cadence and size, tick cadence, then the tick model. Tiering cuts the tick line by about 64%. Reflection is the biggest line for the cold tier, so move it to every 15 or 30 minutes before shrinking the state.

## Implementation plan

1. Build the affordance registry and context filter.
2. Build a headless Python simulation with 20 NPCs, five jobs, three stores, one job board, rent, food, sleep, and three goals. Run 30 in-game days.
3. Log every decision, wage, purchase, rent payment, conversation, goal update, token count, and cost.
4. Measure job fill, employment, money distribution, delinquency, goal progress, repetition, and cost per day.
5. Integrate five NPCs in Unreal, starting in Belmonte, using the village and wanderer actors and the live bridge.
6. Add LOD, batching, concurrency caps, and fallbacks.
7. Scale to 200 and compare the tick lane on GPT-OSS-20B and Qwen 3.7 Flash over 1,000 logged decisions; compare chatter on DeepSeek V4.1 Flash over 500 lines.

## Open questions

- How long is an in-game day in real time?
- Is chatter text-only, audible, or both?
- Can the player see happiness, or only infer it from behavior?
- When several NPCs apply for one job, who wins?
- Should critical services such as the train go unstaffed?
- How should the simulation catch up while the player is away?
- How much identity drift is allowed after major events?
- Do NPCs learn about unseen interactables, such as a job board inside a building?

## References

- JEV: https://docs.typesafe.ai/introduction
- OpenAI pricing: https://developers.openai.com/api/docs/pricing?tab=suite
- OpenRouter models and prices: https://openrouter.ai/models
- JevTown: https://github.com/NevaMind-AI/JevTown
- BFCL small decision-model pilot: https://huggingface.co/datasets/pyuvraj/bfcl-v4-jev-routing/blob/main/results_report.md

## Related Yorimichi code

- Village residents: games/yorimichi/unreal/Source/Yorimichi/VillageLife.h
- Playable wanderer: games/yorimichi/unreal/Source/Yorimichi/WandererCharacter.h
- Live bridge verbs: games/yorimichi/unreal/Source/Yorimichi/YorimichiLive.h
- Belmonte train service: games/yorimichi/unreal/Source/Yorimichi/BelmonteTrainService.h
- Zeppelin service: games/yorimichi/unreal/Source/Yorimichi/ZeppelinService.h
