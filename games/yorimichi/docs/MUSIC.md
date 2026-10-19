# Music library

Yorimichi's music is generated with Suno v6 (`chirp-hawk`) and kept outside the
repository as a tagged library release. The game can use a small selection, all
of it, or none of it. The runtime director is a separate step; the first job of
this library is to provide enough distinct, correctly tagged material to choose
from.

The library has three parts:

| Part | Cues | Tracks | Purpose |
| --- | ---: | ---: | --- |
| Zone score | 28 zones | 168 | day, quiet and contrast takes for every zone |
| Action and set pieces | 12 | 24 | combat, pursuit, boss, storms, rituals, victory and defeat |
| Style library | 28 | 56 | lofi hip hop, percussion-heavy action, ambient, jazz and world |

Each generation returns two takes. All tracks are instrumental: no lyrics,
vocals or choir. The request asks for a 480-second arrangement, but Suno returns
different lengths, usually between three and eight minutes. That variation is
useful: the runtime can enter a track at a phrase boundary and leave it when the
scene changes instead of forcing every cue to the same clock.

## Tags

Every track is tagged in three places: its group manifest under
`build/yorimichi/music/`, the release's `catalog.json`, and the MP3 ID3 fields.
The important selectors are:

- `category`: `calm`, `moderate`, `energetic`, `action` or `contrast`.
- `style_family`: `orchestral`, `ambient`, `lofi`, `energy`, `jazz` or `world`.
- `energy`: 1 (quiet) through 5 (intense).
- `intent`: `exploration`, `ambient`, `contrast`, `combat`, `action`,
  `environment`, `set_piece`, `reward`, `story`, `calm` or `celebration`.
- `mood`, `use`, `bpm_target` and `loop`: describe the moment a cue fits.
- `zone`, `zone_name`, `role`, `group` and `clip_id`: provenance.

The `zone` tracks are deliberately similar within a zone so a quiet take can
crossfade into a day take. The action and style libraries are deliberately
different: use `category` and `style_family` to keep a lofi exploration cue out
of a boss fight.

## Generate

The credential flow and endpoint details are in
[`docs/SUNO_API.md`](../../../docs/SUNO_API.md). The ignored repository-root
`.env` holds `SUNO_CLIENT_COOKIE` and `SUNO_CLIENT_UAT`; the client rotates them
after every refresh. Never print or commit either value.

The three batch runners are resumable and write one manifest after each cue:

```sh
python3 games/yorimichi/tools/generate_music.py            # zones
python3 games/yorimichi/tools/generate_action.py           # action library
python3 games/yorimichi/tools/generate_variety.py          # style library
```

Add `--zone KEY --role quiet`, or `--cue KEY`, to regenerate one item. Outputs
go to the ignored `build/yorimichi/music/`:

| File | Contents |
| --- | --- |
| `<zone>/manifest.json` | zone identity, prompts, takes, durations and file paths |
| `library/<cue>/manifest.json` | action cue and its provenance |
| `variety/<cue>/manifest.json` | style cue and its selector metadata |
| `index.json` | the review page's combined index |
| `reviews.json` | ratings and notes from the review page |

Generation costs 5 credits per track. A normal request returns two takes, so a
cue costs 10 credits. The player-license decrypt path does not spend the
account's separate download credits.

## Review

Serve the page only on the Tailscale address, so it is not exposed on the LAN:

```sh
python3 games/yorimichi/tools/music_review_server.py --bind <tailscale-ip> --port 8099
```

Open `http://<tailscale-ip>:8099/`. The page has separate zone, action and style
sections, plays the MP3 review copies with seeking, and saves Good / Maybe / No
plus a note for every clip. It polls `index.json`, so newly generated cues
appear without restarting the server. The server supports HTTP range requests,
which is what lets the browser scrub multi-minute tracks.

## Download and release

The MP3 review set is large enough that it stays out of git. The repository keeps
the plans, the generators, the fetch tool and a checksum lock. Build the release
archive and lock with:

```sh
python3 games/yorimichi/assets/audio/music/tag.py
python3 games/yorimichi/assets/audio/music/bundle.py --url \
  https://github.com/<owner>/<repo>/releases/download/yorimichi-music-v1/yorimichi-music-v1.zip
```

`tag.py` writes ID3 title, artist, album, genre and custom `YORIMICHI_*` fields
without re-encoding the audio. `bundle.py` includes the MP3s, manifests,
`catalog.json` and a short `README.md`; it leaves the large decrypted `.m4a`
masters out by default. Pass `--include-masters` only when a local archive needs
them. The lock records the bundle URL, zip SHA-256 and every file's size and
hash.

Fetch and verify the published bundle into the Atelier cache:

```sh
python3 games/yorimichi/assets/audio/music/fetch.py
```

Use `--bundle PATH` for a local zip. A fresh clone can verify exactly which
bytes belong to the soundtrack without carrying the audio in git. The release
may contain far more tracks than the shipped game uses; the tags are the
selection contract.

## Optional game build

The default build does not download or import music. Name the music steps only
when the build should bake in a selection:

```sh
YORIMICHI_MUSIC_CATEGORIES=calm,moderate \
YORIMICHI_MUSIC_STYLES=lofi,ambient \
uv run atelier build yorimichi unreal.music
```

`audio.music` writes the selected list to
`build/yorimichi/audio/music/manifest.json`; `unreal.music` imports those files
as `/Game/Audio/Music/<section>/<group>/` and stages the tagged asset list at
`/Game/Data/Music/library.json`. Selectors are comma-separated and can
be combined with `YORIMICHI_MUSIC_GROUPS` and `YORIMICHI_MUSIC_LIMIT`. A build
without the music steps remains valid and contains no music assets.

The runtime should not play a track continuously just because one exists. Start
music on arrival or after a landmark, leave silence and ambience between cues,
and crossfade on a phrase boundary over several seconds. Calm and lofi cues fit
exploration, interiors, menus and safe travel; energy 4-5 and `action` cues fit
fights, chases and set pieces. Avoid changing tracks during dialogue, a cutscene
or an interaction prompt, and fade out before a hard scene transition. The long
takes exist to make those choices possible, not to loop as short stingers.
