# Zone soundtrack

Yorimichi's zone score is generated with Suno v6 from the plan in
[`assets/audio/music/plan.json`](../assets/audio/music/plan.json). The plan covers 28 zones, each with two prompts
(`day` and `quiet`); each generation returns two variants, so every zone gets four tracks.

The direction is an original instrumental adventure score: chamber orchestra, warm woodwinds, harp and strings,
light hand percussion, and touches of koto and shinobue. The melodies are restrained rather than bombastic, and no
track has vocals, lyrics or choir. The model is `chirp-hawk` (v6, Suno's best model); the request asks for a
480-second arrangement, though the actual generated length varies between roughly three and eight minutes.

## Generate

The API flow and credential setup are in [`docs/SUNO_API.md`](../../../docs/SUNO_API.md). The batch runner is
resumable and writes each completed role to the zone manifest:

```sh
python3 games/yorimichi/tools/generate_music.py                 # all zones
python3 games/yorimichi/tools/generate_music.py --zone spawn    # one zone
python3 games/yorimichi/tools/generate_music.py --zone spawn --role quiet
```

Outputs go to the ignored `build/yorimichi/music/`:

| File | Contents |
| --- | --- |
| `<zone>/manifest.json` | zone identity, prompts, clip ids, model, duration, file paths and credit estimate |
| `<zone>/*.mp3` | review copies |
| `<zone>/*.m4a` | decrypted masters |
| `index.json` | the live index the review page reads |
| `reviews.json` | ratings and notes from the review page |

Generation costs 5 credits per track (10 for a two-track batch). The current account has enough monthly credit for
the full set. Downloads use the player-license decrypt path and do not consume download credits; see the API guide
for the AES-GCM/AES-CTR flow.

## Review

Serve the page on the tailnet, binding only to the Tailscale address so it is not exposed on the LAN:

```sh
python3 games/yorimichi/tools/music_review_server.py --bind <tailscale-ip> --port 8099
```

Then open `http://<tailscale-ip>:8099/`. The page groups tracks by zone, plays the MP3s with seeking, saves
Good / Maybe / No and a note per clip, and refreshes as new zones finish. The server supports HTTP range requests,
so the browser can scrub long tracks.

## Integration

Keep the generated masters under `build/yorimichi/music/` until they are reviewed. When a zone's four tracks are
approved, add the selected files to the game's audio asset pipeline with their manifest entry (prompt, model, clip
id and duration) as provenance. The tracks are deliberately long and musically similar within a zone so the game
can crossfade between them; do not cut them into short loops before the blend is designed.
