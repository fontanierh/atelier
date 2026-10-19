# Suno music API

Suno has no public self-serve developer API. The consumer web app talks to an internal REST API, and a subscribed
account can use that same API to generate instrumental music for games. This page documents the flow used by the
working client at `games/yorimichi/tools/suno_client.py`. The endpoints are internal and can change without notice.

## Credentials

The ignored repository-root `.env` holds the two values copied from a signed-in browser:

```sh
SUNO_CLIENT_COOKIE=...   # __client, the long-lived refresh JWT
SUNO_CLIENT_UAT=...      # __client_uat, its companion timestamp
```

`.env` stays mode 0600 and is ignored by git. Never print, paste or commit these values. The refresh token rotates
when it is used; the client writes the new value back to `.env` after every refresh.

To re-copy the values, open `https://suno.com` while signed in, open DevTools, then **Application → Cookies**:

- `auth.suno.com` → `__client` (HttpOnly, long JWT starting with `eyJ`)
- `.suno.com` → `__client_uat` (a Unix timestamp)

If `auth.suno.com` is not listed, open the Network tab, filter `auth.suno.com`, reload, and copy the request's
`Cookie` header from a `v1/client` call.

## Token refresh

The access token lasts about one hour. Exchange the refresh cookie for one:

```http
GET https://auth.suno.com/v1/client?__clerk_api_version=2025-11-10&_clerk_js_version=5.117.0
Cookie: __client=<...>; __client_uat=<...>
```

Read `response.last_active_session_id` as `<sid>`, then:

```http
POST https://auth.suno.com/v1/client/sessions/<sid>/tokens?__clerk_api_version=2025-11-10&_clerk_js_version=5.117.0
Cookie: __client=<...>; __client_uat=<...>
```

The response's `jwt` is the bearer token for the API. Both calls return rotated `__client` / `__client_uat` cookies;
persist them. Then send:

```http
Authorization: Bearer <jwt>
```

to `https://studio-api-prod.suno.com` (the older `studio-api.prod.suno.com` host also accepts the same token).

## Account and costs

```http
GET https://studio-api-prod.suno.com/api/billing/info/
```

The response includes `credits`, `total_credits_left`, `monthly_usage`, `monthly_limit`, `plan`, and
`download_usage`.

- **Generation:** 5 credits per track. One request normally returns two tracks, so a batch costs 10 credits.
- **Official downloads:** a separate download bucket. Premier includes 60 downloads per billing period; extra
  packs are sold at about $2.99 for 1, $8.95 for 3, $14.95 for 5, and $29.90 for 10. These are not generation credits.
- The `/api/download/clip/{id}` endpoint can answer `not_authorized` for clips generated through this API. The
  playback-license path below produces the same audio without spending a download credit.

## Captcha

`POST /api/c/check` with `{"ctype":"generation"}` returns `required: true` and `captcha_version: 2` for the web
client. The generation Turnstile site key is `0x4AAAAAADI7xDNyj-3LcIbi`. A real browser is needed: render the
widget on `suno.com`, wait for its callback, and use the token once. The working client drives a local Chrome on
debug port 9223 through Playwright.

## Generate

```http
POST https://studio-api-prod.suno.com/api/generate/v2-web/
Content-Type: application/json
Authorization: Bearer <jwt>
```

```json
{
  "prompt": "",
  "title": "",
  "gpt_description_prompt": "instrumental game score, warm woodwinds and harp, ...",
  "make_instrumental": true,
  "mv": "chirp-hawk",
  "generation_type": "TEXT",
  "metadata": {},
  "token": "<turnstile token>",
  "token_provider": 2,
  "task": null,
  "project_id": null,
  "override_fields": [],
  "duration": null,
  "edit_session_id": null,
  "transaction_uuid": "<uuid4>"
}
```

Model keys:

| Key | Version |
| --- | --- |
| `chirp-hawk` | v6 |
| `chirp-goose` | v6 mini |
| `chirp-fenix` | v5.5 |
| `chirp-crow` | v5 |

For a custom song, put lyrics in `prompt`, set `tags` and `title`, and leave `gpt_description_prompt` empty.
For game music, keep `make_instrumental` true and describe the mood and instrumentation instead of naming artists
or franchises.

The response has `clips[]` with `id`, `status`, `model_name`, and metadata. A batch normally contains two clips.

## Poll

```http
GET https://studio-api-prod.suno.com/api/feed/v2?ids=<id>,<id>
```

Statuses are `submitted`, `streaming`, `complete`, and `error`. Download after every clip is `complete`.

## Download and decrypt

The clip's `audio_url` is an access-controlled `/api/forbidden` URL. The playable file is in `media_urls`:

```http
GET https://studio-api-prod.suno.com/api/clip/<id>
```

`media_urls[0].url` is an encrypted `.m4a` (Opus in MP4) on CloudFront. Fetch it, then get the per-clip license:

```http
POST https://studio-api-prod.suno.com/api/mango/rights
Content-Type: application/json

{"content_params":{"content_id":"<id>","content_type":"clip"}}
```

The response is base64 `key` and `iv`. The wrapping key is `SHA-256(<access jwt>)`, imported as AES-GCM. For each
base64 blob, the first 12 bytes are the GCM nonce, the rest is ciphertext plus tag, and the additional data is the
UTF-8 clip id:

```python
import base64, hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

gcm = AESGCM(hashlib.sha256(jwt.encode()).digest())

def unwrap(blob: str, clip_id: str) -> bytes:
    raw = base64.b64decode(blob)
    return gcm.decrypt(raw[:12], raw[12:], clip_id.encode())

key = unwrap(rights["key"], clip_id)
iv = unwrap(rights["iv"], clip_id)
```

Decrypt the CloudFront bytes with AES-CTR (128-bit counter, starting at `iv`). The result is a normal `.m4a`:

```python
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

dec = Cipher(algorithms.AES(key), modes.CTR(iv)).decryptor()
plain = dec.update(encrypted) + dec.finalize()
```

Convert for review if useful:

```sh
ffmpeg -v error -i track.m4a -codec:a libmp3lame -q:a 2 track.mp3
```

## Working client

`games/yorimichi/tools/suno_client.py` (mode 700) implements the whole flow and rotates the cookie into `.env`:

```sh
python3 games/yorimichi/tools/suno_client.py billing
python3 games/yorimichi/tools/suno_client.py feed
python3 games/yorimichi/tools/suno_client.py generate "autumn coastal road, warm woodwinds, instrumental" --instrumental --wait --download
python3 games/yorimichi/tools/suno_client.py download <clip-id>
```

Generation needs the local Chrome debug port 9223 open on a `suno.com` page. Outputs go to the Atelier cache under `suno/out/`.

## Music for games

- The Yorimichi library has 28 zone scores (day, quiet and contrast pairs), 12 action/set-piece cues and 28 style
  cues (lofi, percussion-heavy energy, ambient, jazz and world). Each request returns two takes.
- Instrumental only, no lyrics or choir. Zone music is restrained chamber-orchestral with Japanese color; the style
  library deliberately leaves that palette for lofi, percussion and other moods.
- Validate the decrypted file with `ffprobe`. Keep the model, prompt, clip id and credit cost in a provenance file.
- Keep the decrypted M4A masters and MP3 review copies under `build/<game>/music/` while under review. Publish the
  MP3s, manifests and catalog as a release asset; the optional game build selects and imports only what it needs.
- Tag every track with `category`, `style_family`, `energy`, `intent`, `mood`, `use`, `bpm_target`, `loop` and clip
  provenance. A flat dump of files is not enough for a runtime that has to choose music by context.
