# Publishing an existing game package

`atelier release publish` uploads an existing independently verified macOS package to the selected source
checkout's GitHub `origin`. It does no cook, extraction, signing, game launch or native verification.
Publication is an external write: run it only for a release the operator has authorized.

Keep the package directory produced by the game's archive step, including `manifest.json`, `SHA256SUMS`
and either its ZIP or all `.zip.part-aa`, `.zip.part-ab`, … files. Keep the successful native package
verification report and separate smoke-test evidence. The report is a local native-verification
attestation, not a cryptographic authority or proof of gameplay parity. Read the game's packaging guide
for generating it; publication never invents or replaces that evidence.

For a game whose `[release]` configuration uses the `example-macos-` tag prefix:

```sh
uv run atelier release publish example build/example/package \
  --tag example-macos-2026-10-15 \
  --verification build/example/release-check/verification.json \
  --notes-file build/example/release-notes.md
```

Replace `example` and the tag with the actual game and its configured tag prefix. The title defaults to
the tag; `--title "Release title"` overrides it. `--prerelease` marks a prerelease, which ordinary
`atelier playtest` latest selection skips. Notes should distinguish verified package, smoke-test and
multiplayer evidence, including the revisions each actually covers. Inspect reports/notes for private
information before publishing; the repository and uploaded assets are public.

The selected source must be clean, including nonignored untracked files. Its HEAD must match the package's
full cook revision or unambiguously resolve the older manifest's prefix of at least eight characters.
The verification report must attest exactly the package revision and original file inventory. A recorded
dirty cook is refused. If running the newer publisher from another checkout, name the clean producer explicitly:

```sh
uv run atelier release publish example /path/to/verified/package \
  --tag example-macos-2026-10-15 --verification /path/to/verification.json \
  --source /path/to/clean/package-source --notes-file /path/to/release-notes.md
```

This does not require another cook. Preserve the existing artifacts and receipts. A source mismatch needs
the correct clean source and evidence, not changed stamps, a rewritten report or an invented parity claim.
The GitHub repository comes from that source's `origin`; the normal authenticated `gh` identity creates
the release. The command does not select another author, rewrite Git identity or handle credentials itself.

The publisher streams the original verified bytes into private staging under `build/<game>/release-publish/`,
without retaining a joined ZIP. It defaults to 200 MiB parts and six simultaneous uploads. `--part-mib N`
accepts 1–1900 MiB and `--workers N` accepts 1–6. These are bounded upload controls, not native worker settings.
Input hashes and identities are checked, and source/input/staged-output changes refuse final publication.
Staging is removed on completion or interruption; it can be regenerated from unchanged inputs.

Publication first creates or observes a draft with the exact tag, source commit, title, notes and prerelease
setting. It uploads the archive parts, `manifest.json`, the original `package-manifest.json` and
`verification.json`. Every completed asset must have the expected size and GitHub SHA-256 digest. Only after
all those checks does it upload `SHA256SUMS` last, then publish the draft. The checksum manifest lists the
archive files in the existing downloader/package format. The published manifest preserves package fields
and adds the exact source, archive, original-manifest, verification and notes identities.

Each transfer gets at most three attempts. An ambiguous upload failure observes the remote asset before
retrying; a completed matching upload is reused. Metadata reads and final publication also have bounded
attempts and observations. Draft creation is sent once: its successful response pins the numeric release ID,
without waiting for a tag/listing index to catch up. Local publishers for the same repository/tag share an
automatic destination mutex, with no native-capacity reservation; other tags and builds are independent.

The publisher stores the create intent before sending it, then retains the returned release ID under
the machine-local `~/.cache/atelier/release-publication/` directory; changing `ATELIER_CACHE` does not split
this ownership namespace. An interrupted or uncertain create becomes
observation-only, even in a new process: retry the identical command to find the accepted draft, never delete
its claim to make it send another create. If no accepted draft can be observed, the command reports that
uncertainty and sends no second create. A confirmed authentication/certificate or validation rejection can
retry after its cause is fixed. A selected release that was externally deleted is not silently recreated.
These local claims cannot serialize an independent publisher on another machine; keep one publisher per tag.

Missing GitHub digests, wrong size/hash, duplicate/unexpected
assets, changed metadata or a tag pointing elsewhere refuse. There is no clobber, delete or automatic repair.
Use a fresh authorized tag, or have the owner inspect the conflict before a separate repair.

To cancel, press Ctrl-C. The publisher stops scheduling transfers and ends only its owned `gh` processes.
A request may have committed before cancellation; keep the remote assets and rerun **the exact same command**
with unchanged package/report/source/notes/part size. It reobserves remote state and skips assets already verified.
An unfinished draft stays out of public latest selection. A fully published identical release is an idempotent
success; an incomplete existing published release is never filled in by this command. Do not launch a second
publisher for the same tag while the first still runs, or manually publish its unfinished draft.

These checks do not make local files and GitHub metadata one atomic transaction. Another actor can change
remote state during a request; the command checks again and reports conflicts or unobserved completion.
Keep one publisher per tag and rerun unchanged after an ambiguous final response.

The implementation uses the documented [GitHub asset upload API](https://docs.github.com/en/rest/releases/assets#upload-a-release-asset)
through [authenticated `gh api`](https://cli.github.com/manual/gh_api). No real GitHub publication is part of its mocked tests.

## Retain the build checkpoint

Configured games retain existing producer artifacts locally, publish the verified public package and print its
link, then start a detached private backup. The publish command does not wait for private network transfers.
Private failures never fail or roll back the public release. Configure the private repository once with
`atelier cache configure --repository OWNER/REPOSITORY`; its identity stays outside tracked source.

`atelier cache status` includes pending, uploading, failed and completed backups. Requests and logs live beside
the immutable checkpoint store. Rerunning the identical publish command reuses the retained capture, observes the
public release and resumes private upload. Completed remote packs are checksum-verified and reused. The detached
worker reads only the retained store; it never visits the producer checkout or holds native capacity. A failed
worker leaves a durable pending request. If local retention itself fails, the public release can still succeed:
the command explicitly reports the problem; preserve the producer and rerun after repairing cache access.

To resume an already captured backup from an interrupted earlier publisher, without recapturing the producer:

```sh
uv run atelier cache backup-resume GAME --checkpoint KEY --tag TAG \
  --revision FULL_SOURCE_SHA --public-repository OWNER/PUBLIC_REPOSITORY
```

This verifies the existing private capture/source binding and published public tag/readiness assets before
scheduling upload. No build/cook is requested. Keep agreed producer/evidence pins until checkpoint verification
and receiving restore are accepted; retain referenced packs. See [build checkpoints](BUILD_CHECKPOINTS.md).
