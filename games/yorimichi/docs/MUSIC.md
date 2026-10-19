# Zone soundtrack

Yorimichi's zone score is generated with Suno v6 from the plan in
[`assets/audio/music/plan.json`](../assets/audio/music/plan.json). The plan covers 28 zones, each with three prompts
(day, quiet and contrast); each generation returns two variants, so every zone gets six tracks.

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

Keep the generated masters under `build/yorimichi/music/` until they are reviewed. When a zone's six tracks are
approved, add the selected files to the game's audio asset pipeline with their manifest entry (prompt, model, clip
id and duration) as provenance. The tracks are deliberately long and musically similar within a zone so the game
can crossfade between them; do not cut them into short loops before the blend is designed.

## Bundling

The complete set is about 1.2 GB with the contrast pass, so it should not be committed to git. Use a release asset or object store and the existing fetch pattern:

1. Build the zip and lock file:

   python3 games/yorimichi/assets/audio/music/bundle.py --url https://example.invalid/yorimichi-music-v1.zip

2. Publish that zip at the URL. A GitHub Release asset or the project object store both work.
3. Commit music.lock.json: it records the bundle URL, the zip SHA-256, and every file's path, size and SHA-256.
4. Add assets/audio/music/fetch.py to game.toml [fetch].scripts, with needs = ["yorimichi/music"].
5. Run atelier fetch yorimichi. The fetch script downloads and verifies the zip into the Atelier cache; the game build imports from there.

The lock file is the contract. A fresh clone can verify exactly which bytes belong to the soundtrack without carrying the audio in git. The review page and the full-size bundle stay outside the repository.

If a single-clone workflow is required, Git LFS is the alternative. The full set is near the free LFS storage and bandwidth limits, and compressed loop edits are the practical way to keep a committed subset under a few hundred megabytes.
