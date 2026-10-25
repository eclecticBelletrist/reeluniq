# Known issues

## Limits of what the modes do

### 1. A neural similarity model still sees the same clip

`light`, `dust` and `operator` change the file hash, the frame hashes and the perceptual hash (PDQ). SSCD, an open model for copy detection, still scores their frames as close to the original (see "Measured" in the README). `meta` leaves the picture identical by design.
**What this means:** the variants are different files and different frames, not different-looking videos to a similarity model. Whether a particular platform treats them as duplicates is its own decision; the closed models platforms use were not measured, only open ones.
**Status:** accepted. A mode that moves SSCD further was built and left out because it showed on flat surfaces (Decision 2 in `KEY_DECISIONS.md`).

### 2. `operator` is slow on large sources

Every frame goes through Python and OpenCV. Times are in the README. A long 4K clip takes many minutes per variant on a laptop.
**Status:** accepted. `light` and `dust` are the fast modes.

## Not tested

### 3. Real devices

The Windows build and both macOS builds are built and smoke-tested on GitHub's runners only (all four modes and the web page start). They have not been run on a physical Windows 10 machine or a Mac.

### 4. Real phone footage beyond one clip

The tests use synthetic clips. The HDR (HLG to SDR) path is checked on a synthetic round trip, not on a real iPhone HDR or Dolby Vision file. Variable frame rate and rotated vertical clips are covered by the code paths but not by a test.

## Behaviour to know about

### 5. Unsigned builds

SmartScreen on Windows and Gatekeeper on macOS warn about the first start, and some antivirus products flag PyInstaller programs. The README and the guide in each archive give the one-time steps. No signed build exists.

### 6. The page copies the file

The page uploads the video to the local server, which stores a copy under the data folder and deletes it when the variants are done. The limit is 4 GB. For a file over the limit, when the queue is full or when the disk is short, the browser can report "no connection" instead of the server's message.

### 7. Rare MP4 layouts in `meta`

`meta` reads files that start with an `ftyp` box (MP4, MOV) and refuses other containers. It inserts boxes and shifts the chunk offsets in `stco` and `co64`; 64-bit boxes inside `moov` and offsets that would overflow 32 bits after the shift are not handled. Neither occurs in phone footage. Whether a file came from x264 is decided from its first 4 MB.

### 8. A shared output folder

With `--out` pointing at one folder for several sources, `report.json` is overwritten on each run, and `meta` names its files from the seed, so two sources made with the same seed can overwrite each other's files. Without `--out` each source gets its own `<name>_variants` folder, so `x.mp4` and `x.mov` in one folder still share `x_variants`.

### 9. Plain http in PIN mode

`app --host 0.0.0.0` asks for a PIN, one attempt at a time, over plain http. The PIN and the cookie are visible to anyone on that network. It is meant for a home network.

### 10. AI-origin labels after a re-encode

An AIGC tag and a C2PA box that declares generated media are carried into every result (there is no switch). A C2PA manifest is bound by hash to the original bytes, so in a re-encoded or rewritten file the box is present but will not validate. The page shows only the last log line of a running job; the full line is in the console.

### 11. A failed `watch` job is not retried

`watch` creates the result folder for a video before the job runs, and skips any video whose folder exists. After a failure, delete that folder to try again.
