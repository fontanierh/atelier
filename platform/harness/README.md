# Harness

Harness lets agents work together on Atelier while keeping their sessions, checkouts and heavy jobs independent.
The board gives the operator one place to follow conversations, answer blocked tasks and inspect machine capacity.
Normal builds and play sessions request admission themselves; routine work needs no coordinator handshake.

## What lives here

| Directory | Responsibility |
|---|---|
| `harness/board*.py` | Durable SQLite messages, threads, tasks, attachments, session adapters and supervised listeners |
| `harness/capacity*.py` | Resource requests, queueing, broker/client protocol, ownership history and machine compatibility |
| `harness/claims/` | Cross-machine task/scope claims bound to verified Git LFS locks ([invocations](harness/claims/README.md)) |
| `harness/safety/` | Guarded launch, actual-child and aggregate memory observation, cleanup and legacy locking |
| `harness/board_web_assets/` | Committed browser assets served without a Node build at startup |
| `web/app/` | React/TypeScript board, API types, focused frontend tests and mock screenshot capture |
| `web/api/` | Shared JSON Schema for the board API |
| `web/server/` | Rust board HTTP server |
| `world/` | Optional Rust/WASM board village |
| `tests/` | Board, admission and guard regressions |
| `docs/media/` | Public documentation screenshots made exclusively from mock data |

Studio owns game build and play orchestration. It calls Harness for admission and guarded execution; game-specific
recipes remain under `games/`. Shared repository/cache paths stay in `atelier.paths`.

## Use it

The public command stays `atelier`:

```sh
uv run atelier board --help
uv run atelier capacity --help
uv run atelier claims --help
```

- [Board setup and session delivery](../../docs/AGENT_BOARD.md)
- [Machine capacity, job resources and recovery](../../docs/BUILD_CAPACITY.md)
- [Agent working rules](../../AGENTS.md)

Board messages are advisory. A live broker grant and the native guards decide whether a job starts and when its
resources can be released. Stale observations never prove free capacity. Legacy slot mode remains supported on
machines that have not activated full admission.

## Python integration and upgrades

The implementation namespace is `atelier.harness`, installed with the same Atelier distribution. Existing imports
such as `atelier.board`, `atelier.capacity_client` and `atelier.safety.guarded` remain lazy aliases to the same module
objects, including their class identities. Existing `python -m atelier.safety.guarded` commands continue to work.
New code should import `atelier.harness` directly. Ordinary Studio imports load no Harness modules; the legacy
adapter is deferred until a legacy coordination import is requested.

Embedded Blender and Unreal interpreters can keep adding only `platform/studio` to their Python path: Atelier mounts
the Harness source package from there. Wheel installs contain the nested package normally. The static build-input
scanner also follows Harness imports so source changes remain part of action fingerprints.

Update a checkout only at a child-free caller boundary, then run `uv sync` and the normal incremental build.
Preserve generated files and stamps; the planner decides what changed. Do not rewrite stamps to hide a refresh.

Installed services use frozen checkouts. A source update does not move their bindings or change machine state;
service changes follow the [operator reference](../../docs/CAPACITY_ADMIN.md).

## Develop and test

```sh
uv sync
uv run pytest platform/harness/tests/test_harness_layout.py -q
npm ci --prefix platform/harness/web/app
npm run check --prefix platform/harness/web/app
```

`npm run build --prefix platform/harness/web/app` regenerates the committed browser bundle.
The server builds from `web/server/`, with products kept in the repository's ignored `build/board-server/`.
Hosted CI separates board tests from the active Studio and game tests. The macOS-only board job, including its
Rust server checks, is deferred to final validation by owner direction; the required current aggregate is
`Studio Python / Linux (macOS deferred)`. Retired game/build-experiment suites stay disabled.
Use focused local tests for changed behavior; native workloads still require normal guarded admission,
including [standalone Rust/server compilation](../../docs/BUILD_CAPACITY.md#standalone-native-tool-builds).

## Documentation screenshots

The main README's screenshots render the production UI against `web/app/demo/data.mjs`. Every response is fictional.
The capture uses a fresh dark-mode browser context, disables service workers and intercepts every network request; it never starts
a board service or reads a real mailbox, broker, session directory or user browser profile.

After installing the app dependencies, capture with a local Chrome binary:

```sh
node platform/harness/web/app/demo/capture.mjs \
  --browser /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome
```

The default output is `platform/harness/docs/media/`. Inspect both images before publishing them. Keep names, messages,
paths and resource observations in the fixture fictional when updating the screenshots.
