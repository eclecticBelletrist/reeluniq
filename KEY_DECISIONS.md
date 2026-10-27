# Key decisions

Each entry records what was decided, why, and what was rejected. Entry numbers are stable identifiers.

| # | Decision |
|---|---|
| 1 | ffmpeg runs as a separate program, bundled in the release archives |
| 2 | Four modes only; the experimental ones stay out |
| 3 | `operator` warps every frame itself instead of using an ffmpeg filter |
| 4 | `meta` copies the streams and proves they are unchanged |
| 5 | The page is a standard-library server bound to loopback |
| 6 | Unsigned builds, with the console window kept |

---

## Decision 1: ffmpeg runs as a separate program, bundled in the release archives

**Decision:** reeluniq starts `ffmpeg` and `ffprobe` as child processes. The release archives carry unmodified GPL builds of them next to the executable (`REELUNIQ_FFMPEG` and `REELUNIQ_FFPROBE` override the location, then `PATH` is searched).

**Rationale:**
- A person who double-clicks a program should not have to install anything first.
- A separate process keeps reeluniq's own code under Apache-2.0 while the bundled builds, which include x264 and x265, stay GPL. Sources and licences are listed in `packaging/THIRD-PARTY.txt`.
- The builds are pinned by URL and SHA-256 in the release workflow, so a rebuilt release does not pick up a different binary.

**Rejected:** linking libav through PyAV (ties the licence of the Python code to the build, and needs a wheel per platform); asking the user to install ffmpeg (the main failure for non-technical users).

## Decision 2: Four modes only; the experimental ones stay out

**Decision:** `meta`, `light`, `dust` and `operator` ship. A mode that perturbs the picture to move neural descriptors was built and not included.

**Rationale:**
- The shipped modes change the file, its frame hashes and its perceptual hashes. Measured on an open descriptor model (SSCD), they do not make the clip look different to it (see "Measured" in the README).
- The perturbation that did move SSCD left visible ripple and a colour cast on flat surfaces. Picture quality matters more than the extra distance, so it was dropped.

**Rejected:** shipping it behind a flag (a mode that visibly degrades the picture would be used by mistake).

## Decision 3: `operator` warps every frame itself instead of using an ffmpeg filter

**Decision:** `operator` decodes to raw frames, resamples each one from the source in a single sub-pixel affine step (OpenCV, Lanczos) along a path that depends on time only, and pipes the frames to a second ffmpeg that encodes.

**Rationale:**
- `zoompan` and integer `crop` expressions round to whole pixels, which shows as a slow shimmer on a slow zoom. One resample at sub-pixel precision does not.
- A path that depends on time only and eases to zero speed at every waypoint cannot twitch; an earlier version that reacted to picture motion did.

**Cost:** it is the slowest mode, since each frame passes through Python. Timings are in the README.

**Rejected:** `zoompan` (shimmer); reacting to subject motion (twitching).

## Decision 4: `meta` copies the streams and proves they are unchanged

**Decision:** `meta` never re-encodes. After writing a variant it decodes the picture and the sound of both files and compares an md5 of the frames, and the report says whether they match.

**Rationale:** "the picture is untouched" is the only promise this mode makes, so it is checked on every file. The check decodes both files fully, which is why `meta` takes about as long as `light` on a 4K clip.

**Rejected:** comparing packet hashes (equal packets can still decode differently if the container rewrite is wrong); skipping the check (the mode would be unverifiable).

## Decision 5: The page is a standard-library server bound to loopback

**Decision:** `reeluniq app` uses `http.server` on `127.0.0.1`, no framework, no accounts. Requests need a `Host` of this machine and a matching `Origin`. With `--host 0.0.0.0` a PIN cookie is required instead.

**Rationale:**
- A web page open in the same browser could otherwise post to a local server it can reach (DNS rebinding, cross-site requests). The Host and Origin check closes that without a login.
- Nothing to install means nothing to bundle beyond what the archive already has.
- The PIN mode exists for a phone on the same network. The connection is plain http, so it is for a network you trust.

**Rejected:** a web framework (a dependency for six routes); no check on loopback (the cross-site case).

## Decision 6: Unsigned builds, with the console window kept

**Decision:** the Windows and macOS builds are not code-signed, and the program keeps its console window.

**Rationale:**
- Signing needs a paid certificate and an Apple developer account; this is a small utility. The README and the guide in each archive explain the one-time SmartScreen and Gatekeeper steps.
- The console window is the program (it hosts the page). Closing it quits, and the window says so.

**Rejected:** hiding the window (the program would run invisibly, with no way to quit).
