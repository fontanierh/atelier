# Autonomous NPCs in Yorimichi

Status: design proposal. Nothing in this document is implemented yet.

Date: 2026-10-19.

## Goal

Yorimichi should have a town of autonomous NPCs with their own identity, jobs, homes, goals, needs, and social life. They keep living when the player is not interacting with them. The player can watch them, talk to them, and change their circumstances.

The design must work with hosted inference only. The target is 200 NPCs, one instance per NPC. Local models are not an option.

## Three layers

| Layer | Responsibility | Cadence |
| --- | --- | --- |
| Unreal | Movement, animation, collision, schedule execution, shared clock | Every frame |
| Decision model | Fast choices from the concrete affordances in range: open a door, talk to Mira, board the train, stay aboard, wait | On a decision deadline or an event |
| Language model | Speech, periodic reflection, medium- and long-term planning | When someone speaks or a reflection is due |

The decision model is the fast cognitive layer. The language model is the slow cognitive layer. Unreal is the reflex layer.

## Identity

Each NPC has a fixed sheet and a changing state.

The fixed sheet contains:

- name, age, origin, and home city
- personality traits and values
- fears, secrets, and voice style
- skills and work history
- a life goal
- a compact set of behavioral dispositions, such as whether they would steal if starving, risk their life for a friend, betray someone for money, lie, lead, or leave town

The changing state contains:

- mood, energy, and hunger
- money, job, and home
- relationships and reputation
- knowledge and beliefs
- current intention
- recent memories
- happiness score

Identity is authored once and stored as data. The language model can help write the prose bio and voice guide during development, but identity is not generated at runtime.

### Life goals

Life goals are structured, not free text. A goal has stages, progress, priority, and secrecy.

Example:

    Goal: open a bakery in Hidamari.
    Stage 1: save 300 coins. Progress: 120.
    Stage 2: find a vacant shop.
    Stage 3: get a permit.
    Stage 4: open and hire one clerk.

The decision model is weak at multi-step planning. It should choose the next action inside the current stage, not invent the whole plan. A deterministic goal state machine owns the stages.

## Knowledge and beliefs

The world has a shared gazetteer: places, routes, prices, job board, train schedule, shops, and public facts.

Each NPC has a personal knowledge graph. A fact has a source, a confidence, and possibly a false belief. NPCs know their hometown, workplace, routes, and a few rumors. They do not know everything. The mind sees their beliefs, not the ground truth. The player can teach them things, lie to them, or spread rumors.

## Memory

Memory has four parts:

- recent events, kept verbatim
- older events, summarized and compacted
- direct conversations and overheard speech
- important facts and relationships, retrieved when relevant

Every memory stores who, what, where, when, and whether it was direct or overheard. The language model writes the summaries during reflection. The decision model receives a compact working set: the current situation, the plan checkpoint, and the most relevant memories.

The full memory can be large. The decision prompt should stay small.

## Talking and hearing

Every NPC who speaks uses a language model. That includes conversations with the player and conversations with other NPCs.

When an NPC decides to talk:

1. The decision model chooses the target and the intent, for example: talk to Mira about the bakery job.
2. The language model writes the line using the speaker's persona, relationship, relevant memories, and the chosen intent.
3. The line goes to the direct listener and to every NPC within the hearing radius.
4. Every listener stores the line in their own memory and context.
5. A listener calls the language model only if they decide to respond.

A conversation is a short turn-taking session with a lock. One NPC speaks, the direct listener can respond, and nearby NPCs hear the exchange. Overhearers can later join if the decision model chooses to. Walls and rooms can block hearing; start with a radius plus a same-area check.

The speaker pays for one language-model call. The listeners pay nothing to hear the line. They pay later only if their larger context makes a future call bigger, or if they choose to speak.

Example: Mira tells Bob that the bakery is hiring. Bob hears it directly. The baker standing nearby hears it too. Both remember it. Later, the baker can mention it to someone else. News, gossip, warnings, and secrets spread through the town this way.

## Actions and affordances

The decision model does not choose from a fixed verb list like eat, sleep, or work. It chooses from the concrete interactions available at that moment.

The simulation maintains an affordance registry. Each object, actor, vehicle, or place exposes the actions it supports:

- Door: open, close, enter, leave, lock, knock.
- Food: eat, buy, cook.
- Carried item: eat, drink, read, use, give, drop.
- Bed: sleep, rest.
- Job board: browse, apply.
- Shop counter: buy, sell, work a shift.
- Workstation: work a shift.
- Train: board, ride, disembark.
- Zeppelin: board, ride, disembark.
- NPC: talk, ask, help, trade.
- Bench: sit, rest, sleep rough.
- Home: enter, leave, sleep, store items.

Hunger and sleep are needs, not actions. The NPC satisfies hunger by interacting with food, and sleep by interacting with a bed. If no bed is available, the ground or a bench offers sleep rough.

At each decision, the simulation builds the action list from context:

1. Find the objects and actors in range.
2. Ask each one which actions it currently offers.
3. Filter by preconditions: is it open, is it locked, is the NPC allowed, is the vehicle docked, does the NPC have money, is the shift active?
4. Add the always-available actions: wait, and talk to a nearby NPC if one is present.
5. Add movement options: the relevant reachable destinations, such as home, work, the station, the current goal, or a nearby exit.
6. Rank and cap the list. If there are more than about 16 candidates, use a two-stage choice: first category (talk, interact, move, wait), then the concrete target.

If nothing is in range to interact with, there is no interact action. If three things are in range, each becomes a separate option. The NPC can always act on what is around them, but only through the actions that object exposes.

Examples:

- At home: open the door, enter home, sleep in bed, eat the bread, leave for work.
- On the street: talk to Mira, board the train, enter the bakery, walk to the station.
- At the zeppelin dock: board the zeppelin to Hidamari, talk to the pilot, walk to the market.
- Aboard a moving zeppelin: talk to a passenger, stay aboard, look out the window. Disembark appears only when docked.
- Aboard a train: talk to a passenger, stay aboard, disembark at the next stop when the train is stopped.

Context can remove actions. In a moving vehicle, the movement options are replaced by the vehicle's stops. Aboard an in-transit zeppelin, only talk, stay, and look are available. In a conversation, only talk or end the conversation. In a shop during a shift, the work actions are available; leaving is allowed but has consequences.

Each option carries an id, label, target, preconditions, expected effects, and risk. Expected effects include time, money, hunger, energy, happiness, and relationship changes. The decision model picks one option; the simulation validates it again and executes it. The model cannot invent an action that was not offered.

## Needs, sleep, and happiness

NPCs get tired and hungry. Sleeping at home restores energy. Sleeping on the street gives poor rest and a penalty.

Each NPC has a happiness score: an unbounded unsigned integer, clamped at zero.

The score is the lifetime record. Decisions use the expected change and a recent mood value, so a rich NPC still cares about a bad night's sleep. The recent mood is a bounded 0 to 100 value based on the last few days.

Example deterministic rewards:

| Event | Change | Limit |
| --- | ---: | --- |
| Sleep at home | +6 | once per day |
| Sleep on the street | -12 | once per day |
| Pay rent | +2 | once per rent period |
| Miss rent | -25 | once per period |
| Get evicted | -60 | once |
| Complete a work shift | +4 | once per shift |
| Complete a goal stage | +40 | per stage |
| Complete a life goal | +250 | once |
| Go hungry | -2 | per hour |
| Good conversation | +1 | once per pair per hour |
| Help someone | +5 | per act |

The NPC knows the goal and the next step, not the exact reward formula. They know simple consequences: sleeping at home is better than sleeping outside, and missing rent risks eviction.

Each action option can carry a precomputed expected change and a short label, such as "Sleep in your bed: +6, safe" or "Sleep rough here: -12, cold." The decision model chooses the action; the simulation does the arithmetic.

Use cooldowns, diminishing returns, and daily caps to prevent farming. Do not let an NPC sleep all day for a reward or repeat the same conversation for points.

## Economy and jobs

The world starts with a fixed list of base jobs: shop clerk, cafe worker, station attendant, dock worker, groundskeeper, and so on.

Jobs have:

- title
- employer
- location
- shift start and end
- wage
- requirements
- capacity
- status

The job board lists vacancies. NPCs apply when they need money or want a better job. If a job is vacant and the NPC meets the requirements, they get it. If several apply, the employer picks by skill, reliability, or first come. Add an application cooldown and a rejection memory so NPCs do not spam the board.

The world pays wages. Rent, food, taxes, and purchases from world-owned stores take money back out. Log every source and sink so the money supply can be checked.

Stores need a clerk to open. If the clerk is absent, the store is closed and earns nothing. Avoid tying critical transport to staffing at first; a missing train conductor can break the player's travel.

Every NPC has a canonical home. Rent is due regularly. If they cannot pay, they are evicted. The home becomes available and another NPC can take it. The evicted NPC becomes homeless until they recover.

Later, NPCs can start businesses: save capital, find a vacant storefront, open, and hire. This is a natural extension of the goal system.

## Decision loop

The world runs on a shared clock. A social tick runs at a fixed rate, for example 1 Hz. All NPCs see the same tick and events in the same order. Movement and animation run inside Unreal at the normal frame rate.

Each NPC has a next_decision_at time. When it comes up, or when an event interrupts, the simulation builds a compact state:

- identity and current mood
- place, time, job, money, and home
- nearby people and available places
- current plan checkpoint
- recent and relevant memories
- the current observation

Then the decision model answers a few narrow questions:

- Noul: "Am I hungry?" "Is the person in front of me someone I know?" "Is my shift starting soon?"
- Choice: "What do I do next?" with the 8 to 16 concrete options built from the current affordances.
- Score: "How urgent is this?" or "How much do I want to talk to this person?"

Use confidence. Above the threshold, act. Below it, continue the current action or idle. If the choice is talk, pass the target and intent to the conversation manager. If the choice is interact, run the object action. If the choice is go somewhere, Unreal handles the path.

While an NPC is walking, Unreal owns the path. The mind receives progress events: arrived, blocked, interrupted, path failed. If the path fails, re-decide. If a new observation arrives, inject it as an interruption: "You are still heading to the mill. You see Bob on the road. You are not in a hurry."

Observation injection needs a cooldown. Otherwise NPCs stop every few meters to talk. Use a per-pair conversation cooldown and a novelty check.

Decisions can run asynchronously. Send a request with a state version; apply the answer only if the state is still current. If the answer is stale, discard it or re-decide.

## Shared clock and scale

The shared clock makes encounters ordered and reproducible. When two NPCs meet, create one encounter event with a deterministic initiator, not two independent decisions. Put a conversation lock on both so they cannot start another conversation mid-exchange.

For determinism, use a fixed seed, a fixed event order, and log every decision request and response. That lets you replay a day and see why an NPC did something.

Use simulation level of detail. Nearby NPCs get full cognition. Distant NPCs follow schedules and update the economy at day boundaries. When the player approaches, promote them to full simulation. The shared clock still applies when they are co-simulated.

## Hosted model stack

All inference is hosted. No local models.

### Decisions

Use JEV or Laya.

| Model | Hosting | Price | Context | Notes |
| --- | --- | ---: | ---: | --- |
| JEV 1.14 | TypeSafe or Vercel AI Gateway | $0.042 per 1M input, output free | 32K | Handles a 20K decision prompt |
| Laya Studio | Laya Studio | $0.0357 per 1M input | 1,024-token model | 15% below JEV; compact the decision state to about 800 tokens |

Laya is the cheaper hosted decision model, but it cannot take a 20K prompt. If the decision state must stay at 20K, use JEV. If the state is compact, Laya is much cheaper.

### Chatter

| Model | Input per 1M | Output per 1M | Notes |
| --- | ---: | ---: | --- |
| Gemma 4 E4B | $0.02 | $0.10 | 131K context; cheapest practical chatter |
| GPT-OSS-20B | $0.05 | $0.20 | 131K context; better general chat quality |
| Ling 3.0 Flash | $0.02 | $0.06 | 256K context; test reliability, can over-think |

Use Gemma or GPT-OSS for ambient NPC-to-NPC chatter. Use Luna for player-facing or story-critical dialogue.

### Reasoning

Keep Luna for periodic planning and reflection. It reviews recent events, updates the plan checkpoint, and writes the memory summary. Run it every 30 to 60 in-game minutes, not every tick.

### Routing and accounting

Route calls through Vercel AI Gateway so the same key can reach JEV, Laya, Gemma, GPT-OSS, and Luna. Record every paid call through atelier.ai.ledger.

## Cost estimates

These are estimates as of October 2026. Prices change; verify before committing.

Assumptions:

- 200 NPCs, one instance per NPC
- 20K input tokens per call unless marked compact
- one decision every 30 seconds
- 24 chat lines per NPC per hour, about six conversations of four lines
- two Luna reflections per NPC per hour
- Luna reasoning at 90% cached input
- no voice synthesis

Per 1,000 calls:

| Call | Cost per 1,000 |
| --- | ---: |
| JEV decision, 20K input | $0.84 |
| Laya Studio decision, 1K input | $0.036 |
| Gemma decision, 20K in and 50 out | $0.405 |
| Gemma line, 20K in and 150 out | $0.415 |
| GPT-OSS-20B line, 20K in and 150 out | $1.03 |
| Luna line, 20K in and 150 out, 90% cached | $0.455 |

Totals for 200 NPCs:

| Stack | Per hour | 2-hour session | 40-hour month |
| --- | ---: | ---: | ---: |
| Laya 1K + Gemma chatter 8K + Luna reasoning | $1.88 | $3.76 | $75 |
| Laya 1K + Gemma chatter 20K + Luna reasoning | $3.03 | $6.06 | $121 |
| JEV 20K + Gemma chatter 8K + Luna reasoning | $21.18 | $42.36 | $847 |
| JEV 20K + Gemma chatter 20K + Luna reasoning | $22.33 | $44.67 | $893 |
| JEV 20K + Luna cached chatter 20K + reasoning | $22.53 | $45.05 | $901 |
| Gemma decisions 20K + Gemma chatter 20K + Luna reasoning | $11.89 | $23.79 | $476 |

The largest lever is compacting the decision state. Laya at 1K is about 24 times cheaper than JEV at 20K for the decision step. Switching chatter from cached Luna to Gemma saves a smaller amount because Luna's cached input is already cheap.

If NPCs chat twice as much, 48 lines per NPC per hour, the Laya + Gemma 8K stack rises to about $2.72 per hour, or $5.44 per two-hour session. The JEV 20K + Gemma 8K stack rises to about $22.02 per hour, or $44.04 per session.

## Implementation plan

1. Build the affordance registry and context filter. Define each interactable's actions, preconditions, and effects, then build the per-NPC action list from range and context.
2. Build a headless Python simulation with 20 NPCs, five jobs, three stores, one job board, rent, food, sleep, and three life goals. Run 30 in-game days.
3. Log every decision, wage, purchase, rent payment, conversation, goal update, token count, and cost.
4. Measure job fill rate, employment, money distribution, rent delinquency, goal progress, conversation repetition, confidence distribution, and cost per simulated day.
5. Integrate five NPCs into Unreal, starting in Belmonte. Use the existing village and wanderer actors and the live bridge.
6. Add simulation LOD, batched decisions, concurrency caps, and fallbacks.
7. Scale to 200 NPCs and compare JEV/Luna against Laya/Gemma on 1,000 decisions and 500 lines.

## Open questions

- How long is an in-game day in real time?
- Is NPC-to-NPC chatter text-only, audible, or both?
- How much of the 20K context is static persona and world text, and how much is fresh conversation?
- Can the player see the happiness score, or only mood through behavior and dialogue?
- When several NPCs apply for one job, does the employer use skill, reliability, first come, or a lottery?
- Should critical services such as the train be allowed to go unstaffed?
- How should the simulation catch up when the player is away?
- How much identity drift should be allowed after major events?
- How many nearby objects should be offered before switching to a two-stage choice?
- Which contexts should restrict the action set: vehicles, shops, conversations, jail, sleep?
- Should vehicle travel be one composite action or a sequence of board, stay, and disembark decisions?
- How do NPCs learn about interactables they cannot see, such as a job board inside a building or a train at the next platform?

## References

- JEV documentation: https://docs.typesafe.ai/introduction
- JEV on Vercel AI Gateway: https://vercel.com/ai-gateway/models/jev
- Laya pricing: https://laya.studio/pricing
- Laya API: https://laya.studio/docs/api
- JevTown, a JEV-based AI town: https://github.com/NevaMind-AI/JevTown
- JevTown data card: https://jevtown.com/data-card
- BFCL V4 small decision-model pilot: https://huggingface.co/datasets/pyuvraj/bfcl-v4-jev-routing/blob/main/results_report.md
- OpenAI pricing: https://developers.openai.com/api/docs/pricing?tab=suite
- Gemma 4 E4B pricing: https://www.llmboard.ai/models/gemma-4-e4b
- GPT-OSS-20B on Vercel: https://vercel.com/ai-gateway/models/gpt-oss-20b/providers

## Related Yorimichi code

- Village residents: games/yorimichi/unreal/Source/Yorimichi/VillageLife.h
- Playable wanderer: games/yorimichi/unreal/Source/Yorimichi/WandererCharacter.h
- Live bridge verbs: games/yorimichi/unreal/Source/Yorimichi/YorimichiLive.h
- Belmonte train service: games/yorimichi/unreal/Source/Yorimichi/BelmonteTrainService.h
- Zeppelin service: games/yorimichi/unreal/Source/Yorimichi/ZeppelinService.h
- Happiness, jobs, homes, and memory are new systems proposed by this document.
